from PyQt5.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QFileDialog,
)
from PyQt5.QtGui import QPixmap
import qrcode
from io import BytesIO


class QRCodeDialog(QDialog):
    """Display a QR code for sharing the remote URL."""

    def __init__(self, data, parent=None):
        super().__init__(parent)
        self.setWindowTitle("[WEB] Remote QR")
        if parent and hasattr(parent, "css"):
            self.setStyleSheet(parent.css(
                "QDialog {background:{bg};color:{fg};}"
                "QLabel {color:{fg};}"
                "QPushButton {background:{alt};color:{fg};border:2px solid {fg};"
                "padding:6px 12px;font-weight:bold;}"
                "QPushButton:hover {background:{hover};}"
            ))
        buf = BytesIO()
        qrcode.make(data).save(buf, format="PNG")
        buf.seek(0)
        pix = QPixmap()
        pix.loadFromData(buf.read(), "PNG")

        v = QVBoxLayout(self)
        v.addWidget(QLabel(f"<b>{data}</b>"))
        img = QLabel()
        img.setPixmap(pix)
        v.addWidget(img)

        save = QPushButton("Save PNG…")
        save.clicked.connect(lambda: self._save_png(pix))
        v.addWidget(save)

    def _save_png(self, pix):
        path, _ = QFileDialog.getSaveFileName(self, "Save QR", "", "PNG (*.png)")
        if path:
            pix.save(path, "PNG")
