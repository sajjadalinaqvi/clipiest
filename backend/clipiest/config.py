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

DOWNLOADS_DIR = (ROOT / "Downloads").resolve()
DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)

# Server
HOST = env("CLIPIEST_HOST", "127.0.0.1")
PORT = int(env("CLIPIEST_PORT", "8780"))
PUBLIC_URL = (env("CLIPIEST_PUBLIC_URL", f"http://{HOST}:{PORT}")).rstrip("/")

CONFIG_FILE = DATA_DIR / "config.json"

WHISPER_MODELS = [
    "large-v3-turbo",
    "large-v3",
    "medium",
    "small",
    "base",
    "tiny"
]

def _try_import_peakcut_ai() -> dict | None:
    """Attempts to auto-discover saved AI settings from PeakCut if present on the system."""
    import json
    candidates = [
        Path(r"D:\notsaju Clips\peakcut\ai.json"),
        Path(r"C:\peakcut\ai.json"),
        Path(r"C:\peakcut\data\ai.json")
    ]
    try:
        stor = Path(r"C:\peakcut\storage.json")
        if stor.exists():
            p = json.loads(stor.read_text(encoding="utf-8")).get("path")
            if p:
                candidates.insert(0, Path(p) / "ai.json")
    except Exception:
        pass
        
    for cand in candidates:
        if cand.exists():
            try:
                d = json.loads(cand.read_text(encoding="utf-8"))
                if isinstance(d, dict) and d.get("base_url"):
                    ms = d.get("models") or []
                    model = ms[0] if ms else "qwen/qwen3.5-9b"
                    prov = "lmstudio" if d.get("provider") in ("custom", "lmstudio") else d.get("provider", "lmstudio")
                    return {
                        "provider": prov,
                        "base_url": d.get("base_url", "http://localhost:1235/v1"),
                        "api_key": d.get("key", "lm-studio"),
                        "model": model
                    }
            except Exception:
                pass
    return None

def load_user_config() -> dict:
    import json
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception:
            pass
            
    pk_ai = _try_import_peakcut_ai()
    if pk_ai:
        imported = {
            "configured": True,
            "ai": pk_ai,
            "whisper": {
                "engine": "faster_whisper",
                "model": "small",
                "use_cpu": False
            }
        }
        try:
            CONFIG_FILE.write_text(json.dumps(imported, indent=2), encoding="utf-8")
        except Exception:
            pass
        return imported

    return {
        "configured": False,
        "ai": {
            "provider": "lmstudio",
            "base_url": "http://localhost:1235/v1",
            "api_key": "lm-studio",
            "model": "qwen/qwen3.5-9b"
        },
        "whisper": {
            "engine": "faster_whisper",
            "model": "large-v3-turbo",
            "use_cpu": False
        }
    }

def save_user_config(cfg: dict) -> dict:
    import json
    global AI_PROVIDER, AI_KEY, AI_MODELS, AI_BASE_URL, WHISPER_MODEL, USE_CPU
    cfg["configured"] = True
    ai_cfg = cfg.get("ai", {})
    AI_PROVIDER = ai_cfg.get("provider", "lmstudio").strip().lower()
    AI_KEY = ai_cfg.get("api_key", "").strip()
    AI_BASE_URL = (ai_cfg.get("base_url", "")).strip().rstrip("/")
    model_name = ai_cfg.get("model", "").strip() or "local-model"
    AI_MODELS = [model_name]

    whisper_cfg = cfg.get("whisper", {})
    WHISPER_MODEL = whisper_cfg.get("model", "large-v3-turbo")
    USE_CPU = bool(whisper_cfg.get("use_cpu", False))

    CONFIG_FILE.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    return cfg

def is_configured() -> bool:
    cfg = load_user_config()
    return bool(cfg.get("configured", False))

# Initial runtime values loaded from config.json or fallback
_initial_cfg = load_user_config()
if _initial_cfg.get("configured"):
    _ai = _initial_cfg.get("ai", {})
    AI_PROVIDER = _ai.get("provider", "lmstudio").strip().lower()
    AI_KEY = _ai.get("api_key", "").strip()
    AI_BASE_URL = (_ai.get("base_url", "")).strip().rstrip("/")
    AI_MODELS = [_ai.get("model", "").strip() or "local-model"]
    _wh = _initial_cfg.get("whisper", {})
    WHISPER_MODEL = _wh.get("model", "large-v3-turbo")
    USE_CPU = bool(_wh.get("use_cpu", False))
else:
    # Defaults prior to user initial setup
    AI_PROVIDER = env("CLIPIEST_AI_PROVIDER", "lmstudio").strip().lower()
    AI_KEY = env("CLIPIEST_AI_KEY", "")
    AI_MODELS = [m.strip() for m in (env("CLIPIEST_AI_MODELS") or "local-model").split(",") if m.strip()]
    AI_BASE_URL = (env("CLIPIEST_AI_BASE_URL") or "http://127.0.0.1:1234/v1").rstrip("/")
    WHISPER_MODEL = env("CLIPIEST_WHISPER_MODEL", "large-v3-turbo")
    USE_CPU = env("CLIPIEST_CPU", "0") == "1"

# ASR Model Settings
ASR_ENGINE = env("CLIPIEST_ASR_ENGINE", "faster_whisper")  # faster_whisper | sherpa_onnx

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
