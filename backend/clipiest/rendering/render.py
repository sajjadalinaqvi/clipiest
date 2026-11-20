"""High-performance FFmpeg rendering engine with NVENC, QSV, and x264 acceleration."""
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from ..config import FONTS_DIR, HAS_NVENC, HAS_QSV
from .layouts import render_graph, text_positions
from .captions import write_subtitles

NO_WINDOW = 0x08000000 if os.name == "nt" else 0

def probe_video(path: Path) -> dict:
    """Probes video dimensions and duration using ffprobe."""
    import json
    cmd = ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)]
    r = subprocess.run(cmd, capture_output=True, text=True, check=True, creationflags=NO_WINDOW)
    j = json.loads(r.stdout)
    v = next(x for x in j["streams"] if x["codec_type"] == "video")
    return {
        "w": int(v["width"]),
        "h": int(v["height"]),
        "duration": float(j["format"]["duration"])
    }

def render_clip(
    src_path: Path,
    out_dir: Path,
    name: str,
    start: float,
    end: float,
    layout: str = "blur",
    top: float = 0.32,
    cam_rect: tuple = (0, 0, 320, 240),
    game_rect: tuple = (320, 0, 960, 720),
    words: list = None,
    caption_style: str = "bounce",
    caption_y: int = 1450,
    hook: str = "",
) -> dict:
    """Renders a vertical 1080x1920 MP4 with burned-in ASS captions and audio normalization."""
    src_path = Path(src_path).resolve()
    out_dir = Path(out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_mp4 = out_dir / f"{name}.mp4"
    out_jpg = out_dir / f"{name}.jpg"

    meta_in = probe_video(src_path)
    vw, vh = meta_in["w"], meta_in["h"]

    def clamp_rect(r, def_x, def_y, def_w, def_h):
        if not r or len(r) != 4:
            r = (def_x, def_y, def_w, def_h)
        x, y, w, h = r
        x = max(0, min(vw - 2, int(x)))
        y = max(0, min(vh - 2, int(y)))
        w = max(2, min(vw - x, int(w)))
        h = max(2, min(vh - y, int(h)))
        return (x, y, w, h)

    cam_rect = clamp_rect(cam_rect, 0, 0, int(vw * 0.25), int(vh * 0.30))
    game_rect = clamp_rect(game_rect, int(vw * 0.25), 0, int(vw * 0.75), vh)

    # Compute layout and text coordinates
    coords = text_positions(layout, top, caption_y)
    hook_y = coords["hook_y"]
    safe_caption_y = coords["caption_y"]

    # Short temp work directory to prevent Windows path length > 260 chars
    work = Path(tempfile.mkdtemp(prefix="clp"))
    try:
        # Copy fonts locally into work/f so FFmpeg ASS subtitle renderer finds them without global font registration
        f_dir = work / "f"
        f_dir.mkdir(parents=True, exist_ok=True)
        for ttf in FONTS_DIR.glob("*.ttf"):
            shutil.copyfile(ttf, f_dir / ttf.name)

        # Build layout filter
        rects = [cam_rect, game_rect]
        graph = render_graph(layout, rects, top)

        has_subtitles = bool((words and len(words) > 0) or hook.strip())
        if has_subtitles:
            write_subtitles(
                words or [], caption_style, work, "subs", hook=hook, caption_y=safe_caption_y, hook_y=hook_y
            )
            fc = f"{graph};[base]ass=subs.ass:fontsdir=f[v]"
        else:
            (work / "subs.ass").write_text("", encoding="utf-8")
            (work / "subs.srt").write_text("", encoding="utf-8")
            fc = f"{graph};[base]null[v]"

        base_cmd = [
            "ffmpeg", "-y", "-v", "error",
            "-ss", f"{start:.2f}",
            "-t", f"{end - start:.2f}",
            "-i", str(src_path),
            "-filter_complex", fc,
            "-map", "[v]",
            "-map", "0:a?",
            "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",
            "-c:a", "aac",
            "-b:a", "160k",
            "-ar", "48000",
            "-movflags", "+faststart"
        ]

        # Encoders to attempt in order
        encoders = []
        if HAS_NVENC:
            encoders.append(("nvenc", ["-c:v", "h264_nvenc", "-preset", "p5", "-cq", "20", "-pix_fmt", "yuv420p"]))
        if HAS_QSV:
            encoders.append(("qsv", ["-c:v", "h264_qsv", "-global_quality", "23", "-preset", "fast", "-pix_fmt", "nv12"]))
        encoders.append(("libx264", ["-c:v", "libx264", "-crf", "20", "-preset", "fast", "-pix_fmt", "yuv420p"]))

        err = None
        encoder_used = "libx264"
        for enc_name, enc_args in encoders:
            cmd = base_cmd + enc_args + ["rendered.mp4"]
            r = subprocess.run(cmd, cwd=str(work), capture_output=True, text=True, creationflags=NO_WINDOW)
            if r.returncode == 0:
                encoder_used = enc_name
                break
            err = r.stderr

        if not (work / "rendered.mp4").exists():
            raise RuntimeError(f"Rendering failed: {err}")

        # Extract crisp thumbnail cover frame
        cover_t = min(1.0, (end - start) / 2)
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-ss", f"{cover_t:.2f}", "-i", "rendered.mp4", "-frames:v", "1", "-q:v", "3", "cover.jpg"],
            cwd=str(work), capture_output=True, creationflags=NO_WINDOW
        )

        # Move generated files into destination
        shutil.move(str(work / "rendered.mp4"), str(out_mp4))
        if (work / "cover.jpg").exists():
            shutil.move(str(work / "cover.jpg"), str(out_jpg))
        shutil.copyfile(str(work / "subs.ass"), str(out_dir / f"{name}.ass"))
        shutil.copyfile(str(work / "subs.srt"), str(out_dir / f"{name}.srt"))

        meta = probe_video(out_mp4)
        return {
            "status": "done",
            "file": f"{name}.mp4",
            "cover": f"{name}.jpg",
            "srt": f"{name}.srt",
            "ass": f"{name}.ass",
            "meta": meta,
            "encoder": encoder_used
        }
    finally:
        shutil.rmtree(work, ignore_errors=True)
