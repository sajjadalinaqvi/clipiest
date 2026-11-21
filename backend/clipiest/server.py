"""Clipiest Master API Server.
Unifies PeakCut's job engine, live stream ingestion, and telemetry with
NeonClipping's interactive visual cropping, 11 layouts, and re-edit workflows.
"""
import os
import sys
import json
import uuid
import time
import math
import shutil
import threading
import subprocess
import re
import urllib.request
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from .config import (
    DATA_DIR, ROOT, BACKEND_DIR, TMP_DIR, DOWNLOADS_DIR, HOST, PORT, PUBLIC_URL,
    HAS_NVENC, HAS_QSV, AI_PROVIDER, AI_MODELS, AI_BASE_URL, AI_KEY, WHISPER_MODEL,
    load_user_config, save_user_config, is_configured, WHISPER_MODELS,
    COOKIES_FILE, get_cookies_file
)
from .pipeline.orchestrator import run_clip_pipeline
from .pipeline.queue import JobQueue, SystemMonitor
from .pipeline.downloader import get_ytdl
from .rendering.layouts import CATALOG, LAYOUT_IDS, geometry, text_positions, render_graph
from .rendering.captions import STYLES, write_subtitles
from .rendering.render import render_clip, probe_video
from .rendering.reedit import attach_reedit, find_file
from .vision.previews import extract_storyboard, extract_seek_frame, preview_video_url, extract_youtube_id
from .vision.facecam import detect_facecam
from .ai.learn import record_feedback, load_weights
from .ai.providers import list_supported_providers, test_llm_connection, fetch_models_from_provider, fetch_models_with_url
from .live.session import LiveClipManager
from .storage.manager import get_disk_info, open_folder_in_os
from . import creators

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        yield
    except (asyncio.CancelledError, KeyboardInterrupt):
        pass

app = FastAPI(title="Clipiest API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND_DIR = ROOT / "frontend"
state: Dict[str, Any] = {}
live_managers: Dict[str, LiveClipManager] = {}

# Attach Re-Edit system
attach_reedit(app, DATA_DIR, state)

# -------------------------------------------------------------
# Helpers
# -------------------------------------------------------------
def find_clip_file(filename: str) -> Optional[Path]:
    p = DATA_DIR / filename
    if p.exists():
        return p
    try:
        for sub in DATA_DIR.iterdir():
            if sub.is_dir() and sub.name != "models":
                cand = sub / filename
                if cand.exists():
                    return cand
                if sub.name == "creators":
                    for c_dir in sub.iterdir():
                        if c_dir.is_dir():
                            for child_name in ("clips", "videos"):
                                cand2 = c_dir / child_name / filename
                                if cand2.exists():
                                    return cand2
    except OSError:
        pass
    return None

def find_clip_id(id_str: str, suffix: str = ".mp4") -> Optional[Path]:
    return find_clip_file(id_str + suffix)

def get_source_file(source_id: str) -> Optional[Path]:
    return find_clip_file(f"{source_id}.mp4")

# -------------------------------------------------------------
# Content Creator Workspaces Endpoints
# -------------------------------------------------------------
@app.get("/api/creators")
def api_list_creators():
    return creators.list_creators()

@app.post("/api/creators")
def api_create_creator(body: dict):
    if not isinstance(body, dict):
        raise HTTPException(400, "Invalid JSON body.")
    try:
        return creators.create_creator(body)
    except ValueError as e:
        raise HTTPException(400, str(e))

@app.get("/api/creators/{cid}")
def api_get_creator(cid: str):
    c = creators.get_creator(cid)
    if not c:
        raise HTTPException(404, f"Creator '{cid}' not found.")
    return c

@app.put("/api/creators/{cid}")
def api_update_creator(cid: str, body: dict):
    if not isinstance(body, dict):
        raise HTTPException(400, "Invalid JSON body.")
    try:
        return creators.update_creator(cid, body)
    except KeyError:
        raise HTTPException(404, f"Creator '{cid}' not found.")
    except ValueError as e:
        raise HTTPException(400, str(e))

@app.delete("/api/creators/{cid}")
def api_delete_creator(cid: str):
    ok = creators.delete_creator(cid)
    if not ok:
        raise HTTPException(404, f"Creator '{cid}' not found.")
    return {"deleted": True, "id": cid}

@app.post("/api/creators/{cid}/open-folder")
def api_open_creator_folder(cid: str):
    ok = creators.open_creator_folder(cid)
    return {"success": ok, "id": cid}

@app.get("/api/creators/{cid}/clips")
def api_get_creator_clips(cid: str):
    return creators.get_creator_clips(cid)

@app.get("/api/creators/{cid}/videos")
def api_get_creator_videos(cid: str):
    return creators.get_creator_videos(cid)

@app.get("/api/creators/{cid}/logs")
def api_get_creator_logs(cid: str, limit: int = 50):
    return creators.get_creator_logs(cid, limit=limit)

# -------------------------------------------------------------
# Configuration & Setup Gate Endpoints
# -------------------------------------------------------------
@app.get("/api/config")
def get_system_config():
    cfg = load_user_config()
    return {
        **cfg,
        "whisper_models": WHISPER_MODELS,
        "providers": list_supported_providers()
    }

@app.post("/api/config")
def update_system_config(body: dict):
    if not isinstance(body, dict):
        raise HTTPException(400, "Invalid JSON body.")
    saved = save_user_config(body)
    return {"success": True, "config": saved}

@app.post("/api/llm/test")
def api_test_llm(body: dict):
    provider = body.get("provider", "lmstudio")
    base_url = body.get("base_url", "")
    api_key = body.get("api_key", "")
    model = body.get("model", "")
    return test_llm_connection(provider, base_url, api_key, model)

@app.get("/api/llm/ping")
def api_llm_ping():
    """Lightweight ambient check to see if the LLM provider/server is alive without generating tokens."""
    cfg = load_user_config()
    ai_cfg = cfg.get("ai", {})
    provider = (ai_cfg.get("provider") or AI_PROVIDER or "lmstudio").lower().strip()
    base_url = (ai_cfg.get("base_url") or AI_BASE_URL or PROVIDERS.get(provider, "http://localhost:1235/v1")).rstrip("/")
    api_key = ai_cfg.get("api_key") or AI_KEY or ""
    model = ai_cfg.get("model") or AI_MODELS[0]
    try:
        models, working_url = fetch_models_with_url(provider, base_url, api_key)
        is_ok = bool(models)
        return {
            "success": is_ok,
            "provider": provider,
            "model": model,
            "models_count": len(models),
            "base_url": working_url
        }
    except Exception as e:
        return {
            "success": False,
            "provider": provider,
            "model": model,
            "error": explain_ai_error(e, provider)
        }

@app.get("/api/llm/models")
def api_get_llm_models(provider: str = "lmstudio", base_url: str = "", api_key: str = ""):
    models, working_url = fetch_models_with_url(provider, base_url, api_key)
    return {"provider": provider, "models": models, "base_url": working_url}

# -------------------------------------------------------------
# System & Telemetry Endpoints
# -------------------------------------------------------------
@app.get("/api/telemetry")
def get_telemetry():
    sys_metrics = SystemMonitor.get_metrics()
    disk_info = get_disk_info(DATA_DIR)
    active_jobs = sum(1 for v in state.values() if isinstance(v, dict) and v.get("status") == "running")
    cfg = load_user_config()
    ai_cfg = cfg.get("ai", {})
    wh_cfg = cfg.get("whisper", {})
    return {
        **sys_metrics,
        "disk": disk_info,
        "active_jobs": active_jobs,
        "configured": is_configured(),
        "hardware": {
            "nvenc": HAS_NVENC,
            "qsv": HAS_QSV,
            "whisper_model": wh_cfg.get("model", WHISPER_MODEL),
            "ai_provider": ai_cfg.get("provider", AI_PROVIDER),
            "ai_models": [ai_cfg.get("model", "local-model")]
        }
    }

@app.get("/api/open-folder")
def api_open_folder():
    ok = open_folder_in_os(DATA_DIR)
    return {"success": ok, "path": str(DATA_DIR)}

# -------------------------------------------------------------
# Video Upload & Previews
# -------------------------------------------------------------
@app.post("/upload")
@app.post("/api/upload")
async def upload_video(file: UploadFile = File(...), creator: Optional[str] = Form(None)):
    source_id = uuid.uuid4().hex[:12]
    import re
    safe_name = re.sub(r"[^\w\- ]", "_", Path(file.filename or "upload").stem).strip()[:40].strip(" _") or "upload"
    
    if creator:
        c_root, c_videos, c_clips = creators.get_creator_dirs(creator)
        vdir = c_videos
        target_path = vdir / f"{source_id}.mp4"
    else:
        vdir = DATA_DIR / f"{safe_name}_{source_id[:8]}"
        vdir.mkdir(parents=True, exist_ok=True)
        target_path = vdir / f"{source_id}.mp4"
    
    try:
        with target_path.open("wb") as out:
            while chunk := await file.read(4 * 1024 * 1024):
                out.write(chunk)
        meta = probe_video(target_path)
        if creator:
            creators.log_creator_event(creator, f"Uploaded video '{file.filename}' ({round(meta.get('duration', 0))}s)", action="upload")
    except asyncio.CancelledError:
        target_path.unlink(missing_ok=True)
        try:
            if not creator:
                vdir.rmdir()
        except OSError:
            pass
        raise
    except Exception as e:
        target_path.unlink(missing_ok=True)
        try:
            if not creator:
                vdir.rmdir()
        except OSError:
            pass
        raise HTTPException(400, f"Invalid or unreadable video file: {e}")
    finally:
        try:
            await file.close()
        except Exception:
            pass
        
    return {
        "id": source_id,
        "filename": file.filename,
        "path": str(target_path),
        "creator": creator,
        **meta
    }

def clean_error_message(err: Exception) -> str:
    """Strips terminal ANSI color sequences and translates known errors into actionable user advice."""
    msg = str(err)
    msg = re.sub(r'(?:\x1b|\033|%;|\^\[)\[[0-9;]*[a-zA-Z]|\[[0-9]+[0-9;]*[a-zA-Z]', '', msg)
    if any(p in msg.lower() for p in ["sign in to confirm your age", "confirm your age", "use --cookies", "inappropriate for some users", "cookies for the authentication"]):
        return "This video is age-restricted or requires YouTube sign-in. Please upload a cookies.txt file in LLM & Settings > YouTube Cookies to access this video."
    return msg.strip()

@app.post("/preview/url")
@app.post("/api/preview/url")
def api_preview_url(body: dict):
    if not isinstance(body, dict):
        raise HTTPException(400, "Invalid JSON body.")
    url = str(body.get("url", "")).strip()
    if not url:
        raise HTTPException(400, "Please provide a valid video URL.")
    creator_id = body.get("creator_id") or body.get("creator")
    try:
        data = preview_video_url(url, creator_id=creator_id)
        return data
    except Exception as e:
        raise HTTPException(400, f"Failed to inspect video: {clean_error_message(e)}")

@app.get("/preview/{source_id}/storyboard")
@app.get("/api/preview/{source_id}/storyboard")
def get_storyboard(source_id: str):
    src = get_source_file(source_id)
    if src and src.exists():
        meta = probe_video(src)
        frames = extract_storyboard(src, meta["duration"], src.parent)
        return {
            "source_id": source_id,
            "frames": [f.name for f in frames],
            "duration": meta["duration"],
            "w": meta["w"],
            "h": meta["h"]
        }
    
    # Check if this is a URL preview folder with frame images
    folder = DATA_DIR / source_id
    if not folder.exists():
        for sub in DATA_DIR.iterdir():
            if sub.is_dir() and (sub / source_id).exists():
                folder = sub / source_id
                break
    
    if folder.exists():
        meta_f = folder / "source.json"
        meta = {}
        if meta_f.exists():
            try:
                meta = json.loads(meta_f.read_text(encoding="utf-8"))
            except Exception:
                pass
        frame_files = sorted(folder.glob("frame_*.jpg"))
        if frame_files:
            return {
                "source_id": source_id,
                "frames": [f"{folder.name}/{f.name}" for f in frame_files],
                "duration": meta.get("duration", 0),
                "w": meta.get("w", 1920),
                "h": meta.get("h", 1080)
            }

    raise HTTPException(404, "Source video not found.")

@app.get("/preview/{source_id}/seek")
@app.get("/api/preview/{source_id}/seek")
def get_seek(source_id: str, sec: float = 0.0):
    src = get_source_file(source_id)
    if not src or not src.exists():
        raise HTTPException(404, "Source video not found.")
    frame = extract_seek_frame(src, sec, src.parent)
    if not frame or not frame.exists():
        raise HTTPException(500, "Failed to extract seek frame.")
    return FileResponse(frame, media_type="image/jpeg")

@app.post("/preview/{source_id}/autocam")
@app.post("/api/facecam/detect")
def run_facecam_detection(source_id: str):
    src = get_source_file(source_id)
    if src and src.exists():
        return detect_facecam(src)

    # Check for image preview folder
    folder = DATA_DIR / source_id
    if not folder.exists():
        for sub in DATA_DIR.iterdir():
            if sub.is_dir() and (sub / source_id).exists():
                folder = sub / source_id
                break
    
    if folder.exists():
        frame_files = sorted(folder.glob("frame_*.jpg"))
        if frame_files:
            return detect_facecam(frame_files)

    raise HTTPException(404, "Source video not found.")

# -------------------------------------------------------------
# Layouts & Styling Endpoints
# -------------------------------------------------------------
@app.get("/layouts")
@app.get("/api/layouts")
def get_layouts(top: float = 0.32):
    try:
        return [
            {
                "id": key,
                "name": name,
                "description": description,
                **geometry(key, top),
                **text_positions(key, top)
            }
            for key, name, description in CATALOG
        ]
    except ValueError as e:
        raise HTTPException(400, str(e))

@app.get("/api/caption-styles")
def get_caption_styles():
    return [
        {"id": k, "name": v["name"], "color": v["color"], "outline": v["outline"]}
        for k, v in STYLES.items()
    ]

@app.get("/api/ai/providers")
def get_ai_providers():
    return {
        "providers": list_supported_providers(),
        "active_provider": AI_PROVIDER,
        "active_models": AI_MODELS
    }

# -------------------------------------------------------------
# Job Submission & Pipeline
# -------------------------------------------------------------
@app.post("/make")
@app.post("/api/make")
@app.post("/api/jobs")
def create_clipping_job(body: dict):
    if not is_configured():
        raise HTTPException(400, "LLM is not configured yet. Please complete initial LLM setup in settings first.")

    url = str(body.get("url", "")).strip()
    source_id = str(body.get("id", "")).strip()
    if not url and not source_id:
        raise HTTPException(400, "Provide a video URL or an uploaded video ID.")
    
    job_id = uuid.uuid4().hex[:12]
    creator_ref = body.get("creator_id") or body.get("creator")
    state[job_id] = {
        "job_id": job_id,
        "status": "queued",
        "progress": 0.0,
        "stage": "Waiting in queue...",
        "created_at": time.time(),
        "clips": [],
        "creator": creator_ref
    }
    
    t = threading.Thread(target=run_clip_pipeline, args=(body, state, job_id), daemon=True)
    t.start()
    
    return {"job_id": job_id, "status": "queued"}

@app.get("/jobs/{job_id}")
@app.get("/status/{job_id}")
@app.get("/make/{job_id}")
@app.get("/api/jobs/{job_id}")
def get_job_status(job_id: str):
    if job_id not in state:
        raise HTTPException(404, "Job not found.")
    return state[job_id]

@app.get("/api/jobs")
def list_jobs():
    return [
        {"job_id": k, **v} for k, v in state.items()
        if isinstance(v, dict)
    ]

@app.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: str):
    if job_id in state and isinstance(state[job_id], dict):
        state[job_id]["status"] = "cancelled"
        state[job_id]["stage"] = "Cancelled by user"
        return {"cancelled": True}
    raise HTTPException(404, "Job not found.")

# -------------------------------------------------------------
# Single Manual Clip Export
# -------------------------------------------------------------
@app.post("/export")
@app.post("/api/export")
def manual_export(body: dict):
    source_id = str(body.get("id", ""))
    url = str(body.get("url", "")).strip()
    slice_id = str(body.get("slice_id", "")).strip()
    src = None
    
    if slice_id:
        slice_p = next((p for p in (DATA_DIR / "slices").glob(f"{slice_id}.*") if p.suffix in (".mp4", ".mkv", ".webm")), None)
        slice_meta_p = DATA_DIR / "slices" / f"{slice_id}.json"
        if slice_p and slice_p.exists():
            if slice_meta_p.exists():
                try:
                    sm = json.loads(slice_meta_p.read_text(encoding="utf-8"))
                    if url and sm.get("url") and sm.get("url") != url:
                        slice_p = None
                        slice_id = ""
                    elif source_id and sm.get("source_id") and sm.get("source_id") != source_id:
                        slice_p = None
                        slice_id = ""
                except Exception:
                    pass
            if slice_p:
                src = slice_p

    if not src:
        src = get_source_file(source_id)
    
    # If src does not exist locally, check if it's a URL preview or provided URL
    if not src or not src.exists():
        if not url and source_id:
            folder = DATA_DIR / source_id
            if not folder.exists():
                for sub in DATA_DIR.iterdir():
                    if sub.is_dir() and (sub / source_id).exists():
                        folder = sub / source_id
                        break
            if folder.exists() and (folder / "source.json").exists():
                try:
                    s_data = json.loads((folder / "source.json").read_text(encoding="utf-8"))
                    url = s_data.get("url", "")
                except Exception:
                    pass

    if not src and not url:
        raise HTTPException(400, "Source video not found. Upload a video or enter a URL first.")
    
    start = max(0.0, float(body.get("start", 0)))
    end = float(body.get("end", start + 30.0))
    if end <= start:
        raise HTTPException(400, "End time must be greater than start time.")
    
    layout = body.get("layout", "stack")
    if layout not in LAYOUT_IDS:
        raise HTTPException(400, f"Unknown layout: {layout}")
        
    top_h = float(body.get("top", 0.32))
    caption_style = body.get("caption_style", "bounce")
    hook_style = body.get("hook_style", "banner")
    caption_y = int(body.get("caption_y", 1450))
    hook_y = int(body.get("hook_y", 260)) if body.get("hook_y") is not None else None
    hook = str(body.get("hook", ""))
    words = body.get("words", [])
    if not slice_id and body.get("slice_id"):
        # Slice was discarded because it belonged to another video URL; discard stale words too!
        words = []

    if slice_id and not words:
        words_p = DATA_DIR / "slices" / f"{slice_id}_words.json"
        if words_p.exists():
            try:
                words = json.loads(words_p.read_text(encoding="utf-8"))
            except Exception:
                pass

    cam_in = body.get("cam", {"x": 0.0, "y": 0.0, "w": 0.25, "h": 0.30})
    game_in = body.get("game", {"x": 0.25, "y": 0.0, "w": 0.75, "h": 1.0})
    
    clip_id = uuid.uuid4().hex[:12]
    job_id = f"export_{clip_id}"
    state[job_id] = {"status": "rendering", "progress": 0.1, "stage": "Preparing export..."}
    
    def render_worker():
        try:
            target_src = src
            slice_start = start
            slice_end = end
            out_dir = DATA_DIR / "exports"
            out_dir.mkdir(parents=True, exist_ok=True)

            if slice_id and target_src and target_src.exists():
                slice_start = 0.0
                slice_end = min(probe_video(target_src)["duration"], end - start if end > start else 9999)
            elif not target_src or not target_src.exists():
                from .pipeline.downloader import download_video_section
                state[job_id] = {"status": "downloading", "progress": 0.3, "stage": "Downloading requested slice..."}
                target_src = download_video_section(url, out_dir, f"raw_{clip_id}", start, end)
                slice_start = 0.0
                slice_end = min(probe_video(target_src)["duration"], end - start)

            # Auto-transcribe if words are missing or empty so every clip gets fresh, accurate captions!
            nonlocal words
            if not words or len(words) == 0:
                try:
                    state[job_id] = {"status": "rendering", "progress": 0.45, "stage": "Transcribing clip audio for captions..."}
                    from .audio.transcribe import transcribe_audio_segment
                    dur = probe_video(target_src)["duration"]
                    t_res = transcribe_audio_segment(
                        target_src,
                        slice_start,
                        min(slice_end, dur),
                        DATA_DIR / "tmp"
                    )
                    words = t_res.get("words", [])
                except Exception as t_err:
                    words = []

            meta = probe_video(target_src)
            vw, vh = meta["w"], meta["h"]
            cam_rect = (
                max(0, min(vw - 2, int(cam_in["x"] * vw))),
                max(0, min(vh - 2, int(cam_in["y"] * vh))),
                max(2, min(vw, int(cam_in["w"] * vw))),
                max(2, min(vh, int(cam_in["h"] * vh)))
            )
            game_rect = (
                max(0, min(vw - 2, int(game_in["x"] * vw))),
                max(0, min(vh - 2, int(game_in["y"] * vh))),
                max(2, min(vw, int(game_in["w"] * vw))),
                max(2, min(vh, int(game_in["h"] * vh)))
            )

            state[job_id] = {"status": "rendering", "progress": 0.6, "stage": "Rendering vertical 9:16 video..."}
            res = render_clip(
                src_path=target_src,
                out_dir=out_dir,
                name=clip_id,
                start=slice_start,
                end=slice_end,
                layout=layout,
                top=top_h,
                cam_rect=cam_rect,
                game_rect=game_rect,
                words=words,
                caption_style=caption_style,
                caption_y=caption_y,
                hook=hook,
                hook_y=hook_y,
                hook_style=hook_style
            )
            
            (out_dir / f"{clip_id}.json").write_text(json.dumps({
                "source": source_id or clip_id,
                "settings": {
                    "id": source_id,
                    "slice_id": slice_id,
                    "start": start,
                    "end": end,
                    "layout": layout,
                    "top": top_h,
                    "cam": cam_in,
                    "game": game_in,
                    "caption_style": caption_style,
                    "hook_style": hook_style,
                    "caption_y": caption_y,
                    "hook_y": hook_y,
                    "hook": hook,
                    "words": words,
                    "source_url": url
                },
                "result": {**res, "status": "done"}
            }, indent=2), encoding="utf-8")
            
            state[job_id] = {
                "status": "done",
                "clip_id": clip_id,
                "file": f"{clip_id}.mp4",
                "download_url": f"/api/download/{clip_id}.mp4",
                "cover": f"{clip_id}.jpg",
                "srt": f"{clip_id}.srt",
                **res
            }
        except Exception as e:
            state[job_id] = {"status": "error", "error": str(e)}
            
    threading.Thread(target=render_worker, daemon=True).start()
    return {"job_id": job_id, "clip_id": clip_id}

# -------------------------------------------------------------
# New Studio Workflow: Moment Scouting, Slicing & Storage
# -------------------------------------------------------------
@app.post("/api/moments/scout")
def api_scout_moments(body: dict):
    """Step 2: Analyzes video using LLM and returns ONLY recommended timestamps and moments metadata."""
    import numpy as np
    import shutil
    from .pipeline.downloader import get_ytdl
    from .ai.games import detect_game
    from .ai.brain import find_viral_moments_ai
    from .audio.transcribe import youtube_words_from_info, transcribe_audio_segment
    from .audio.highlights import _audio_profile, rank_highlights

    url = str(body.get("url", "")).strip()
    source_id = str(body.get("id", "")).strip()
    count = max(1, min(12, int(body.get("count", 4))))
    min_len = max(5, min(180, float(body.get("min_len", 30))))
    max_len = max(min_len, min(180, float(body.get("max_len", 60))))
    instructions = str(body.get("instructions") or body.get("user_instructions") or body.get("prompt") or "").strip()

    title, uploader, duration = "", "", 0.0
    yt_words = None
    audio_file = None
    tmp_clean = []
    is_age_restricted = False

    try:
        if url:
            info = None
            try:
                with get_ytdl({"skip_download": True}) as y:
                    info = y.extract_info(url, download=False)
                title = info.get("title") or "Video"
                uploader = info.get("uploader") or info.get("channel") or ""
                duration = float(info.get("duration") or 0)
                yt_words = youtube_words_from_info(info)
            except Exception as ytdl_err:
                err_s = str(ytdl_err).lower()
                is_age_restricted = any(phrase in err_s for phrase in ["sign in", "confirm your age", "cookies", "inappropriate", "private"])
                # Age restriction, sign-in required, or unauthenticated stream fallback
                yt_id = extract_youtube_id(url)
                cand_folders = [DATA_DIR / source_id, DATA_DIR / f"yt_{yt_id}"] if yt_id else [DATA_DIR / source_id]
                for cf in cand_folders:
                    meta_f = cf / "source.json"
                    if meta_f.exists():
                        try:
                            s_data = json.loads(meta_f.read_text(encoding="utf-8"))
                            title = s_data.get("title") or title
                            uploader = s_data.get("uploader") or uploader
                            duration = float(s_data.get("duration") or 0)
                        except Exception:
                            pass
                if not title or title == "Video":
                    if yt_id:
                        title = f"YouTube Video ({yt_id})"
                        try:
                            req = urllib.request.Request(
                                f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={yt_id}&format=json",
                                headers={"User-Agent": "Mozilla/5.0"}
                            )
                            with urllib.request.urlopen(req, timeout=5) as r:
                                o_data = json.loads(r.read().decode("utf-8"))
                                title = o_data.get("title") or title
                                uploader = o_data.get("author_name") or uploader
                        except Exception:
                            pass
                if duration <= 0 and yt_id:
                    try:
                        wp_req = urllib.request.Request(f"https://www.youtube.com/watch?v={yt_id}", headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
                        with urllib.request.urlopen(wp_req, timeout=5) as wp_resp:
                            html_c = wp_resp.read().decode("utf-8", errors="ignore")
                        m_dur = re.findall(r'lengthSeconds":\s*"(\d+)"', html_c)
                        if m_dur:
                            duration = float(m_dur[0])
                    except Exception:
                        pass
                if duration <= 0:
                    duration = 600.0  # Safe default 10 minutes
        else:
            src = get_source_file(source_id)
            if not src or not src.exists():
                raise HTTPException(404, "Source video not found in library.")
            meta = probe_video(src)
            duration = meta["duration"]
            title = src.stem
            audio_file = src

        game_name, hashtags = detect_game(title, uploader)
        rms = np.zeros(max(1, int(duration)))

        if not yt_words:
            if url and not is_age_restricted:
                try:
                    audio_dir = DATA_DIR / "tmp" / f"scout_{uuid.uuid4().hex[:8]}"
                    audio_dir.mkdir(parents=True, exist_ok=True)
                    with get_ytdl({"format": "ba/b", "outtmpl": str(audio_dir / "audio.%(ext)s")}) as y:
                        y.download([url])
                    cand_audio = [f for f in audio_dir.glob("audio.*") if f.suffix not in (".part", ".ytdl")]
                    if cand_audio:
                        audio_file = cand_audio[0]
                        tmp_clean.append(audio_dir)
                except Exception:
                    audio_file = None

            if audio_file and audio_file.exists():
                rms, _ = _audio_profile(audio_file)
                candidates = rank_highlights(audio_file, duration, count * 2, max_len, motion_on=False)
                words = []
                for c in candidates[:min(6, len(candidates))]:
                    res = transcribe_audio_segment(audio_file, c["start"], c["end"], DATA_DIR / "tmp")
                    for w in res.get("words", []):
                        words.append({
                            "start": c["start"] + w["start"],
                            "end": c["start"] + w["end"],
                            "text": w["text"]
                        })
                yt_words = sorted(words, key=lambda x: x["start"])

        moments = find_viral_moments_ai(
            words=yt_words or [],
            db=rms,
            duration=duration,
            title=title,
            uploader=uploader,
            max_clips=count,
            min_len=min_len,
            max_len=max_len,
            game_name=game_name,
            user_instructions=instructions
        )

        for p in tmp_clean:
            shutil.rmtree(p, ignore_errors=True)

        return {
            "success": True,
            "title": title,
            "duration": duration,
            "count": len(moments),
            "instructions": instructions,
            "moments": moments
        }
    except Exception as e:
        for p in tmp_clean:
            shutil.rmtree(p, ignore_errors=True)
        raise HTTPException(500, f"Analysis failed: {clean_error_message(e)}")

@app.get("/hook-styles")
@app.get("/api/hook-styles")
def get_hook_styles():
    from .rendering.captions import HOOK_STYLES
    return [{"id": k, **v} for k, v in HOOK_STYLES.items()]

@app.get("/api/preview/frame")
def api_get_preview_frame(id: str = "", url: str = "", sec: float = 0.0, slice_id: str = ""):
    """Step 3b: Returns a screenshot/frame at the exact requested timestamp."""
    sec = max(0.0, float(sec))
    out_dir = DATA_DIR / "tmp" / "frames"
    out_dir.mkdir(parents=True, exist_ok=True)
    frame_name = f"frame_{uuid.uuid4().hex[:8]}.jpg"
    out_p = out_dir / frame_name

    # 1. If slice_id is provided, extract directly from the downloaded slice
    if slice_id:
        slice_p = next((p for p in (DATA_DIR / "slices").glob(f"{slice_id}.*") if p.suffix in (".mp4", ".mkv", ".webm")), None)
        if slice_p and slice_p.exists():
            meta = probe_video(slice_p)
            dur = max(0.5, float(meta.get("duration", 30.0)))
            target_t = sec if 0.0 <= sec <= dur else (sec % dur)
            cmd = ["ffmpeg", "-y", "-v", "error", "-ss", f"{target_t:.2f}", "-i", str(slice_p), "-frames:v", "1", "-vf", "scale=960:-2", "-q:v", "2", str(out_p)]
            subprocess.run(cmd, capture_output=True, timeout=15, creationflags=0x08000000 if os.name == "nt" else 0)
            if out_p.exists():
                return FileResponse(out_p, media_type="image/jpeg")

    # 2. If id matches a local source video
    src = get_source_file(id) if id else None
    if src and src.exists():
        cmd = ["ffmpeg", "-y", "-v", "error", "-ss", f"{sec:.2f}", "-i", str(src), "-frames:v", "1", "-vf", "scale=960:-2", "-q:v", "2", str(out_p)]
        subprocess.run(cmd, capture_output=True, timeout=15, creationflags=0x08000000 if os.name == "nt" else 0)
        if out_p.exists():
            return FileResponse(out_p, media_type="image/jpeg")

    # 3. Stream extraction via yt-dlp low-res format directly from video stream at the requested timestamp
    if url:
        try:
            from .pipeline.downloader import get_ytdl
            with get_ytdl({'skip_download': True, 'quiet': True}) as y:
                info = y.extract_info(url, download=False)
            formats = [f for f in info.get("formats", []) if f.get("vcodec") not in (None, "none") and f.get("url") and f.get("height", 9999) <= 480]
            st_url = max(formats, key=lambda f: f.get("height", 0))["url"] if formats else info.get("url")
            if st_url:
                cmd = ["ffmpeg", "-y", "-v", "error", "-ss", f"{sec:.2f}", "-i", st_url, "-frames:v", "1", "-vf", "scale=960:-2", "-q:v", "2", str(out_p)]
                subprocess.run(cmd, capture_output=True, timeout=20, creationflags=0x08000000 if os.name == "nt" else 0)
                if out_p.exists():
                    return FileResponse(out_p, media_type="image/jpeg")
        except Exception:
            pass

    # 4. Fallback only if live seeking fails: check storyboard frames in data folder
    if id:
        folder = DATA_DIR / id
        if folder.exists():
            candidates = sorted(folder.glob("frame_*.jpg"))
            if candidates:
                idx = int(sec % max(1, len(candidates)))
                cf = candidates[idx]
                if cf.exists():
                    return FileResponse(cf, media_type="image/jpeg")

    # 5. Check any frame_0.jpg fallback in DATA_DIR
    for fallback in DATA_DIR.rglob("frame_0.jpg"):
        if fallback.exists():
            return FileResponse(fallback, media_type="image/jpeg")

    # 6. Fallback clean canvas placeholder
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (960, 540), color=(15, 20, 32))
    draw = ImageDraw.Draw(img)
    draw.text((480, 270), f"Preview Frame ({sec:.1f}s)", fill=(200, 200, 220), anchor="mm")
    img.save(out_p, quality=85)
    return FileResponse(out_p, media_type="image/jpeg")

@app.post("/api/slice/fetch")
def api_fetch_slice(body: dict):
    """Step 3e: Downloads/extracts ONLY the requested 30s-60s slice from the video."""
    id_str = str(body.get("id", ""))
    url = str(body.get("url", "")).strip()
    start = max(0.0, float(body.get("start", 0)))
    end = float(body.get("end", start + 30.0))
    quality = int(str(body.get("quality", "720")).replace("p", ""))

    slice_id = f"slice_{uuid.uuid4().hex[:8]}"
    out_dir = DATA_DIR / "slices"
    out_dir.mkdir(parents=True, exist_ok=True)

    sec_file = None
    src = get_source_file(id_str) if id_str else None
    if src and src.exists():
        out_mp4 = out_dir / f"{slice_id}.mp4"
        cmd = [
            "ffmpeg", "-y", "-v", "error",
            "-ss", f"{start:.2f}",
            "-i", str(src),
            "-t", f"{end - start:.2f}",
            "-c:v", "libx264", "-c:a", "aac",
            "-threads", "2",
            "-movflags", "+faststart",
            str(out_mp4)
        ]
        subprocess.run(cmd, check=True, timeout=120, creationflags=0x08000000 if os.name == "nt" else 0)
        sec_file = out_mp4
    elif url:
        try:
            from .pipeline.downloader import download_video_section
            sec_file = download_video_section(url, out_dir, slice_id, start, end, height=quality)
        except Exception as e:
            raise HTTPException(500, f"Failed to fetch slice: {clean_error_message(e)}")
    else:
        raise HTTPException(400, "No source video or URL provided.")

    if not sec_file or not sec_file.exists():
        raise HTTPException(500, "Slice video file could not be generated.")

    meta = probe_video(sec_file)
    dur = float(meta.get("duration", end - start))
    mid_sec = max(0.0, min(dur - 0.2, dur / 2.0))
    preview_jpg = out_dir / f"{slice_id}_preview.jpg"
    cmd = [
        "ffmpeg", "-y", "-v", "error",
        "-ss", f"{mid_sec:.2f}",
        "-i", str(sec_file),
        "-frames:v", "1",
        "-vf", "scale=960:-2",
        "-q:v", "2",
        str(preview_jpg)
    ]
    subprocess.run(cmd, capture_output=True, timeout=15, creationflags=0x08000000 if os.name == "nt" else 0)

    try:
        (out_dir / f"{slice_id}.json").write_text(json.dumps({
            "slice_id": slice_id,
            "source_id": id_str,
            "url": url,
            "start": start,
            "end": end
        }), encoding="utf-8")
    except Exception:
        pass

    return {
        "success": True,
        "slice_id": slice_id,
        "duration": dur,
        "file": f"/media/slices/{sec_file.name}",
        "preview": f"/media/slices/{preview_jpg.name}" if preview_jpg.exists() else None
    }

@app.post("/api/slice/captions")
def api_slice_captions(body: dict):
    """Step 3f: Transcribes the slice using Faster-Whisper to produce exact word timestamps and hook."""
    slice_id = str(body.get("slice_id", ""))
    hook = str(body.get("hook", ""))
    lang = body.get("lang") or None

    slice_p = next((p for p in (DATA_DIR / "slices").glob(f"{slice_id}.*") if p.suffix in (".mp4", ".mkv", ".webm")), None)
    if not slice_p or not slice_p.exists():
        raise HTTPException(404, "Slice video not found.")

    from .audio.transcribe import transcribe_audio_segment
    res = transcribe_audio_segment(slice_p, 0.0, probe_video(slice_p)["duration"], DATA_DIR / "tmp", language=lang)
    words = res.get("words", [])

    try:
        (DATA_DIR / "slices" / f"{slice_id}_words.json").write_text(json.dumps(words), encoding="utf-8")
    except Exception:
        pass

    return {
        "success": True,
        "words": words,
        "hook": hook.upper() if hook else (words[0]["text"].upper() if words else "WATCH THIS")
    }

@app.get("/api/download/{filename}")
def api_download_file(filename: str):
    """Step 4: Direct browser download into user Downloads."""
    candidates = [
        DOWNLOADS_DIR / filename,
        DATA_DIR / "exports" / filename,
        DATA_DIR / filename
    ]
    for c in candidates:
        if c.exists() and c.is_file():
            return FileResponse(
                c,
                media_type="video/mp4",
                filename=filename,
                headers={"Content-Disposition": f'attachment; filename="{filename}"'}
            )
    raise HTTPException(404, "File not found for download.")

PROTECTED_STORAGE_FILENAMES = {
    "config.json",
    "cookies.txt",
    "weights.json",
    "feedback.jsonl",
    "creators.json",
    "creator.json",
    "profile.json",
    "ai.json",
    "CACHEDIR.TAG",
}

PROTECTED_STORAGE_DIRS = {
    "models",
    ".git",
    ".locks",
}

def is_protected_storage_file(p: Path) -> bool:
    """Returns True if the file is a sensitive system configuration or protected model file."""
    if p.name in PROTECTED_STORAGE_FILENAMES:
        return True
    if any(part in PROTECTED_STORAGE_DIRS for part in p.parts):
        return True
    if p.suffix.lower() in (".env", ".key", ".token", ".py", ".pyc"):
        return True
    if "creators" in p.parts and p.suffix.lower() == ".json":
        return True
    return False

@app.get("/api/storage/files")
def api_get_storage_files():
    """Step 5: Lists only safe disposable media & temp files in the data directory (sensitive configs locked & hidden)."""
    import datetime
    items = []
    def cat_for(ext):
        ext = ext.lower()
        if ext in (".mp4", ".mkv", ".webm", ".avi", ".mov"): return "video"
        if ext in (".wav", ".m4a", ".mp3", ".aac", ".ogg"): return "audio"
        if ext in (".srt", ".ass"): return "subtitles"
        if ext == ".json": return "metadata"
        if ext in (".jpg", ".jpeg", ".png", ".webp"): return "image"
        return "other"

    for p in DATA_DIR.rglob("*"):
        if p.is_file():
            if is_protected_storage_file(p):
                continue
            try:
                st = p.stat()
                rel = p.relative_to(DATA_DIR).as_posix()
                size_mb = round(st.st_size / (1024 * 1024), 2)
                mtime = datetime.datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                items.append({
                    "name": p.name,
                    "rel_path": rel,
                    "category": cat_for(p.suffix),
                    "size_bytes": st.st_size,
                    "size_formatted": f"{size_mb:.2f} MB" if size_mb >= 0.1 else f"{round(st.st_size / 1024, 1)} KB",
                    "modified": mtime,
                    "url": f"/media/{rel}",
                    "protected": False
                })
            except OSError:
                pass
    items.sort(key=lambda x: x["modified"], reverse=True)
    return {"total": len(items), "files": items}

@app.post("/api/storage/delete")
def api_delete_storage_file(body: dict):
    """Step 5: Manually deletes specified file(s) from data folder, strictly enforcing hard-lock on sensitive configs."""
    rel_path = str(body.get("path", "")).strip()
    files = body.get("files") or ([rel_path] if rel_path else [])
    deleted_count = 0
    for f in files:
        target = (DATA_DIR / f).resolve()
        if DATA_DIR in target.parents and target.exists() and target.is_file():
            if is_protected_storage_file(target):
                continue
            try:
                target.unlink(missing_ok=True)
                deleted_count += 1
            except OSError:
                pass
    return {"success": True, "deleted": deleted_count}

@app.post("/api/storage/clean-tmp")
def api_clean_tmp():
    """Step 5: Safely cleans all temporary files inside data/tmp."""
    import shutil
    tmp_path = DATA_DIR / "tmp"
    count = 0
    if tmp_path.exists():
        for p in tmp_path.glob("*"):
            try:
                if p.is_file():
                    p.unlink(missing_ok=True)
                    count += 1
                elif p.is_dir():
                    shutil.rmtree(p, ignore_errors=True)
                    count += 1
            except Exception:
                pass
    return {"success": True, "cleaned": count}

# -------------------------------------------------------------
# YouTube Authentication & Cookies Management
# -------------------------------------------------------------
@app.get("/api/cookies/status")
def get_cookies_status():
    cf = get_cookies_file()
    if cf and cf.exists() and cf.is_file():
        return {
            "configured": True,
            "filename": cf.name,
            "path": str(cf),
            "size_bytes": cf.stat().st_size
        }
    return {
        "configured": False,
        "filename": None,
        "path": None,
        "size_bytes": 0
    }

@app.post("/api/cookies/upload")
async def upload_cookies(file: UploadFile = File(...)):
    try:
        if not file.filename.lower().endswith(".txt"):
            raise HTTPException(400, "Please upload a valid .txt cookie file (Netscape format).")
        content = await file.read()
        if len(content) < 10:
            raise HTTPException(400, "Cookie file is empty or invalid.")
        COOKIES_FILE.write_bytes(content)
        return {
            "success": True,
            "message": "YouTube cookies successfully saved.",
            "size_bytes": len(content)
        }
    finally:
        try:
            await file.close()
        except Exception:
            pass

@app.delete("/api/cookies")
def delete_cookies():
    cf = get_cookies_file()
    if cf and cf.exists():
        try:
            cf.unlink()
        except Exception as e:
            raise HTTPException(500, f"Failed to delete cookies file: {e}")
    return {"success": True, "message": "Cookies removed."}

# -------------------------------------------------------------
# Clip Library & Media Retrieval
# -------------------------------------------------------------
@app.get("/library")
@app.get("/api/library")
def get_library(creator: Optional[str] = None):
    records = []
    json_files = list(DATA_DIR.glob("*.json"))
    try:
        for sub in DATA_DIR.iterdir():
            if sub.is_dir() and sub.name not in ("models", "creators"):
                json_files.extend(sub.glob("*.json"))
            elif sub.is_dir() and sub.name == "creators":
                for c_dir in sub.iterdir():
                    if c_dir.is_dir():
                        cdir_clips = c_dir / "clips"
                        if cdir_clips.exists():
                            json_files.extend(cdir_clips.glob("*.json"))
    except OSError:
        pass
        
    for f in json_files:
        if f.name.endswith((".state.json", ".request.json", ".weights.json", "creator.json")):
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            mp4 = f.with_suffix(".mp4")
            result = data.get("result", {})
            if result.get("status") == "done" and mp4.exists():
                settings = data.get("settings", {})
                clip_creator = settings.get("creator")
                if not clip_creator and "creators" in f.parts:
                    try:
                        idx = f.parts.index("creators")
                        clip_creator = f.parts[idx + 1]
                    except (ValueError, IndexError):
                        pass
                if creator and clip_creator != creator:
                    continue

                try:
                    rel_path = f.relative_to(DATA_DIR)
                    rel_folder = str(rel_path.parent).replace("\\", "/")
                except ValueError:
                    rel_folder = ""
                folder_prefix = f"/media/{rel_folder}" if rel_folder and rel_folder != "." else "/media"

                records.append({
                    "id": f.stem,
                    "title": settings.get("title") or "Clipiest Clip",
                    "hook": settings.get("hook", ""),
                    "layout": settings.get("layout", "stack"),
                    "caption_style": settings.get("caption_style", "bounce"),
                    "created": f.stat().st_mtime,
                    "duration": result.get("duration", 0),
                    "file": f"{folder_prefix}/{f.stem}.mp4",
                    "cover": f"{folder_prefix}/{f.stem}.jpg" if (f.with_suffix(".jpg")).exists() else None,
                    "srt": f"/text/{f.stem}/srt",
                    "settings": settings,
                    "folder": rel_folder,
                    "creator": clip_creator
                })
        except Exception:
            continue
            
    return sorted(records, key=lambda x: x["created"], reverse=True)

@app.delete("/clip/{clip_id}")
@app.delete("/api/library/{clip_id}")
def delete_clip(clip_id: str):
    p = find_clip_file(f"{clip_id}.json")
    if not p:
        raise HTTPException(404, "Clip not found.")
    for ext in (".json", ".mp4", ".jpg", ".srt", ".ass"):
        f = p.with_suffix(ext)
        if f.exists():
            try:
                f.unlink()
            except OSError:
                pass
    return {"deleted": True, "id": clip_id}

@app.get("/media/{filename:path}")
def serve_media(filename: str):
    p = DATA_DIR / filename
    if not p.exists():
        p = find_clip_file(filename)
    if not p or not p.exists():
        raise HTTPException(404, "Media file not found.")
    
    suffix = p.suffix.lower()
    media_types = {
        ".mp4": "video/mp4",
        ".webm": "video/webm",
        ".m4a": "audio/mp4",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".srt": "text/plain; charset=utf-8",
        ".ass": "text/plain; charset=utf-8",
        ".json": "application/json"
    }
    return FileResponse(p, media_type=media_types.get(suffix, "application/octet-stream"))

@app.get("/text/{clip_id}/{kind}")
def download_caption_text(clip_id: str, kind: str):
    if kind not in ("srt", "ass"):
        raise HTTPException(400, "Supported caption formats: srt, ass")
    p = find_clip_file(f"{clip_id}.{kind}")
    if not p or not p.exists():
        raise HTTPException(404, "Caption file not found.")
    return FileResponse(p, filename=f"clipiest-{clip_id}.{kind}", media_type="text/plain; charset=utf-8")

# -------------------------------------------------------------
# User Feedback & Self-Learning Ridge Regression
# -------------------------------------------------------------
@app.post("/feedback")
@app.post("/api/feedback")
def submit_feedback(body: dict):
    clip_id = str(body.get("clip_id", ""))
    rating = int(body.get("rating", 3))
    features = body.get("features", {})
    
    if not features and clip_id:
        p = find_clip_file(f"{clip_id}.json")
        if p and p.exists():
            try:
                meta = json.loads(p.read_text(encoding="utf-8"))
                features = meta.get("features", {})
            except Exception:
                pass
                
    weights = record_feedback(DATA_DIR, clip_id, rating, features)
    return {"status": "ok", "rating": rating, "weights": weights}

# -------------------------------------------------------------
# Live Stream Ingestion & Instant Clipping
# -------------------------------------------------------------
@app.post("/live/start")
@app.post("/api/live/start")
def start_live_session(body: dict):
    stream_url = str(body.get("url", "")).strip()
    if not stream_url:
        raise HTTPException(400, "Provide a stream URL (Twitch or YouTube Live).")
    
    channel = body.get("channel", "")
    session_id = uuid.uuid4().hex[:8]
    
    mgr = LiveClipManager(DATA_DIR, session_id, stream_url, channel)
    mgr.start()
    live_managers[session_id] = mgr
    
    return {"session_id": session_id, "url": stream_url, "status": "running"}

@app.post("/live/stop")
@app.post("/api/live/stop")
def stop_live_session(body: dict):
    session_id = str(body.get("session_id", ""))
    mgr = live_managers.get(session_id)
    if not mgr:
        raise HTTPException(404, "Live session not found.")
    mgr.stop()
    return {"session_id": session_id, "status": "stopped"}

@app.post("/live/clip")
@app.post("/api/live/clip")
def instant_live_clip(body: dict):
    session_id = str(body.get("session_id", ""))
    mgr = live_managers.get(session_id)
    if not mgr:
        raise HTTPException(404, "Live session not found.")
    
    sec = float(body.get("duration", 60.0))
    clip_path = mgr.clip_buffer(duration_sec=sec)
    if not clip_path or not clip_path.exists():
        raise HTTPException(500, "Failed to slice live buffer. Check if stream has recorded enough seconds.")
    
    return {"status": "clipped", "path": str(clip_path), "file": clip_path.name}

@app.get("/live/{session_id}")
@app.get("/api/live/status")
def live_session_status(session_id: Optional[str] = None):
    if not session_id:
        return [
            {"session_id": sid, "status": mgr.get_status()}
            for sid, mgr in live_managers.items()
        ]
    mgr = live_managers.get(session_id)
    if not mgr:
        raise HTTPException(404, "Session not found.")
    return mgr.get_status()

# -------------------------------------------------------------
# Frontend Static Files Mount & SPA Routing
# -------------------------------------------------------------
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

@app.get("/")
def serve_index():
    index_file = FRONTEND_DIR / "index.html"
    if index_file.exists():
        return HTMLResponse(index_file.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>Clipiest API is running. Build frontend files to load UI.</h1>")
