"""Content Creator Workspaces module for Clipiest.
Provides dedicated workspaces for creators where videos, clips, settings,
and logs are organized into separate folders:
    data/creators/<creator_id>/
        ├── creator.json
        ├── videos/         (source video archives)
        ├── clips/          (rendered viral short clips)
        └── log.jsonl       (activity history)
"""
import copy
import json
import os
import re
import shutil
import sys
import subprocess
import time
from pathlib import Path
from typing import Optional, Dict, Any, List

from .config import DATA_DIR

CREATORS_DIR = DATA_DIR / "creators"

def ensure_creators_dir() -> Path:
    CREATORS_DIR.mkdir(parents=True, exist_ok=True)
    return CREATORS_DIR

DEFAULT_CREATOR_SETTINGS = {
    "name": "",
    "channel": "",
    "avatar": "",
    "default_layout": "stack",
    "default_caption_style": "bounce",
    "min_len": 15,
    "max_len": 60,
    "game": "",
    "trigger_words": "clip that, clip it, insane, clutch",
    "notes": "",
    "created": 0.0
}

def creator_root(cid: str) -> Path:
    clean_cid = re.sub(r"[^\w\-]", "", str(cid).strip().lower())
    if not clean_cid:
        raise ValueError("Invalid creator ID")
    return ensure_creators_dir() / clean_cid

def get_creator_dirs(cid: str) -> tuple[Path, Path, Path]:
    root = creator_root(cid)
    vdir = root / "videos"
    cdir = root / "clips"
    vdir.mkdir(parents=True, exist_ok=True)
    cdir.mkdir(parents=True, exist_ok=True)
    return root, vdir, cdir

def list_creators() -> List[Dict[str, Any]]:
    """Lists all creators with statistics (clip count, video count, disk usage)."""
    ensure_creators_dir()
    out = []
    
    for c_dir in sorted(CREATORS_DIR.iterdir()):
        if not c_dir.is_dir():
            continue
        cfg_path = c_dir / "creator.json"
        if not cfg_path.exists():
            continue
        try:
            data = json.loads(cfg_path.read_text(encoding="utf-8"))
            cid = data.get("id") or c_dir.name
            
            # Count clips
            clips_dir = c_dir / "clips"
            clip_count = len(list(clips_dir.glob("*.mp4"))) if clips_dir.exists() else 0
            
            # Count videos
            videos_dir = c_dir / "videos"
            video_count = len(list(videos_dir.glob("*.mp4"))) + len(list(videos_dir.glob("*.mkv"))) + len(list(videos_dir.glob("*.webm"))) if videos_dir.exists() else 0
            
            # Disk usage
            total_bytes = 0
            for f in c_dir.rglob("*"):
                if f.is_file():
                    try:
                        total_bytes += f.stat().st_size
                    except OSError:
                        pass
            disk_mb = round(total_bytes / (1024 * 1024), 1)
            
            out.append({
                **DEFAULT_CREATOR_SETTINGS,
                **data,
                "id": cid,
                "clip_count": clip_count,
                "video_count": video_count,
                "disk_mb": disk_mb,
                "folder_path": str(c_dir.resolve())
            })
        except Exception:
            continue
            
    return sorted(out, key=lambda c: c.get("name", "").lower())

def get_creator(cid: str) -> Optional[Dict[str, Any]]:
    """Returns single creator details including folders and stats."""
    try:
        root = creator_root(cid)
    except ValueError:
        return None
    cfg_path = root / "creator.json"
    if not cfg_path.exists():
        return None
    try:
        data = json.loads(cfg_path.read_text(encoding="utf-8"))
        cid = data.get("id") or root.name
        clips_dir = root / "clips"
        videos_dir = root / "videos"
        
        clip_count = len(list(clips_dir.glob("*.mp4"))) if clips_dir.exists() else 0
        video_count = len(list(videos_dir.glob("*.mp4"))) + len(list(videos_dir.glob("*.mkv"))) if videos_dir.exists() else 0
        
        total_bytes = 0
        for f in root.rglob("*"):
            if f.is_file():
                try:
                    total_bytes += f.stat().st_size
                except OSError:
                    pass
        disk_mb = round(total_bytes / (1024 * 1024), 1)
        
        return {
            **DEFAULT_CREATOR_SETTINGS,
            **data,
            "id": cid,
            "clip_count": clip_count,
            "video_count": video_count,
            "disk_mb": disk_mb,
            "folder_path": str(root.resolve()),
            "logs": get_creator_logs(cid, limit=20)
        }
    except Exception:
        return None

def create_creator(data: Dict[str, Any]) -> Dict[str, Any]:
    """Creates a new isolated creator workspace with dedicated videos and clips folders."""
    name = str(data.get("name", "")).strip()
    if not name:
        raise ValueError("Creator name cannot be empty.")
        
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40] or "creator"
    cid = slug
    counter = 2
    while (ensure_creators_dir() / cid).exists():
        cid = f"{slug}-{counter}"
        counter += 1
        
    root, vdir, cdir = get_creator_dirs(cid)
    
    creator_obj = {
        **DEFAULT_CREATOR_SETTINGS,
        "id": cid,
        "name": name,
        "channel": str(data.get("channel", "")).strip(),
        "avatar": str(data.get("avatar", "")).strip(),
        "default_layout": str(data.get("default_layout", "stack")).strip(),
        "default_caption_style": str(data.get("default_caption_style", "bounce")).strip(),
        "min_len": max(5, min(180, int(data.get("min_len", 15)))),
        "max_len": max(10, min(180, int(data.get("max_len", 60)))),
        "game": str(data.get("game", "")).strip(),
        "trigger_words": str(data.get("trigger_words", "clip that, clip it, insane, clutch")).strip(),
        "notes": str(data.get("notes", "")).strip(),
        "created": time.time()
    }
    
    (root / "creator.json").write_text(json.dumps(creator_obj, indent=2), encoding="utf-8")
    log_creator_event(cid, f"Workspace created for creator '{name}'", action="created")
    
    return {
        **creator_obj,
        "clip_count": 0,
        "video_count": 0,
        "disk_mb": 0.0,
        "folder_path": str(root.resolve())
    }

def update_creator(cid: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Updates settings and preferences for an existing creator."""
    root = creator_root(cid)
    cfg_path = root / "creator.json"
    if not cfg_path.exists():
        raise KeyError(f"Creator '{cid}' not found")
        
    current = json.loads(cfg_path.read_text(encoding="utf-8"))
    
    for key in ("name", "channel", "avatar", "default_layout", "default_caption_style", "game", "trigger_words", "notes"):
        if key in data:
            current[key] = str(data[key]).strip()
    if "min_len" in data:
        current["min_len"] = max(5, min(180, int(data["min_len"])))
    if "max_len" in data:
        current["max_len"] = max(10, min(180, int(data["max_len"])))
        
    cfg_path.write_text(json.dumps(current, indent=2), encoding="utf-8")
    log_creator_event(cid, "Settings updated", action="update")
    return get_creator(cid) or current

def delete_creator(cid: str) -> bool:
    """Deletes creator workspace and all associated folders."""
    root = creator_root(cid)
    if not root.exists():
        return False
    shutil.rmtree(root, ignore_errors=True)
    return True

def open_creator_folder(cid: str) -> bool:
    """Opens creator directory in the host OS File Explorer."""
    root = creator_root(cid)
    if not root.exists():
        root.mkdir(parents=True, exist_ok=True)
    p = str(root.resolve())
    try:
        if sys.platform == "win32":
            os.startfile(p)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", p])
        else:
            subprocess.Popen(["xdg-open", p])
        return True
    except Exception:
        return False

def log_creator_event(cid: str, msg: str, action: str = "info"):
    """Appends an event to the creator's log.jsonl file."""
    try:
        root = creator_root(cid)
        if not root.exists():
            return
        log_file = root / "log.jsonl"
        with log_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"time": time.time(), "action": action, "msg": msg}) + "\n")
    except Exception:
        pass

def get_creator_logs(cid: str, limit: int = 50) -> List[Dict[str, Any]]:
    """Returns the latest activity logs for the creator."""
    try:
        root = creator_root(cid)
        log_file = root / "log.jsonl"
        if not log_file.exists():
            return []
        lines = log_file.read_text(encoding="utf-8", errors="ignore").splitlines()
        out = []
        for line in reversed(lines[-limit:]):
            if line.strip():
                try:
                    out.append(json.loads(line))
                except Exception:
                    pass
        return out
    except Exception:
        return []

def get_creator_clips(cid: str) -> List[Dict[str, Any]]:
    """Returns all rendered clips residing inside this creator's clips/ folder."""
    try:
        root = creator_root(cid)
        clips_dir = root / "clips"
        if not clips_dir.exists():
            return []
        records = []
        for jf in clips_dir.glob("*.json"):
            try:
                data = json.loads(jf.read_text(encoding="utf-8"))
                mp4 = jf.with_suffix(".mp4")
                if not mp4.exists():
                    continue
                result = data.get("result", {})
                settings = data.get("settings", {})
                records.append({
                    "id": jf.stem,
                    "title": settings.get("title") or "Creator Clip",
                    "hook": settings.get("hook", ""),
                    "layout": settings.get("layout", "stack"),
                    "caption_style": settings.get("caption_style", "bounce"),
                    "created": jf.stat().st_mtime,
                    "duration": result.get("duration", 0),
                    "file": f"/media/creators/{cid}/clips/{jf.stem}.mp4",
                    "cover": f"/media/creators/{cid}/clips/{jf.stem}.jpg" if (jf.with_suffix(".jpg")).exists() else None,
                    "srt": f"/text/{jf.stem}/srt",
                    "settings": settings,
                    "creator": cid
                })
            except Exception:
                continue
        return sorted(records, key=lambda x: x["created"], reverse=True)
    except Exception:
        return []

def get_creator_videos(cid: str) -> List[Dict[str, Any]]:
    """Returns all source archive videos residing inside this creator's videos/ folder."""
    try:
        root = creator_root(cid)
        videos_dir = root / "videos"
        if not videos_dir.exists():
            return []
        records = []
        for vf in list(videos_dir.glob("*.mp4")) + list(videos_dir.glob("*.mkv")) + list(videos_dir.glob("*.webm")):
            try:
                st = vf.stat()
                size_mb = round(st.st_size / (1024 * 1024), 1)
                records.append({
                    "name": vf.name,
                    "stem": vf.stem,
                    "size_mb": size_mb,
                    "modified": st.st_mtime,
                    "file": f"/media/creators/{cid}/videos/{vf.name}",
                    "path": str(vf.resolve()),
                    "creator": cid
                })
            except Exception:
                continue
        return sorted(records, key=lambda x: x["modified"], reverse=True)
    except Exception:
        return []
