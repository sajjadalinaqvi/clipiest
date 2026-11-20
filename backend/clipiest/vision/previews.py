"""Rapid early preview frames for Clipiest.
Extracts frames across the duration before or during full source video download.
"""
import io
import json
import os
import re
import subprocess
import urllib.request
import uuid
from pathlib import Path
from typing import Optional
from PIL import Image
import yt_dlp

from ..config import DATA_DIR, get_cookies_file
from ..ai.games import detect_game
from .facecam import detect_facecam

def extract_youtube_id(url: str) -> Optional[str]:
    """Extracts 11-char YouTube video ID from various URL patterns."""
    if not url:
        return None
    patterns = [
        r'(?:v=|\/v\/|embed\/|shorts\/|youtu\.be\/|\/e\/)([0-9A-Za-z_-]{11})',
        r'^([0-9A-Za-z_-]{11})$'
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None

NO_WINDOW = 0x08000000 if os.name == "nt" else 0

def extract_early_previews(url: str, job_id: str, data_dir: Path, publish_fn=lambda x: None) -> list:
    folder = data_dir / f"{job_id}-preview"
    folder.mkdir(parents=True, exist_ok=True)
    frames = []

    def report_ready(img_path: Path, t: float, kind: str):
        frames.append({
            "url": f"/api/preview/{job_id}/{len(frames)}",
            "time": round(t, 1),
            "kind": kind
        })
        publish_fn({
            "preview_status": "ready" if len(frames) >= 4 else "loading",
            "preview_frames": list(frames)
        })

    # Query video info without downloading
    with yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True, 'skip_download': True, 'socket_timeout': 15}) as y:
        info = y.extract_info(url, download=False)
    
    duration = float(info.get("duration") or 0)
    if duration <= 0:
        duration = 100.0

    # 1. Attempt YouTube storyboard extraction (instant, no stream seek)
    boards = [f for f in info.get("formats", []) if f.get("protocol") == "mhtml" and f.get("fragments") and f.get("fps")]
    if boards:
        try:
            board = max(boards, key=lambda f: f.get("width", 0))
            cols = board.get("columns", 1)
            rows = board.get("rows", 1)
            tiles = cols * rows
            sheets = {}
            for i, frac in enumerate((0.08, 0.30, 0.60, 0.85)):
                t = duration * frac
                idx = int(t * board["fps"])
                sheet_idx = min(idx // tiles, len(board["fragments"]) - 1)
                cell = idx % tiles
                if sheet_idx not in sheets:
                    req = urllib.request.Request(board["fragments"][sheet_idx]["url"], headers={"User-Agent": "Mozilla/5.0"})
                    with urllib.request.urlopen(req, timeout=12) as resp:
                        sheets[sheet_idx] = Image.open(io.BytesIO(resp.read())).convert("RGB")
                img = sheets[sheet_idx]
                cw, ch = img.width // cols, img.height // rows
                x = (cell % cols) * cw
                y = (cell // cols) * ch
                out_p = folder / f"{i}.jpg"
                img.crop((x, y, x + cw, y + ch)).save(out_p, quality=92)
                report_ready(out_p, t, "storyboard")
            return frames
        except Exception:
            pass

    # 2. Fallback: seek low-res stream directly
    formats = [f for f in info.get("formats", []) if f.get("vcodec") not in (None, "none") and f.get("url") and f.get("height", 9999) <= 480]
    stream_url = max(formats, key=lambda f: f.get("height", 0))["url"] if formats else info.get("url")
    if stream_url:
        for i, frac in enumerate((0.08, 0.30, 0.60, 0.85)):
            t = duration * frac
            out_p = folder / f"{i}.jpg"
            cmd = ["ffmpeg", "-y", "-v", "error", "-ss", f"{t:.2f}", "-i", stream_url, "-frames:v", "1", "-vf", "scale=640:-2", str(out_p)]
            r = subprocess.run(cmd, capture_output=True, timeout=25, creationflags=NO_WINDOW)
            if r.returncode == 0 and out_p.exists():
                report_ready(out_p, t, "stream")

    return frames

def extract_storyboard(src_path: Path, duration: float, out_dir: Path) -> list[Path]:
    """Extracts 4 evenly spaced frames from a local video for preview bounding boxes."""
    out_dir.mkdir(parents=True, exist_ok=True)
    frames = []
    dur = max(duration, 1.0)
    for i, frac in enumerate((0.10, 0.35, 0.65, 0.85)):
        t = dur * frac
        out_p = out_dir / f"{src_path.stem}_sb_{i}.jpg"
        if not out_p.exists():
            cmd = ["ffmpeg", "-y", "-v", "error", "-ss", f"{t:.2f}", "-i", str(src_path), "-frames:v", "1", "-vf", "scale=640:-2", str(out_p)]
            subprocess.run(cmd, capture_output=True, timeout=15, creationflags=NO_WINDOW)
        if out_p.exists():
            frames.append(out_p)
    return frames

def extract_seek_frame(src_path: Path, sec: float, out_dir: Path) -> Path | None:
    """Extracts a single frame at the given timestamp."""
    out_dir.mkdir(parents=True, exist_ok=True)
    out_p = out_dir / f"{src_path.stem}_seek_{int(sec * 10)}.jpg"
    if not out_p.exists():
        cmd = ["ffmpeg", "-y", "-v", "error", "-ss", f"{sec:.2f}", "-i", str(src_path), "-frames:v", "1", "-vf", "scale=640:-2", str(out_p)]
        subprocess.run(cmd, capture_output=True, timeout=15, creationflags=NO_WINDOW)
    return out_p if out_p.exists() else None

def preview_video_url(url: str, creator_id: Optional[str] = None) -> dict:
    """Inspects a video URL (YouTube, Twitch, etc.), extracts metadata, game, and high-res preview frames."""
    url = url.strip()
    if not url:
        raise ValueError("Video URL cannot be empty.")

    cookie_p = get_cookies_file()
    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "socket_timeout": 15
    }
    if cookie_p:
        opts["cookiefile"] = str(cookie_p)

    info = None
    age_restricted = False
    try:
        with yt_dlp.YoutubeDL(opts) as y:
            info = y.extract_info(url, download=False)
    except Exception as ytdl_err:
        err_str = str(ytdl_err)
        yt_id = extract_youtube_id(url)
        if yt_id:
            age_restricted = any(phrase in err_str.lower() for phrase in ["sign in", "confirm your age", "cookies", "inappropriate", "private"])
            title = f"YouTube Video ({yt_id})"
            uploader = "YouTube Creator"
            try:
                oembed_url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={yt_id}&format=json"
                req = urllib.request.Request(oembed_url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
                with urllib.request.urlopen(req, timeout=6) as resp:
                    oembed_data = json.loads(resp.read().decode("utf-8"))
                    title = oembed_data.get("title") or title
                    uploader = oembed_data.get("author_name") or uploader
            except Exception:
                pass
            dur_val = 0.0
            try:
                wp_req = urllib.request.Request(f"https://www.youtube.com/watch?v={yt_id}", headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
                with urllib.request.urlopen(wp_req, timeout=5) as wp_resp:
                    html_content = wp_resp.read().decode("utf-8", errors="ignore")
                m_dur = re.findall(r'lengthSeconds":\s*"(\d+)"', html_content)
                if m_dur:
                    dur_val = float(m_dur[0])
            except Exception:
                pass

            info = {
                "id": yt_id,
                "title": title,
                "uploader": uploader,
                "duration": dur_val,
                "thumbnail": f"https://i.ytimg.com/vi/{yt_id}/maxresdefault.jpg"
            }
        else:
            raise ytdl_err

    vid_id = info.get("id") or uuid.uuid4().hex[:8]
    title = info.get("title") or "Video"
    uploader = info.get("uploader") or info.get("channel") or ""
    duration = float(info.get("duration") or 0)

    if duration >= 3600:
        dur_str = f"{int(duration // 3600)}h {int((duration % 3600) // 60)}m {int(duration % 60)}s"
    elif duration > 0:
        dur_str = f"{int(duration // 60)}m {int(duration % 60)}s"
    else:
        dur_str = "Live / Unknown"

    game, hashtags = detect_game(title, uploader)

    source_id = f"yt_{vid_id}"
    rel_folder = source_id
    if creator_id:
        from ..creators import get_creator_dirs
        _, c_videos_dir, _ = get_creator_dirs(creator_id)
        folder = c_videos_dir / source_id
        rel_folder = f"creators/{creator_id}/videos/{source_id}"
    else:
        folder = DATA_DIR / source_id

    folder.mkdir(parents=True, exist_ok=True)
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    # 1. Download high-res cover thumbnail
    thumb_candidates = [
        f"https://i.ytimg.com/vi/{vid_id}/maxresdefault.jpg",
        f"https://i.ytimg.com/vi/{vid_id}/hq720.jpg",
        f"https://i.ytimg.com/vi/{vid_id}/hqdefault.jpg",
        info.get("thumbnail")
    ]
    main_img = None
    cover_path = folder / "frame_0.jpg"
    for tc in thumb_candidates:
        if not tc:
            continue
        try:
            req = urllib.request.Request(tc, headers=headers)
            with urllib.request.urlopen(req, timeout=6) as resp:
                data = resp.read()
                im = Image.open(io.BytesIO(data)).convert("RGB")
                im.save(cover_path, quality=92)
                main_img = im
                break
        except Exception:
            continue

    # 2. Download timeline frames (hq1, hq2, hq3 for YouTube)
    saved_frames = [cover_path] if cover_path.exists() else []
    for idx, num in enumerate(("1", "2", "3"), start=1):
        sub_url = f"https://i.ytimg.com/vi/{vid_id}/hq{num}.jpg"
        out_p = folder / f"frame_{idx}.jpg"
        try:
            req = urllib.request.Request(sub_url, headers=headers)
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = resp.read()
                im = Image.open(io.BytesIO(data)).convert("RGB")
                im.save(out_p, quality=90)
                saved_frames.append(out_p)
        except Exception:
            pass

    # 3. Fallback duplicate frames if only cover exists
    if len(saved_frames) < 2 and main_img:
        for idx in (1, 2, 3):
            out_p = folder / f"frame_{idx}.jpg"
            if not out_p.exists():
                try:
                    main_img.save(out_p, quality=90)
                    saved_frames.append(out_p)
                except Exception:
                    pass

    w, h = (main_img.width, main_img.height) if main_img else (1920, 1080)

    # 4. Detect facecam on frames
    cam_box = {"x": 0.0, "y": 0.0, "w": 0.28, "h": 0.32}
    try:
        if saved_frames:
            fc_res = detect_facecam(saved_frames)
            if fc_res.get("detected") and fc_res.get("box"):
                cam_box = fc_res["box"]
    except Exception:
        pass

    # 5. Save source.json
    frame_rels = [f"{rel_folder}/{f.name}" for f in sorted(folder.glob("frame_*.jpg"))]
    meta_payload = {
        "id": source_id,
        "url": url,
        "title": title,
        "uploader": uploader,
        "duration": duration,
        "duration_formatted": dur_str,
        "w": w,
        "h": h,
        "thumbnail": f"/media/{rel_folder}/frame_0.jpg",
        "frames": frame_rels,
        "game": game,
        "hashtags": hashtags,
        "cam": cam_box,
        "creator": creator_id,
        "age_restricted": age_restricted
    }
    if age_restricted:
        meta_payload["notice"] = (
            "Age-restricted or sign-in required video detected. "
            "Preview frames were loaded via YouTube CDN. "
            "To download video slices or audio, please configure YouTube cookies in LLM & Settings."
        )
    (folder / "source.json").write_text(json.dumps(meta_payload, indent=2), encoding="utf-8")

    if creator_id:
        try:
            from ..creators import log_creator_event
            log_creator_event(creator_id, f"Inspected video '{title}' ({dur_str})", action="preview")
        except Exception:
            pass

    return meta_payload
