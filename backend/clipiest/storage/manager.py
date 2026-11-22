"""Storage directory manager and disk telemetry for Clipiest."""
import os
import shutil
import sys
import time
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any, List
from ..config import DATA_DIR, DOWNLOADS_DIR

PROTECTED_STORAGE_FILENAMES = {
    "config.json",
    "cookies.txt",
    "weights.json",
    "feedback.jsonl",
    "creators.json",
    "creator.json",
    "profile.json",
    "ai.json",
    "social_accounts.json",
    "CACHEDIR.TAG",
}

PROTECTED_STORAGE_DIRS = {
    "models",
    ".git",
    ".locks",
}

def is_protected_storage_file(p: Path) -> bool:
    """Returns True if the file is a sensitive system configuration, model weight, or creator profile."""
    if p.name in PROTECTED_STORAGE_FILENAMES:
        return True
    if any(part in PROTECTED_STORAGE_DIRS for part in p.parts):
        return True
    if p.suffix.lower() in (".env", ".key", ".token", ".py", ".pyc"):
        return True
    if "creators" in p.parts and p.suffix.lower() == ".json":
        return True
    return False

_last_cleanup_time = 0.0

def cleanup_on_shutdown(data_dir: Optional[Path] = None, downloads_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Automatically cleans up all generated clipping artifacts, downloaded videos/audio,
    thumbnails, slice JSON files, and ASS/SRT subtitles when the server shuts down.
    Strictly preserves protected configurations, Whisper models, and creator profiles.
    """
    global _last_cleanup_time
    now = time.time()
    # Throttle default shutdown invocations to avoid redundant double-execution between lifespan and atexit
    if data_dir is None and downloads_dir is None:
        if now - _last_cleanup_time < 2.0:
            return {"deleted_files": 0, "deleted_dirs": 0}
        _last_cleanup_time = now

    d_dir = Path(data_dir) if data_dir else DATA_DIR
    dl_dir = Path(downloads_dir) if downloads_dir else DOWNLOADS_DIR

    deleted_files = 0
    deleted_dirs = 0

    if not d_dir.exists():
        return {"deleted_files": 0, "deleted_dirs": 0}

    def safe_unlink(p: Path) -> bool:
        nonlocal deleted_files
        if not p.is_file():
            return False
        if is_protected_storage_file(p):
            return False
        try:
            p.unlink(missing_ok=True)
            deleted_files += 1
            return True
        except OSError:
            return False

    # 1. Purge exports directory (clipped videos, thumbnails, .ass, .srt, .json)
    exports_dir = d_dir / "exports"
    if exports_dir.exists():
        for item in exports_dir.glob("*"):
            if item.is_file():
                safe_unlink(item)
            elif item.is_dir() and item.name not in PROTECTED_STORAGE_DIRS:
                shutil.rmtree(item, ignore_errors=True)
                deleted_dirs += 1
        exports_dir.mkdir(parents=True, exist_ok=True)

    # 2. Purge slices directory (sliced videos, thumbnails, _words.json, .json)
    slices_dir = d_dir / "slices"
    if slices_dir.exists():
        for item in slices_dir.glob("*"):
            if item.is_file():
                safe_unlink(item)
            elif item.is_dir() and item.name not in PROTECTED_STORAGE_DIRS:
                shutil.rmtree(item, ignore_errors=True)
                deleted_dirs += 1
        slices_dir.mkdir(parents=True, exist_ok=True)

    # 3. Purge tmp directory (frames, scout audio cuts, temp wavs)
    tmp_dir = d_dir / "tmp"
    if tmp_dir.exists():
        for item in tmp_dir.glob("*"):
            if item.is_file():
                safe_unlink(item)
            elif item.is_dir() and item.name not in PROTECTED_STORAGE_DIRS:
                shutil.rmtree(item, ignore_errors=True)
                deleted_dirs += 1
        tmp_dir.mkdir(parents=True, exist_ok=True)

    # 4. Purge Downloads directory (exported videos copied to Downloads/)
    if dl_dir.exists():
        for item in dl_dir.glob("*"):
            if item.is_file() and not is_protected_storage_file(item):
                ext = item.suffix.lower()
                if ext in (
                    ".mp4", ".mkv", ".webm", ".avi", ".mov",
                    ".wav", ".m4a", ".mp3", ".aac", ".ogg",
                    ".ass", ".srt", ".jpg", ".jpeg", ".png", ".webp", ".json"
                ):
                    safe_unlink(item)
        dl_dir.mkdir(parents=True, exist_ok=True)

    # 5. Clean creator workspaces: clear clips/ and videos/ subfolders, preserve creator.json / profile.json
    creators_dir = d_dir / "creators"
    if creators_dir.exists():
        for c_dir in creators_dir.iterdir():
            if c_dir.is_dir():
                for sub_name in ("clips", "videos"):
                    sub_p = c_dir / sub_name
                    if sub_p.exists():
                        for item in sub_p.glob("*"):
                            if item.is_file() and not is_protected_storage_file(item):
                                safe_unlink(item)
                            elif item.is_dir() and item.name not in PROTECTED_STORAGE_DIRS:
                                shutil.rmtree(item, ignore_errors=True)
                                deleted_dirs += 1
                        sub_p.mkdir(parents=True, exist_ok=True)

    # 6. Purge yt_* folders, preview folders, and other generated job directories in d_dir
    for item in list(d_dir.iterdir()):
        if item.is_dir():
            if item.name in PROTECTED_STORAGE_DIRS:
                continue
            if item.name in ("exports", "slices", "tmp", "creators"):
                continue
            shutil.rmtree(item, ignore_errors=True)
            deleted_dirs += 1

    # 7. Clean loose media, ass/srt, thumbnail, and temporary metadata files directly in root d_dir
    for item in list(d_dir.iterdir()):
        if item.is_file() and not is_protected_storage_file(item):
            ext = item.suffix.lower()
            if ext in (
                ".mp4", ".mkv", ".webm", ".avi", ".mov",
                ".wav", ".m4a", ".mp3", ".aac", ".ogg",
                ".ass", ".srt", ".jpg", ".jpeg", ".png", ".webp", ".json"
            ):
                safe_unlink(item)

    print(f"[Clipiest] Shutdown cleanup complete: deleted {deleted_files} files and {deleted_dirs} directories.")
    return {"deleted_files": deleted_files, "deleted_dirs": deleted_dirs}

def get_storage_info() -> dict:
    try:
        usage = shutil.disk_usage(DATA_DIR)
        free_gb = round(usage.free / (1024 ** 3), 1)
        total_gb = round(usage.total / (1024 ** 3), 1)
    except Exception:
        free_gb, total_gb = 50.0, 500.0
        
    return {
        "path": str(DATA_DIR.resolve()),
        "free_gb": free_gb,
        "total_gb": total_gb,
        "min_free_gb": 3.0,
        "is_full": free_gb < 3.0
    }

def open_storage_folder(folder_path=None):
    """Opens directory in operating system's native file explorer."""
    target = Path(folder_path) if folder_path else DATA_DIR
    target.mkdir(parents=True, exist_ok=True)
    p = str(target.resolve())
    if sys.platform == "win32":
        os.startfile(p)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", p])
    else:
        subprocess.Popen(["xdg-open", p])

def get_disk_info(data_dir=None) -> dict:
    return get_storage_info()

def open_folder_in_os(data_dir=None) -> bool:
    try:
        open_storage_folder(data_dir)
        return True
    except Exception:
        return False
