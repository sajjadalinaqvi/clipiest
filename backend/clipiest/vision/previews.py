"""Rapid early preview frames for Clipiest.
Extracts 4 frames across the duration before full source video download completes.
"""
import io
import os
import subprocess
import urllib.request
from pathlib import Path
from PIL import Image
import yt_dlp

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
