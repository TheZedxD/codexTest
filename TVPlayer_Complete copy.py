"""
PyQt "Live TV" player • r45‑COMPLETE STABLE EDITION – 2025‑06‑02
───────────────────────────────────────────────────────────────────────────────
✓  FIXED: All missing methods and classes included
✓  STABILIZED schedule system with improved ad break handling
✓  Enhanced web remote with volume controls and restart capability  
✓  Settings changes auto-reset schedules and return to guide
✓  Mobile-responsive media browser webpage
✓  Improved error handling and segment management
✓  Better Flask server stability with restart functionality
✓  NO EMOJI VERSION - All symbols replaced with ASCII characters
✓  FIXED: OnDemand channel behavior - stops current playback when revisited
✓  FIXED: Schedule progression - properly advances to next program
✓  FIXED: Complete Matrix theme throughout application
✓  ADDED: Web remote IP popup at startup
✓  FIXED: Single-click next video navigation
✓  FIXED: Sequential video playback (no random order)
✓  FIXED: Channels start playing immediately (no standby)
✓  FIXED: Continuous playback loop when no ads
✓  REMOVED: Strict 15/30 minute time slot requirements
✓  FIXED: TRUE LIVE TV - All channels play simultaneously from synchronized schedule
✓  FIXED: Channel switching joins programs already in progress
✓  ENHANCED: Seeking mechanism with verification and retry
"""

from __future__ import annotations
import json, math, os, random, re, shutil, subprocess, sys, logging, socket, threading
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import platform
import webbrowser
import signal
import weakref

# Optional: demote quirky HW decoders on some Mint builds
if sys.platform.startswith('linux'):
    os.environ["GST_PLUGIN_FEATURE_RANK"] = "vaapih264dec:0,vaapih265dec:0,omxh264dec:0,omxh265dec:0"

# FIXED: Import QtCore properly - import the module itself, not from itself
from PyQt5 import QtCore
from PyQt5.QtCore import (Qt, QTimer, QUrl, QSettings, qInstallMessageHandler,
                         QtMsgType, QMessageLogContext, pyqtSignal, QObject, QThread, QSize)
from PyQt5.QtGui import QColor, QKeySequence, QPalette, QFont, QMovie, QPixmap, QIcon, QKeyEvent
from PyQt5.QtMultimedia import QMediaContent, QMediaPlayer
from PyQt5.QtMultimediaWidgets import QVideoWidget
from PyQt5.QtWidgets import (
    QApplication, QDialog, QFileDialog, QDialogButtonBox, QGridLayout, QLabel,
    QMainWindow, QPushButton, QPlainTextEdit, QVBoxLayout, QHBoxLayout,
    QWidget, QShortcut, QKeySequenceEdit, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox, QSpinBox, QCheckBox, QSlider, QFormLayout,
    QStackedLayout, QSizePolicy, QLineEdit, QGroupBox, QMenu, QTreeWidget,
    QTreeWidgetItem, QSplitter, QInputDialog, QFocusFrame,
    QListWidget, QListWidgetItem,
    QGraphicsDropShadowEffect
)

# Flask imports for web server
from flask import Flask, request, jsonify, render_template_string
from werkzeug.serving import run_simple

# FIXED: Remove duplicate imports and add missing ones
try:
    import psutil  # For system monitoring
except ImportError:
    psutil = None
    logging.warning("psutil not available - some system info features will be disabled")

# ──────────────────────── helpers / paths ────────────────────────
def _qt_msg(m: QtMsgType, c: QMessageLogContext, t: str) -> None:
    # mute noisy warnings
    if m == QtMsgType.QtWarningMsg and any(x in t for x in ["paintEngine", "QVector<int>", "queue arguments", "single cell span"]):
        return
    sys.__stderr__.write(t + "\n")
qInstallMessageHandler(_qt_msg)

VIDEO_EXTS = (".mp4", ".avi", ".mkv", ".mov", ".ts", ".m4v", ".wmv", ".flv", ".webm")
SUB_EXTS = (".srt", ".ass", ".vtt")

ROOT_DIR = Path(__file__).resolve().parent
ROOT_CHANNELS = ROOT_DIR / "Channels"
ROOT_CHANNELS.mkdir(exist_ok=True)

# Default data files (can be changed in settings)
DEFAULT_CACHE_FILE = ROOT_DIR / "durations.json"
DEFAULT_HOTKEY_FILE = ROOT_DIR / "hotkeys.json"
CACHE_FILE = DEFAULT_CACHE_FILE  # backward compatibility
HOTKEY_FILE = DEFAULT_HOTKEY_FILE
STATIC_GIF = ROOT_DIR / "static.gif"
SCHEDULE_DIR = ROOT_DIR / "schedules"
SCHEDULE_DIR.mkdir(exist_ok=True)

# TV Constants
AD_BREAK_DURATION_MS = 3 * 60 * 1000  # 3 minutes between shows
MIN_SHOW_DURATION_MS = 5 * 60 * 1000  # 5 minutes minimum
TIME_SLOT_MS = 15 * 60 * 1000         # 15-minute slots
GUIDE_HOURS_AHEAD = 12                 # 12 hours in guide
SHOW_REPEAT_HOURS = 4                  # 4 hour repeat minimum
AD_REPEAT_HOURS = 2                    # 2 hour ad repeat
MIDROLL_AD_DURATION_MS = 3 * 60 * 1000 # 3 minutes mid-roll
MIDROLL_THRESHOLD_MS = 45 * 60 * 1000  # 45+ min shows get mid-roll
MOVIE_THRESHOLD_MS = 90 * 60 * 1000    # 90+ min get 2 mid-rolls

# ─── Logging setup ─────────────────────────────────────────────────────────
LOG_DIR = ROOT_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)
log_file = LOG_DIR / "errors.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
    handlers=[logging.FileHandler(log_file), logging.StreamHandler(sys.__stdout__)]
)

def _handle_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    logging.error("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))

sys.excepthook = _handle_exception

# ── HELPERS ───────────────────────────────────────
def discover_channels(root: Path) -> List[Path]:
    """Return channel subfolders that contain Shows and Commercials folders."""
    if not root.exists():
        return []
    return sorted([item for item in root.iterdir() 
                  if item.is_dir() and (item / "Shows").exists() and (item / "Commercials").exists()],
                  key=lambda p: p.name.lower())

def probe_duration(path: Path) -> int:
    """Fast ffprobe wrapper → duration in ms."""
    if not shutil.which("ffprobe"):
        logging.warning("ffprobe not found – using dummy duration for %s", path)
        return 30_000
    try:
        out = subprocess.check_output([
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(path)
        ], stderr=subprocess.STDOUT, text=True, timeout=5)
        return max(1000, int(float(out.strip()) * 1000))
    except Exception as e:
        logging.warning("ffprobe failure (%s) – using dummy duration for %s", e, path)
        return 30_000

def gather_files(dir_: Path, exts=VIDEO_EXTS, recursive: bool = True) -> List[Path]:
    """Return media files from *dir_*.

    If *recursive* is True (default) search subdirectories as well. This allows
    season folders or other groupings inside the Shows/Commercials folders to be
    detected automatically.
    """
    if not dir_.exists():
        return []
    pattern = "**/*" if recursive else "*"
    return sorted(
        f for f in dir_.glob(pattern) if f.is_file() and f.suffix.lower() in exts
    )

def ms_to_hms(ms: int) -> str:
    s = ms // 1000
    return f"{s//3600:02d}:{(s//60)%60:02d}:{s%60:02d}"

def format_show_name(path: Path) -> str:
    """Clean up show names for display."""
    name = path.stem
    name = re.sub(r'^(S\d+E\d+|Episode\s*\d+|Ep\s*\d+)\s*[-_]\s*', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\s*[-_]\s*(S\d+E\d+|Episode\s*\d+|Ep\s*\d+)$', '', name, flags=re.IGNORECASE)
    name = re.sub(r'[._]+', ' ', name)
    name = re.sub(r'\s+', ' ', name).strip()
    return name[:50] + "..." if len(name) > 50 else name

# ───────────── SRT parser ─────────────
_TIMERE = re.compile(r"(\d{2}):(\d{2}):(\d{2}),(\d{3})")

def _t2ms(m):
    h, mi, s, ms = map(int, m.groups())
    return ((h*60+mi)*60+s)*1000+ms

def parse_srt(path: Path) -> List[Tuple[int,int,str]]:
    cues, txt, start, end = [], [], None, None
    try:
        for line in path.read_text(encoding="utf8", errors="ignore").splitlines():
            if not line.strip():
                if start is not None:
                    cues.append((start, end, "\n".join(txt)))
                start = end = None
                txt = []
                continue
            if start is None and "-->" in line:
                try:
                    a, b = line.split("-->")
                    start, end = _t2ms(_TIMERE.search(a)), _t2ms(_TIMERE.search(b))
                except Exception as e:
                    logging.debug(f"Invalid subtitle timing line '{line}': {e}")
                    continue
            elif start is not None:
                txt.append(line.strip())
        if start is not None:
            cues.append((start, end, "\n".join(txt)))
    except Exception as e:
        logging.warning("Failed to parse SRT file %s: %s", path, e)
    return cues

# ───────────── File Manager Helper ──────────────────
def open_in_file_manager(path: Path):
    """Open a path in the system file manager."""
    try:
        if platform.system() == "Windows":
            subprocess.run(["explorer", str(path)], check=True)
        elif platform.system() == "Darwin":
            subprocess.run(["open", str(path)], check=True)
        else:
            subprocess.run(["xdg-open", str(path)], check=True)
    except Exception as e:
        logging.error(f"Failed to open file manager: {e}")

# ───────────── Enhanced Signal bridge ──────────────────────────────────────
class RemoteSignalBridge(QObject):
    command_received = pyqtSignal(str)
    restart_server_requested = pyqtSignal()

# ───────────── IP Address Info Dialog ──────────────────────────────────────
class IPInfoDialog(QDialog):
    """Show web remote access information at startup."""
    def __init__(self, port: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("[WEB] Web Remote Access")
        self.setModal(True)
        self.setFixedSize(450, 300)
        
        # Apply Matrix theme
        self.setStyleSheet("""
            QDialog {
                background-color: #000000;
                color: #00ff00;
                border: 2px solid #00ff00;
            }
            QLabel {
                color: #00ff00;
                font-family: "Consolas", monospace;
                padding: 5px;
            }
            QPushButton {
                background-color: #001100;
                color: #00ff00;
                border: 2px solid #00ff00;
                padding: 8px 16px;
                font-weight: bold;
                font-size: 14px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #003300;
                border-color: #39ff14;
            }
            QGroupBox {
                color: #00ff00;
                border: 2px solid #00ff00;
                border-radius: 6px;
                margin-top: 10px;
                font-weight: bold;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        
        # Title
        title = QLabel("[TV] TV STATION WEB REMOTE")
        title.setStyleSheet("font-size: 18px; font-weight: bold; text-align: center; padding: 10px;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        # Info group
        info_group = QGroupBox("[ACCESS] Connection Information")
        info_layout = QVBoxLayout(info_group)
        
        # Get local IPs
        ips = self._get_local_ips()
        
        info_text = QLabel(f"[PORT] Server running on port: {port}\n\n[URL] Access from any device on your network:")
        info_text.setWordWrap(True)
        info_layout.addWidget(info_text)
        
        # IP addresses
        for ip in ips:
            url_label = QLabel(f"  >> http://{ip}:{port}")
            url_label.setStyleSheet("font-size: 14px; color: #39ff14; font-weight: bold;")
            url_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            info_layout.addWidget(url_label)
        
        layout.addWidget(info_group)
        
        # Instructions
        instructions = QLabel("[!] Save these addresses to access the remote control\n    from your phone, tablet, or other computer")
        instructions.setStyleSheet("font-style: italic; padding: 10px;")
        instructions.setAlignment(Qt.AlignCenter)
        layout.addWidget(instructions)
        
        layout.addStretch()
        
        # OK button
        ok_button = QPushButton("[OK] START WATCHING")
        ok_button.clicked.connect(self.accept)
        ok_button.setDefault(True)
        layout.addWidget(ok_button)
        
    def _get_local_ips(self):
        """Get local IP addresses."""
        ips = ['127.0.0.1']
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            main_ip = s.getsockname()[0]
            s.close()
            if main_ip not in ips:
                ips.append(main_ip)
        except Exception as e:
            logging.warning(f"IP detection error: {e}")
        
        # Try to get all IPs
        try:
            hostname = socket.gethostname()
            for ip in socket.gethostbyname_ex(hostname)[2]:
                if ip not in ips and not ip.startswith("127."):
                    ips.append(ip)
        except Exception as e:
            logging.warning(f"IP detection error: {e}")
            
        return ips

# ───────────── Enhanced Flask Server Manager ────────────────────────
class FlaskServerManager(QObject):
    """Manages Flask server with restart capability."""
    
    def __init__(self, tv_player):
        super().__init__()
        self.tv_player = tv_player
        self.app = None
        self.server_thread = None
        self.server_process = None
        self.port = 5050
        self.is_running = False
        
    def start_server(self, port=5050):
        """Start or restart the Flask server."""
        if self.is_running:
            self.stop_server()
            
        self.port = port
        self.app = self._create_app()
        
        # Test if port is available
        try:
            test_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            test_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            test_socket.bind(('0.0.0.0', port))
            test_socket.close()
            
            # Start server in thread
            self.server_thread = threading.Thread(target=self._run_server, daemon=True)
            self.server_thread.start()
            self.is_running = True
            
            # Get local IPs for user info
            local_ips = self._get_local_ips()
            logging.info(f"[WEB REMOTE] Server started on port {port}")
            for ip in local_ips:
                logging.info(f"[WEB REMOTE] Access at: http://{ip}:{port}")
                
        except Exception as e:
            logging.error(f"Failed to start Flask server: {e}")
            self.is_running = False
            
    def stop_server(self):
        """Stop the Flask server."""
        if self.is_running and self.server_thread:
            self.is_running = False
            logging.info("[WEB REMOTE] Stopping server...")
            
    def restart_server(self):
        """Restart the Flask server."""
        logging.info("[WEB REMOTE] Restarting server...")
        self.start_server(self.port)
        
    def _run_server(self):
        """Run the Flask server."""
        try:
            run_simple('0.0.0.0', self.port, self.app, 
                      use_reloader=False, use_debugger=False, 
                      threaded=True, use_evalex=False)
        except Exception as e:
            logging.error(f"Flask server error: {e}")
            self.is_running = False
            
    def _get_local_ips(self):
        """Get local IP addresses."""
        ips = ['127.0.0.1']
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            main_ip = s.getsockname()[0]
            s.close()
            if main_ip not in ips:
                ips.append(main_ip)
        except:
            pass
        return ips
    
    def _create_app(self):
        """Create Flask application with all routes."""
        app = Flask(__name__)

        @app.after_request
        def add_headers(response):
            response.headers['Access-Control-Allow-Origin'] = '*'
            return response
        
        @app.route('/')
        def remote_page():
            return '''
<!DOCTYPE html>
<html>
<head>
    <title>Infinite Tv Remote</title>
    <meta name="viewport" content="width=device-width,initial-scale=1">
    <style>
        :root{
            --bg:#000000;
            --grid:#001100;
            --grid-hover:#002200;
            --grid-active:#003300;
            --fg:#00ff00;
            --border:#00ff00;
            --shadow:0 0 8px #39ff14;
        }
        *{box-sizing:border-box;font-family:"Consolas",monospace;margin:0;padding:0}
        body{background:var(--bg);color:var(--fg);text-align:center;padding:10px;min-height:100vh}
        h1{margin:20px 0;font-size:24px;text-shadow:var(--shadow);letter-spacing:2px}
        .status{background:var(--grid);border:2px solid var(--border);padding:10px;border-radius:6px;
                font-weight:bold;box-shadow:var(--shadow);margin-bottom:20px;font-size:14px}
        .btn{display:block;width:90%;max-width:240px;margin:6px auto;padding:12px;
             font-size:16px;font-weight:bold;color:var(--fg);background:var(--grid);
             border:2px solid var(--border);border-radius:8px;text-shadow:var(--shadow);
             transition:all .2s;cursor:pointer;letter-spacing:1px}
        .btn:hover{background:var(--grid-hover);transform:scale(1.02);box-shadow:var(--shadow)}
        .btn:active{background:var(--grid-active);transform:scale(0.98)}
        .small{font-size:13px;padding:8px}
        .volume-group{margin:20px 0;padding:15px;border:2px solid var(--border);border-radius:8px;
                      background:rgba(0,255,0,0.05)}
        .volume-title{margin-bottom:12px;font-size:16px;color:var(--fg);font-weight:bold;
                      text-shadow:var(--shadow)}
        .volume-row{display:flex;gap:10px;justify-content:center;flex-wrap:wrap}
        .vol-btn{flex:1;min-width:90px;max-width:130px}
        #feedback{margin-top:16px;min-height:24px;font-size:16px;font-weight:bold;
                  text-shadow:var(--shadow)}
        .nav-links{margin:15px 0;padding:12px;border:2px solid var(--border);border-radius:8px;
                   background:rgba(0,255,0,0.05)}
        .nav-links a{color:var(--fg);text-decoration:none;padding:10px 16px;
                     border:2px solid var(--border);border-radius:6px;margin:0 8px;
                     display:inline-block;transition:all .2s;font-weight:bold}
        .nav-links a:hover{background:var(--grid-hover);transform:scale(1.05);
                           box-shadow:var(--shadow)}
        .matrix-bg{position:fixed;top:0;left:0;width:100%;height:100%;pointer-events:none;
                   opacity:0.1;z-index:-1;overflow:hidden}
    </style>
</head>
<body>
    <div class="matrix-bg"></div>
    <h1>[TV] INFINITE TV CONTROL</h1>
    <div class="status">[OK] SYSTEM ONLINE</div>

    <button class="btn" onclick="send('play')">[>] PLAY / PAUSE</button>

    <button class="btn" onclick="send('next_channel')">[CH+] CHANNEL UP</button>
    <button class="btn" onclick="send('prev_channel')">[CH-] CHANNEL DOWN</button>

    <div class="volume-row">
        <button class="btn vol-btn small" onclick="send('cursor_up')">[^] UP</button>
        <button class="btn vol-btn small" onclick="send('cursor_ok')">[OK]</button>
        <button class="btn vol-btn small" onclick="send('cursor_down')">[v] DOWN</button>
        <button class="btn vol-btn small" onclick="send('cursor_left')">[<] LEFT</button>
        <button class="btn vol-btn small" onclick="send('cursor_right')">[>] RIGHT</button>
    </div>
    <div class="volume-row">
        <button class="btn vol-btn small" onclick="send('cursor_back')">[ESC] CLOSE</button>
    </div>

    <div class="volume-group">
        <div class="volume-title">[VOL] VOLUME MATRIX</div>
        <div class="volume-row">
            <button class="btn vol-btn small" onclick="send('volume_up')">[+] UP</button>
            <button class="btn vol-btn small" onclick="send('mute')">[M] MUTE</button>
            <button class="btn vol-btn small" onclick="send('volume_down')">[-] DOWN</button>
        </div>
    </div>


    <button class="btn" onclick="send('guide')">[G] TV GUIDE</button>
    <button class="btn" onclick="send('ondemand')">[O] ON DEMAND</button>
    <button class="btn small" onclick="send('last')">[L] LAST CHANNEL</button>

    <button class="btn small" onclick="send('info')">[i] INFO</button>
    <button class="btn small" onclick="send('fs')">[F] FULLSCREEN</button>
    <button class="btn small" onclick="send('restart_server')">[R] RESTART</button>

    <div class="nav-links">
        <a href="/media">[M] Media Browser</a>
        <a href="/guide">[G] Channel Guide</a>
        <a href="/status">[S] System Status</a>
    </div>

    <div id="feedback"></div>

<script>
let fb=document.getElementById('feedback'),tid;
function send(cmd){
    fb.textContent='[...] PROCESSING'; 
    fb.style.color='#39ff14';
    clearTimeout(tid);
    fetch('/action',{method:'POST',headers:{'Content-Type':'application/json'},
           body:JSON.stringify({cmd})})
    .then(r=>r.json())
    .then(j=>{
        if(j.success) {
            fb.textContent='[OK] '+cmd.toUpperCase()+' EXECUTED';
            fb.style.color='#00ff00';
            if(cmd === 'restart_server') {
                setTimeout(()=>{location.reload()}, 2000);
            }
        } else {
            fb.textContent='[ERR] COMMAND FAILED';
            fb.style.color='#ff0000';
        }
    })
    .catch(e=>{
        fb.textContent='[ERR] CONNECTION LOST';
        fb.style.color='#ff0000';
    });
    tid=setTimeout(()=>{fb.textContent='';fb.style.color='#00ff00'},3000);
}

// Matrix rain effect
const chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789@#$%^&*()";
let matrix = document.querySelector('.matrix-bg');
setInterval(() => {
    let drop = document.createElement('div');
    drop.textContent = chars[Math.floor(Math.random() * chars.length)];
    drop.style.position = 'absolute';
    drop.style.color = '#00ff00';
    drop.style.left = Math.random() * 100 + '%';
    drop.style.top = '-20px';
    drop.style.fontSize = Math.random() * 20 + 10 + 'px';
    drop.style.opacity = Math.random() * 0.5 + 0.5;
    matrix.appendChild(drop);
    
    let pos = -20;
    let fall = setInterval(() => {
        pos += 2;
        drop.style.top = pos + 'px';
        drop.style.opacity -= 0.01;
        if(pos > window.innerHeight || drop.style.opacity <= 0) {
            clearInterval(fall);
            drop.remove();
        }
    }, 50);
}, 100);
</script>
</body>
</html>
            '''

        @app.route('/media')
        def media_browser():
            """Enhanced media browser page with Matrix theme."""
            return '''
<!DOCTYPE html>
<html>
<head>
    <title>Infinite Tv Media Browser</title>
    <meta name="viewport" content="width=device-width,initial-scale=1">
    <style>
        * {box-sizing:border-box;margin:0;padding:0}
        body {background:#000;color:#0f0;font-family:Consolas,monospace;padding:10px}
        h1 {text-align:center;margin:20px 0;color:#0f0;text-shadow:0 0 15px #0f0;
            font-size:26px;letter-spacing:3px}
        .search-box {width:100%;max-width:600px;margin:0 auto 20px;padding:14px;
                    background:#001100;border:2px solid #0f0;border-radius:8px;
                    color:#0f0;font-size:16px;font-family:Consolas,monospace;
                    box-shadow:0 0 10px #39ff14}
        .search-box:focus {outline:none;border-color:#39ff14;background:#002200}
        .filters {text-align:center;margin:20px 0}
        .filter-btn {background:#001100;color:#0f0;border:2px solid #0f0;
                    padding:10px 20px;margin:0 5px;border-radius:6px;cursor:pointer;
                    font-weight:bold;transition:all .2s}
        .filter-btn:hover {background:#002200;transform:scale(1.05);box-shadow:0 0 10px #39ff14}
        .filter-btn.active {background:#003300;border-color:#39ff14}
        .media-grid {display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));
                    gap:20px;margin:20px 0}
        .media-item {background:#001100;border:2px solid #0f0;border-radius:10px;
                    padding:20px;transition:all .3s;position:relative;overflow:hidden}
        .media-item::before {content:'';position:absolute;top:0;left:-100%;width:100%;
                            height:2px;background:linear-gradient(90deg,transparent,#39ff14,transparent);
                            animation:scan 3s infinite}
        @keyframes scan {to{left:100%}}
        .media-item:hover {transform:translateY(-5px);box-shadow:0 10px 20px rgba(0,255,0,0.4);
                          background:#002200;border-color:#39ff14}
        .media-title {font-weight:bold;margin-bottom:10px;color:#39ff14;font-size:16px}
        .media-info {font-size:13px;color:#0f0;margin:5px 0;opacity:0.9}
        .play-btn {background:#003300;color:#0f0;border:2px solid #0f0;
                  padding:10px 20px;border-radius:6px;cursor:pointer;margin-top:12px;
                  width:100%;font-weight:bold;transition:all .2s}
        .play-btn:hover {background:#004400;border-color:#39ff14;transform:scale(1.02);
                        box-shadow:0 0 15px #39ff14}
        .back-link {display:inline-block;margin:10px 0;color:#0f0;text-decoration:none;
                   border:2px solid #0f0;padding:10px 20px;border-radius:6px;
                   font-weight:bold;transition:all .2s}
        .back-link:hover {background:#002200;transform:scale(1.05);box-shadow:0 0 10px #39ff14}
        @media (max-width:600px) {
            .media-grid {grid-template-columns:1fr}
            h1 {font-size:22px}
        }
    </style>
</head>
<body>
    <a href="/" class="back-link">[<] BACK TO REMOTE</a>
    <h1>[MEDIA] CONTENT MATRIX</h1>
    
    <input type="text" id="searchBox" class="search-box" placeholder="[SEARCH] Enter show, channel, or filename...">
    
    <div class="filters">
        <button class="filter-btn active" onclick="filterContent('all')">[*] ALL</button>
        <button class="filter-btn" onclick="filterContent('shows')">[S] SHOWS</button>
        <button class="filter-btn" onclick="filterContent('commercials')">[C] COMMERCIALS</button>
    </div>
    
    <div id="mediaGrid" class="media-grid">
        <div style="text-align:center;grid-column:1/-1;color:#39ff14">
            [LOADING] Accessing media database...
        </div>
    </div>

<script>
let allMedia = [];
let filteredMedia = [];
let currentFilter = 'all';

async function loadMedia() {
    try {
        const response = await fetch('/api/media');
        allMedia = await response.json();
        filteredMedia = [...allMedia];
        renderMedia();
    } catch (e) {
        document.getElementById('mediaGrid').innerHTML = '<p style="color:#f00;text-align:center">[ERROR] Failed to access media matrix</p>';
    }
}

function renderMedia() {
    const grid = document.getElementById('mediaGrid');
    if (filteredMedia.length === 0) {
        grid.innerHTML = '<p style="text-align:center;color:#f90;grid-column:1/-1">[EMPTY] No media files found</p>';
        return;
    }
    
    grid.innerHTML = filteredMedia.map(item => `
        <div class="media-item">
            <div class="media-title">[T] ${item.title}</div>
            <div class="media-info">[CH] ${item.channel}</div>
            <div class="media-info">[TIME] ${item.duration}</div>
            <div class="media-info">[TYPE] ${item.type}</div>
            <div class="media-info">[SIZE] ${item.size}</div>
            <button class="play-btn" data-path="${encodeURIComponent(item.path)}" onclick="playMedia(this.dataset.path)">[>] EXECUTE PLAYBACK</button>
        </div>
    `).join('');
}

function filterContent(type) {
    currentFilter = type;
    document.querySelectorAll('.filter-btn').forEach(btn => btn.classList.remove('active'));
    event.target.classList.add('active');
    applyFilters();
}

function applyFilters() {
    const searchTerm = document.getElementById('searchBox').value.toLowerCase();
    
    filteredMedia = allMedia.filter(item => {
        const matchesFilter = currentFilter === 'all' || item.type.toLowerCase() === currentFilter.slice(0,-1);
        const matchesSearch = !searchTerm || 
            item.title.toLowerCase().includes(searchTerm) ||
            item.channel.toLowerCase().includes(searchTerm) ||
            item.filename.toLowerCase().includes(searchTerm);
        return matchesFilter && matchesSearch;
    });
    
    renderMedia();
}

async function playMedia(encodedPath) {
    const path = decodeURIComponent(encodedPath);
    try {
        const response = await fetch('/action', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({cmd: 'play_media', path: path})
        });
        const result = await response.json();
        if (result.success) {
            alert('[OK] PLAYBACK INITIATED: ' + path.split('/').pop());
        } else {
            alert('[ERR] PLAYBACK FAILED');
        }
    } catch (e) {
        alert('[ERR] CONNECTION ERROR');
    }
}

document.getElementById('searchBox').addEventListener('input', applyFilters);
loadMedia();
</script>
</body>
</html>
            '''

        @app.route('/api/media')
        def api_media():
            """API endpoint for media data."""
            try:
                media_data = self.tv_player.get_all_media_for_api()
                return jsonify(media_data)
            except Exception as e:
                logging.error(f"Media API error: {e}")
                return jsonify([])

        @app.route('/guide')
        def remote_guide():
            """Simple channel guide page."""
            return '''
<!DOCTYPE html>
<html>
<head>
    <title>Infinite Tv Guide</title>
    <meta name="viewport" content="width=device-width,initial-scale=1">
    <style>
        body{background:#000;color:#0f0;font-family:Consolas,monospace;padding:10px}
        h1{text-align:center;margin:20px 10px;font-size:22px}
        table{width:100%;border-collapse:collapse;margin-top:10px}
        th,td{border:1px solid #0f0;padding:6px;text-align:left}
        th{background:#001100}
        tr:nth-child(even){background:#001000}
        a{color:#0f0;text-decoration:none}
    </style>
</head>
<body>
    <h1>[GUIDE] CHANNEL LISTING</h1>
    <a href="/">[<] BACK TO REMOTE</a>
    <table id="guide"></table>
<script>
async function loadGuide(){
    const res=await fetch('/api/guide');
    const data=await res.json();
    const tbl=document.getElementById('guide');
    tbl.innerHTML='<tr><th>Channel</th><th>Now</th><th>Next</th></tr>'+
        data.map(ch=>`<tr><td>${ch.channel}</td><td><a href="#" onclick="gotoCh(${ch.index});return false;">${ch.current}</a></td>`+
        `<td>${ch.shows.slice(1,3).map(s=>s.title).join(' , ')}</td></tr>`).join('');
}
function gotoCh(idx){
    fetch('/action',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({cmd:'goto:'+idx})});
}
loadGuide();
</script>
</body>
</html>
            '''

        @app.route('/api/guide')
        def api_guide():
            try:
                guide = self.tv_player.get_guide_for_api()
                return jsonify(guide)
            except Exception as e:
                logging.error(f"Guide API error: {e}")
                return jsonify([])

        @app.route('/status')
        def status_page():
            """Status page."""
            try:
                status = self.tv_player.get_status_for_api()
                return jsonify(status)
            except Exception as e:
                return jsonify({"error": str(e)})

        @app.route('/action', methods=['POST'])
        def handle_action():
            try:
                data = request.get_json(force=True)
                cmd = data.get('cmd')
                
                if cmd == 'restart_server':
                    # Signal restart (handled by main thread)
                    self.tv_player.signal_bridge.restart_server_requested.emit()
                    return jsonify({"success": True, "command": cmd})
                elif cmd == 'play_media':
                    path = data.get('path')
                    if path:
                        self.tv_player.signal_bridge.command_received.emit(f"play_media:{path}")
                        return jsonify({"success": True, "command": cmd})
                else:
                    self.tv_player.signal_bridge.command_received.emit(cmd)
                    return jsonify({"success": True, "command": cmd})
                    
            except Exception as e:
                logging.error(f"Action handler error: {e}")
                return jsonify({"success": False, "error": str(e)}), 500

        return app

# ───────────── Console widget ─────────────
class Console(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent, Qt.Tool)
        self.setWindowTitle("[LOG] Infinite Tv Console")
        self.resize(900, 500)
        
        # Apply Matrix theme
        self.setStyleSheet("""
            QDialog {
                background-color: #000000;
                color: #00ff00;
            }
            QPlainTextEdit {
                background-color: #001100;
                color: #00ff00;
                border: 2px solid #00ff00;
                font-family: "Consolas", monospace;
                font-size: 11px;
                selection-background-color: #00ff00;
                selection-color: #000000;
            }
            QLabel {
                color: #00ff00;
                font-weight: bold;
            }
            QPushButton {
                background-color: #001100;
                color: #00ff00;
                border: 2px solid #00ff00;
                padding: 6px 12px;
                font-weight: bold;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #003300;
                border-color: #39ff14;
            }
        """)
        
        self.text = QPlainTextEdit(readOnly=True)
        self.text.setFont(QFont("Consolas", 10))
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("[LOG] System Log Output:"))
        layout.addWidget(self.text)
        
        btn_layout = QHBoxLayout()
        clear_btn = QPushButton("[CLR] Clear Log")
        clear_btn.clicked.connect(self.text.clear)
        btn_layout.addWidget(clear_btn)
        
        export_btn = QPushButton("[EXP] Export Log")
        export_btn.clicked.connect(self.export_log)
        btn_layout.addWidget(export_btn)
        
        layout.addLayout(btn_layout)
        
    def write(self, line: str):
        line = line.rstrip('\n')
        if line.strip():
            self.text.appendPlainText(line)
    
    def flush(self):
        pass
    
    def export_log(self):
        """Export log to file."""
        try:
            filename, _ = QFileDialog.getSaveFileName(
                self, "Export Log", 
                str(ROOT_DIR / f"tv_station_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"),
                "Text Files (*.txt);;All Files (*)"
            )
            if filename:
                with open(filename, 'w') as f:
                    f.write(self.text.toPlainText())
                QMessageBox.information(self, "[OK] Export Complete", f"Log exported to:\n{filename}")
        except Exception as e:
            QMessageBox.warning(self, "[ERR] Export Failed", f"Failed to export log:\n{e}")

# ───────────── Enhanced Settings dialog ─────────────
class SettingsDialog(QDialog):
    def __init__(self, s: Dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("[SET] Infinite Tv Settings")
        self.setModal(True)
        self.resize(500, 420)
        
        # Apply Matrix theme
        self.setStyleSheet("""
            QDialog {
                background-color: #000000;
                color: #00ff00;
            }
            QGroupBox {
                color: #00ff00;
                border: 2px solid #00ff00;
                border-radius: 6px;
                margin-top: 10px;
                font-weight: bold;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
            QLabel {
                color: #00ff00;
            }
            QSpinBox, QSlider {
                background-color: #001100;
                color: #00ff00;
                border: 1px solid #00ff00;
            }
            QCheckBox {
                color: #00ff00;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border: 2px solid #00ff00;
                background-color: #001100;
            }
            QCheckBox::indicator:checked {
                background-color: #00ff00;
            }
            QPushButton {
                background-color: #001100;
                color: #00ff00;
                border: 2px solid #00ff00;
                padding: 6px 12px;
                font-weight: bold;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #003300;
                border-color: #39ff14;
            }
        """)
        
        layout = QVBoxLayout(self)
        
        # Video Settings Group
        video_group = QGroupBox("[VID] Video & Audio")
        video_layout = QFormLayout(video_group)
        
        self.vol = QSlider(Qt.Horizontal)
        self.vol.setRange(0, 100)
        self.vol.setValue(s["default_volume"])
        vol_layout = QHBoxLayout()
        vol_layout.addWidget(self.vol)
        self.vol_label = QLabel(f"{s['default_volume']}%")
        vol_layout.addWidget(self.vol_label)
        self.vol.valueChanged.connect(lambda v: self.vol_label.setText(f"{v}%"))
        video_layout.addRow("Default Volume:", vol_layout)
        
        self.sub_sz = QSpinBox()
        self.sub_sz.setRange(8, 72)
        self.sub_sz.setValue(s["subtitle_size"])
        video_layout.addRow("Subtitle Font Size:", self.sub_sz)
        
        self.chk_stat = QCheckBox("Static effect on channel change")
        self.chk_stat.setChecked(s["static_fx"])
        video_layout.addRow(self.chk_stat)
        
        layout.addWidget(video_group)
        
        # Scheduling Settings Group
        sched_group = QGroupBox("[SCHED] Scheduling")
        sched_layout = QFormLayout(sched_group)
        
        info_label = QLabel("[!] Changing these settings will rebuild all schedules\nand return you to the TV Guide.")
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: #f39c12; font-style: italic; padding: 8px;")
        sched_layout.addRow(info_label)
        
        self.min_show_len = QSpinBox()
        self.min_show_len.setRange(5, 60)
        self.min_show_len.setValue(s.get("min_show_minutes", 5))
        self.min_show_len.setSuffix(" minutes")
        sched_layout.addRow("Minimum Show Length:", self.min_show_len)

        self.ad_break_len = QSpinBox()
        self.ad_break_len.setRange(1, 30)
        self.ad_break_len.setValue(s.get("ad_break_minutes", 3))
        self.ad_break_len.setSuffix(" minutes")
        sched_layout.addRow("Ad Break Length:", self.ad_break_len)
        
        layout.addWidget(sched_group)
        
        # Web Remote Settings
        web_group = QGroupBox("[WEB] Web Remote")
        web_layout = QFormLayout(web_group)
        
        self.web_port = QSpinBox()
        self.web_port.setRange(1024, 65535)
        self.web_port.setValue(s.get("web_port", 5050))
        web_layout.addRow("Web Remote Port:", self.web_port)
        
        layout.addWidget(web_group)
        
        # Advanced Settings Group
        advanced_group = QGroupBox("[ADV] Advanced")
        advanced_layout = QFormLayout(advanced_group)

        self.cache_clear = QPushButton("[CLR] Clear Duration Cache")
        self.cache_clear.clicked.connect(self._clear_cache)
        advanced_layout.addRow(self.cache_clear)

        layout.addWidget(advanced_group)

        # File Locations
        file_group = QGroupBox("[FILES] Data Files")
        file_layout = QFormLayout(file_group)

        self.cache_edit = QLineEdit(s.get("cache_file", str(DEFAULT_CACHE_FILE)))
        browse_cache = QPushButton("[...]")
        browse_cache.clicked.connect(lambda: self._browse_file(self.cache_edit))
        cache_row = QHBoxLayout()
        cache_row.addWidget(self.cache_edit)
        cache_row.addWidget(browse_cache)
        file_layout.addRow("Cache File:", cache_row)

        self.hotkey_edit = QLineEdit(s.get("hotkey_file", str(DEFAULT_HOTKEY_FILE)))
        browse_hot = QPushButton("[...]")
        browse_hot.clicked.connect(lambda: self._browse_file(self.hotkey_edit))
        hot_row = QHBoxLayout()
        hot_row.addWidget(self.hotkey_edit)
        hot_row.addWidget(browse_hot)
        file_layout.addRow("Hotkey File:", hot_row)

        self.channels_edit = QLineEdit(s.get("channels_dir", str(ROOT_CHANNELS)))
        browse_chan = QPushButton("[...]")
        browse_chan.clicked.connect(lambda: self._browse_folder(self.channels_edit))
        chan_row = QHBoxLayout()
        chan_row.addWidget(self.channels_edit)
        chan_row.addWidget(browse_chan)
        file_layout.addRow("Channels Folder:", chan_row)

        layout.addWidget(file_group)
        
        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        
    def _clear_cache(self):
        try:
            cache_path = Path(self.parent().cache_file)
            if cache_path.exists():
                cache_path.unlink()
            QMessageBox.information(self, "[OK] Cache Cleared", "Duration cache has been cleared.")
        except Exception as e:
            QMessageBox.warning(self, "[ERR] Error", f"Failed to clear cache: {e}")

    def _browse_file(self, edit: QLineEdit):
        path, _ = QFileDialog.getSaveFileName(self, "Select File", edit.text(), "JSON Files (*.json)")
        if path:
            edit.setText(path)

    def _browse_folder(self, edit: QLineEdit):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder", edit.text(), QFileDialog.ShowDirsOnly)
        if folder:
            edit.setText(folder)
        
    def result(self) -> Dict:
        return {
            "default_volume": self.vol.value(),
            "subtitle_size": self.sub_sz.value(),
            "static_fx": self.chk_stat.isChecked(),
            "min_show_minutes": self.min_show_len.value(),
            "ad_break_minutes": self.ad_break_len.value(),
            "web_port": self.web_port.value(),
            "cache_file": self.cache_edit.text(),
            "hotkey_file": self.hotkey_edit.text(),
            "channels_dir": self.channels_edit.text()
        }

# ───────────── Hot-key dialog ─────────────
class HotkeyDialog(QDialog):
    def __init__(self, mapping: Dict[str,str], defaults: Dict[str,str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("[KEYS] Configure Hot-keys")
        self.setModal(True)
        
        # Apply Matrix theme
        self.setStyleSheet("""
            QDialog {
                background-color: #000000;
                color: #00ff00;
            }
            QLabel {
                color: #00ff00;
            }
            QKeySequenceEdit {
                background-color: #001100;
                color: #00ff00;
                border: 1px solid #00ff00;
                padding: 4px;
            }
            QPushButton {
                background-color: #001100;
                color: #00ff00;
                border: 2px solid #00ff00;
                padding: 4px 8px;
                font-weight: bold;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #003300;
                border-color: #39ff14;
            }
        """)
        
        layout = QVBoxLayout(self)
        
        info = QLabel("[KEYS] Configure keyboard shortcuts for TV controls:")
        info.setWordWrap(True)
        layout.addWidget(info)
        
        grid = QGridLayout()
        grid.setColumnStretch(1, 1)
        self.edits = {}
        
        row = 0
        for action, default in defaults.items():
            label = QLabel(action.replace('_', ' ').title() + ":")
            edit = QKeySequenceEdit(QKeySequence(mapping.get(action, default)))
            clear_btn = QPushButton("[X]")
            clear_btn.clicked.connect(edit.clear)
            clear_btn.setMaximumWidth(40)
            
            grid.addWidget(label, row, 0)
            grid.addWidget(edit, row, 1)
            grid.addWidget(clear_btn, row, 2)
            
            self.edits[action] = edit
            row += 1
            
        layout.addLayout(grid)
        
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        
    def result(self):
        return {action: edit.keySequence().toString() for action, edit in self.edits.items()}

# ───────────── TV Network Editor ─────────────
class NetworkEditor(QMainWindow):
    """TV Network Editor - File Manager for Channel Content with Icon Management"""
    
    def __init__(self, tv_player: 'TVPlayer', parent=None):
        super().__init__(parent)
        self.tv = tv_player
        self.setWindowTitle("[EDIT] Infinite Tv Network Editor")
        self.resize(1200, 700)
        self.setWindowIcon(QIcon())
        
        # Apply Matrix theme
        self.setStyleSheet("""
            QMainWindow { background-color: #000000; }
            QTreeWidget {
                background-color: #001100; color: #00ff00; border: 2px solid #00ff00; 
                font-size: 11px; alternate-background-color: #002200;
            }
            QTreeWidget::item { 
                padding: 2px; border-bottom: 1px solid #003300; height: 22px; 
            }
            QTreeWidget::item:selected { background-color: #00ff00; color: #000000; }
            QTreeWidget::item:hover { background-color: #003300; }
            QHeaderView::section {
                background-color: #002200; color: #00ff00; padding: 6px; 
                border: 1px solid #00ff00; font-weight: bold; font-size: 11px;
            }
            QLabel { color: #00ff00; padding: 2px; font-size: 11px; }
            QPushButton {
                background-color: #001100; color: #00ff00; border: 2px solid #00ff00;
                padding: 6px 10px; border-radius: 4px; font-weight: bold; font-size: 11px;
                min-height: 20px; max-height: 26px;
            }
            QPushButton:hover { background-color: #003300; border-color: #39ff14; }
            QPushButton:pressed { background-color: #004400; }
            QPushButton:checked { background-color: #00ff00; color: #000000; }
            QSplitter::handle { background-color: #00ff00; width: 3px; }
            QGroupBox {
                color: #00ff00; border: 2px solid #00ff00; border-radius: 4px; 
                margin-top: 8px; font-weight: bold; font-size: 11px; padding-top: 8px;
            }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }
            QStatusBar { background-color: #001100; color: #00ff00; font-size: 10px; border-top: 1px solid #00ff00; }
            QMenu {
                background-color: #001100; color: #00ff00; border: 2px solid #00ff00;
            }
            QMenu::item:selected { background-color: #003300; }
        """)
        
        # Central widget with compact layout
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(4)
        
        # Compact toolbar
        toolbar_layout = QHBoxLayout()
        toolbar_layout.setContentsMargins(2, 2, 2, 2)
        toolbar_layout.setSpacing(4)
        
        refresh_btn = QPushButton("[R] Refresh")
        refresh_btn.setToolTip("Refresh Content")
        refresh_btn.clicked.connect(self.refresh_content)
        toolbar_layout.addWidget(refresh_btn)
        
        new_channel_btn = QPushButton("[+] New Ch")
        new_channel_btn.setToolTip("New Channel")
        new_channel_btn.clicked.connect(self.create_new_channel)
        toolbar_layout.addWidget(new_channel_btn)
        
        import_btn = QPushButton("[I] Import")
        import_btn.setToolTip("Import Files")
        import_btn.clicked.connect(self.import_files)
        toolbar_layout.addWidget(import_btn)
        
        # Icon management buttons
        self.change_icon_btn = QPushButton("[ICO] Icon")
        self.change_icon_btn.setToolTip("Change Channel Icon")
        self.change_icon_btn.clicked.connect(self.change_selected_channel_icon)
        self.change_icon_btn.setEnabled(False)
        toolbar_layout.addWidget(self.change_icon_btn)
        
        self.remove_icon_btn = QPushButton("[X] Del Icon")
        self.remove_icon_btn.setToolTip("Remove Channel Icon")
        self.remove_icon_btn.clicked.connect(self.remove_selected_channel_icon)
        self.remove_icon_btn.setEnabled(False)
        toolbar_layout.addWidget(self.remove_icon_btn)
        
        toolbar_layout.addStretch()

        self.status_label = QLabel("[OK] Ready")
        self.status_label.setMaximumHeight(20)
        toolbar_layout.addWidget(self.status_label)

        # Enlarged channel icon preview
        self.icon_preview = QLabel()
        self.icon_preview.setFixedSize(64, 64)
        self.icon_preview.setScaledContents(True)
        self.icon_preview.setStyleSheet("border:2px solid #00ff00")
        toolbar_layout.addWidget(self.icon_preview)
        
        main_layout.addLayout(toolbar_layout)
        
        # Compact splitter
        splitter = QSplitter(Qt.Horizontal)
        
        # Left panel - Channel list (more compact)
        left_panel = QGroupBox("[CH] Channels")
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(4, 6, 4, 4)
        left_layout.setSpacing(2)
        
        self.channel_tree = QTreeWidget()
        self.channel_tree.setHeaderLabel("Channel")
        self.channel_tree.itemClicked.connect(self.on_channel_selected)
        self.channel_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.channel_tree.customContextMenuRequested.connect(self.show_channel_context_menu)
        self.channel_tree.setRootIsDecorated(False)
        self.channel_tree.setIndentation(0)
        self.channel_tree.setUniformRowHeights(True)
        left_layout.addWidget(self.channel_tree)
        
        splitter.addWidget(left_panel)
        
        # Right panel - Content view (more compact)
        right_panel = QGroupBox("[FILES] Content")
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(4, 6, 4, 4)
        right_layout.setSpacing(2)
        
        # Compact filter buttons
        filter_layout = QHBoxLayout()
        filter_layout.setContentsMargins(0, 0, 0, 0)
        filter_layout.setSpacing(2)
        
        self.show_all_btn = QPushButton("[*] All")
        self.show_all_btn.setCheckable(True)
        self.show_all_btn.setChecked(True)
        self.show_all_btn.clicked.connect(lambda: self.filter_content("all"))
        filter_layout.addWidget(self.show_all_btn)
        
        self.show_shows_btn = QPushButton("[S] Shows")
        self.show_shows_btn.setCheckable(True)
        self.show_shows_btn.clicked.connect(lambda: self.filter_content("show"))
        filter_layout.addWidget(self.show_shows_btn)
        
        self.show_commercials_btn = QPushButton("[C] Ads")
        self.show_commercials_btn.setCheckable(True)
        self.show_commercials_btn.clicked.connect(lambda: self.filter_content("commercial"))
        filter_layout.addWidget(self.show_commercials_btn)
        
        self.show_misc_btn = QPushButton("[M] Misc")
        self.show_misc_btn.setCheckable(True)
        self.show_misc_btn.clicked.connect(lambda: self.filter_content("misc"))
        filter_layout.addWidget(self.show_misc_btn)
        
        filter_layout.addStretch()
        right_layout.addLayout(filter_layout)
        
        # Compact content tree
        self.content_tree = QTreeWidget()
        self.content_tree.setHeaderLabels(["Name", "Type", "Duration", "Size"])
        self.content_tree.setSortingEnabled(True)
        self.content_tree.setAlternatingRowColors(True)
        self.content_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.content_tree.customContextMenuRequested.connect(self.show_content_context_menu)
        self.content_tree.setSelectionMode(QTreeWidget.ExtendedSelection)
        self.content_tree.setRootIsDecorated(False)
        self.content_tree.setUniformRowHeights(True)
        
        # Compact column widths
        self.content_tree.setColumnWidth(0, 250)
        self.content_tree.setColumnWidth(1, 70)
        self.content_tree.setColumnWidth(2, 70)
        self.content_tree.setColumnWidth(3, 70)
        
        right_layout.addWidget(self.content_tree)
        
        splitter.addWidget(right_panel)
        splitter.setSizes([250, 950])  # More space for content
        
        main_layout.addWidget(splitter)
        
        # Compact status bar
        status_bar = self.statusBar()
        status_bar.showMessage("[OK] Infinite Tv Network Editor Ready")
        status_bar.setMaximumHeight(20)
        
        # Initialize
        self.current_channel = None
        self.current_filter = "all"
        self.refresh_content()

    def _update_icon_preview(self, channel: Optional[Path]):
        """Show enlarged icon preview for selected channel."""
        if channel:
            logo = self.tv._find_logo(channel)
            if logo:
                pix = QPixmap(logo).scaled(64, 64, Qt.KeepAspectRatio,
                                        Qt.SmoothTransformation)
                self.icon_preview.setPixmap(pix)
                return
        self.icon_preview.clear()
    
    def refresh_content(self):
        """Refresh the channel list and content."""
        self.channel_tree.clear()
        self.content_tree.clear()
        self._update_icon_preview(None)
        
        channels = discover_channels(ROOT_CHANNELS)
        
        for channel in channels:
            item = QTreeWidgetItem(self.channel_tree)
            item.setText(0, channel.name)
            item.setData(0, Qt.UserRole, channel)
            
            # Add channel logo if exists
            logo_path = self.tv._find_logo(channel)
            if logo_path:
                item.setIcon(0, QIcon(logo_path))
        
        self.status_label.setText(f"[OK] Found {len(channels)} channels")
        self.statusBar().showMessage(f"[OK] Loaded {len(channels)} channels")
    
    def on_channel_selected(self, item, column):
        """Handle channel selection."""
        channel = item.data(0, Qt.UserRole)
        if channel:
            self.current_channel = channel
            self.load_channel_content(channel)
            # Enable icon management buttons
            self.change_icon_btn.setEnabled(True)
            self.remove_icon_btn.setEnabled(True)
            self._update_icon_preview(channel)
        else:
            self.change_icon_btn.setEnabled(False)
            self.remove_icon_btn.setEnabled(False)
            self._update_icon_preview(None)
    
    def load_channel_content(self, channel: Path):
        """Load content for the selected channel."""
        self.content_tree.clear()
        
        # Load shows
        shows_dir = channel / "Shows"
        if shows_dir.exists():
            self._load_directory_content(shows_dir, "show", QColor("#00ff00"))
        
        # Load commercials
        commercials_dir = channel / "Commercials"
        if commercials_dir.exists():
            self._load_directory_content(commercials_dir, "commercial", QColor("#ff4444"))
        
        # Load misc files (root level video files)
        for file in channel.iterdir():
            if file.is_file() and file.suffix.lower() in VIDEO_EXTS:
                self._add_file_item(file, "misc", QColor("#ffaa00"))
        
        # Apply filter
        self.apply_content_filter()
        
        self.statusBar().showMessage(f"[OK] Loaded content for {channel.name}")
    
    def _load_directory_content(self, directory: Path, content_type: str, color: QColor):
        """Load video files from a directory."""
        for file in gather_files(directory):
            self._add_file_item(file, content_type, color)
    
    def _add_file_item(self, file: Path, content_type: str, color: QColor):
        """Add a file item to the content tree."""
        item = QTreeWidgetItem(self.content_tree)
        item.setText(0, file.name)
        item.setText(1, content_type.capitalize())
        
        # Get duration
        duration_ms = self.tv._get_duration(file)
        item.setText(2, ms_to_hms(duration_ms))
        item.setData(2, Qt.UserRole, duration_ms)
        
        # Get file size
        size_mb = file.stat().st_size / (1024 * 1024)
        item.setText(3, f"{size_mb:.1f}MB")
        
        # Store file path in user data
        item.setData(0, Qt.UserRole, file)
        item.setData(1, Qt.UserRole, content_type)
        
        # Set color based on type
        for col in range(4):
            item.setForeground(col, color)
    
    def filter_content(self, filter_type: str):
        """Filter content by type."""
        self.current_filter = filter_type
        
        # Update button states
        self.show_all_btn.setChecked(filter_type == "all")
        self.show_shows_btn.setChecked(filter_type == "show")
        self.show_commercials_btn.setChecked(filter_type == "commercial")
        self.show_misc_btn.setChecked(filter_type == "misc")
        
        self.apply_content_filter()
    
    def apply_content_filter(self):
        """Apply the current filter to the content tree."""
        root = self.content_tree.invisibleRootItem()
        for i in range(root.childCount()):
            item = root.child(i)
            content_type = item.data(1, Qt.UserRole)
            
            if self.current_filter == "all":
                item.setHidden(False)
            else:
                item.setHidden(content_type != self.current_filter)
    
    def change_selected_channel_icon(self):
        """Change icon for the currently selected channel."""
        if self.current_channel:
            self.change_channel_icon(self.current_channel)
    
    def remove_selected_channel_icon(self):
        """Remove icon for the currently selected channel."""
        if self.current_channel:
            self.remove_channel_icon(self.current_channel)
    
    def show_channel_context_menu(self, position):
        """Show context menu for channel tree."""
        item = self.channel_tree.itemAt(position)
        if not item:
            return
        
        channel = item.data(0, Qt.UserRole)
        if not channel:
            return
        
        menu = QMenu(self)
        
        # Icon management section
        icon_menu = menu.addMenu("[ICO] Icon")
        icon_menu.addAction("[SET] Change Icon", lambda: self.change_channel_icon(channel))
        icon_menu.addAction("[DEL] Remove Icon", lambda: self.remove_channel_icon(channel))
        
        menu.addSeparator()
        
        # File operations
        menu.addAction("[OPEN] Open Folder", lambda: self._open_in_file_manager(channel))
        menu.addAction("[REN] Rename", lambda: self.rename_channel(channel))
        
        menu.addSeparator()
        menu.addAction("[DEL] Delete Channel", lambda: self.delete_channel(channel))
        
        menu.exec_(self.channel_tree.mapToGlobal(position))
    
    def change_channel_icon(self, channel: Path):
        """Change the icon for a channel."""
        # Start from the channel directory
        start_dir = str(channel)
        
        icon_file, _ = QFileDialog.getOpenFileName(
            self, f"[ICO] Select Icon for {channel.name}",
            start_dir, "Image Files (*.png *.jpg *.jpeg *.gif *.bmp *.ico)"
        )
        
        if icon_file:
            try:
                source = Path(icon_file)
                
                # Always use .png for consistency
                target = channel / "logo.png"
                
                # Remove existing logo files first
                for ext in ('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.ico'):
                    existing_logo = channel / f"logo{ext}"
                    if existing_logo.exists():
                        existing_logo.unlink()
                        logging.info(f"Removed old icon: {existing_logo}")
                
                # Copy and convert to PNG if necessary
                if source.suffix.lower() == '.png' and source != target:
                    shutil.copy2(source, target)
                else:
                    # Convert to PNG for consistency
                    from PyQt5.QtGui import QPixmap
                    pixmap = QPixmap(str(source))
                    if not pixmap.isNull():
                        # Scale to reasonable size if too large
                        if pixmap.width() > 64 or pixmap.height() > 64:
                            pixmap = pixmap.scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                        pixmap.save(str(target), "PNG")
                    else:
                        # Fallback to direct copy
                        shutil.copy2(source, target)
                
                # Update TV player's logo cache immediately
                self.tv._rebuild_logos()
                
                # Refresh the channel tree to show new icon
                selected_item = self.channel_tree.currentItem()
                self.refresh_content()
                
                # Restore selection
                if selected_item:
                    for i in range(self.channel_tree.topLevelItemCount()):
                        item = self.channel_tree.topLevelItem(i)
                        if item.data(0, Qt.UserRole) == channel:
                            self.channel_tree.setCurrentItem(item)
                            break
                
                self.statusBar().showMessage(f"[OK] Icon updated for {channel.name}")
                logging.info(f"Updated icon for {channel.name}: {target}")
                self._update_icon_preview(channel)

            except Exception as e:
                logging.error(f"Failed to change icon: {e}")
                QMessageBox.critical(self, "[ERR] Error", f"Failed to change icon:\n{e}")
    
    def remove_channel_icon(self, channel: Path):
        """Remove the icon for a channel."""
        try:
            removed_files = []
            for ext in ('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.ico'):
                logo_file = channel / f"logo{ext}"
                if logo_file.exists():
                    logo_file.unlink()
                    removed_files.append(logo_file.name)
            
            if removed_files:
                # Update TV player's logo cache immediately
                self.tv._rebuild_logos()
                
                # Refresh the channel tree to remove icon
                selected_item = self.channel_tree.currentItem()
                self.refresh_content()
                
                # Restore selection
                if selected_item:
                    for i in range(self.channel_tree.topLevelItemCount()):
                        item = self.channel_tree.topLevelItem(i)
                        if item.data(0, Qt.UserRole) == channel:
                            self.channel_tree.setCurrentItem(item)
                            break
                
                self.statusBar().showMessage(f"[OK] Icon removed from {channel.name}")
                logging.info(f"Removed icons from {channel.name}: {', '.join(removed_files)}")
                self._update_icon_preview(channel)
            else:
                self.statusBar().showMessage(f"[!] No icon found for {channel.name}")
                
        except Exception as e:
            logging.error(f"Failed to remove icon: {e}")
            QMessageBox.critical(self, "[ERR] Error", f"Failed to remove icon:\n{e}")
    
    def show_content_context_menu(self, position):
        """Show context menu for content tree."""
        selected_items = self.content_tree.selectedItems()
        if not selected_items:
            item = self.content_tree.itemAt(position)
            if not item:
                return
            selected_items = [item]

        files = [it.data(0, Qt.UserRole) for it in selected_items if it.data(0, Qt.UserRole)]
        if not files:
            return

        menu = QMenu(self)

        # Move to submenu (only show if there are other channels)
        channels = discover_channels(ROOT_CHANNELS)
        other_channels = [ch for ch in channels if ch != self.current_channel]

        if other_channels:
            send_menu = menu.addMenu("[MOV] Move to...")
            for channel in other_channels:
                send_menu.addAction(channel.name,
                    lambda checked, ch=channel: self.move_files_to_channel(files, ch))
        if other_channels:
            copy_menu = menu.addMenu("[CPY] Copy to...")
            for channel in other_channels:
                copy_menu.addAction(channel.name,
                    lambda checked, ch=channel: self.copy_files_to_channel(files, ch))
            menu.addSeparator()

        # File operations
        if len(files) == 1:
            file_path = files[0]
            menu.addAction("[REN] Rename", lambda: self.rename_file(file_path))
            menu.addAction("[INFO] Info", lambda: self.show_file_info(file_path))
        menu.addSeparator()
        menu.addAction("[DEL] Delete", lambda: [self.delete_file(f) for f in files])
        
        menu.exec_(self.content_tree.mapToGlobal(position))
    
    def move_file_to_channel(self, file_path: Path, target_channel: Path):
        """Move a file to another channel."""
        try:
            # Determine target directory based on file type
            content_type = None
            if file_path.parent.name == "Shows":
                target_dir = target_channel / "Shows"
                content_type = "show"
            elif file_path.parent.name == "Commercials":
                target_dir = target_channel / "Commercials"
                content_type = "commercial"
            else:
                # Ask user where to place misc files
                msg = QMessageBox(self)
                msg.setWindowTitle("[?] Choose Destination")
                msg.setText(f"Where should '{file_path.name}' be placed in {target_channel.name}?")
                msg.addButton("[S] Shows", QMessageBox.YesRole)
                msg.addButton("[C] Commercials", QMessageBox.NoRole)
                msg.addButton("[X] Cancel", QMessageBox.RejectRole)
                
                result = msg.exec_()
                if result == 0:  # Shows
                    target_dir = target_channel / "Shows"
                elif result == 1:  # Commercials
                    target_dir = target_channel / "Commercials"
                else:
                    return
            
            # Ensure target directory exists
            target_dir.mkdir(parents=True, exist_ok=True)
            
            # Check if file exists
            target_path = target_dir / file_path.name
            if target_path.exists():
                reply = QMessageBox.question(
                    self, "[!] File Exists",
                    f"'{file_path.name}' already exists in {target_channel.name}.\nOverwrite?",
                    QMessageBox.Yes | QMessageBox.No
                )
                if reply != QMessageBox.Yes:
                    return
            
            # Move the file
            shutil.move(str(file_path), str(target_path))
            
            # Clear cache for the moved file
            if str(file_path) in self.tv.durations:
                del self.tv.durations[str(file_path)]
            
            # Refresh content
            if self.current_channel:
                self.load_channel_content(self.current_channel)
            
            # Clear schedules for affected channels
            if self.current_channel in self.tv.schedules:
                del self.tv.schedules[self.current_channel]
            if target_channel in self.tv.schedules:
                del self.tv.schedules[target_channel]
            
            self.statusBar().showMessage(f"[OK] Moved {file_path.name} to {target_channel.name}")
            logging.info(f"Moved {file_path} to {target_path}")
            
        except Exception as e:
            logging.error(f"Failed to move file: {e}")
            QMessageBox.critical(self, "[ERR] Error", f"Failed to move file:\n{e}")

    def move_files_to_channel(self, files: List[Path], target_channel: Path):
        for f in files:
            self.move_file_to_channel(f, target_channel)

    def copy_files_to_channel(self, files: List[Path], target_channel: Path):
        for f in files:
            try:
                dest_dir = target_channel / ("Shows" if f.parent.name == "Shows" else "Commercials")
                if not dest_dir.exists():
                    dest_dir.mkdir(parents=True, exist_ok=True)
                dest = dest_dir / f.name
                if dest.exists():
                    continue
                shutil.copy2(str(f), str(dest))
            except Exception as e:
                logging.error(f"Copy failed for {f}: {e}")
    
    def rename_file(self, file_path: Path):
        """Rename a file."""
        current_name = file_path.name
        new_name, ok = QInputDialog.getText(
            self, "[REN] Rename File",
            "New name:", QLineEdit.Normal,
            current_name
        )
        
        if ok and new_name and new_name != current_name:
            try:
                new_path = file_path.parent / new_name
                if new_path.exists():
                    QMessageBox.warning(self, "[ERR] Error", "A file with that name already exists.")
                    return
                
                file_path.rename(new_path)
                
                # Update cache
                if str(file_path) in self.tv.durations:
                    duration = self.tv.durations[str(file_path)]
                    del self.tv.durations[str(file_path)]
                    self.tv.durations[str(new_path)] = duration
                    self.tv._save_cache()
                
                # Refresh
                if self.current_channel:
                    self.load_channel_content(self.current_channel)
                
                self.statusBar().showMessage(f"[OK] Renamed to {new_name}")
                
            except Exception as e:
                logging.error(f"Failed to rename file: {e}")
                QMessageBox.critical(self, "[ERR] Error", f"Failed to rename file:\n{e}")
    
    def delete_file(self, file_path: Path):
        """Delete a file."""
        reply = QMessageBox.question(
            self, "[!] Delete File",
            f"Are you sure you want to delete '{file_path.name}'?",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            try:
                file_path.unlink()
                
                # Remove from cache
                if str(file_path) in self.tv.durations:
                    del self.tv.durations[str(file_path)]
                    self.tv._save_cache()
                
                # Clear schedule for this channel
                if self.current_channel and self.current_channel in self.tv.schedules:
                    del self.tv.schedules[self.current_channel]
                
                # Refresh
                if self.current_channel:
                    self.load_channel_content(self.current_channel)
                
                self.statusBar().showMessage(f"[OK] Deleted {file_path.name}")
                
            except Exception as e:
                logging.error(f"Failed to delete file: {e}")
                QMessageBox.critical(self, "[ERR] Error", f"Failed to delete file:\n{e}")
    
    def show_file_info(self, file_path: Path):
        """Show detailed file information."""
        try:
            stat = file_path.stat()
            duration_ms = self.tv._get_duration(file_path)
            
            info = f"[FILE] {file_path.name}\n"
            info += f"[PATH] {file_path}\n"
            info += f"[SIZE] {stat.st_size / (1024*1024):.2f} MB\n"
            info += f"[TIME] {ms_to_hms(duration_ms)}\n"
            info += f"[MOD] {datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')}\n"
            
            # Check if subtitles exist
            for ext in SUB_EXTS:
                if file_path.with_suffix(ext).exists():
                    info += f"[SUB] {ext} available\n"
            
            QMessageBox.information(self, "[INFO] File Info", info)
            
        except Exception as e:
            logging.error(f"Failed to get file info: {e}")
            QMessageBox.critical(self, "[ERR] Error", f"Failed to get file info:\n{e}")
    
    def create_new_channel(self):
        """Create a new channel."""
        name, ok = QInputDialog.getText(
            self, "[+] New Channel",
            "Channel name:", QLineEdit.Normal
        )
        
        if ok and name:
            try:
                channel_path = ROOT_CHANNELS / name
                if channel_path.exists():
                    QMessageBox.warning(self, "[ERR] Error", "A channel with that name already exists.")
                    return
                
                # Create channel structure
                channel_path.mkdir()
                (channel_path / "Shows").mkdir()
                (channel_path / "Commercials").mkdir()
                
                # Refresh
                self.refresh_content()
                
                self.statusBar().showMessage(f"[OK] Created channel: {name}")
                
            except Exception as e:
                logging.error(f"Failed to create channel: {e}")
                QMessageBox.critical(self, "[ERR] Error", f"Failed to create channel:\n{e}")
    
    def rename_channel(self, channel: Path):
        """Rename a channel."""
        current_name = channel.name
        new_name, ok = QInputDialog.getText(
            self, "[REN] Rename Channel",
            "New name:", QLineEdit.Normal,
            current_name
        )
        
        if ok and new_name and new_name != current_name:
            try:
                new_path = channel.parent / new_name
                if new_path.exists():
                    QMessageBox.warning(self, "[ERR] Error", "A channel with that name already exists.")
                    return
                
                channel.rename(new_path)
                
                # Update TV player's channel list
                self.tv.reload_channels()
                
                # Refresh
                self.refresh_content()
                
                self.statusBar().showMessage(f"[OK] Renamed channel to {new_name}")
                
            except Exception as e:
                logging.error(f"Failed to rename channel: {e}")
                QMessageBox.critical(self, "[ERR] Error", f"Failed to rename channel:\n{e}")
    
    def delete_channel(self, channel: Path):
        """Delete a channel."""
        # Count files
        file_count = len(list(channel.rglob("*")))
        
        reply = QMessageBox.question(
            self, "[!] Delete Channel",
            f"Are you sure you want to delete '{channel.name}'?\n"
            f"This will delete {file_count} files and cannot be undone.",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            try:
                shutil.rmtree(channel)
                
                # Clear from cache
                for file in channel.rglob("*"):
                    if str(file) in self.tv.durations:
                        del self.tv.durations[str(file)]
                self.tv._save_cache()
                
                # Update TV player
                self.tv.reload_channels()
                
                # Refresh
                self.refresh_content()
                self.content_tree.clear()
                
                self.statusBar().showMessage(f"[OK] Deleted channel: {channel.name}")
                
            except Exception as e:
                logging.error(f"Failed to delete channel: {e}")
                QMessageBox.critical(self, "[ERR] Error", f"Failed to delete channel:\n{e}")
    
    def import_files(self):
        """Import video files to a channel."""
        if not self.current_channel:
            QMessageBox.warning(self, "[!] No Selection", "Please select a channel first.")
            return
        
        files, _ = QFileDialog.getOpenFileNames(
            self, "[IMP] Import Video Files", "",
            f"Video Files (*{' *'.join(VIDEO_EXTS)})"
        )
        
        if files:
            # Compact dialog for import location
            reply = QMessageBox(self)
            reply.setWindowTitle("[?] Import Location")
            reply.setText(f"Import to {self.current_channel.name}:")
            shows_btn = reply.addButton("[S] Shows", QMessageBox.YesRole)
            ads_btn = reply.addButton("[C] Commercials", QMessageBox.NoRole)
            cancel_btn = reply.addButton("[X] Cancel", QMessageBox.RejectRole)
            
            result = reply.exec_()
            if result == 0:  # Shows
                target_dir = self.current_channel / "Shows"
            elif result == 1:  # Commercials
                target_dir = self.current_channel / "Commercials"
            else:
                return
            
            # Import files
            imported = 0
            for file_path in files:
                try:
                    source = Path(file_path)
                    target = target_dir / source.name
                    
                    if target.exists():
                        reply = QMessageBox.question(self, "[!] File Exists",
                            f"'{source.name}' exists. Overwrite?")
                        if reply != QMessageBox.Yes:
                            continue
                    
                    shutil.copy2(source, target)
                    imported += 1
                    
                except Exception as e:
                    logging.error(f"Import failed for {file_path}: {e}")
            
            # Clear schedule and refresh
            if self.current_channel in self.tv.schedules:
                del self.tv.schedules[self.current_channel]
            
            self.load_channel_content(self.current_channel)
            self.statusBar().showMessage(f"[OK] Imported {imported} of {len(files)} files")
    
    def _open_in_file_manager(self, path: Path):
        """Open a path in the system file manager."""
        open_in_file_manager(path)

# ───────────── Saved Channels Editor ─────────────
class SavedChannelsDialog(QDialog):
    """Manage saved channel folder list."""

    def __init__(self, tv: 'TVPlayer', parent=None):
        super().__init__(parent)
        self.tv = tv
        self.setWindowTitle("[CFG] Saved Channel Folders")
        self.resize(500, 300)

        self.setStyleSheet(
            "QDialog {background:#000;color:#00ff00;}"
            "QPushButton {background:#001100;color:#00ff00;border:2px solid #00ff00;padding:6px;font-weight:bold;}"
            "QPushButton:hover {background:#003300;}"
            "QListWidget {background:#001100;color:#00ff00;border:2px solid #00ff00;}"
        )

        layout = QVBoxLayout(self)
        self.list_widget = QListWidget()
        layout.addWidget(self.list_widget)

        btn_row = QHBoxLayout()
        add_btn = QPushButton("[ADD]")
        remove_btn = QPushButton("[DEL]")
        set_btn = QPushButton("[SET ACTIVE]")
        btn_row.addWidget(add_btn)
        btn_row.addWidget(remove_btn)
        btn_row.addWidget(set_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        close_btn = QPushButton("[CLOSE]")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

        add_btn.clicked.connect(self.add_folder)
        remove_btn.clicked.connect(self.remove_selected)
        set_btn.clicked.connect(self.activate_selected)

        self.refresh_list()

    def refresh_list(self):
        self.list_widget.clear()
        for path in self.tv.settings.get("recent_channels", []):
            self.list_widget.addItem(QListWidgetItem(path))

    def add_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "[ADD] Channel Folder", str(ROOT_CHANNELS.parent))
        if folder:
            recents = self.tv.settings.get("recent_channels", [])
            if folder not in recents:
                recents.insert(0, folder)
                self.tv.settings["recent_channels"] = recents[:5]
                self.tv._save_settings()
                self.refresh_list()
                self.tv._populate_recent_menu()

    def remove_selected(self):
        item = self.list_widget.currentItem()
        if item:
            path = item.text()
            recents = self.tv.settings.get("recent_channels", [])
            if path in recents:
                recents.remove(path)
                self.tv.settings["recent_channels"] = recents
                self.tv._save_settings()
                self.refresh_list()
                self.tv._populate_recent_menu()

    def activate_selected(self):
        item = self.list_widget.currentItem()
        if item:
            self.tv.load_channels_folder(item.text())
            self.accept()

# ───────────── Guide widget ─────────────
class GuideWidget(QWidget):
    """12-hour TV guide with proper time slots and WIP panel."""
    HOURS = GUIDE_HOURS_AHEAD
    SLOTS_PER_HOUR = 4
    TOTAL_SLOTS = HOURS * SLOTS_PER_HOUR
    SLOT_MS = TIME_SLOT_MS
    
    COLORS = [
        QColor("#00ff00"), QColor("#39ff14"), QColor("#00cc00"), QColor("#33ff33"),
        QColor("#66ff66"), QColor("#00ff44"), QColor("#44ff44"), QColor("#00ff88"),
        QColor("#88ff88"), QColor("#00ffaa"), QColor("#aaffaa"), QColor("#00ffcc"),
        QColor("#ccffcc"), QColor("#00ff00"), QColor("#33ff00"), QColor("#66ff00")
    ]

    def __init__(self, tv: 'TVPlayer'):
        super().__init__(tv)
        self.tv = tv
        self.setObjectName("tvguide")
        
        # Apply Matrix theme
        self.setStyleSheet("""
            QWidget {
                background-color: #000000;
                color: #00ff00;
            }
            QGroupBox {
                font-weight: bold;
                font-size: 14px;
                color: #00ff00;
                border: 2px solid #00ff00;
                border-radius: 6px;
                margin-top: 6px;
                padding: 10px;
                background: rgba(0, 255, 0, 0.05);
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
            QLabel {
                color: #00ff00;
            }
            QTableWidget {
                background: #001100;
                color: #00ff00;
                font: 11px "Consolas", monospace;
                gridline-color: #003300;
                selection-background-color: #00ff00;
                selection-color: #000000;
                border: 2px solid #00ff00;
            }
            QTableWidget::item {
                padding: 4px;
                border: 1px solid #003300;
                background-clip: padding;
            }
            QHeaderView::section {
                background: #002200;
                color: #00ff00;
                font-weight: bold;
                padding: 6px;
                border: 1px solid #00ff00;
            }
            QMenu {
                background-color: #001100;
                color: #00ff00;
                border: 2px solid #00ff00;
            }
            QMenu::item:selected {
                background-color: #003300;
            }
        """)
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(5)

        header = QHBoxLayout()
        header.addStretch()
        self.remote_label = QLabel("REMOTE: ?")
        self.net_label = QLabel("NET: ?")
        header.addWidget(self.remote_label)
        header.addWidget(self.net_label)
        # panel showing system time and weather
        self.info_box = QGroupBox()
        info_layout = QVBoxLayout(self.info_box)
        info_layout.setContentsMargins(5, 5, 5, 5)
        info_layout.setSpacing(2)
        self.time_label = QLabel()
        self.weather_label = QLabel("Weather: ...")
        self.refresh_label = QLabel("<u>refresh</u>")
        self.refresh_label.setCursor(Qt.PointingHandCursor)
        self.refresh_label.mousePressEvent = lambda e: self.update_weather()
        info_layout.addWidget(self.time_label, alignment=Qt.AlignCenter)
        info_layout.addWidget(self.weather_label, alignment=Qt.AlignCenter)
        info_layout.addWidget(self.refresh_label, alignment=Qt.AlignRight)
        self.info_box.mousePressEvent = lambda e: self.show_weather_dialog()
        header.addWidget(self.info_box)
        main_layout.addLayout(header)
        
        # WIP Panel - Enhanced version
        wip_panel = QGroupBox("[NEXT] Upcoming Shows")
        wip_layout = QVBoxLayout(wip_panel)
        self.upcoming_label = QLabel("Loading upcoming shows...")
        self.upcoming_label.setStyleSheet("color: #00ff00; font-size: 12px; padding: 5px; line-height: 1.5;")
        self.upcoming_label.setWordWrap(True)
        wip_layout.addWidget(self.upcoming_label)
        main_layout.addWidget(wip_panel)
        
        # Create table
        self.table = QTableWidget(0, self.TOTAL_SLOTS + 1)
        
        # Headers
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Fixed)
        self.base_col_size = 120
        self.table.horizontalHeader().setDefaultSectionSize(self.base_col_size)
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)
        self.base_row_size = 60  # larger rows for bigger icons
        self.table.verticalHeader().setDefaultSectionSize(self.base_row_size)
        self.base_icon_size = 48
        self.table.setIconSize(QSize(self.base_icon_size, self.base_icon_size))

        self.zoom_level = 0
        self.max_zoom_level = 3
        self._apply_zoom()

        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.cellClicked.connect(self._on_cell_clicked)
        
        # Enable right-click
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        
        main_layout.addWidget(self.table, 1)
        
        # Timers
        self.upcoming_timer = QTimer(self)
        self.upcoming_timer.timeout.connect(self._update_upcoming_shows)
        self.upcoming_timer.start(30000)  # 30 seconds
        
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.refresh)
        self.refresh_timer.start(15 * 60 * 1000)  # 15 minutes

        self.now_playing_timer = QTimer(self)
        self.now_playing_timer.timeout.connect(self._update_now_playing)
        self.now_playing_timer.start(60000)  # 1 minute

        # timers for time/weather panel
        self.time_timer = QTimer(self)
        self.time_timer.timeout.connect(self._update_time)
        self.time_timer.start(60000)

        self.weather_timer = QTimer(self)
        self.weather_timer.timeout.connect(self.update_weather)
        self.weather_timer.start(3 * 60 * 60 * 1000)

        self._update_time()
        self.update_weather()

    def update_status_indicators(self):
        """Update remote and internet status indicators."""
        remote_ok = self.tv.flask_manager.is_running
        remote_color = "#00ff00" if remote_ok else "#ff0000"
        self.remote_label.setText("REMOTE" + (" OK" if remote_ok else " OFF"))
        self.remote_label.setStyleSheet(f"color: {remote_color}")

        connected = self._has_net()
        net_color = "#00ff00" if connected else "#ff0000"
        self.net_label.setText("NET" + (" OK" if connected else " OFF"))
        self.net_label.setStyleSheet(f"color: {net_color}")

    def _apply_zoom(self):
        """Apply zoom settings to table headers and icons."""
        scale = 1 + self.zoom_level * 0.25
        self.table.horizontalHeader().setDefaultSectionSize(int(self.base_col_size * scale))
        self.table.verticalHeader().setDefaultSectionSize(int(self.base_row_size * scale))
        size = int(self.base_icon_size * scale)
        self.table.setIconSize(QSize(size, size))

    def zoom_in(self):
        """Increase guide zoom level."""
        if self.zoom_level < self.max_zoom_level:
            self.zoom_level += 1
            self.tv._show_loading("Zooming...")
            self._apply_zoom()
            self.refresh()
            self.tv._hide_loading()

    def zoom_out(self):
        """Decrease guide zoom level (not below default)."""
        if self.zoom_level > 0:
            self.zoom_level -= 1
            self.tv._show_loading("Zooming...")
            self._apply_zoom()
            self.refresh()
            self.tv._hide_loading()
        
    def refresh(self):
        """Refresh the 12-hour TV guide."""
        if not self.tv.channels_real:
            return
            
        self.table.setRowCount(len(self.tv.channels_real))
        
        # Calculate time slots
        now = datetime.now().replace(second=0, microsecond=0)
        minutes = (now.minute // 15) * 15
        start_time = now.replace(minute=minutes)
        
        # Set headers
        self.table.setHorizontalHeaderItem(0, QTableWidgetItem("Channel"))
        for slot in range(self.TOTAL_SLOTS):
            time_slot = start_time + timedelta(minutes=15 * slot)
            header_text = time_slot.strftime("%H:%M")
            if slot % 4 == 0:  # Hour boundaries
                header_text = time_slot.strftime("%H:%M\n%a")
            self.table.setHorizontalHeaderItem(slot + 1, QTableWidgetItem(header_text))
        
        # Clear all cells and spans
        self.table.clearContents()
        for row in range(self.table.rowCount()):
            for col in range(self.table.columnCount()):
                self.table.setSpan(row, col, 1, 1)
        
        # Fill channel data
        for row, channel in enumerate(self.tv.channels_real):
            # Channel name with logo
            channel_item = QTableWidgetItem(f"[{row+1:02d}] {channel.name}")
            logo = self.tv.channel_logo.get(channel)
            if logo:
                channel_item.setIcon(QIcon(logo))
            channel_item.setData(Qt.UserRole, {'channel': channel})
            self.table.setItem(row, 0, channel_item)
            
            # Get schedule
            schedule = self.tv.get_schedule_for_guide(channel, start_time, self.HOURS)
            self._fill_schedule_row(row, schedule, start_time)
        
        self._update_upcoming_shows()
    
    def _fill_schedule_row(self, row: int, schedule: List, start_time: datetime):
        """Fill a row with scheduled programs."""
        occupied_cols = set()
        show_colors = {}
        color_index = 0
        now = datetime.now()
        
        for program_start, program_path, duration_ms, is_ad in schedule:
            # Parse JSON for ad segments
            try:
                segment_data = json.loads(program_path)
                program_path = segment_data['path']
            except (json.JSONDecodeError, TypeError):
                pass
                
            # Calculate positions
            start_offset_ms = (program_start - start_time).total_seconds() * 1000
            end_offset_ms = start_offset_ms + duration_ms
            
            # Check if currently playing
            program_end = program_start + timedelta(milliseconds=duration_ms)
            is_current = program_start <= now < program_end
            
            # Convert to columns
            start_col = int(start_offset_ms / self.SLOT_MS) + 1
            end_col = int(end_offset_ms / self.SLOT_MS) + 1
            
            # Boundary checks
            if start_col < 1:
                start_col = 1
            if start_col > self.TOTAL_SLOTS or start_col >= end_col:
                continue
            if end_col > self.TOTAL_SLOTS + 1:
                end_col = self.TOTAL_SLOTS + 1
                
            # Find available space
            while start_col in occupied_cols and start_col < end_col:
                start_col += 1
            
            if start_col >= end_col:
                continue
                
            # Calculate span
            span = end_col - start_col
            for col in range(start_col, min(start_col + span, self.TOTAL_SLOTS + 1)):
                if col in occupied_cols:
                    span = col - start_col
                    break
            
            if span <= 0:
                continue
            
            # Mark occupied
            for col in range(start_col, start_col + span):
                occupied_cols.add(col)
            
            # Create cell
            display_name = "[AD] ADS" if is_ad else format_show_name(Path(program_path))
            duration_mins = duration_ms // 60000
            
            if duration_mins > 0:
                if is_ad:
                    display_name = f"[AD] AD BREAK\n({duration_mins}m)"
                else:
                    display_name += f"\n({duration_mins}m)"
            
            if is_current:
                display_name = f"[>] {display_name}"
            
            cell = QTableWidgetItem(display_name)
            cell.setData(Qt.UserRole, {
                'path': str(Path(program_path)),
                'start': program_start,
                'duration': duration_ms,
                'channel': self.tv.channels_real[row],
                'is_ad': is_ad
            })
            
            # Colors
            if is_ad:
                cell.setBackground(QColor("#ff4444" if is_current else "#cc0000"))
                cell.setForeground(QColor("#ff0000") if is_current else QColor("#ffffff"))
            else:
                show_key = Path(program_path).stem
                if show_key not in show_colors:
                    show_colors[show_key] = self.COLORS[color_index % len(self.COLORS)]
                    color_index += 1

                base_color = show_colors[show_key]
                if is_current:
                    cell.setBackground(base_color)
                    cell.setForeground(QColor("#ff0000"))
                else:
                    cell.setBackground(base_color.darker(150))
                    cell.setForeground(QColor("#ffffff"))
            
            if is_current:
                font = cell.font()
                font.setBold(True)
                cell.setFont(font)
            
            cell.setTextAlignment(Qt.AlignCenter)
            
            # Place item and span
            if start_col < self.table.columnCount():
                self.table.setItem(row, start_col, cell)
                if span > 1:  # Only set span if greater than 1
                    self.table.setSpan(row, start_col, 1, span)
    
    def _on_cell_clicked(self, row: int, col: int):
        """Handle cell clicks."""
        if col == 0:
            item = self.table.item(row, col)
            if item and item.data(Qt.UserRole):
                data = item.data(Qt.UserRole)
                channel = data.get('channel')
                if channel:
                    self._jump_to_channel(channel)
            return
            
        item = self.table.item(row, col)
        if item and item.data(Qt.UserRole):
            data = item.data(Qt.UserRole)
            program_name = format_show_name(Path(data['path']))
            start_time = data['start']
            duration = ms_to_hms(data['duration'])
            
            info_text = (
                f"<b>{program_name}</b><br>"
                f"Start: {start_time.strftime('%a %H:%M')}<br>"
                f"Duration: {duration}<br>"
                f"Channel: {data['channel'].name}"
            )

            dialog = QDialog(self)
            dialog.setWindowTitle("[INFO] Program Info")
            dlg_layout = QVBoxLayout(dialog)

            logo = self.tv.channel_logo.get(data['channel'])
            if logo:
                icon_lbl = QLabel()
                icon_lbl.setPixmap(QPixmap(logo).scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                icon_lbl.setAlignment(Qt.AlignCenter)
                dlg_layout.addWidget(icon_lbl)

            lbl = QLabel(info_text)
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet("font-size: 16px;")
            dlg_layout.addWidget(lbl)

            btn_row = QHBoxLayout()
            watch_btn = QPushButton("[WATCH]")
            watch_btn.clicked.connect(lambda: (dialog.accept(), self._jump_to_show(data)))
            open_btn = QPushButton("[OPEN]")
            open_btn.clicked.connect(lambda: open_in_file_manager(Path(data['path']).parent))
            close_btn = QPushButton("[OK]")
            close_btn.clicked.connect(dialog.accept)
            btn_row.addWidget(watch_btn)
            btn_row.addWidget(open_btn)
            btn_row.addWidget(close_btn)
            dlg_layout.addLayout(btn_row)

            dialog.exec_()
    
    def _show_context_menu(self, position):
        """Show right-click context menu."""
        item = self.table.itemAt(position)
        if not item or not item.data(Qt.UserRole):
            return

        data = item.data(Qt.UserRole)

        menu = QMenu(self)

        if 'channel' in data:
            menu.addAction("[TV] Jump to Channel", lambda: self._jump_to_channel(data['channel']))
        elif not data.get('is_ad'):
            jump_action = menu.addAction("[TV] Jump to Show")
            jump_action.triggered.connect(lambda: self._jump_to_show(data))

        if menu.actions():
            menu.exec_(self.table.mapToGlobal(position))
    
    def _jump_to_show(self, data):
        """Jump to a specific show on a channel."""
        channel = data['channel']
        start_time = data['start']
        
        channel_idx = self.tv.channels_real.index(channel) + 2
        delta = channel_idx - self.tv.ch_idx
        self.tv.change_channel(delta)
        
        now = datetime.now()
        if start_time > now:
            time_until = start_time - now
            hours = int(time_until.total_seconds() // 3600)
            minutes = int((time_until.total_seconds() % 3600) // 60)
            
            if hours > 0:
                self.tv._osd(f"Show starts in {hours}h {minutes}m")
            else:
                self.tv._osd(f"Show starts in {minutes} minutes")
        else:
            self.tv._osd("Jumped to channel - show in progress")

    def _jump_to_channel(self, channel: Path):
        """Switch directly to the given channel."""
        if channel in self.tv.channels_real:
            channel_idx = self.tv.channels_real.index(channel) + 2
            delta = channel_idx - self.tv.ch_idx
            self.tv.change_channel(delta)
    
    def _update_upcoming_shows(self):
        """Update the upcoming shows display."""
        if not self.tv.channels_real:
            return
            
        upcoming = []
        now = datetime.now()
        
        for channel in self.tv.channels_real:
            schedule = self.tv.get_schedule_for_guide(channel, now, 6)
            
            for start_time, program_path, duration_ms, is_ad in schedule:
                if is_ad or start_time <= now:
                    continue
                    
                upcoming.append({
                    'channel': channel,
                    'show': format_show_name(Path(program_path)),
                    'start': start_time,
                    'path': program_path
                })
        
        upcoming.sort(key=lambda x: x['start'])
        
        # Pick 5 random upcoming shows
        display_shows = random.sample(upcoming, min(5, len(upcoming))) if upcoming else []
        display_shows.sort(key=lambda x: x['start'])
        
        if display_shows:
            text_lines = []
            for show in display_shows:
                time_str = show['start'].strftime('%a %H:%M')
                channel_name = show['channel'].name
                show_name = show['show']
                
                time_until = show['start'] - now
                hours = int(time_until.total_seconds() // 3600)
                minutes = int((time_until.total_seconds() % 3600) // 60)
                
                when = f"in {hours}h {minutes}m" if hours > 0 else f"in {minutes}m"
                text_lines.append(f"[TV] <b>{show_name}</b> - {channel_name} - {time_str} ({when})")
            
            self.upcoming_label.setText("<br>".join(text_lines))
        else:
            self.upcoming_label.setText("No upcoming shows found")
    
    def _update_now_playing(self):
        """Update the guide to refresh 'now playing' indicators."""
        self.refresh()

    # ---- Time and weather panel helpers ----
    def _update_time(self):
        """Update the current time display."""
        self.time_label.setText(datetime.now().strftime('%a %H:%M'))

    def update_weather(self):
        """Fetch weather info if internet is available."""
        self.weather_label.setText('Loading weather...')
        if not self._has_net():
            self.weather_label.setText('Weather: N/A')
            self.weather_data = None
            return
        try:
            import requests
            res = requests.get('https://wttr.in/?format=j1', timeout=5)
            data = res.json()
            cur = data['current_condition'][0]
            temp = cur['temp_C']
            desc = cur['weatherDesc'][0]['value']
            self.weather_label.setText(f"{temp}\u00B0C {desc}")
            self.weather_data = data['weather'][0]
        except Exception:
            self.weather_label.setText('Weather: N/A')
            self.weather_data = None

    def show_weather_dialog(self):
        """Display a dialog with today's detailed weather."""
        if not getattr(self, 'weather_data', None):
            return
        day = self.weather_data
        astronomy = day.get('astronomy', [{}])[0]
        text = (
            f"Max: {day.get('maxtempC')}\u00B0C\n"
            f"Min: {day.get('mintempC')}\u00B0C\n"
            f"Sunrise: {astronomy.get('sunrise','?')}\n"
            f"Sunset: {astronomy.get('sunset','?')}"
        )
        dlg = QDialog(self)
        dlg.setWindowTitle('[WEATHER] Today')
        l = QVBoxLayout(dlg)
        l.addWidget(QLabel(text))
        close_btn = QPushButton('[OK]')
        close_btn.clicked.connect(dlg.accept)
        l.addWidget(close_btn, alignment=Qt.AlignCenter)
        dlg.exec_()

    def _has_net(self) -> bool:
        try:
            socket.create_connection(('8.8.8.8', 53), timeout=2).close()
            return True
        except Exception:
            return False

# ───────────── On Demand widget ─────────────
class OnDemandWidget(QWidget):
    """OnDemand channel for browsing and selecting shows."""
    
    def __init__(self, tv: 'TVPlayer'):
        super().__init__(tv)
        self.tv = tv
        self.setObjectName("ondemand")
        self.current_selection = None
        
        # Apply Matrix theme
        self.setStyleSheet("""
            QWidget {
                background-color: #000000;
                color: #00ff00;
            }
            QLabel {
                color: #00ff00;
            }
            QLineEdit {
                background-color: #001100;
                color: #00ff00;
                border: 2px solid #00ff00;
                border-radius: 6px;
                padding: 8px;
                font-size: 14px;
            }
            QLineEdit:focus {
                border-color: #39ff14;
                background-color: #002200;
            }
            QCheckBox {
                color: #00ff00;
                font-weight: bold;
                spacing: 5px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border: 2px solid #00ff00;
                background-color: #001100;
                border-radius: 3px;
            }
            QCheckBox::indicator:checked {
                background-color: #00ff00;
            }
            QTreeWidget {
                background-color: #001100;
                color: #00ff00;
                border: 2px solid #00ff00;
                border-radius: 6px;
                font-size: 12px;
                selection-background-color: #00ff00;
                selection-color: #000000;
            }
            QTreeWidget::item {
                padding: 6px;
                border-bottom: 1px solid #003300;
            }
            QTreeWidget::item:selected {
                background-color: #00ff00;
                color: #000000;
            }
            QTreeWidget::item:hover {
                background-color: #003300;
            }
            QHeaderView::section {
                background-color: #002200;
                color: #00ff00;
                padding: 8px;
                border: 1px solid #00ff00;
                font-weight: bold;
            }
            QPushButton {
                background-color: #001100;
                color: #00ff00;
                border: 2px solid #00ff00;
                border-radius: 8px;
                padding: 12px 24px;
                font-size: 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #003300;
                border-color: #39ff14;
            }
            QPushButton:pressed {
                background-color: #004400;
            }
            QPushButton:disabled {
                background-color: #000000;
                color: #003300;
                border-color: #003300;
            }
        """)
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)
        
        # Header
        header_layout = QHBoxLayout()
        title_label = QLabel("[TV] ONDEMAND - Browse & Play")
        title_label.setStyleSheet("""
            font-size: 24px; 
            font-weight: bold; 
            color: #00ff00;
            padding: 10px;
            text-shadow: 0 0 10px #39ff14;
        """)
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        
        # Search and filters
        search_layout = QHBoxLayout()
        search_label = QLabel("[SEARCH] Search:")
        search_label.setStyleSheet("color: #00ff00; font-weight: bold;")
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search shows...")
        self.search_box.textChanged.connect(self.filter_content)
        
        search_layout.addWidget(search_label)
        search_layout.addWidget(self.search_box, 1)
        
        # Filter checkboxes
        self.include_commercials = QCheckBox("Include Commercials")
        self.include_commercials.setChecked(False)
        self.include_commercials.stateChanged.connect(self.filter_content)
        
        search_layout.addWidget(self.include_commercials)
        
        main_layout.addLayout(header_layout)
        main_layout.addLayout(search_layout)
        
        # Content list
        self.content_list = QTreeWidget()
        self.content_list.setHeaderLabels(["Title", "Channel", "Duration", "Type"])
        self.content_list.setSortingEnabled(True)
        self.content_list.setAlternatingRowColors(True)
        self.content_list.setSelectionMode(QTreeWidget.SingleSelection)
        self.content_list.itemSelectionChanged.connect(self.on_selection_changed)
        self.content_list.itemDoubleClicked.connect(self.play_selected)
        
        # Set column widths
        self.content_list.setColumnWidth(0, 400)  # Title
        self.content_list.setColumnWidth(1, 150)  # Channel
        self.content_list.setColumnWidth(2, 100)  # Duration
        self.content_list.setColumnWidth(3, 100)  # Type
        
        main_layout.addWidget(self.content_list, 1)
        
        # Bottom controls
        controls_layout = QHBoxLayout()
        
        # Info panel
        self.info_panel = QLabel("Select a show to see details")
        self.info_panel.setStyleSheet("""
            background-color: rgba(0, 255, 0, 0.1);
            color: #00ff00;
            padding: 10px;
            border: 2px solid #00ff00;
            border-radius: 6px;
            font-size: 12px;
        """)
        self.info_panel.setWordWrap(True)
        self.info_panel.setMaximumHeight(80)
        
        controls_layout.addWidget(self.info_panel, 1)
        
        # Play button
        self.play_button = QPushButton("[>] PLAY NOW")
        self.play_button.setEnabled(False)
        self.play_button.clicked.connect(self.play_selected)
        self.play_button.setMinimumWidth(150)
        
        controls_layout.addWidget(self.play_button)
        
        main_layout.addLayout(controls_layout)
        
        # Initialize content
        self.refresh_content()
    
    def refresh_content(self):
        """Refresh the content list from all channels."""
        self.content_list.clear()
        
        for channel in self.tv.channels_real:
            self._load_channel_content(channel)
        
        self.filter_content()
    
    def _load_channel_content(self, channel: Path):
        """Load content from a specific channel."""
        # Load shows
        shows_dir = channel / "Shows"
        if shows_dir.exists():
            for show_file in gather_files(shows_dir):
                self._add_content_item(show_file, channel, "Show")
        
        # Load commercials if enabled
        if self.include_commercials.isChecked():
            commercials_dir = channel / "Commercials" 
            if commercials_dir.exists():
                for commercial_file in gather_files(commercials_dir):
                    self._add_content_item(commercial_file, channel, "Commercial")
    
    def _add_content_item(self, file_path: Path, channel: Path, content_type: str):
        """Add a content item to the list."""
        item = QTreeWidgetItem(self.content_list)
        
        # Format title
        title = format_show_name(file_path)
        item.setText(0, title)
        item.setText(1, channel.name)
        
        # Duration
        duration_ms = self.tv._get_duration(file_path)
        item.setText(2, ms_to_hms(duration_ms))
        item.setData(2, Qt.UserRole, duration_ms)
        
        item.setText(3, content_type)
        
        # Store file path
        item.setData(0, Qt.UserRole, file_path)
        
        # Color coding
        if content_type == "Commercial":
            for col in range(4):
                item.setForeground(col, QColor("#ff4444"))
        else:
            for col in range(4):
                item.setForeground(col, QColor("#00ff00"))
    
    def filter_content(self):
        """Filter content based on search and checkbox."""
        search_text = self.search_box.text().lower()
        include_commercials = self.include_commercials.isChecked()
        
        # Clear and reload
        self.content_list.clear()
        
        for channel in self.tv.channels_real:
            # Always load shows
            shows_dir = channel / "Shows"
            if shows_dir.exists():
                for show_file in gather_files(shows_dir):
                    title = format_show_name(show_file).lower()
                    channel_name = channel.name.lower()
                    if not search_text or search_text in title or search_text in channel_name:
                        self._add_content_item(show_file, channel, "Show")
            
            # Load commercials if enabled
            if include_commercials:
                commercials_dir = channel / "Commercials"
                if commercials_dir.exists():
                    for commercial_file in gather_files(commercials_dir):
                        title = format_show_name(commercial_file).lower()
                        channel_name = channel.name.lower()
                        if not search_text or search_text in title or search_text in channel_name:
                            self._add_content_item(commercial_file, channel, "Commercial")
    
    def on_selection_changed(self):
        """Handle selection change."""
        selected_items = self.content_list.selectedItems()
        if selected_items:
            item = selected_items[0]
            file_path = item.data(0, Qt.UserRole)
            
            if file_path:
                self.current_selection = file_path
                self.play_button.setEnabled(True)
                
                # Update info panel
                channel_name = item.text(1)
                duration = item.text(2)
                content_type = item.text(3)
                title = item.text(0)
                
                info_text = f"[SHOW] {title}\n"
                info_text += f"[TV] Channel: {channel_name} | [TIME] Duration: {duration} | [TYPE] Type: {content_type}"
                
                self.info_panel.setText(info_text)
        else:
            self.current_selection = None
            self.play_button.setEnabled(False)
            self.info_panel.setText("Select a show to see details")
    
    def play_selected(self):
        """Play the selected content."""
        if self.current_selection:
            # Set the OnDemand channel to play this content
            self.tv._start_ondemand_playback(self.current_selection)
            # Switch to the live view
            self.tv.stack.setCurrentIndex(0)
            self.tv._osd(f"Now Playing: {format_show_name(self.current_selection)}")

# ───────────── Remote widgets ─────────────
class Remote(QWidget):
    """Matrix-inspired floating remote control with improved layout."""
    def __init__(self, tv: 'TVPlayer'):
        super().__init__(None, Qt.Tool | Qt.WindowStaysOnTopHint)
        self.setWindowTitle("[REM] TV Remote")
        self.setFixedSize(340, 220)

        # Matrix CSS
        self.setStyleSheet("""
            QWidget { background-color: #000000; border: 2px solid #00ff00; }
            QPushButton {
                color: #00ff00;
                font-family: "Consolas", monospace;
                font-size: 18px;
                font-weight: bold;
                min-width: 72px;
                min-height: 48px;
                background-color: #001100;
                border: 2px solid #00ff00;
                border-radius: 8px;
                margin: 4px;
            }
            QPushButton:hover {
                background-color: #002200;
                border-color: #39ff14;
            }
            QPushButton:pressed {
                background-color: #003300;
                border-color: #66ff66;
            }
        """)

        # layout: 3 rows × 4 columns (reorganised for a more logical flow)
        grid = QGridLayout(self)
        grid.setSpacing(6)

        # Row 0 - navigation controls
        grid.addWidget(self._btn("HOME",     tv.go_guide),         0, 0)
        grid.addWidget(self._btn("GUIDE",    tv.go_guide),         0, 1)
        grid.addWidget(self._btn("INFO",     tv.toggle_info),      0, 2)
        grid.addWidget(self._btn("DEMAND",   tv.go_ondemand),      0, 3)

        # Row 1 - channel / playback controls
        grid.addWidget(self._btn("CH UP",    lambda: tv.change_channel(1)), 1, 0)
        grid.addWidget(self._btn("PLAY",     tv.toggle_play),      1, 1)
        grid.addWidget(self._btn("MUTE",     tv.mute),             1, 2)
        grid.addWidget(self._btn("CH DN",    lambda: tv.change_channel(-1)),1, 3)

        # Row 2 - volume and misc controls
        grid.addWidget(self._btn("VOL-",     tv.vol_down),         2, 0)
        grid.addWidget(self._btn("LAST",     tv.go_last_channel),  2, 1)
        grid.addWidget(self._btn("VOL+",     tv.vol_up),           2, 2)
        grid.addWidget(self._btn("FULL",     tv.toggle_fs),        2, 3)

        # optional neon drop-shadow for extra flair
        glow = QColor(0, 255, 0)
        for btn in self.findChildren(QPushButton):
            effect = QGraphicsDropShadowEffect()
            effect.setBlurRadius(12)
            effect.setColor(glow)
            effect.setOffset(0, 0)
            btn.setGraphicsEffect(effect)

    # helper to create buttons
    def _btn(self, text: str, slot):
        b = QPushButton(text, clicked=slot)
        b.setCursor(Qt.PointingHandCursor)
        return b

class DevRemote(QWidget):
    def __init__(self, tv: 'TVPlayer'):
        super().__init__(None, Qt.Tool | Qt.WindowStaysOnTopHint)
        self.setWindowTitle("[DEV] Developer Remote")
        self.setStyleSheet("""
            QWidget { background: #000000; border: 2px solid #00ff00; }
            QPushButton { 
                color: #00ff00; 
                font-size: 14px;
                min-width: 70px; 
                min-height: 35px;
                background: #001100;
                border: 2px solid #00ff00;
                border-radius: 4px;
                margin: 1px;
            }
            QPushButton:hover { background: #003300; border-color: #39ff14; }
        """)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        
        buttons = [
            ("PLAY", tv.player.play),
            ("PAUSE", tv.player.pause),
            ("PREV", lambda: tv.change_video(-1)),
            ("NEXT", lambda: tv.change_video(1)),
            ("Debug", lambda: tv.console.show()),
            ("Reload", tv.reload_schedule)
        ]
        
        for text, func in buttons:
            layout.addWidget(QPushButton(text, clicked=func))
            
        self.setFixedHeight(50)

class CursorController(QObject):
    """Simple cursor controller for remote navigation."""
    def __init__(self, tv: 'TVPlayer'):
        super().__init__(tv)
        self.tv = tv

    def _send(self, key):
        widget = QApplication.focusWidget()
        if widget:
            press = QKeyEvent(QtCore.QEvent.KeyPress, key, Qt.NoModifier)
            release = QKeyEvent(QtCore.QEvent.KeyRelease, key, Qt.NoModifier)
            QApplication.postEvent(widget, press)
            QApplication.postEvent(widget, release)

    def up(self):
        self._send(Qt.Key_Up)

    def down(self):
        self._send(Qt.Key_Down)

    def left(self):
        self._send(Qt.Key_Left)

    def right(self):
        self._send(Qt.Key_Right)

    def select(self):
        self._send(Qt.Key_Return)

    def back(self):
        """Send an Escape key press to close dialogs or go back."""
        self._send(Qt.Key_Escape)

# ───────────── MAIN TV PLAYER CLASS - ENHANCED AND COMPLETE ─────────────
class TVPlayer(QMainWindow):
    DEFAULT_KEYS = {
        "next_video": "Ctrl+Right", "prev_video": "Ctrl+Left",
        "next_channel": "PageDown", "prev_channel": "PageUp",
        "last_channel": "Ctrl+L", "guide": "G",
        "toggle_fullscreen": "F11", "show_console": "Ctrl+`",
        "toggle_remote": "Tab", "toggle_info": "Ctrl+I",
        "reload_schedule": "Ctrl+R",
        "volume_up": "+", "volume_down": "-", "mute": "M",
        "toggle_subtitles": "S",
        "ondemand": "0",
        "guide_zoom_in": "Ctrl+=",
        "guide_zoom_out": "Ctrl+-"
    }
    
    DEFAULT_SETTINGS = {
        "default_volume": 50,
        "subtitle_size": 24,
        "static_fx": True,
        "min_show_minutes": 5,
        "ad_break_minutes": 3,
        "channels_dir": str(ROOT_CHANNELS),
        "web_port": 5050,
        "cache_file": str(DEFAULT_CACHE_FILE),
        "hotkey_file": str(DEFAULT_HOTKEY_FILE),
        "load_last_folder": True,
        "recent_channels": "[]"
    }

    def __init__(self):
        super().__init__()
        self.setWindowTitle("[TV] Infinite Tv")
        self.resize(1400, 800)
        self._apply_dark_theme()

        # Load settings and cache
        self.settings = self._load_settings()
        self._auto_select_channels_folder()
        self.cache_file = Path(self.settings.get("cache_file", str(DEFAULT_CACHE_FILE)))
        self.hotkey_file = Path(self.settings.get("hotkey_file", str(DEFAULT_HOTKEY_FILE)))
        self.durations = self._load_cache()
        self.last_ch_idx: Optional[int] = None
        # Keep track of last show order per channel to avoid identical
        # shuffles when rebuilding schedules
        self._last_show_order: Dict[Path, List[str]] = {}

        # Global schedule start time - all channels sync to this (midnight today for consistency)
        self.global_schedule_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        self.startup_time = datetime.now()
        logging.info(f"Global schedule start: {self.global_schedule_start}")
        
        # Enhanced remote signal bridge
        self.signal_bridge = RemoteSignalBridge()
        self.signal_bridge.command_received.connect(self.handle_remote_command)
        self.signal_bridge.restart_server_requested.connect(self.restart_web_server)

        # Flask server manager
        self.flask_manager = FlaskServerManager(self)
        self.cursor = CursorController(self)

        # Channel discovery
        self.channels_real = discover_channels(ROOT_CHANNELS)
        self.channels = [None, "OnDemand"] + self.channels_real
        self._rebuild_logos()

        # Load previous shuffle order for each channel if available
        for ch in self.channels_real:
            self._last_show_order[ch] = self._load_last_order(ch)

        # Use default channel icon as application icon
        if self.channels_real:
            logo = self._find_logo(self.channels_real[0])
            if logo:
                icon = QIcon(logo)
                QApplication.instance().setWindowIcon(icon)
                self.setWindowIcon(icon)
        self.ch_idx = 0

        # Enhanced media player setup with better error handling
        self.player = QMediaPlayer(None, QMediaPlayer.VideoSurface)
        self.video = QVideoWidget()
        self.player.setVideoOutput(self.video)
        self.player.setVolume(self.settings["default_volume"])

        # Enhanced playback state tracking
        self.playback_state = {
            'current_program': None,
            'program_start_time': None,
            'segment_info': None,
            'segment_timer': None,
            'last_position': 0,
            'current_schedule_index': -1  # Add this to track schedule position
        }

        # Add OnDemand widget
        self.ondemand = OnDemandWidget(self)

        # Subtitle system
        self.sub_label = QLabel("", self.video, alignment=Qt.AlignHCenter | Qt.AlignBottom)
        self.sub_label.setStyleSheet("""
            color: #00ff00; 
            background: rgba(0,0,0,220); 
            padding: 6px 12px; 
            border-radius: 6px;
            font-weight: bold;
            border: 1px solid #00ff00;
        """)
        self.sub_label.setFont(QFont("Consolas", self.settings["subtitle_size"]))
        self.sub_label.hide()

        # Static effect
        self.static_label = QLabel(self)
        self.static_label.setScaledContents(True)
        self.static_label.hide()
        self.static_movie = QMovie(str(STATIC_GIF)) if STATIC_GIF.exists() else None
        if self.static_movie:
            self.static_label.setMovie(self.static_movie)

        # UI Components
        self.guide = GuideWidget(self)
        self.console = Console(self)
        self.remote = Remote(self)
        self.dev_remote = DevRemote(self)
        self.remote.hide()
        self.dev_remote.hide()

        # Focus highlight for cursor navigation
        self.focus_frame = QFocusFrame(self)
        self.focus_frame.setStyleSheet("QFocusFrame{border:2px solid white;}")
        QApplication.instance().focusChanged.connect(self._on_focus_changed)
        
        # Network Editor
        self.network_editor = NetworkEditor(self)

        # Enhanced logging setup
        console_handler = logging.StreamHandler(self.console)
        console_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        logging.getLogger().addHandler(console_handler)

        # Layout
        self.stack = QStackedLayout()
        self.stack.addWidget(self.video)  # 0 = Video
        self.stack.addWidget(self.guide)  # 1 = Guide
        self.stack.addWidget(self.ondemand)  # 2 = OnDemand
        container = QWidget()
        container.setLayout(self.stack)
        self.setCentralWidget(container)

        # OSD and Info overlays
        self._setup_overlays()

        # Enhanced schedule data with better tracking
        self.schedules: Dict[Path, List] = {}
        self.current_schedule_index: Dict[Path, int] = {}
        
        # Removed schedule timer - now using media end events for progression

        # Playback state
        self.sub_cues = []
        self.sub_enabled = False

        # OnDemand playback state
        self.ondemand_content = None
        self.ondemand_start_time = None

        # Setup UI
        self._build_menu()
        self.hotkeys = self._load_hotkeys()
        self._bind_keys()
        
        # Enhanced player signal connections
        self.player.positionChanged.connect(self._on_position_changed)
        self.player.mediaStatusChanged.connect(self._on_media_status_changed)
        self.player.stateChanged.connect(self._on_player_state_changed)
        self.player.durationChanged.connect(self._on_duration_changed)
        
        # Enhanced error handling
        if hasattr(self.player, 'errorOccurred'):
            self.player.errorOccurred.connect(self._on_player_error)
        elif hasattr(self.player, 'error'):
            self.player.error.connect(lambda: self._on_player_error(self.player.error()))

        # Initialize and start web server
        logging.info("Infinite Tv initialized - %d channels found", len(self.channels_real))
        logging.info("All channels synchronized to: %s", self.global_schedule_start.strftime('%Y-%m-%d %H:%M'))
        
        # Build initial schedules for all channels
        self._show_loading("Building schedules...")
        for i, channel in enumerate(self.channels_real):
            if channel not in self.schedules:
                self.schedules[channel] = self._build_tv_schedule(channel)
                logging.info(
                    "Built schedule for channel %d/%d: %s",
                    i + 1,
                    len(self.channels_real),
                    channel.name,
                )
        self._hide_loading()
        
        QTimer.singleShot(100, lambda: self.change_channel(0))  # Start with guide
        QTimer.singleShot(500, self.show_web_server_info)  # Show IP info after init

    # ── MISSING METHOD IMPLEMENTATIONS ──────────────────────────────────
    def _apply_dark_theme(self):
        """Apply Matrix-style dark theme (black + neon-green)."""
        app = QApplication.instance()
        app.setStyle("Fusion")

        palette = QPalette()

        # core surfaces
        palette.setColor(QPalette.Window,          QColor("#000000"))
        palette.setColor(QPalette.Base,            QColor("#001100"))
        palette.setColor(QPalette.AlternateBase,   QColor("#002200"))

        # text & headings
        palette.setColor(QPalette.WindowText,      QColor("#00ff00"))
        palette.setColor(QPalette.Text,            QColor("#00ff00"))
        palette.setColor(QPalette.ButtonText,      QColor("#00ff00"))
        palette.setColor(QPalette.HighlightedText, QColor("#000000"))

        # buttons & selection
        palette.setColor(QPalette.Button,          QColor("#001100"))
        palette.setColor(QPalette.Highlight,       QColor("#00ff00"))
        palette.setColor(QPalette.Link,            QColor("#00ff00"))

        # tooltips & misc
        palette.setColor(QPalette.ToolTipBase,     QColor("#000000"))
        palette.setColor(QPalette.ToolTipText,     QColor("#00ff00"))
        palette.setColor(QPalette.BrightText,      QColor("#ff0000"))

        app.setPalette(palette)

    def _setup_overlays(self):
        """Setup OSD and info overlays."""
        self.osd = QLabel("", self)
        self.osd.setStyleSheet("""
            font-size: 28px; 
            color: #00ff00; 
            background: rgba(0,0,0,220); 
            padding: 12px 20px; 
            border-radius: 8px;
            font-weight: bold;
            border: 2px solid #00ff00;
            text-shadow: 0 0 10px #39ff14;
        """)
        self.osd.hide()
        
        self.osd_logo = QLabel(self)
        self.osd_logo.setScaledContents(True)
        self.osd_logo.hide()
        
        self.info = QLabel("", self)
        self.info.setStyleSheet("""
            font-size: 16px; 
            color: #00ff00; 
            background: rgba(0,0,0,220); 
            padding: 12px; 
            border-radius: 8px;
            border: 2px solid #00ff00;
            font-family: "Consolas", monospace;
        """)
        self.info.hide()

        # Loading overlay used during schedule refreshes
        self.loading_label = QLabel("Refreshing...", self)
        self.loading_label.setStyleSheet("""
            font-size: 24px;
            color: #00ff00;
            background: rgba(0,0,0,220);
            padding: 20px;
            border-radius: 8px;
            border: 2px solid #00ff00;
            font-weight: bold;
        """)
        self.loading_label.setAlignment(Qt.AlignCenter)
        self.loading_label.hide()

    # ── ENHANCED WEB SERVER METHODS ──────────────────────────────────
    def show_web_server_info(self):
        """Show web server information dialog at startup."""
        port = self.settings.get("web_port", 5050)
        self.flask_manager.start_server(port)
        
        # Show IP info dialog
        ip_dialog = IPInfoDialog(port, self)
        ip_dialog.exec_()
        self.guide.update_status_indicators()
        
    def start_web_server(self):
        """Start the web server."""
        port = self.settings.get("web_port", 5050)
        self.flask_manager.start_server(port)
        self.guide.update_status_indicators()
        
    def restart_web_server(self):
        """Restart the web server (called from remote)."""
        QTimer.singleShot(100, lambda: self.flask_manager.restart_server())
        self._osd("Web Server Restarting...")
        QTimer.singleShot(500, self.guide.update_status_indicators)

    def get_all_media_for_api(self) -> List[Dict]:
        """Get all media files for the API."""
        media_data = []
        
        for channel in self.channels_real:
            # Shows
            shows_dir = channel / "Shows"
            if shows_dir.exists():
                for show_file in gather_files(shows_dir):
                    duration_ms = self._get_duration(show_file)
                    size_mb = show_file.stat().st_size / (1024 * 1024)
                    
                    media_data.append({
                        'title': format_show_name(show_file),
                        'filename': show_file.name,
                        'channel': channel.name,
                        'duration': ms_to_hms(duration_ms),
                        'size': f"{size_mb:.1f} MB",
                        'type': 'Show',
                        'path': str(show_file)
                    })
            
            # Commercials
            commercials_dir = channel / "Commercials"
            if commercials_dir.exists():
                for commercial_file in gather_files(commercials_dir):
                    duration_ms = self._get_duration(commercial_file)
                    size_mb = commercial_file.stat().st_size / (1024 * 1024)
                    
                    media_data.append({
                        'title': format_show_name(commercial_file),
                        'filename': commercial_file.name,
                        'channel': channel.name,
                        'duration': ms_to_hms(duration_ms),
                        'size': f"{size_mb:.1f} MB",
                        'type': 'Commercial',
                        'path': str(commercial_file)
                    })
        
        return sorted(media_data, key=lambda x: (x['channel'], x['type'], x['title']))

    def get_status_for_api(self) -> Dict:
        """Get current status for API."""
        current_channel = "Guide"
        current_program = "N/A"
        
        if self.ch_idx == 1:
            current_channel = "OnDemand"
            if self.ondemand_content:
                current_program = format_show_name(self.ondemand_content)
        elif self.ch_idx > 1 and self.ch_idx - 2 < len(self.channels_real):
            channel = self.channels_real[self.ch_idx - 2]
            current_channel = channel.name
            
            current = self.get_current_program(channel)
            if current:
                start_time, program_path, duration, is_ad, segment_info = current
                if is_ad:
                    current_program = "Commercial Break"
                else:
                    current_program = format_show_name(Path(program_path))
        
        return {
            'channel': current_channel,
            'program': current_program,
            'volume': self.player.volume(),
            'muted': self.player.isMuted(),
            'state': ['Stopped', 'Playing', 'Paused'][self.player.state()],
            'channels_count': len(self.channels_real)
        }

    def get_guide_for_api(self) -> List[Dict]:
        """Return a lightweight schedule for the remote guide page."""
        now = datetime.now()
        guide = []
        for idx, channel in enumerate(self.channels_real, start=2):
            schedule = self.get_schedule_for_guide(channel, now, 2)
            shows = [
                {
                    'title': format_show_name(Path(p)),
                    'time': t.strftime('%H:%M')
                }
                for t, p, d, a in schedule if not a
            ]
            current = self.get_current_program(channel)
            current_title = format_show_name(Path(current[1])) if current else ''
            guide.append({'index': idx, 'channel': channel.name,
                          'current': current_title, 'shows': shows})
        return guide

    # ── ENHANCED REMOTE COMMAND HANDLING ──────────────────────────────────
    def handle_remote_command(self, cmd: str):
        """Enhanced remote command handling with volume controls."""
        try:
            if ':' in cmd:
                # Handle commands with parameters
                cmd_parts = cmd.split(':', 1)
                cmd_name = cmd_parts[0]
                cmd_param = cmd_parts[1]
                
                if cmd_name == 'play_media':
                    # Start the requested media on the OnDemand channel
                    media_path = Path(cmd_param)
                    self._start_ondemand_playback(media_path)

                    # Remember previous channel for "last" function
                    prev_idx = self.ch_idx
                    if prev_idx > 1:
                        self.last_ch_idx = prev_idx

                    # Switch to the OnDemand channel but keep playing
                    self.ch_idx = 1
                    self.stack.setCurrentIndex(0)
                    self._osd(f"OnDemand Playback: {format_show_name(media_path)}")
                    if hasattr(self, 'info') and self.info.isVisible():
                        self._update_info_display()
                    return
                elif cmd_name == 'goto':
                    try:
                        self.go_channel_index(int(cmd_param))
                    except ValueError:
                        pass
                    return
                    
            # Standard commands
            commands = {
                "play": self.toggle_play,
                "next_channel": lambda: self.change_channel(1),
                "prev_channel": lambda: self.change_channel(-1),
                "next": lambda: self.change_video(1),
                "prev": lambda: self.change_video(-1),
                "guide": self.go_guide,
                "last": self.go_last_channel,
                "info": self.toggle_info,
                "fs": self.toggle_fs,
                "ondemand": self.go_ondemand,
                "volume_up": self.vol_up,
                "volume_down": self.vol_down,
                "mute": self.mute,
                "cursor_up": self.cursor.up,
                "cursor_down": self.cursor.down,
                "cursor_left": self.cursor.left,
                "cursor_right": self.cursor.right,
                "cursor_ok": self.cursor.select,
                "cursor_back": self.cursor.back
            }
            
            if cmd in commands:
                commands[cmd]()
                logging.info(f"[REMOTE] Executed: {cmd}")
            else:
                logging.warning(f"[REMOTE] Unknown command: {cmd}")
                
        except Exception as e:
            logging.error(f"[REMOTE] Error executing {cmd}: {e}")

    # ── ENHANCED SCHEDULE MANAGEMENT ──────────────────────────────────

    def _build_tv_schedule(self, channel: Path) -> List[Tuple[datetime, str, int, bool]]:
        """Build a TV schedule for a channel - plays videos in order, synchronized across channels."""
        shows = list(gather_files(channel / "Shows"))
        ads = list(gather_files(channel / "Commercials"))

        # Shuffle content so each schedule rebuild is unique and not identical
        # to the previous shuffle for this channel
        # Load previously used order from disk as fallback
        prev_order = self._last_show_order.get(channel)
        if prev_order is None:
            prev_order = self._load_last_order(channel)
        attempts = 0
        while attempts < 5:
            random.shuffle(shows)
            if [str(s) for s in shows] != prev_order or len(shows) < 2:
                break
            attempts += 1
        current_order = [str(s) for s in shows]
        self._last_show_order[channel] = current_order
        self._save_last_order(channel, current_order)

        random.shuffle(ads)
        
        if not shows:
            logging.warning(f"No shows found for channel {channel.name}")
            return []
        
        schedule = []
        # Use global schedule start time so all channels are synchronized
        current_time = self.global_schedule_start
        end_time = current_time + timedelta(hours=48)  # 48 hour schedule
        
        show_index = 0
        ad_index = 0
        
        # Build schedule sequentially
        while current_time < end_time:
            # Get next show in order
            show = shows[show_index % len(shows)]
            show_duration = self._get_duration(show)
            
            # Add show
            schedule.append((current_time, str(show), show_duration, False))
            current_time += timedelta(milliseconds=show_duration)
            show_index += 1
            
            # Add ad break if we have ads
            if ads and show_index % 2 == 0:  # Add ads every 2 shows
                # Add ad break
                ad_break_duration = self.settings.get("ad_break_minutes", 3) * 60 * 1000
                remaining_time = ad_break_duration
                ad_break_start = current_time
                
                while remaining_time > 0 and ads:
                    ad = ads[ad_index % len(ads)]
                    ad_duration = min(self._get_duration(ad), remaining_time)
                    
                    # Create ad segment
                    segment_info = {
                        'path': str(ad),
                        'start_offset': 0,
                        'duration': ad_duration
                    }
                    segment_json = json.dumps(segment_info)
                    
                    schedule.append((current_time, segment_json, ad_duration, True))
                    current_time += timedelta(milliseconds=ad_duration)
                    remaining_time -= ad_duration
                    ad_index += 1
        
        logging.info(f"Built schedule for {channel.name}: {len([s for s in schedule if not s[3]])} shows, {len([s for s in schedule if s[3]])} ads")
        return schedule

    def get_schedule_for_guide(self, channel: Path, start_time: datetime, hours: int) -> List:
        """Get schedule data for the TV guide."""
        if channel not in self.schedules:
            self.schedules[channel] = self._build_tv_schedule(channel)

        schedule = self.schedules[channel]
        end_time = start_time + timedelta(hours=hours)

        items = [(t, p, d, a) for t, p, d, a in schedule if start_time <= t < end_time]

        current = self.get_current_program(channel)
        if current:
            c_start, program, duration, is_ad, _ = current
            c_end = c_start + timedelta(milliseconds=duration)
            if c_start < start_time and c_end > start_time:
                if not items or items[0][0] != c_start:
                    items.insert(0, (c_start, program, duration, is_ad))

        return items

    def get_current_program(self, channel: Path) -> Optional[Tuple[datetime, str, int, bool, Dict]]:
        """Get the currently playing program for a channel based on synchronized schedule."""
        if channel not in self.schedules:
            self.schedules[channel] = self._build_tv_schedule(channel)
        
        now = datetime.now()
        schedule = self.schedules[channel]
        
        if not schedule:
            return None
        
        # Calculate total schedule duration
        total_duration_ms = sum(duration for _, _, duration, _ in schedule)
        if total_duration_ms == 0:
            return None
            
        # Calculate how much time has passed since schedule start
        time_since_start = (now - self.global_schedule_start).total_seconds() * 1000
        
        # Handle negative time (shouldn't happen but just in case)
        if time_since_start < 0:
            time_since_start = 0
            
        # Calculate position within the looping schedule
        position_in_loop = time_since_start % total_duration_ms
        
        # Find which program should be playing at this position
        accumulated_time = 0
        for i, (original_start, program, duration, is_ad) in enumerate(schedule):
            if accumulated_time <= position_in_loop < accumulated_time + duration:
                # Calculate when this instance of the program started
                loops_completed = int(time_since_start // total_duration_ms)
                loop_start = self.global_schedule_start + timedelta(milliseconds=loops_completed * total_duration_ms)
                program_start = loop_start + timedelta(milliseconds=accumulated_time)
                
                segment_info = {}
                try:
                    segment_data = json.loads(program)
                    segment_info = segment_data
                    program = segment_data['path']
                except (json.JSONDecodeError, TypeError):
                    pass
                
                self.current_schedule_index[channel] = i
                
                # Log for debugging
                elapsed_in_program = position_in_loop - accumulated_time
                logging.debug(f"Channel {channel.name}: Playing {Path(program).name} at {elapsed_in_program/1000:.1f}s of {duration/1000:.1f}s")
                
                return (program_start, program, duration, is_ad, segment_info)
                
            accumulated_time += duration
        
        # Shouldn't reach here, but if we do, return first program
        if schedule:
            start_time, program, duration, is_ad = schedule[0]
            segment_info = {}
            try:
                segment_data = json.loads(program)
                segment_info = segment_data
                program = segment_data['path']
            except (json.JSONDecodeError, TypeError):
                pass
            self.current_schedule_index[channel] = 0
            return (self.global_schedule_start, program, duration, is_ad, segment_info)
            
        return None

    def _advance_to_next_program(self, channel: Path):
        """Advance to the next program in the channel's schedule - respecting live timing."""
        try:
            # Just tune to the channel again - it will pick up whatever should be playing NOW
            self._tune_to_channel(channel)
                
        except Exception as e:
            logging.error(f"Error advancing to next program: {e}")

    def _load_program_enhanced(self, program_path: Path, seek_pos: int = 0):
        """Enhanced program loading with better segment handling and seeking."""
        try:
            logging.info(f"Loading program: {program_path.name}, seek to: {seek_pos/1000:.1f}s")
            
            # Clear any existing segment timer
            if hasattr(self, '_segment_timer') and self._segment_timer:
                self._segment_timer.stop()
                self._segment_timer = None
                
            self.playback_state['current_program'] = program_path
            self.playback_state['program_start_time'] = datetime.now() - timedelta(milliseconds=seek_pos)
            
            # Handle segment information
            segment_info = getattr(self, '_current_segment_info', None)
            if segment_info:
                self.playback_state['segment_info'] = segment_info
                delattr(self, '_current_segment_info')
            else:
                self.playback_state['segment_info'] = None
            
            self._load_subtitles(program_path)
            
            # Stop any current playback first
            if self.player.state() != QMediaPlayer.StoppedState:
                self.player.stop()
                # Wait a bit for stop to complete
                QTimer.singleShot(50, lambda: self._continue_load_program(program_path, seek_pos, segment_info))
            else:
                self._continue_load_program(program_path, seek_pos, segment_info)
                    
        except Exception as e:
            logging.error(f"Load program error: {e}")
            self._osd("Playback Error")
            # Try retuning on error
            if self.ch_idx > 1:
                channel = self.channels_real[self.ch_idx - 2]
                QTimer.singleShot(1000, lambda: self._tune_to_channel(channel))
                
    def _continue_load_program(self, program_path: Path, seek_pos: int, segment_info: dict):
        """Continue loading program after stop completes."""
        try:
            media_url = QUrl.fromLocalFile(str(program_path))
            content = QMediaContent(media_url)
            self.player.setMedia(content)
            
            # For ads with segment info, set up timer
            if segment_info and 'duration' in segment_info:
                remaining_time = segment_info['duration'] - seek_pos
                if remaining_time > 0:
                    self._segment_timer = QTimer()
                    self._segment_timer.timeout.connect(self._on_segment_end_enhanced)
                    self._segment_timer.setSingleShot(True)
                    self._segment_timer.start(int(remaining_time))
                    logging.info(f"Set segment timer for {remaining_time/1000:.1f}s")
            
            # Set up media loaded handler if we need to seek
            if seek_pos > 0:
                self._pending_seek = seek_pos
                self.player.mediaStatusChanged.connect(self._on_media_loaded_for_seek)
                # Also try setting position immediately in case media loads fast
                QTimer.singleShot(100, lambda: self._try_immediate_seek(seek_pos))
            
            # Start playback
            self.player.play()
            
        except Exception as e:
            logging.error(f"Continue load program error: {e}")
            self._osd("Playback Error")
            
    def _try_immediate_seek(self, seek_pos: int):
        """Try to seek immediately if media is already loaded."""
        if hasattr(self, '_pending_seek') and self.player.mediaStatus() in [QMediaPlayer.LoadedMedia, QMediaPlayer.BufferedMedia]:
            logging.info(f"Media already loaded, seeking immediately to {seek_pos/1000:.1f}s")
            self.player.setPosition(seek_pos)
            if hasattr(self, '_pending_seek'):
                delattr(self, '_pending_seek')
                
    def _on_media_loaded_for_seek(self, status):
        """Handle media loaded event for seeking."""
        if status in [QMediaPlayer.LoadedMedia, QMediaPlayer.BufferedMedia] and hasattr(self, '_pending_seek'):
            seek_pos = self._pending_seek
            delattr(self, '_pending_seek')
            
            logging.info(f"Media ready (status={status}), seeking to: {seek_pos/1000:.1f}s")
            
            # Try seeking multiple times if needed
            def do_seek(attempts=0):
                self.player.setPosition(seek_pos)
                # Verify seek worked after a short delay
                if attempts < 3:
                    QTimer.singleShot(100, lambda: verify_seek(attempts))
                    
            def verify_seek(attempts):
                actual_pos = self.player.position()
                if abs(actual_pos - seek_pos) > 1000:  # More than 1 second off
                    logging.warning(f"Seek failed, expected {seek_pos/1000:.1f}s, got {actual_pos/1000:.1f}s, retrying...")
                    do_seek(attempts + 1)
                else:
                    logging.info(f"Seek successful, at {actual_pos/1000:.1f}s")
                    
            do_seek()
            
            # Disconnect this handler
            try:
                self.player.mediaStatusChanged.disconnect(self._on_media_loaded_for_seek)
            except Exception as e:
                logging.debug(f"Disconnect error: {e}")
        elif status in [QMediaPlayer.InvalidMedia, QMediaPlayer.UnknownMediaStatus]:
            logging.error(f"Failed to load media, status: {status}")
            if hasattr(self, '_pending_seek'):
                delattr(self, '_pending_seek')
            try:
                self.player.mediaStatusChanged.disconnect(self._on_media_loaded_for_seek)
            except Exception as e:
                logging.debug(f"Disconnect error: {e}")

    def _on_segment_end_enhanced(self):
        """Enhanced segment end handling - maintain live TV timing."""
        try:
            logging.info("Segment ended, checking live schedule")
            
            if self.ch_idx <= 1 or self.ch_idx - 2 >= len(self.channels_real):
                return
                
            channel = self.channels_real[self.ch_idx - 2]
            
            # Clear segment info
            self.playback_state['segment_info'] = None
            if hasattr(self, '_segment_timer'):
                self._segment_timer = None
            
            # Retune to pick up whatever should be playing now
            QTimer.singleShot(200, lambda: self._tune_to_channel(channel))
            
        except Exception as e:
            logging.error(f"Segment end error: {e}")

    def reload_schedule(self):
        """Reload program schedules with synchronized timing."""
        self._show_loading("Refreshing schedules...")

        # Clear existing schedules
        self.schedules.clear()
        self.current_schedule_index.clear()

        # Start a brand new synchronized schedule beginning now
        self.global_schedule_start = datetime.now()

        # Rebuild all schedules
        for channel in self.channels_real:
            self.schedules[channel] = self._build_tv_schedule(channel)
        
        if self.ch_idx == 0:
            self.guide.refresh()
        elif self.ch_idx > 1:
            real_channel_idx = self.ch_idx - 2
            if real_channel_idx < len(self.channels_real):
                current_channel = self.channels_real[real_channel_idx]
                self._tune_to_channel(current_channel)
        
        self._hide_loading()
        self._osd("Schedules Reloaded")

    # ── ENHANCED CHANNEL NAVIGATION METHODS ──────────────────────────────────
    def change_channel(self, delta: int):
        """Change to a different channel."""
        if not self.channels:
            return
            
        prev_idx = self.ch_idx
        self.ch_idx = (self.ch_idx + delta) % len(self.channels)
        
        # Set last channel (skip guide and ondemand)
        if prev_idx > 1:  # Real channel
            self.last_ch_idx = prev_idx
        
        logging.info(f"Changing channel: {prev_idx} -> {self.ch_idx}")
        
        if self.ch_idx == 0:
            self._show_guide()
        elif self.ch_idx == 1:
            self._show_ondemand()
        else:
            # Real channel (index - 2 to account for guide and ondemand)
            real_channel_idx = self.ch_idx - 2
            self._tune_to_channel(self.channels_real[real_channel_idx])

    def _show_guide(self):
        """Show the TV guide."""
        self.player.pause()
        self.stack.setCurrentIndex(1)
        self.guide.refresh()
        self.guide.table.setFocus()
        self._osd("TV GUIDE - 12 Hour Schedule")
        self._stop_static()
        
        if hasattr(self, 'info') and self.info.isVisible():
            self._update_info_display()

    def _show_ondemand(self):
        """FIXED: Show the OnDemand channel - stop current playback when revisited."""
        # If we're already on OnDemand and in the player view, go back to browser
        if self.ch_idx == 1 and self.stack.currentIndex() == 0:
            # Stop current OnDemand playback
            self.player.stop()
            self.ondemand_content = None
            self.ondemand_start_time = None
            self.stack.setCurrentIndex(2)
            self.ondemand.content_list.setFocus()
            self._osd("OnDemand - Browse & Select")
        else:
            # Show OnDemand browser
            self.player.stop()  # Stop any current playback
            self.stack.setCurrentIndex(2)
            self.ondemand.refresh_content()
            self.ondemand.content_list.setFocus()
            self._osd("OnDemand - Browse & Select")

        self._stop_static()
        if hasattr(self, 'info') and self.info.isVisible():
            self._update_info_display()

    def _tune_to_channel(self, channel: Path):
        """Tune to a specific channel - joins program already in progress."""
        self.stack.setCurrentIndex(0)
        self.video.setFocus()
        
        if hasattr(self, 'info') and self.info.isVisible():
            self._update_info_display()
        
        # Ensure we have a schedule
        if channel not in self.schedules:
            self.schedules[channel] = self._build_tv_schedule(channel)
        
        current = self.get_current_program(channel)
        if not current:
            self._osd("NO CONTENT", logo=self.channel_logo.get(channel))
            self._stop_static()
            return
        
        start_time, program_path, duration, is_ad, segment_info = current
        
        # Calculate exact position in the current program
        now = datetime.now()
        elapsed = (now - start_time).total_seconds() * 1000
        seek_pos = max(0, int(elapsed))
        
        logging.info(f"Tuning to {channel.name}: {Path(program_path).name} at {seek_pos/1000:.1f}s/{duration/1000:.1f}s")
        
        # Handle ad segments properly
        if segment_info and 'start_offset' in segment_info:
            base_offset = segment_info['start_offset']
            max_segment_duration = segment_info.get('duration', duration)
            
            if seek_pos > max_segment_duration:
                # If we're past this segment, check schedule again
                logging.info("Past current segment, rechecking schedule")
                QTimer.singleShot(100, lambda: self._tune_to_channel(channel))
                return
                
            seek_pos += base_offset
            logging.info(f"Ad segment: adjusted seek to {seek_pos/1000:.1f}s")
        
        # Make sure we're not seeking past the end of the video
        if seek_pos >= duration:
            # We should be in the next program
            logging.info("Past end of current program, rechecking schedule")
            QTimer.singleShot(100, lambda: self._tune_to_channel(channel))
            return
        
        self._start_static()
        
        if segment_info:
            self._current_segment_info = segment_info
        
        # Load the program at the exact position it should be at
        self._load_program_enhanced(Path(program_path), seek_pos)
        
        channel_num = self.ch_idx
        channel_name = channel.name
        
        # Show what's currently playing
        if is_ad:
            show_name = "Commercial Break"
        else:
            show_name = format_show_name(Path(program_path))
        
        # Calculate time remaining
        time_remaining = duration - seek_pos
        mins_remaining = max(0, int(time_remaining / 60000))
        
        if mins_remaining > 0:
            self._osd(f"CH {channel_num:02d} - {channel_name} - {show_name} ({mins_remaining}m left)", 
                     logo=self.channel_logo.get(channel), duration=4000)
        else:
            self._osd(f"CH {channel_num:02d} - {channel_name} - {show_name} (ending)", 
                     logo=self.channel_logo.get(channel), duration=4000)
        
        QTimer.singleShot(800, self._stop_static)

    def _start_ondemand_playback(self, content_path: Path):
        """Start playing OnDemand content."""
        self._show_loading("Loading OnDemand...")
        self.ondemand_content = content_path
        self.ondemand_start_time = datetime.now()
        self._load_program_enhanced(content_path, 0)
        self.video.setFocus()
        QTimer.singleShot(800, self._hide_loading)
        logging.info(f"Started OnDemand playback: {content_path}")

    def go_ondemand(self):
        """FIXED: Jump to the OnDemand channel properly."""
        if self.ch_idx == 1:
            # Already on OnDemand - toggle between browser and player
            if self.stack.currentIndex() == 0 and self.ondemand_content:
                # Currently playing - go to browser
                self.player.stop()
                self.ondemand_content = None
                self.ondemand_start_time = None
                self.stack.setCurrentIndex(2)
                self.ondemand.content_list.setFocus()
                self._osd("OnDemand - Browse & Select")
            else:
                # Already in browser
                self._osd("OnDemand - Browse")
        else:
            # Go to OnDemand channel
            target_idx = 1
            self.change_channel(target_idx - self.ch_idx)

    def go_guide(self):
        """Go to the TV guide."""
        if self.ch_idx != 0:
            self.change_channel(-self.ch_idx)
        else:
            self._osd("Already viewing TV Guide")
        self.guide.update_status_indicators()

    def go_last_channel(self):
        """Go to the last watched channel."""
        if self.last_ch_idx is None or self.last_ch_idx == self.ch_idx:
            self._osd("No previous channel")
            return

        delta = self.last_ch_idx - self.ch_idx
        self.change_channel(delta)

    def go_channel_index(self, index: int):
        """Switch directly to a channel by index (0 = guide, 1 = on-demand)."""
        if 0 <= index < len(self.channels):
            delta = index - self.ch_idx
            if delta:
                self.change_channel(delta)

    # ── MEDIA MANAGEMENT METHODS ──────────────────────────────────
    def _get_duration(self, path: Path) -> int:
        """Get cached duration or probe file."""
        key = str(path)
        if key not in self.durations:
            self.durations[key] = probe_duration(path)
            self._save_cache()
        return self.durations[key]

    def _load_cache(self) -> Dict[str, int]:
        """Load duration cache."""
        try:
            with open(self.cache_file, 'r') as f:
                data = json.load(f)
                return {k: int(v) for k, v in data.items() if isinstance(v, (int, float))}
        except Exception as e:
            logging.warning(f"Failed to load cache: {e}")
            return {}

    def _save_cache(self):
        """Save duration cache."""
        try:
            with open(self.cache_file, 'w') as f:
                json.dump(self.durations, f, indent=2)
        except Exception as e:
            logging.warning(f"Failed to save cache: {e}")

    def _load_last_order(self, channel: Path) -> List[str]:
        """Load last shuffled show order for a channel."""
        file = SCHEDULE_DIR / f"{channel.name}_order.json"
        try:
            with open(file, 'r') as f:
                return json.load(f)
        except Exception:
            return []

    def _save_last_order(self, channel: Path, order: List[str]):
        """Persist last shuffled show order for a channel."""
        file = SCHEDULE_DIR / f"{channel.name}_order.json"
        try:
            with open(file, 'w') as f:
                json.dump(order, f)
        except Exception as e:
            logging.warning(f"Failed to save schedule cache for {channel}: {e}")

    def _load_settings(self) -> Dict:
        """Load application settings."""
        settings = QSettings("TVStation", "LiveTV")
        result = self.DEFAULT_SETTINGS.copy()
        
        for key, default in result.items():
            value = settings.value(key, default)
            if isinstance(default, bool):
                result[key] = str(value).lower() == 'true'
            elif isinstance(default, int):
                result[key] = int(value)
            elif key == "recent_channels":
                try:
                    result[key] = json.loads(str(value))
                except Exception:
                    result[key] = []
            else:
                result[key] = str(value)
        
        return result

    def _save_settings(self):
        """Save application settings."""
        settings = QSettings("TVStation", "LiveTV")
        for key, value in self.settings.items():
            if key == "recent_channels":
                settings.setValue(key, json.dumps(value))
            else:
                settings.setValue(key, str(value) if not isinstance(value, bool) else value)

    def _auto_select_channels_folder(self):
        """Select appropriate channels folder based on settings."""
        global ROOT_CHANNELS
        ROOT_CHANNELS = Path(self.settings.get("channels_dir", str(ROOT_CHANNELS)))
        if self.settings.get("load_last_folder", True):
            recents = self.settings.get("recent_channels", [])
            for path in recents:
                logging.info(f"Trying channels folder: {path}")
                p = Path(path)
                if (p / "Shows").exists() and (p / "Commercials").exists():
                    ROOT_CHANNELS = p
                    break
            else:
                logging.info("No saved channels folder found, using default")
        ROOT_CHANNELS.mkdir(exist_ok=True)

    def _update_recent_channels(self, folder: str):
        """Add folder to recent channels list and save settings."""
        recents = self.settings.get("recent_channels", [])
        if folder in recents:
            recents.remove(folder)
        recents.insert(0, folder)
        self.settings["recent_channels"] = recents[:5]
        self.settings["channels_dir"] = folder
        self._save_settings()
        self._populate_recent_menu()

    def _populate_recent_menu(self):
        """Populate the recent channels submenu."""
        if not hasattr(self, "recent_menu"):
            return
        self.recent_menu.clear()
        for path in self.settings.get("recent_channels", []):
            name = Path(path).name
            self.recent_menu.addAction(name, lambda checked, p=path: self.load_channels_folder(p))

    def _find_logo(self, channel: Path) -> Optional[str]:
        """Find channel logo file."""
        for ext in ('.png', '.jpg', '.jpeg', '.gif'):
            logo_file = channel / f"logo{ext}"
            if logo_file.exists():
                return str(logo_file)
        return None

    def _rebuild_logos(self):
        """Rebuild channel logo cache."""
        self.channel_logo: Dict[Path, str] = {}
        for channel in self.channels_real:
            logo = self._find_logo(channel)
            if logo:
                self.channel_logo[channel] = logo

    def _load_hotkeys(self) -> Dict[str, str]:
        """Load hotkey configuration."""
        try:
            with open(self.hotkey_file, 'r') as f:
                saved = json.load(f)
                return {**self.DEFAULT_KEYS, **saved}
        except Exception as e:
            logging.warning(f"Failed to load hotkeys: {e}")
            return self.DEFAULT_KEYS.copy()

    def _save_hotkeys(self):
        """Save hotkey configuration."""
        try:
            with open(self.hotkey_file, 'w') as f:
                json.dump(self.hotkeys, f, indent=2)
        except Exception as e:
            logging.warning(f"Failed to save hotkeys: {e}")

    def _bind_keys(self):
        """Bind keyboard shortcuts."""
        for shortcut in getattr(self, '_shortcuts', []):
            shortcut.setParent(None)
        
        self._shortcuts = []
        actions = {
            "next_video": lambda: self.change_video(1),
            "prev_video": lambda: self.change_video(-1),
            "next_channel": lambda: self.change_channel(1),
            "prev_channel": lambda: self.change_channel(-1),
            "last_channel": self.go_last_channel,
            "guide": self.go_guide,
            "toggle_fullscreen": self.toggle_fs,
            "show_console": self.console.show,
            "toggle_remote": self.toggle_remote,
            "toggle_info": self.toggle_info,
            "reload_schedule": self.reload_schedule,
            "volume_up": self.vol_up,
            "volume_down": self.vol_down,
            "mute": self.mute,
            "toggle_subtitles": self.tog_subs,
            "ondemand": self.go_ondemand,
            "guide_zoom_in": self.guide.zoom_in,
            "guide_zoom_out": self.guide.zoom_out
        }
        
        for action, sequence in self.hotkeys.items():
            if action in actions and sequence:
                shortcut = QShortcut(QKeySequence(sequence), self)
                shortcut.activated.connect(actions[action])
                shortcut.setContext(Qt.ApplicationShortcut)
                self._shortcuts.append(shortcut)

    # ── UI CONTROL METHODS ──────────────────────────────────
    def vol_up(self):
        """Increase volume."""
        vol = min(100, self.player.volume() + 5)
        self.player.setVolume(vol)
        self._osd(f"VOLUME {vol}%")

    def vol_down(self):
        """Decrease volume."""
        vol = max(0, self.player.volume() - 5)
        self.player.setVolume(vol)
        self._osd(f"VOLUME {vol}%")

    def mute(self):
        """Toggle mute."""
        muted = not self.player.isMuted()
        self.player.setMuted(muted)
        self._osd("MUTED" if muted else "UNMUTED")

    def toggle_play(self):
        """Toggle play/pause."""
        if self.player.state() == QMediaPlayer.PlayingState:
            self.player.pause()
            self._osd("PAUSED")
        else:
            self.player.play()
            self._osd("PLAYING")

    def change_video(self, delta: int):
        """Change to next/previous video - for live TV, this skips within the schedule."""
        if self.ch_idx == 0:
            return
            
        if self.ch_idx == 1:  # OnDemand
            self._osd("Use OnDemand browser to select content")
            return
            
        channel = self.channels_real[self.ch_idx - 2]
        
        if delta > 0:
            self._osd("Live TV - Cannot skip ahead")
        else:
            # Previous video - restart current program
            current = self.get_current_program(channel)
            if current:
                start_time, program_path, duration, is_ad, segment_info = current
                # For live TV, we can't really go back in time, but we can restart current show
                if segment_info:
                    self._current_segment_info = segment_info
                self._load_program_enhanced(Path(program_path), 0)
                self._osd("Program Restarted (from beginning)")

    def toggle_info(self):
        """Toggle program information display."""
        if self.ch_idx == 0:
            self._osd("No program info in guide")
            return
        
        if self.info.isVisible():
            self.info.hide()
        else:
            self._update_info_display()
            self.info.show()

    def toggle_remote(self):
        """Toggle remote control window."""
        if self.remote.isVisible():
            self.remote.hide()
        else:
            self.remote.show()
            self.remote.move(self.x() + 50, self.y() + self.height() - self.remote.height() - 50)

    def toggle_dev_remote(self):
        """Toggle developer remote control window."""
        if self.dev_remote.isVisible():
            self.dev_remote.hide()
        else:
            self.dev_remote.show()
            self.dev_remote.move(self.x() + 350, self.y() + self.height() - self.dev_remote.height() - 50)

    def toggle_fs(self):
        """Toggle fullscreen mode."""
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()
            
        self._osd("FULLSCREEN " + ("ON" if self.isFullScreen() else "OFF"))

    # ── SUBTITLE SYSTEM ──────────────────────────────────
    def _load_subtitles(self, video_path: Path):
        """Load subtitle file if available."""
        self.sub_cues = []
        
        for ext in SUB_EXTS:
            sub_path = video_path.with_suffix(ext)
            if sub_path.exists():
                if ext == '.srt':
                    self.sub_cues = parse_srt(sub_path)
                break

    def tog_subs(self):
        """Toggle subtitle display."""
        if not self.sub_cues:
            self._osd("No subtitles available")
            return
        
        self.sub_enabled = not self.sub_enabled
        if not self.sub_enabled:
            self.sub_label.hide()
        
        self._osd("SUBTITLES " + ("ON" if self.sub_enabled else "OFF"))

    def _on_position_changed(self, position: int):
        """Handle player position changes."""
        # Log position for debugging (only log every 5 seconds to avoid spam)
        if hasattr(self, '_last_log_time'):
            if datetime.now() - self._last_log_time > timedelta(seconds=5):
                if self.playback_state.get('current_program'):
                    logging.debug(f"Playback position: {position/1000:.1f}s in {self.playback_state['current_program'].name}")
                self._last_log_time = datetime.now()
        else:
            self._last_log_time = datetime.now()
            
        # Handle subtitles
        if self.sub_enabled and self.sub_cues:
            text = ""
            for start, end, subtitle_text in self.sub_cues:
                if start <= position <= end:
                    text = subtitle_text
                    break
            
            self.sub_label.setText(text)
            self.sub_label.setVisible(bool(text))

    # ── ENHANCED INFO DISPLAY ──────────────────────────────────
    def _update_info_display(self):
        """Update the program information display."""
        if self.ch_idx == 0:
            info_text = "[TV] TV GUIDE CHANNEL\n"
            info_text += "[SCHED] 12-Hour Program Schedule\n"
            info_text += "[BROWSE] Browse upcoming shows\n"
            info_text += "[CLICK] Click programs for details"
        elif self.ch_idx == 1:
            info_text = "[TV] ONDEMAND CHANNEL\n"
            if self.ondemand_content:
                show_name = format_show_name(self.ondemand_content)
                elapsed = datetime.now() - self.ondemand_start_time if self.ondemand_start_time else timedelta(0)
                info_text += f"[SHOW] Playing: {show_name}\n"
                info_text += f"[TIME] Playing for: {str(elapsed).split('.')[0]}\n"
                info_text += "[USER] User-selected content"
            else:
                info_text += "[BROWSE] Browse & Select Content\n"
                info_text += "[SHOWS] All shows from all channels\n"
                info_text += "[PLAY] Choose what to watch"
        elif self.ch_idx > 1 and self.ch_idx - 2 < len(self.channels_real):
            # Real channel
            channel = self.channels_real[self.ch_idx - 2]
            current = self.get_current_program(channel)
            
            if current:
                start_time, program_path, duration, is_ad, segment_info = current
                program_name = format_show_name(Path(program_path))
                end_time = start_time + timedelta(milliseconds=duration)
                
                info_text = f"[TV] {channel.name}\n"
                if is_ad:
                    info_text += f"[AD] Commercial Break\n"
                else:
                    info_text += f"[SHOW] {program_name}\n"
                info_text += f"[TIME] {ms_to_hms(duration)}\n"
                info_text += f"[END] Ends {end_time.strftime('%H:%M:%S')}"
            else:
                info_text = f"[TV] {channel.name}\nNo program information available"
        else:
            info_text = "No information available"
        
        self.info.setText(info_text)
        self.info.adjustSize()
        self.info.move(20, self.height() - self.info.height() - 20)

    # ── OSD AND VISUAL EFFECTS ──────────────────────────────────
    def _osd(self, text: str, duration: int = 3000, logo: Optional[str] = None):
        """Show on-screen display message with multi-line support."""
        self.osd.setText(text)
        self.osd.adjustSize()
        
        x = max(20, self.width() - self.osd.width() - 20)
        y = self.menuBar().height() + 20
        self.osd.move(x, y)
        self.osd.raise_()
        self.osd.show()
        
        if logo:
            pixmap = QPixmap(logo).scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.osd_logo.setPixmap(pixmap)
            self.osd_logo.adjustSize()
            self.osd_logo.move(x - self.osd_logo.width() - 10, y)
            self.osd_logo.show()
            self.osd_logo.raise_()
        else:
            self.osd_logo.hide()
        
        if duration > 0:
            QTimer.singleShot(duration, self.osd.hide)
            QTimer.singleShot(duration, self.osd_logo.hide)

    def _start_static(self):
        """Start static visual effect."""
        if self.settings["static_fx"] and self.static_movie:
            self.static_label.setGeometry(self.rect())
            self.static_label.raise_()
            self.static_movie.start()
            self.static_label.show()

    def _stop_static(self):
        """Stop static visual effect."""
        if self.static_label.isVisible():
            self.static_label.lower()
            if self.static_movie:
                self.static_movie.stop()
            self.static_label.hide()

    # Loading overlay helpers
    def _show_loading(self, message: str = "Loading..."):
        """Display loading overlay with a message."""
        self.loading_label.setText(message)
        self.loading_label.setGeometry(self.rect())
        self.loading_label.raise_()
        self.loading_label.show()
        QApplication.processEvents()

    def _hide_loading(self):
        """Hide loading overlay."""
        self.loading_label.hide()

    # ── ENHANCED SETTINGS MANAGEMENT ──────────────────────────────────
    def show_settings(self):
        """Enhanced settings dialog with schedule reset warning."""
        dialog = SettingsDialog(self.settings, self)
        if dialog.exec_() == QDialog.Accepted:
            old_settings = self.settings.copy()
            self.settings.update(dialog.result())
            self.cache_file = Path(self.settings.get("cache_file", str(DEFAULT_CACHE_FILE)))
            self.hotkey_file = Path(self.settings.get("hotkey_file", str(DEFAULT_HOTKEY_FILE)))
            self._save_settings()
            self.durations = self._load_cache()
            self.hotkeys = self._load_hotkeys()
            self._bind_keys()
            
            # Apply volume immediately
            self.player.setVolume(self.settings["default_volume"])
            self.sub_label.setFont(QFont("Consolas", self.settings["subtitle_size"]))
            
            # Check if schedule-affecting settings changed
            schedule_affecting = ['min_show_minutes', 'ad_break_minutes']
            needs_schedule_reset = any(old_settings.get(key) != self.settings.get(key) for key in schedule_affecting)

            if old_settings.get('channels_dir') != self.settings.get('channels_dir'):
                global ROOT_CHANNELS
                ROOT_CHANNELS = Path(self.settings['channels_dir'])
                ROOT_CHANNELS.mkdir(exist_ok=True)
                self.reload_channels()

            # Check if web port changed
            if old_settings.get("web_port") != self.settings.get("web_port"):
                self.restart_web_server()
            
            if needs_schedule_reset:
                self._reset_schedules_and_return_to_guide()
                self._osd("Settings Updated - Schedules Rebuilt")
            else:
                self._osd("Settings Updated")

    def _reset_schedules_and_return_to_guide(self):
        """Reset all schedules and return to guide."""
        try:
            # Clear all schedule data
            self.schedules.clear()
            self.current_schedule_index.clear()
            
            # Start new schedules from the current moment
            self.global_schedule_start = datetime.now()
            
            # Stop current playback
            self.player.stop()
            
            # Clear any segment timers
            if hasattr(self, '_segment_timer') and self._segment_timer:
                self._segment_timer.stop()
                self._segment_timer = None
            
            # Reset playback state
            self.playback_state = {
                'current_program': None,
                'program_start_time': None,
                'segment_info': None,
                'segment_timer': None,
                'last_position': 0,
                'current_schedule_index': -1
            }
            
            # Rebuild schedules for all channels
            for channel in self.channels_real:
                self.schedules[channel] = self._build_tv_schedule(channel)
            
            # Go to guide
            self.ch_idx = 0
            self._show_guide()
            
            logging.info("Schedules reset and returned to guide")
            
        except Exception as e:
            logging.error(f"Schedule reset error: {e}")

    # ── ENHANCED PLAYER EVENT HANDLERS ──────────────────────────────────
    def _on_player_state_changed(self, state):
        """Handle player state changes."""
        try:
            states = {
                QMediaPlayer.StoppedState: "Stopped",
                QMediaPlayer.PlayingState: "Playing",
                QMediaPlayer.PausedState: "Paused"
            }
            logging.debug(f"Player state changed to: {states.get(state, 'Unknown')}")
            
        except Exception as e:
            logging.error(f"Player state change error: {e}")

    def _on_media_status_changed(self, status):
        """Enhanced media status change handling."""
        try:
            if status == QMediaPlayer.EndOfMedia:
                if self.ch_idx == 1:  # OnDemand channel
                    self.ondemand_content = None
                    self.ondemand_start_time = None
                    self._show_ondemand()
                elif self.ch_idx > 1:  # Real channel
                    real_channel_idx = self.ch_idx - 2
                    if real_channel_idx < len(self.channels_real):
                        current_channel = self.channels_real[real_channel_idx]
                        logging.info(f"Media ended for {current_channel.name}, checking schedule...")
                        # Just retune to pick up whatever should be playing now
                        QTimer.singleShot(100, lambda: self._tune_to_channel(current_channel))
                        
        except Exception as e:
            logging.error(f"Media status change error: {e}")

    def _on_duration_changed(self, duration):
        """Handle duration change - useful for seeking verification."""
        if duration > 0:
            logging.debug(f"Media duration available: {duration/1000:.1f}s")
            # If we have a pending seek, try it now
            if hasattr(self, '_pending_seek'):
                seek_pos = self._pending_seek
                if seek_pos < duration:
                    logging.info(f"Duration available, attempting seek to {seek_pos/1000:.1f}s")
                    self.player.setPosition(seek_pos)

    def _on_player_error(self, error=None):
        """Enhanced player error handling."""
        if error is None:
            error = self.player.error()
            
        error_messages = {
            QMediaPlayer.NoError: "No error",
            QMediaPlayer.ResourceError: "Resource error - File may be corrupted or inaccessible",
            QMediaPlayer.FormatError: "Format error - Unsupported video format",
            QMediaPlayer.NetworkError: "Network error - Check file location",
            QMediaPlayer.AccessDeniedError: "Access denied - Check file permissions"
        }
        
        if hasattr(QMediaPlayer, 'ServiceMissingError'):
            error_messages[QMediaPlayer.ServiceMissingError] = "Service missing - Media codecs may be missing"
        
        error_msg = error_messages.get(error, f"Unknown error ({error})")
        logging.error(f"Media player error: {error_msg}")
        self._osd(f"Playback Error: {error_msg}")
        
        # Try to advance to next program on error
        if self.ch_idx > 1:
            QTimer.singleShot(3000, lambda: self._advance_to_next_program(
                self.channels_real[self.ch_idx - 2]))

    # ── ENHANCED MENU SYSTEM ──────────────────────────────────
    def _build_menu(self):
        """Build enhanced application menu."""
        menubar = self.menuBar()
        
        # Apply Matrix theme to menu
        menubar.setStyleSheet("""
            QMenuBar {
                background-color: #000000;
                color: #00ff00;
                border-bottom: 2px solid #00ff00;
            }
            QMenuBar::item {
                padding: 4px 10px;
                background: transparent;
            }
            QMenuBar::item:selected {
                background: #002200;
            }
            QMenu {
                background-color: #001100;
                color: #00ff00;
                border: 2px solid #00ff00;
            }
            QMenu::item {
                padding: 4px 20px;
            }
            QMenu::item:selected {
                background-color: #003300;
            }
        """)
        
        # Channel Menu
        channel_menu = menubar.addMenu("&Channel")
        channel_menu.addAction("[TV] &Guide", self.go_guide, "G")
        channel_menu.addAction("[SHOW] &OnDemand", self.go_ondemand, "O")
        channel_menu.addAction("[LAST] &Last Channel", self.go_last_channel, "Ctrl+L")
        channel_menu.addSeparator()
        channel_menu.addAction("[UP] Channel &Up", lambda: self.change_channel(1), "PageDown")
        channel_menu.addAction("[DOWN] Channel &Down", lambda: self.change_channel(-1), "PageUp")
        channel_menu.addSeparator()
        
        program_submenu = channel_menu.addMenu("[CTRL] Program Control")
        program_submenu.addAction("[PLAY] Play/Pause", self.toggle_play, "Space")
        program_submenu.addAction("[NEXT] Next Video", lambda: self.change_video(1), "Ctrl+Right")
        program_submenu.addAction("[PREV] Previous Video", lambda: self.change_video(-1), "Ctrl+Left")
        program_submenu.addSeparator()
        program_submenu.addAction("[RELOAD] Reload Schedule", self.reload_schedule, "Ctrl+R")
        
        # File Menu
        file_menu = menubar.addMenu("&Content")
        file_menu.addAction("[OPEN] &Open Channels Folder", self.open_channels_folder, "Ctrl+O")
        file_menu.addAction("[SELECT] &Select Channels Folder...", self.select_channels_folder)
        file_menu.addAction("[SAVED] Manage Saved Folders", self.show_saved_channels_editor)
        self.recent_menu = file_menu.addMenu("[RECENT] Recent Folders")
        self._populate_recent_menu()
        file_menu.addSeparator()
        file_menu.addAction("[EDIT] &TV Network Editor", self.show_network_editor, "Ctrl+E")
        file_menu.addSeparator()
        file_menu.addAction("[RELOAD] &Reload Channels", self.reload_channels, "F5")
        file_menu.addAction("[EXIT] E&xit", self.close, "Ctrl+Q")
        
        # Audio/Video Menu
        av_menu = menubar.addMenu("&Audio/Video")
        volume_submenu = av_menu.addMenu("[VOL] Volume")
        volume_submenu.addAction("[+] Volume Up", self.vol_up, "+")
        volume_submenu.addAction("[-] Volume Down", self.vol_down, "-")
        volume_submenu.addAction("[MUTE] Mute/Unmute", self.mute, "M")
        av_menu.addSeparator()
        av_menu.addAction("[SUB] Toggle &Subtitles", self.tog_subs, "S")
        av_menu.addSeparator()
        av_menu.addAction("[FULL] &Fullscreen", self.toggle_fs, "F11")
        av_menu.addAction("[INFO] Program &Info", self.toggle_info, "Ctrl+I")

        # View Menu - zoom controls
        view_menu = menubar.addMenu("&View")
        view_menu.addAction("[ZOOM+] Zoom In", self.guide.zoom_in, "Ctrl+=")
        view_menu.addAction("[ZOOM-] Zoom Out", self.guide.zoom_out, "Ctrl+-")
        
        # Tools Menu
        tools_menu = menubar.addMenu("&Tools")
        remote_submenu = tools_menu.addMenu("[REMOTE] Remote Controls")
        remote_submenu.addAction("[WEB] Web &Remote", self.toggle_remote, "Tab")
        remote_submenu.addAction("[DEV] &Developer Remote", self.toggle_dev_remote)
        remote_submenu.addAction("[RESTART] &Restart Web Server", self.restart_web_server)
        tools_menu.addSeparator()
        tools_menu.addAction("[LOG] Show &Console", self.console.show, "Ctrl+`")
        
        # Settings Menu
        settings_menu = menubar.addMenu("&Settings")
        settings_menu.addAction("[PREF] &Preferences...", self.show_settings, "Ctrl+P")
        settings_menu.addAction("[KEYS] &Hotkeys...", self.show_hotkeys, "Ctrl+H")
        
        # Help Menu
        help_menu = menubar.addMenu("&Help")
        help_menu.addAction("[?] &Quick Help", self.show_quick_help, "F1")
        help_menu.addAction("[i] &About Infinite Tv", self.show_about)

    def show_hotkeys(self):
        """Show hotkey configuration dialog."""
        dialog = HotkeyDialog(self.hotkeys, self.DEFAULT_KEYS, self)
        if dialog.exec_() == QDialog.Accepted:
            self.hotkeys = dialog.result()
            self._save_hotkeys()
            self._bind_keys()
            self._osd("Hotkeys Updated")

    def show_quick_help(self):
        """Show quick help dialog."""
        help_text = """[TV] Infinite Tv - Quick Help

[BASIC] BASIC CONTROLS:
• G - Open TV Guide  
• O - Open OnDemand (press again to stop)
• Page Up/Down - Change channels
• Ctrl+L - Last channel
• Space - Play/Pause
• F11 - Fullscreen
• Tab - Toggle remote control

[VOL] VOLUME:
• + - Volume up
• - - Volume down  
• M - Mute/unmute

[WEB] WEB REMOTE:
• Access from mobile device
• Full volume controls
• Media browser
• Server restart capability

[OTHER] OTHER:
• S - Toggle subtitles
• Ctrl+I - Program info
• Ctrl+` - Show console
• F5 - Reload channels
• Ctrl+R - Reload schedule

[FEATURES] TRUE LIVE TV:
• All channels play simultaneously
• Switch channels to join programs in progress
• Just like real television!
• Programs continue playing even when not watching
• Synchronized schedules across all channels
• Sequential playback with optional ad breaks

[TIPS] TIPS:
• Next/Previous buttons work differently in Live TV mode
• Previous restarts current program from beginning
• Use TV Guide to see what's on all channels
• OnDemand for on-demand viewing outside schedule
"""
        
        msg = QMessageBox(self)
        msg.setWindowTitle("[HELP] Quick Help")
        msg.setText(help_text)
        msg.setStyleSheet("""
            QMessageBox {
                background-color: #000000;
                color: #00ff00;
            }
            QMessageBox QLabel {
                color: #00ff00;
                font-family: "Consolas", monospace;
            }
            QPushButton {
                background-color: #001100;
                color: #00ff00;
                border: 2px solid #00ff00;
                padding: 6px 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #003300;
            }
        """)
        msg.exec_()

    def show_about(self):
        """Show enhanced about dialog."""
        about_text = f"""
<h2 style="color: #00ff00;">[TV] Infinite Tv</h2>
<p><b>Version:</b> r45-COMPLETE FIXED EDITION v4 - TRUE LIVE TV</p>
<p><b>Release Date:</b> 2025-06-02</p>

<h3 style="color: #00ff00;">[NEW] True Live TV Implementation:</h3>
<ul>
<li>[OK] FIXED: All channels run simultaneously from synchronized schedule</li>
<li>[OK] FIXED: Channel switching joins programs already in progress</li>
<li>[OK] FIXED: Proper seeking with verification and retry mechanism</li>
<li>[OK] FIXED: Programs continue from correct position after ads</li>
<li>[OK] ENHANCED: Debug logging for playback positioning</li>
</ul>

<h3 style="color: #00ff00;">[PREV] Previous Fixes:</h3>
<ul>
<li>[OK] Single-click next video navigation</li>
<li>[OK] Sequential video playback (no random order)</li>
<li>[OK] Channels start playing immediately (no standby)</li>
<li>[OK] Continuous playback loop when no ads</li>
<li>[OK] OnDemand channel stops playback when revisited</li>
<li>[OK] Complete Matrix theme throughout application</li>
<li>[OK] Web remote IP popup at startup</li>
</ul>

<h3 style="color: #00ff00;">[FEATURES] Core Features:</h3>
<ul>
<li>[OK] TRUE LIVE TV - All channels synchronized like broadcast TV</li>
<li>[OK] Sequential TV playback with optional ad breaks</li>
<li>[OK] 12-hour program guide showing live schedule</li>
<li>[OK] OnDemand content browser</li>
<li>[OK] Web Remote Server for mobile devices</li>
<li>[OK] Infinite Tv Network Editor with icon management</li>
<li>[OK] Subtitle support</li>
<li>[OK] Channel logos</li>
</ul>

<h3 style="color: #00ff00;">[INFO] System Info:</h3>
<p><b>Channels:</b> {len(self.channels_real)} loaded</p>
<p><b>Current Channel:</b> {self.ch_idx}</p>
<p><b>Web Server:</b> {'Running' if self.flask_manager.is_running else 'Stopped'}</p>
<p><b>Schedule Start:</b> {self.global_schedule_start.strftime('%Y-%m-%d %H:%M')}</p>
<p><b>Uptime:</b> {str(datetime.now() - self.startup_time).split('.')[0]}</p>

<p style="color: #39ff14;"><b>[C] 2025 Infinite Tv Project - True Live TV Edition</b></p>
        """
        
        msg = QMessageBox(self)
        msg.setWindowTitle("[ABOUT] About Infinite Tv")
        msg.setTextFormat(Qt.RichText)
        msg.setText(about_text)
        msg.setStyleSheet("""
            QMessageBox {
                background-color: #000000;
                color: #00ff00;
            }
            QMessageBox QLabel {
                color: #00ff00;
            }
            QPushButton {
                background-color: #001100;
                color: #00ff00;
                border: 2px solid #00ff00;
                padding: 6px 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #003300;
            }
        """)
        msg.exec_()

    # ── FILE OPERATIONS ──────────────────────────────────
    def open_channels_folder(self):
        """Open the channels folder in the system file explorer."""
        try:
            open_in_file_manager(ROOT_CHANNELS)
            logging.info(f"Opened channels folder: {ROOT_CHANNELS}")
        except Exception as e:
            logging.error(f"Failed to open channels folder: {e}")
            QMessageBox.warning(self, "[ERR] Error",
                f"Could not open channels folder.\nLocation: {ROOT_CHANNELS}\n\nError: {e}")

    def select_channels_folder(self):
        """Allow user to select a different channels folder."""
        global ROOT_CHANNELS
        
        folder = QFileDialog.getExistingDirectory(
            self, "[SEL] Select Channels Folder", str(ROOT_CHANNELS.parent),
            QFileDialog.ShowDirsOnly
        )
        
        if folder:
            self.load_channels_folder(folder)

    def load_channels_folder(self, folder: str):
        """Load a channels folder and remember it."""
        global ROOT_CHANNELS
        ROOT_CHANNELS = Path(folder)
        self.reload_channels()
        self._update_recent_channels(folder)
        self._osd(f"Channels folder changed to: {ROOT_CHANNELS.name}")
        logging.info(f"Channels folder changed to: {ROOT_CHANNELS}")

    def reload_channels(self):
        """Reload channel list and rebuild synchronized schedules."""
        self.channels_real = discover_channels(ROOT_CHANNELS)
        self.channels = [None, "OnDemand"] + self.channels_real
        self._rebuild_logos()
        self.schedules.clear()
        
        # Start a fresh synchronized schedule from now
        self.global_schedule_start = datetime.now()
        
        # Rebuild all schedules
        for channel in self.channels_real:
            self.schedules[channel] = self._build_tv_schedule(channel)
        
        logging.info(f"Reloaded {len(self.channels_real)} channels with synchronized schedules")
        self._osd(f"Found {len(self.channels_real)} channels (synchronized)")
        
        if self.ch_idx == 0:
            self.guide.refresh()

    def show_network_editor(self):
        """Show the TV Network Editor."""
        self.network_editor.show()
        self.network_editor.raise_()
        self.network_editor.activateWindow()

    def show_saved_channels_editor(self):
        """Open saved channels manager."""
        dlg = SavedChannelsDialog(self)
        dlg.exec_()

    # ── WINDOW EVENT HANDLERS ──────────────────────────────────
    def resizeEvent(self, event):
        """Handle window resize."""
        super().resizeEvent(event)
        
        if hasattr(self, 'sub_label'):
            self.sub_label.setGeometry(0, self.video.height() - 100, self.video.width(), 100)
        
        if hasattr(self, 'static_label'):
            self.static_label.setGeometry(self.rect())

        if hasattr(self, 'loading_label') and self.loading_label.isVisible():
            self.loading_label.setGeometry(self.rect())
        
        if hasattr(self, 'info') and self.info.isVisible():
            self._update_info_display()

    def _on_focus_changed(self, old, new):
        if new:
            self.focus_frame.setWidget(new)

    def closeEvent(self, event):
        """Enhanced close event with proper cleanup."""
        try:
            logging.info("Infinite Tv shutting down...")
            
            # Stop Flask server
            if hasattr(self, 'flask_manager') and self.flask_manager.is_running:
                self.flask_manager.stop_server()
            
            # Stop any segment timers
            if hasattr(self, '_segment_timer') and self._segment_timer:
                self._segment_timer.stop()
            
            # Close windows
            for window in [self.remote, self.dev_remote, self.console]:
                if window.isVisible():
                    window.close()
            
            # Save data
            self._save_settings()
            self._save_cache()
            
            super().closeEvent(event)
            
        except Exception as e:
            logging.error(f"Shutdown error: {e}")
            super().closeEvent(event)

# ──────────────────────── MAIN ENTRY POINT ────────────────────────
if __name__ == "__main__":
    try:
        logging.info("[START] Starting Infinite Tv")
        
        app = QApplication(sys.argv)
        app.setApplicationName("Infinite Tv")
        app.setApplicationVersion("r45-complete-fixed")
        app.setOrganizationName("Infinite Tv Project")
        
        tv = TVPlayer()
        tv.show()
        
        exit_code = app.exec_()
        
    except Exception as e:
        logging.exception("Fatal error in Infinite Tv")
        exit_code = 1
    
    sys.exit(exit_code)