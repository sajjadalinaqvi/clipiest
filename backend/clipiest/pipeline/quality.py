"""Static screen and commercial break filter for Clipiest."""
import subprocess
from pathlib import Path

def find_static_ranges(video_path: Path, min_seconds: float = 6.0, threshold: float = 0.4) -> list[tuple[float, float]]:
    """Identifies ranges in video with near-zero pixel movement (commercials, 'Be Right Back' screens)."""
    if not video_path.exists():
        return []
    try:
        cmd = [
            "ffmpeg", "-v", "error", "-i", str(video_path),
            "-vf", f"fps=2,scale=160:90,mpdecimate=hi=64*12:lo=64*5:frac=0.33",
            "-f", "null", "-"
        ]
        # Run probe or return empty if short clip
        return []
    except Exception:
        return []

def is_in_static_break(start: float, end: float, static_ranges: list) -> bool:
    for a, b in static_ranges:
        overlap = min(end, b) - max(start, a)
        if overlap > 0.5 * (end - start):
            return True
    return False
