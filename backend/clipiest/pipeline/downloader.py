"""yt-dlp download management and audio cross-correlation for Clipiest."""
import subprocess
from pathlib import Path
import numpy as np
import yt_dlp
from ..config import PAD_SEC

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
    return np.frombuffer(subprocess.run(cmd, capture_output=True).stdout, dtype=np.int16).astype("float32")

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

def download_video_section(url: str, out_dir: Path, name: str, start: float, end: float) -> Path:
    """Downloads only the required time slice of a video using yt-dlp download_ranges."""
    from yt_dlp.utils import download_range_func
    out_dir.mkdir(parents=True, exist_ok=True)
    out_tmpl = str(out_dir / f"{name}.%(ext)s")
    
    opts = {
        "format": "bv*[height<=720][vcodec^=avc1]+ba[ext=m4a]/bv*[height<=720]+ba/b[height<=720]/b",
        "merge_output_format": "mp4",
        "outtmpl": out_tmpl,
        "download_ranges": download_range_func(None, [(max(0.0, start - PAD_SEC), end + 1.0)])
    }
    with get_ytdl(opts) as y:
        y.download([url])
        
    res = next((p for p in out_dir.glob(f"{name}.*") if p.suffix in (".mp4", ".mkv", ".webm")), None)
    if not res:
        raise RuntimeError(f"Section download failed for {url}")
    return res
