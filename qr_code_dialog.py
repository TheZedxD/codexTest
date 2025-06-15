from __future__ import annotations
import os

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (
    QDialog, QLabel, QLineEdit, QComboBox, QSpinBox, QPushButton,
    QVBoxLayout, QHBoxLayout, QFormLayout, QFileDialog, QMessageBox
)

import qrcode
from PIL.ImageQt import ImageQt


class QRCodeDialog(QDialog):
    """Simple QR code generator dialog."""

    def __init__(self, data: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("[QR] Remote QR Code")
        self.setModal(True)
        self.setFixedSize(320, 420)

        if parent and hasattr(parent, "css"):
            self.setStyleSheet(parent.css("""
                QDialog {{ background-color: {bg}; color: {fg}; }}
                QLabel {{ color: {fg}; }}
                QLineEdit, QComboBox, QSpinBox {{
                    background-color: {alt};
                    color: {fg};
                    border: 1px solid {fg};
                }}
                QPushButton {{
                    background-color: {alt};
                    color: {fg};
                    border: 2px solid {fg};
                    padding: 6px 12px;
                    font-weight: bold;
                    border-radius: 4px;
                }}
                QPushButton:hover {{ background-color: {hover}; }}
            """))

        self.qr_img = None

        self.data_edit = QLineEdit(data)
        self.ec_combo = QComboBox()
        self.ec_combo.addItems(["L", "M", "Q", "H"])
        self.size_combo = QComboBox()
        self.size_combo.addItems(["Small", "Medium", "Large"])
        self.border_spin = QSpinBox()
        self.border_spin.setRange(0, 10)
        self.border_spin.setValue(4)

        form = QFormLayout()
        form.addRow("Data:", self.data_edit)
        form.addRow("Error correction:", self.ec_combo)
        form.addRow("Size:", self.size_combo)
        form.addRow("Border:", self.border_spin)

        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignCenter)

        gen_btn = QPushButton("[GEN] Generate")
        gen_btn.clicked.connect(self.generate_qr)
        save_btn = QPushButton("[SAVE] Save PNG…")
        save_btn.clicked.connect(self.save_png)

        btn_row = QHBoxLayout()
        btn_row.addWidget(gen_btn)
        btn_row.addWidget(save_btn)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.preview, 1)
        layout.addLayout(btn_row)

        # Generate initial QR if data provided
        if data:
            self.generate_qr()

    # ------------------------------------------------------
    def _box_size(self) -> int:
        mapping = {"Small": 5, "Medium": 10, "Large": 15}
        return mapping.get(self.size_combo.currentText(), 10)

    def generate_qr(self):
        data = self.data_edit.text().strip()
        if not data:
            QMessageBox.information(self, "No data", "Please enter something to encode.")
            return
        ec_map = {
            "L": qrcode.constants.ERROR_CORRECT_L,
            "M": qrcode.constants.ERROR_CORRECT_M,
            "Q": qrcode.constants.ERROR_CORRECT_Q,
            "H": qrcode.constants.ERROR_CORRECT_H,
        }
        try:
            qr = qrcode.QRCode(
                error_correction=ec_map[self.ec_combo.currentText()],
                box_size=self._box_size(),
                border=self.border_spin.value(),
            )
            qr.add_data(data)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
            self.qr_img = img
            qimg = ImageQt(img)
            pix = QPixmap.fromImage(qimg)
            self.preview.setPixmap(pix)
            self.preview.setFixedSize(pix.size())
        except Exception as exc:
            QMessageBox.warning(self, "QR generation failed", str(exc))

    def save_png(self):
        if self.qr_img is None:
            QMessageBox.information(self, "Nothing to save", "Generate a QR code first.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save QR code", "qr.png", "PNG images (*.png)")
        if not path:
            return
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            self.qr_img.save(path)
            QMessageBox.information(self, "Saved", f"QR code saved to:\n{path}")
        except Exception as exc:
            QMessageBox.warning(self, "Save failed", str(exc))
