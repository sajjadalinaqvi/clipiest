"""Configuration and hardware auto-detection for Clipiest."""
import os
import sys
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
BACKEND_DIR = Path(__file__).resolve().parent.parent

def _load_dotenv():
    env_file = ROOT / ".env"
    if not env_file.exists():
        env_file = BACKEND_DIR / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

_load_dotenv()
env = os.environ.get

# Directories
DATA_DIR_ENV = env("CLIPIEST_DATA") or env("PEAKCUT_DATA") or env("NEONCLIPPING_DATA")
if DATA_DIR_ENV:
    DATA_DIR = Path(DATA_DIR_ENV).resolve()
else:
    DATA_DIR = (ROOT / "data").resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)

FONTS_DIR = (BACKEND_DIR / "fonts").resolve()
FONTS_DIR.mkdir(parents=True, exist_ok=True)

MODELS_DIR = DATA_DIR / "models"
MODELS_DIR.mkdir(parents=True, exist_ok=True)

TMP_DIR = DATA_DIR / "tmp"
TMP_DIR.mkdir(parents=True, exist_ok=True)

# Server
HOST = env("CLIPIEST_HOST", "127.0.0.1")
PORT = int(env("CLIPIEST_PORT", "8780"))
PUBLIC_URL = (env("CLIPIEST_PUBLIC_URL", f"http://{HOST}:{PORT}")).rstrip("/")

# AI Settings (defaults to Gemini or Ollama)
AI_PROVIDER = env("CLIPIEST_AI_PROVIDER", env("PEAKCUT_AI_PROVIDER", "gemini")).strip().lower()
AI_KEY = env("CLIPIEST_AI_KEY", env("PEAKCUT_AI_KEY", ""))
AI_MODELS = [m.strip() for m in (env("CLIPIEST_AI_MODELS") or env("PEAKCUT_AI_MODELS") or "gemini-2.5-flash,gpt-4o-mini,llama3.2:3b").split(",") if m.strip()]
AI_BASE_URL = (env("CLIPIEST_AI_BASE_URL") or env("PEAKCUT_AI_BASE_URL") or "").rstrip("/")

# ASR Model Settings
ASR_ENGINE = env("CLIPIEST_ASR_ENGINE", "faster_whisper")  # faster_whisper | sherpa_onnx
WHISPER_MODEL = env("CLIPIEST_WHISPER_MODEL", "large-v3-turbo")
USE_CPU = env("CLIPIEST_CPU", "0") == "1"

# Video Defaults
OUT_W = 1080
OUT_H = 1920
OUT_FPS = 30
PAD_SEC = 4.0
FAST_OVER_SEC = 600  # Videos > 10 min download audio first

# Allowed Video Sites
ALLOWED_SITES = ("youtube.com", "youtu.be", "twitch.tv", "kick.com")

# Hardware Acceleration Check
def check_nvenc() -> bool:
    if USE_CPU:
        return False
    try:
        r = subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "nullsrc=s=64x64:d=1", "-c:v", "h264_nvenc", "-f", "null", "-"], capture_output=True, timeout=5)
        return r.returncode == 0
    except Exception:
        return False

def check_qsv() -> bool:
    if USE_CPU:
        return False
    try:
        r = subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "nullsrc=s=64x64:d=1", "-c:v", "h264_qsv", "-f", "null", "-"], capture_output=True, timeout=5)
        return r.returncode == 0
    except Exception:
        return False

HAS_NVENC = check_nvenc()
HAS_QSV = False if HAS_NVENC else check_qsv()

# Setup CUDA DLL paths on Windows if present
if sys.platform == "win32":
    site = Path(sys.prefix) / "Lib" / "site-packages" / "nvidia"
    for sub in ("cublas", "cudnn"):
        b = site / sub / "bin"
        if b.exists():
            try:
                os.add_dll_directory(str(b))
            except (OSError, AttributeError):
                pass
            os.environ["PATH"] = str(b) + os.pathsep + os.environ.get("PATH", "")
