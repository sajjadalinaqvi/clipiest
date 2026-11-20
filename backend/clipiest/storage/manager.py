"""Storage directory manager and disk telemetry for Clipiest."""
import os
import shutil
import sys
import subprocess
from pathlib import Path
from ..config import DATA_DIR

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
