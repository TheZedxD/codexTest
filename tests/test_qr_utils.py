import sys
from pathlib import Path

# Add parent directory to path if needed
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qr_utils import TMP_DIR, make_qr_png


def test_make_qr_png_creates_file():
    out = TMP_DIR / "test_qr.png"
    if out.exists():
        out.unlink()
    make_qr_png("hello", out)
    assert out.exists()
    out.unlink()
