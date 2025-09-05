from pathlib import Path
import qrcode

APP_ROOT = Path(__file__).resolve().parent
TMP_DIR = APP_ROOT / "tmp"


def make_qr_png(text: str, out_path: Path) -> None:
    """Generate a QR code PNG containing *text* and save to *out_path*.

    The parent directory of *out_path* is created automatically. By
    convention, place outputs inside :data:`TMP_DIR`.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img = qrcode.make(text)  # uses Pillow under the hood
    img.save(str(out_path))

