from __future__ import annotations
import logging
from pathlib import Path
from PyQt5.QtMultimedia import QMediaPlayer

APP_ROOT = Path(__file__).resolve().parent
LOG_DIR = APP_ROOT / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

class MediaDiagnostics:
    """Mixin providing verbose QMediaPlayer diagnostics."""
    def __init__(self) -> None:
        self._md_logger = logging.getLogger("qtmultimedia")
        if not self._md_logger.handlers:
            handler = logging.FileHandler(LOG_DIR / "qtmultimedia.log")
            handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
            self._md_logger.addHandler(handler)
            self._md_logger.setLevel(logging.INFO)
        try:
            types = QMediaPlayer().supportedMimeTypes()
            self._md_logger.info("Supported MIME types: %s", ", ".join(types))
            if "video/mp4" not in types and "video/h264" not in types:
                self._md_logger.warning("Missing 'video/mp4' or 'video/h264' support")
        except Exception as e:  # pragma: no cover - diagnostics only
            self._md_logger.error(f"supportedMimeTypes preflight failed: {e}")

    def init_media_diagnostics(self, player: QMediaPlayer) -> None:
        """Connect diagnostics to a QMediaPlayer instance."""
        self._diag_player = player
        if hasattr(player, "errorOccurred"):
            player.errorOccurred.connect(self._on_media_error)
        elif hasattr(player, "error"):
            player.error.connect(self._on_media_error)
        if hasattr(player, "errorChanged"):
            player.errorChanged.connect(self._on_media_error)
        player.mediaStatusChanged.connect(self._on_media_status)

    # ------------------------------------------------------------------
    def _on_media_status(self, status):  # pragma: no cover - runtime info
        self._md_logger.info("media status changed: %s", int(status))

    def _on_media_error(self, *args):  # pragma: no cover - runtime info
        code = getattr(self._diag_player, "error", lambda: None)()
        msg = getattr(self._diag_player, "errorString", lambda: "")()
        self._md_logger.error("media error %s: %s", code, msg)
        if hasattr(self, "_osd"):
            self._osd("Media error. Missing GStreamer plugins or Wayland backend in use")
