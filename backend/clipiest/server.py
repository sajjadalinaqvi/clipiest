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
    HAS_NVENC, HAS_QSV, AI_PROVIDER, AI_MODELS, WHISPER_MODEL,
    load_user_config, save_user_config, is_configured, WHISPER_MODELS
)
from .pipeline.orchestrator import run_clip_pipeline
from .pipeline.queue import JobQueue, SystemMonitor
from .pipeline.downloader import get_ytdl
from .rendering.layouts import CATALOG, LAYOUT_IDS, geometry, text_positions, render_graph
from .rendering.captions import STYLES, write_subtitles
from .rendering.render import render_clip, probe_video
from .rendering.reedit import attach_reedit, find_file
from .vision.previews import extract_storyboard, extract_seek_frame, preview_video_url
from .vision.facecam import detect_facecam
from .ai.learn import record_feedback, load_weights
from .ai.providers import list_supported_providers, test_llm_connection, fetch_models_from_provider, fetch_models_with_url
from .live.session import LiveClipManager
from .storage.manager import get_disk_info, open_folder_in_os
from . import creators

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
    except Exception as e:
        target_path.unlink(missing_ok=True)
        try:
            if not creator:
                vdir.rmdir()
        except OSError:
            pass
        raise HTTPException(400, f"Invalid or unreadable video file: {e}")
        
    return {
        "id": source_id,
        "filename": file.filename,
        "path": str(target_path),
        "creator": creator,
        **meta
    }

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
        raise HTTPException(400, f"Failed to inspect video: {e}")

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
    hook = str(body.get("hook", ""))
    words = body.get("words", [])
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

            if not target_src or not target_src.exists():
                from .pipeline.downloader import download_video_section
                state[job_id] = {"status": "downloading", "progress": 0.3, "stage": "Downloading requested slice..."}
                target_src = download_video_section(url, out_dir, f"raw_{clip_id}", start, end)
                slice_start = 0.0
                slice_end = min(probe_video(target_src)["duration"], end - start)

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
                hook=hook
            )
            
            (out_dir / f"{clip_id}.json").write_text(json.dumps({
                "source": source_id or clip_id,
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
                    "words": words,
                    "source_url": url
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
