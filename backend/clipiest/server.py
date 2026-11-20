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
from pathlib import Path
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from .config import (
    DATA_DIR, ROOT, BACKEND_DIR, TMP_DIR, HOST, PORT, PUBLIC_URL,
    HAS_NVENC, HAS_QSV, AI_PROVIDER, AI_MODELS, WHISPER_MODEL
)
from .pipeline.orchestrator import run_clip_pipeline
from .pipeline.queue import JobQueue, SystemMonitor
from .pipeline.downloader import get_ytdl
from .rendering.layouts import CATALOG, LAYOUT_IDS, geometry, text_positions, render_graph
from .rendering.captions import STYLES, write_subtitles
from .rendering.render import render_clip, probe_video
from .rendering.reedit import attach_reedit, find_file
from .vision.previews import extract_storyboard, extract_seek_frame
from .vision.facecam import detect_facecam
from .ai.learn import record_feedback, load_weights
from .ai.providers import list_supported_providers
from .live.session import LiveClipManager
from .storage.manager import get_disk_info, open_folder_in_os

app = FastAPI(title="Clipiest API", version="1.0.0")

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
    except OSError:
        pass
    return None

def find_clip_id(id_str: str, suffix: str = ".mp4") -> Optional[Path]:
    return find_clip_file(id_str + suffix)

def get_source_file(source_id: str) -> Optional[Path]:
    return find_clip_file(f"{source_id}.mp4")

# -------------------------------------------------------------
# System & Telemetry Endpoints
# -------------------------------------------------------------
@app.get("/api/telemetry")
def get_telemetry():
    sys_metrics = SystemMonitor.get_metrics()
    disk_info = get_disk_info(DATA_DIR)
    active_jobs = sum(1 for v in state.values() if isinstance(v, dict) and v.get("status") == "running")
    return {
        **sys_metrics,
        "disk": disk_info,
        "active_jobs": active_jobs,
        "hardware": {
            "nvenc": HAS_NVENC,
            "qsv": HAS_QSV,
            "whisper_model": WHISPER_MODEL,
            "ai_provider": AI_PROVIDER,
            "ai_models": AI_MODELS
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
async def upload_video(file: UploadFile = File(...)):
    source_id = uuid.uuid4().hex[:12]
    import re
    safe_name = re.sub(r"[^\w\- ]", "_", Path(file.filename or "upload").stem).strip()[:40].strip(" _") or "upload"
    vdir = DATA_DIR / f"{safe_name}_{source_id[:8]}"
    vdir.mkdir(parents=True, exist_ok=True)
    
    target_path = vdir / f"{source_id}.mp4"
    try:
        with target_path.open("wb") as out:
            while chunk := await file.read(4 * 1024 * 1024):
                out.write(chunk)
        meta = probe_video(target_path)
    except Exception as e:
        target_path.unlink(missing_ok=True)
        try:
            vdir.rmdir()
        except OSError:
            pass
        raise HTTPException(400, f"Invalid or unreadable video file: {e}")
        
    return {
        "id": source_id,
        "filename": file.filename,
        "path": str(target_path),
        **meta
    }

@app.get("/preview/{source_id}/storyboard")
@app.get("/api/preview/{source_id}/storyboard")
def get_storyboard(source_id: str):
    src = get_source_file(source_id)
    if not src or not src.exists():
        raise HTTPException(404, "Source video not found.")
    meta = probe_video(src)
    frames = extract_storyboard(src, meta["duration"], src.parent)
    return {
        "source_id": source_id,
        "frames": [f.name for f in frames],
        "duration": meta["duration"],
        "w": meta["w"],
        "h": meta["h"]
    }

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
    if not src or not src.exists():
        raise HTTPException(404, "Source video not found.")
    res = detect_facecam(src)
    return res

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
@app.post("/api/jobs")
def create_clipping_job(body: dict):
    url = str(body.get("url", "")).strip()
    source_id = str(body.get("id", "")).strip()
    if not url and not source_id:
        raise HTTPException(400, "Provide a video URL or an uploaded video ID.")
    
    job_id = uuid.uuid4().hex[:12]
    state[job_id] = {
        "job_id": job_id,
        "status": "queued",
        "progress": 0.0,
        "stage": "Waiting in queue...",
        "created_at": time.time(),
        "clips": []
    }
    
    t = threading.Thread(target=run_clip_pipeline, args=(body, state, job_id), daemon=True)
    t.start()
    
    return {"job_id": job_id, "status": "queued"}

@app.get("/jobs/{job_id}")
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
    src = get_source_file(source_id)
    if not src or not src.exists():
        raise HTTPException(400, "Source video not found. Upload or download first.")
    
    meta = probe_video(src)
    start = float(body.get("start", 0))
    end = float(body.get("end", min(30, meta["duration"])))
    if not (0 <= start < end <= meta["duration"] + 0.1):
        raise HTTPException(400, "Invalid start/end time range.")
    
    layout = body.get("layout", "stack")
    if layout not in LAYOUT_IDS:
        raise HTTPException(400, f"Unknown layout: {layout}")
        
    top_h = float(body.get("top", 0.32))
    caption_style = body.get("caption_style", "bounce")
    hook = str(body.get("hook", ""))
    
    # Calculate crop pixel rects
    vw, vh = meta["w"], meta["h"]
    cam_in = body.get("cam", {"x": 0.0, "y": 0.0, "w": 0.25, "h": 0.30})
    game_in = body.get("game", {"x": 0.25, "y": 0.0, "w": 0.75, "h": 1.0})
    
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
    
    words = body.get("words", [])
    clip_id = uuid.uuid4().hex[:12]
    out_dir = src.parent
    
    job_id = f"export_{clip_id}"
    state[job_id] = {"status": "rendering", "progress": 0.1}
    
    def render_worker():
        try:
            res = render_clip(
                src_path=src,
                out_dir=out_dir,
                name=clip_id,
                start=start,
                end=end,
                layout=layout,
                top=top_h,
                cam_rect=cam_rect,
                game_rect=game_rect,
                words=words,
                caption_style=caption_style,
                hook=hook
            )
            # Save metadata json
            (out_dir / f"{clip_id}.json").write_text(json.dumps({
                "source": source_id,
                "settings": {
                    "id": source_id,
                    "start": start,
                    "end": end,
                    "layout": layout,
                    "top": top_h,
                    "cam": cam_in,
                    "game": game_in,
                    "caption_style": caption_style,
                    "hook": hook,
                    "words": words
                },
                "result": {**res, "status": "done"}
            }, indent=2), encoding="utf-8")
            
            state[job_id] = {
                "status": "done",
                "clip_id": clip_id,
                "file": f"{clip_id}.mp4",
                "cover": f"{clip_id}.jpg",
                "srt": f"{clip_id}.srt",
                **res
            }
        except Exception as e:
            state[job_id] = {"status": "error", "error": str(e)}
            
    threading.Thread(target=render_worker, daemon=True).start()
    return {"job_id": job_id, "clip_id": clip_id}

# -------------------------------------------------------------
# Clip Library & Media Retrieval
# -------------------------------------------------------------
@app.get("/library")
@app.get("/api/library")
def get_library():
    records = []
    json_files = list(DATA_DIR.glob("*.json"))
    try:
        for sub in DATA_DIR.iterdir():
            if sub.is_dir() and sub.name != "models":
                json_files.extend(sub.glob("*.json"))
    except OSError:
        pass
        
    for f in json_files:
        if f.name.endswith((".state.json", ".request.json", ".weights.json")):
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            mp4 = f.with_suffix(".mp4")
            result = data.get("result", {})
            if result.get("status") == "done" and mp4.exists():
                settings = data.get("settings", {})
                folder_name = f.parent.name if f.parent != DATA_DIR else ""
                records.append({
                    "id": f.stem,
                    "title": settings.get("title") or "Clipiest Clip",
                    "hook": settings.get("hook", ""),
                    "layout": settings.get("layout", "stack"),
                    "caption_style": settings.get("caption_style", "bounce"),
                    "created": f.stat().st_mtime,
                    "duration": result.get("duration", 0),
                    "file": f"/media/{folder_name}/{f.stem}.mp4" if folder_name else f"/media/{f.stem}.mp4",
                    "cover": f"/media/{folder_name}/{f.stem}.jpg" if (f.with_suffix(".jpg")).exists() else None,
                    "srt": f"/text/{f.stem}/srt",
                    "settings": settings,
                    "folder": folder_name
                })
        except Exception:
            continue
            
    return sorted(records, key=lambda x: x["created"], reverse=True)

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

@app.post("/api/live/stop")
def stop_live_session(body: dict):
    session_id = str(body.get("session_id", ""))
    mgr = live_managers.get(session_id)
    if not mgr:
        raise HTTPException(404, "Live session not found.")
    mgr.stop()
    return {"session_id": session_id, "status": "stopped"}

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
