"""yt-dlp download management and audio cross-correlation for Clipiest."""
import os
import subprocess
from pathlib import Path
import numpy as np
import yt_dlp
from ..config import PAD_SEC, get_cookies_file

NO_WINDOW = 0x08000000 if os.name == "nt" else 0
BELOW_NORMAL_PRIORITY = 0x00004000 if os.name == "nt" else 0
SUBPROC_FLAGS = NO_WINDOW | BELOW_NORMAL_PRIORITY

def select_lowest_audio_format(info: dict | None) -> str:
    """Selects the smallest format containing audio for fast scouting (audio-only first, else lowest-height stream)."""
    formats = (info or {}).get("formats") or []
    audio_only = [
        f for f in formats
        if f.get("format_id")
        and f.get("acodec") not in (None, "none")
        and f.get("vcodec") in (None, "none")
    ]
    if audio_only:
        return "ba/b[height<=360]/w/b"

    with_audio = [
        f for f in formats
        if f.get("format_id") and f.get("acodec") not in (None, "none")
    ]
    if with_audio:
        with_audio.sort(key=lambda f: (
            f.get("height") or 99999,
            f.get("tbr") or f.get("abr") or 999999
        ))
        return f"{with_audio[0]['format_id']}/ba/b[height<=360]/w/b"

    return "ba/b[height<=360]/b[height<=480]/w/b"


def get_ytdl(extra_opts: dict = None):
    opts = {
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "socket_timeout": 20,
        "retries": 3,
        "fragment_retries": 3,
        "concurrent_fragment_downloads": 4
    }
    cookie_p = get_cookies_file()
    if cookie_p:
        opts["cookiefile"] = str(cookie_p)
    if extra_opts:
        opts.update(extra_opts)
    return yt_dlp.YoutubeDL(opts)

def _pcm(path: Path, start: float = None, length: float = None) -> np.ndarray:
    cmd = ["ffmpeg", "-v", "error"]
    if start is not None:
        cmd += ["-ss", f"{max(0, start):.2f}"]
    if length is not None:
        cmd += ["-t", f"{length:.2f}"]
    cmd += ["-i", str(path), "-vn", "-ac", "1", "-ar", "8000", "-f", "s16le", "pipe:1"]
    return np.frombuffer(subprocess.run(cmd, capture_output=True, creationflags=NO_WINDOW).stdout, dtype=np.int16).astype("float32")

def find_exact_section_start(master_audio_path: Path, section_video_path: Path, expected_start: float) -> float:
    """Finds exact starting timestamp of keyframe-padded downloaded video section using FFT audio cross-correlation."""
    needle = _pcm(section_video_path, 0, 20)
    if len(needle) < 8000 * 5 or float(np.abs(needle).mean()) < 20:
        return expected_start
    
    a0 = max(0.0, expected_start - 20)
    hay = _pcm(master_audio_path, a0, 20 + 20 + len(needle) / 8000 + 2)
    if len(hay) < len(needle):
        return expected_start
        
    size = 1 << (len(hay) + len(needle)).bit_length()
    corr = np.fft.irfft(np.fft.rfft(hay, size) * np.conj(np.fft.rfft(needle, size)), size)[:len(hay) - len(needle) + 1]
    return a0 + int(np.argmax(corr)) / 8000.0

def download_video_section(url: str, out_dir: Path, name: str, start: float, end: float, height: int = 720, pad: float = PAD_SEC) -> Path:
    """Downloads only the required time slice of a video using yt-dlp download_ranges with robust FFmpeg fallback.
    Set pad=0.0 for exact slice/export cuts (avoiding pre-roll dead air before the hook)."""
    from yt_dlp.utils import download_range_func
    out_dir.mkdir(parents=True, exist_ok=True)
    out_tmpl = str(out_dir / f"{name}.%(ext)s")
    s_time = max(0.0, start - pad)
    e_time = end + (1.0 if pad > 0 else 0.15)
    
    # 1. Primary: yt-dlp download_ranges (fastest for YouTube DASH & Kick/Twitch HLS)
    opts = {
        "format": f"bv*[height<={height}]+ba/b[height<={height}]/b",
        "merge_output_format": "mp4",
        "outtmpl": out_tmpl,
        "download_ranges": download_range_func(None, [(s_time, e_time)])
    }
    if pad == 0:
        opts["force_keyframes_at_cuts"] = True
    try:
        with get_ytdl(opts) as y:
            y.download([url])
        res = next((p for p in out_dir.glob(f"{name}.*") if p.suffix in (".mp4", ".mkv", ".webm") and p.stat().st_size > 5000), None)
        if res:
            return res
    except Exception:
        pass

    # 2. Universal Fallback: extract direct stream URL and cut slice with FFmpeg
    # Guarantees 100% support for Twitch VODs, Kick streams, and YouTube fallback
    try:
        with get_ytdl({"skip_download": True}) as y:
            info = y.extract_info(url, download=False)
        stream_url = info.get("url")
        if not stream_url and info.get("formats"):
            formats = [f for f in info["formats"] if f.get("url")]
            if formats:
                cand = [f for f in formats if f.get("height", 9999) <= height]
                stream_url = (cand[-1] if cand else formats[-1])["url"]
        
        if stream_url:
            out_mp4 = out_dir / f"{name}.mp4"
            dur = max(2.0, e_time - s_time)
            cmd = [
                "ffmpeg", "-y", "-v", "error",
                "-ss", f"{s_time:.2f}",
                "-i", stream_url,
                "-t", f"{dur:.2f}",
                "-c:v", "libx264", "-c:a", "aac",
                "-threads", "2",
                "-movflags", "+faststart",
                str(out_mp4)
            ]
            subprocess.run(cmd, timeout=120, check=True, creationflags=SUBPROC_FLAGS)
            if out_mp4.exists() and out_mp4.stat().st_size > 5000:
                return out_mp4
    except Exception as e:
        pass
        
    res = next((p for p in out_dir.glob(f"{name}.*") if p.suffix in (".mp4", ".mkv", ".webm")), None)
    if not res:
        cookie_p = get_cookies_file()
        if not cookie_p and ("youtube.com" in url or "youtu.be" in url):
            raise RuntimeError(f"Section download failed for {url}. If this video is age-restricted or requires sign-in, please upload cookies.txt in Settings > YouTube Cookies.")
        raise RuntimeError(f"Section download failed for {url}")
    return res
