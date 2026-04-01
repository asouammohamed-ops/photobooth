import cv2
import sys
import hashlib
import hmac
import uuid
import os
import win32print
import win32ui
import win32con
from PIL import Image, ImageEnhance, ImageDraw, ImageWin
from PyQt5.QtWidgets import (
    QApplication, QWidget, QPushButton, QVBoxLayout, QHBoxLayout,
    QLabel, QMessageBox, QInputDialog, QComboBox,
    QGroupBox, QGridLayout, QCheckBox, QColorDialog, QSlider
)
from PyQt5.QtGui import QPixmap, QImage
from PyQt5.QtCore import QTimer, Qt

# ─────────────────────────────────────────────
#  إعدادات الترخيص
# ─────────────────────────────────────────────
_S1, _S2, _S3 = "MRC", "PHT", "2026"
LICENSE_FILE = ".sys_config"
DPI = 300

def _get_salt():
    return f"{_S1}_{_S2}_{_S3}"

def _make_mid():
    return hashlib.sha256(str(uuid.getnode()).encode()).hexdigest()[:12].upper()

def _make_key(mid):
    return hmac.new(_get_salt().encode(), mid.encode(), hashlib.sha256).hexdigest()[:8].upper()

def cm_to_px(cm, dpi=DPI):
    return round(cm * dpi / 2.54)

# ─────────────────────────────────────────────
#  تخطيطات الورق (مستوحاة من pibooth)
# ─────────────────────────────────────────────
LAYOUTS = {
    "8 صور (4×2) - جواز سفر":  {"cols": 4, "rows": 2, "photo_w": 3.5, "photo_h": 4.5},
    "6 صور (3×2) - هوية":       {"cols": 3, "rows": 2, "photo_w": 3.5, "photo_h": 4.5},
    "4 صور (2×2) - بطاقة":      {"cols": 2, "rows": 2, "photo_w": 5.0, "photo_h": 5.0},
    "2 صور (2×1) - كبيرة":      {"cols": 2, "rows": 1, "photo_w": 6.0, "photo_h": 8.0},
    "1 صورة كاملة":             {"cols": 1, "rows": 1, "photo_w": 9.0, "photo_h": 13.0},
}

PAPER_SIZES = {
    "A6  (15×10 سم)": (15.0, 10.0),
    "A5  (21×15 سم)": (21.0, 15.0),
    "4×6 (15×10 سم)": (15.24, 10.16),
    "5×7 (18×13 سم)": (17.78, 12.7),
}

BACKGROUNDS = {
    "أبيض":       (255, 255, 255),
    "رمادي فاتح": (240, 240, 240),
    "أزرق فاتح":  (200, 220, 255),
    "مخصص":       None,
}

# ─────────────────────────────────────────────
#  محرك بناء الورقة (منطق pibooth PictureFactory)
# ─────────────────────────────────────────────
def build_sheet(single_img, layout, paper_w_cm, paper_h_cm,
                bg_color, margin_cm=0.3, gap_cm=0.2,
                outlines=False, brightness=1.0, sharpness=1.5):
    sheet_w = cm_to_px(paper_w_cm)
    sheet_h = cm_to_px(paper_h_cm)
    img_w   = cm_to_px(layout["photo_w"])
    img_h   = cm_to_px(layout["photo_h"])
    cols    = layout["cols"]
    rows    = layout["rows"]
    gap     = cm_to_px(gap_cm)

    # توسيط المحتوى على الورقة (مثل pibooth)
    total_w = cols * img_w + (cols - 1) * gap
    total_h = rows * img_h + (rows - 1) * gap
    offset_x = (sheet_w - total_w) // 2
    offset_y = (sheet_h - total_h) // 2

    assert total_w <= sheet_w, "الصور لا تتسع أفقياً"
    assert total_h <= sheet_h, "الصور لا تتسع عمودياً"

    # تحسينات الصورة
    photo = single_img.copy()
    if brightness != 1.0:
        photo = ImageEnhance.Brightness(photo).enhance(brightness)
    photo = ImageEnhance.Sharpness(photo).enhance(sharpness)

    # قص بنسبة الصورة الهدف (خوارزمية pibooth new_size_by_croping_ratio)
    ratio = img_w / img_h
    ow, oh = photo.size
    img_ratio = ow / oh
    if ratio > img_ratio:
        crop_h = int(ow / ratio)
        y0 = (oh - crop_h) // 2
        photo = photo.crop((0, y0, ow, y0 + crop_h))
    elif ratio < img_ratio:
        crop_w = int(ratio * oh)
        x0 = (ow - crop_w) // 2
        photo = photo.crop((x0, 0, x0 + crop_w, oh))
    photo = photo.resize((img_w, img_h), Image.Resampling.LANCZOS)

    # بناء الورقة
    sheet = Image.new('RGB', (sheet_w, sheet_h), bg_color)
    draw  = ImageDraw.Draw(sheet)

    for row in range(rows):
        for col in range(cols):
            x = offset_x + col * (img_w + gap)
            y = offset_y + row * (img_h + gap)
            sheet.paste(photo, (x, y))
            if outlines:
                draw.rectangle([x-1, y-1, x+img_w, y+img_h],
                                outline=(160, 160, 160), width=1)
    return sheet


def print_sheet(sheet, parent=None):
    try:
        printer_name = win32print.GetDefaultPrinter()
        hDC = win32ui.CreateDC()
        hDC.CreatePrinterDC(printer_name)
        px = hDC.GetDeviceCaps(win32con.LOGPIXELSX)
        py = hDC.GetDeviceCaps(win32con.LOGPIXELSY)
        pw = round(sheet.width  * px / DPI)
        ph = round(sheet.height * py / DPI)
        hDC.StartDoc("Passport Photos")
        hDC.StartPage()
        ImageWin.Dib(sheet).draw(hDC.GetHandleOutput(), (0, 0, pw, ph))
        hDC.EndPage()
        hDC.EndDoc()
        hDC.DeleteDC()
        QMessageBox.information(parent, "✅ نجاح", f"تم الإرسال إلى:\n{printer_name}")
    except Exception as e:
        sheet.save("last_capture.jpg", dpi=(DPI, DPI))
        QMessageBox.critical(parent, "❌ خطأ في الطباعة",
                             f"تعذرت الطباعة. تم الحفظ كـ last_capture.jpg\n\n{e}")


# ─────────────────────────────────────────────
#  النافذة الرئيسية
# ─────────────────────────────────────────────
class PhotoBoothPro(QWidget):

    def __init__(self):
        super().__init__()
        self.verify_license()
        self.cap = None
        self.camera_error = False
        self.custom_bg_color = (255, 255, 255)
        self._init_camera()
        self.init_ui()
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_view)
        self.timer.start(30)

    # ── ترخيص ──────────────────────────────
    def verify_license(self):
        mid = _make_mid()
        expected = _make_key(mid)
        if os.path.exists(LICENSE_FILE):
            try:
                with open(LICENSE_FILE) as f:
                    if hmac.compare_digest(f.read().strip(), expected):
                        return
            except OSError:
                pass
        key, ok = QInputDialog.getText(self, 'تفعيل النظام',
                                       f'ID الجهاز: {mid}\nأدخل كود التفعيل:')
        if ok and hmac.compare_digest(key.upper().strip(), expected):
            try:
                with open(LICENSE_FILE, 'w') as f:
                    f.write(expected)
            except OSError as e:
                QMessageBox.warning(self, "تحذير", f"تعذر حفظ الترخيص:\n{e}")
        else:
            sys.exit()

    # ── كاميرا ─────────────────────────────
    def _init_camera(self):
        try:
            cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
            if not cap.isOpened():
                raise RuntimeError("الكاميرا غير متاحة")
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            ret, _ = cap.read()
            if not ret:
                cap.release()
                raise RuntimeError("الكاميرا لا ترسل صوراً")
            self.cap = cap
            self.camera_error = False
        except Exception as e:
            self.camera_error = True
            self.cap = None
            QMessageBox.critical(self, "خطأ في الكاميرا", f"تعذر تشغيل الكاميرا:\n{e}")

    def _read_frame(self):
        if self.cap is None:
            return False, None
        for _ in range(3):
            ret, frame = self.cap.read()
            if ret and frame is not None:
                return True, frame
        self.cap.release()
        self._init_camera()
        return False, None

    # ── واجهة ──────────────────────────────
    def init_ui(self):
        self.setWindowTitle('نظام التصوير الرقمي الاحترافي v2.0')
        self.setMinimumSize(1020, 780)
        self.setLayoutDirection(Qt.RightToLeft)
        self.setStyleSheet("""
            QWidget { background:#f0f2f5; font-family:Arial; font-size:13px; }
            QGroupBox { border:2px solid #bdc3c7; border-radius:8px;
                        margin-top:10px; font-weight:bold; padding:8px; color:#2c3e50; }
            QGroupBox::title { subcontrol-origin:margin; left:10px; padding:0 5px; }
            QComboBox, QSpinBox { padding:5px; border:1px solid #bdc3c7;
                                   border-radius:4px; background:white; }
        """)

        main = QHBoxLayout(self)
        main.setSpacing(12)

        # ── عمود الكاميرا ──
        left = QVBoxLayout()

        title = QLabel("📷  نظام التصوير الرقمي الاحترافي")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size:18px; font-weight:bold; color:#2c3e50; padding:6px;")
        left.addWidget(title)

        self.video_display = QLabel()
        self.video_display.setFixedSize(680, 500)
        self.video_display.setAlignment(Qt.AlignCenter)
        cam_style = "border:3px solid #2c3e50; background:black; border-radius:6px;"
        if self.camera_error:
            self.video_display.setText("⚠️ الكاميرا غير متاحة")
            cam_style = ("border:3px solid red; background:#2c3e50; "
                         "color:white; font-size:20px; border-radius:6px;")
        self.video_display.setStyleSheet(cam_style)
        left.addWidget(self.video_display)

        hint = QLabel("وجّه الزبون داخل الإطار الذهبي ثم اضغط الزر أو ENTER")
        hint.setAlignment(Qt.AlignCenter)
        hint.setStyleSheet("color:#7f8c8d; font-size:12px;")
        left.addWidget(hint)

        self.btn_capture = QPushButton("📸   التقاط وطباعة   (ENTER)")
        self.btn_capture.setFixedHeight(65)
        self.btn_capture.setEnabled(not self.camera_error)
        self.btn_capture.setStyleSheet("""
            QPushButton { background:#27ae60; color:white; font-size:19px;
                          font-weight:bold; border-radius:10px; }
            QPushButton:hover   { background:#2ecc71; }
            QPushButton:disabled{ background:#95a5a6; }
        """)
        self.btn_capture.clicked.connect(self.capture_photo)
        left.addWidget(self.btn_capture)
        main.addLayout(left, 3)

        # ── عمود الإعدادات ──
        right = QVBoxLayout()
        right.setAlignment(Qt.AlignTop)
        right.setSpacing(8)

        # تخطيط
        g1 = QGroupBox("🖼  التخطيط")
        gl = QVBoxLayout(g1)
        self.combo_layout = QComboBox()
        self.combo_layout.addItems(LAYOUTS.keys())
        gl.addWidget(self.combo_layout)
        right.addWidget(g1)

        # ورقة
        g2 = QGroupBox("📄  حجم الورقة")
        gp = QVBoxLayout(g2)
        self.combo_paper = QComboBox()
        self.combo_paper.addItems(PAPER_SIZES.keys())
        gp.addWidget(self.combo_paper)
        right.addWidget(g2)

        # خلفية
        g3 = QGroupBox("🎨  لون الخلفية")
        gb = QVBoxLayout(g3)
        self.combo_bg = QComboBox()
        self.combo_bg.addItems(BACKGROUNDS.keys())
        self.combo_bg.currentTextChanged.connect(
            lambda t: self.btn_color.setVisible(t == "مخصص"))
        gb.addWidget(self.combo_bg)
        self.btn_color = QPushButton("اختر اللون...")
        self.btn_color.setVisible(False)
        self.btn_color.clicked.connect(self._pick_color)
        gb.addWidget(self.btn_color)
        right.addWidget(g3)

        # تحسينات
        g4 = QGroupBox("⚙️  تحسينات الصورة")
        ge = QGridLayout(g4)
        ge.addWidget(QLabel("الإضاءة:"), 0, 0)
        self.slider_bright = QSlider(Qt.Horizontal)
        self.slider_bright.setRange(50, 150)
        self.slider_bright.setValue(100)
        ge.addWidget(self.slider_bright, 0, 1)
        ge.addWidget(QLabel("الحدة:"), 1, 0)
        self.slider_sharp = QSlider(Qt.Horizontal)
        self.slider_sharp.setRange(100, 300)
        self.slider_sharp.setValue(150)
        ge.addWidget(self.slider_sharp, 1, 1)
        self.chk_outlines = QCheckBox("خطوط قطع حول الصور")
        self.chk_outlines.setChecked(True)
        ge.addWidget(self.chk_outlines, 2, 0, 1, 2)
        right.addWidget(g4)

        # معاينة
        g5 = QGroupBox("🔍  معاينة آخر طباعة")
        gv = QVBoxLayout(g5)
        self.preview_label = QLabel("لا توجد معاينة بعد")
        self.preview_label.setFixedSize(255, 175)
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setStyleSheet(
            "background:white; border:1px solid #ccc; color:#aaa; font-size:12px;")
        gv.addWidget(self.preview_label, alignment=Qt.AlignCenter)
        right.addWidget(g5)

        main.addLayout(right, 1)

    def _pick_color(self):
        c = QColorDialog.getColor()
        if c.isValid():
            self.custom_bg_color = (c.red(), c.green(), c.blue())

    def _get_bg_color(self):
        key = self.combo_bg.currentText()
        return self.custom_bg_color if key == "مخصص" else BACKGROUNDS[key]

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self.capture_photo()

    # ── عرض الكاميرا ───────────────────────
    def update_view(self):
        if self.camera_error or self.cap is None:
            return
        ret, frame = self._read_frame()
        if not ret:
            return
        h, w, _ = frame.shape
        layout = LAYOUTS[self.combo_layout.currentText()]
        ratio  = layout["photo_w"] / layout["photo_h"]
        box_h  = int(h * 0.72)
        box_w  = int(box_h * ratio)
        x1 = (w - box_w) // 2
        y1 = (h - box_h) // 2
        cv2.rectangle(frame, (x1, y1), (x1+box_w, y1+box_h), (0, 215, 255), 2)
        rgb  = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        qimg = QImage(rgb.data, w, h, w*3, QImage.Format_RGB888)
        self.video_display.setPixmap(
            QPixmap.fromImage(qimg).scaled(
                self.video_display.width(), self.video_display.height(),
                Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
        )

    # ── التقاط والطباعة ────────────────────
    def capture_photo(self):
        if self.camera_error:
            QMessageBox.warning(self, "تحذير", "الكاميرا غير متاحة.")
            return
        ret, frame = self._read_frame()
        if not ret:
            QMessageBox.critical(self, "خطأ", "تعذرت قراءة الصورة.")
            return

        pil_img   = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        layout    = LAYOUTS[self.combo_layout.currentText()]
        pw, ph    = PAPER_SIZES[self.combo_paper.currentText()]
        bg        = self._get_bg_color()
        bright    = self.slider_bright.value() / 100.0
        sharp     = self.slider_sharp.value()  / 100.0
        outlines  = self.chk_outlines.isChecked()

        sheet = build_sheet(pil_img, layout, pw, ph, bg,
                            brightness=bright, sharpness=sharp, outlines=outlines)

        # معاينة
        thumb = sheet.copy()
        thumb.thumbnail((255, 175))
        qi = QImage(thumb.tobytes(), thumb.width, thumb.height,
                    thumb.width*3, QImage.Format_RGB888)
        self.preview_label.setPixmap(QPixmap.fromImage(qi))

        print_sheet(sheet, self)

    def closeEvent(self, event):
        self.timer.stop()
        if self.cap:
            self.cap.release()
        event.accept()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setLayoutDirection(Qt.RightToLeft)
    w = PhotoBoothPro()
    w.show()
    sys.exit(app.exec_())
