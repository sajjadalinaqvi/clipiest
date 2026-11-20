"""Computer-vision facecam detector for Clipiest.
Combines stationary border edge detection and temporal pixel stillness variance.
"""
import os
import subprocess
from pathlib import Path
import numpy as np

NO_WINDOW = 0x08000000 if os.name == "nt" else 0

W, H = 320, 180
MAX_FRAMES = 24
MIN_SIZE = 0.12
MAX_SIZE = 0.60
ASPECT_MIN = 0.55
ASPECT_MAX = 3.20
STILL_FRAC = 0.35
STILL_MIN = 6.0
STILL_SHARE = 0.30
EDGE_FLUSH = 0.02
EDGE = 2.2

def _duration(path: Path) -> float:
    try:
        proc = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
            capture_output=True, text=True, timeout=30, creationflags=NO_WINDOW
        )
        return float((proc.stdout or "").strip() or 0)
    except Exception:
        return 0.0

def _extract_frames(path: Path, count: int = MAX_FRAMES) -> np.ndarray:
    try:
        dur = _duration(path)
        rate = max(count / dur, 0.02) if dur > 0 else 0.2
        proc = subprocess.run(
            ["ffmpeg", "-v", "error", "-i", str(path),
             "-vf", f"fps={rate:.4f},scale={W}:{H},format=gray",
             "-frames:v", str(count), "-f", "rawvideo", "-"],
            capture_output=True, timeout=60, creationflags=NO_WINDOW
        )
        raw = proc.stdout or b""
        size = W * H
        n = len(raw) // size
        if n < 4:
            return np.zeros((0, H, W), dtype=np.uint8)
        return np.frombuffer(raw[:n * size], dtype=np.uint8).reshape(n, H, W)
    except Exception:
        return np.zeros((0, H, W), dtype=np.uint8)

def _profiles(frames: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    if len(frames) < 4:
        return np.zeros(W), np.zeros(H)
    f = frames.astype(np.int16)
    gx = np.median(np.abs(np.diff(f, axis=2)).sum(axis=1), axis=0)
    gy = np.median(np.abs(np.diff(f, axis=1)).sum(axis=2), axis=0)
    return gx, gy

def _peaks(profile: np.ndarray, limit: int = 10) -> list[tuple[int, float]]:
    if len(profile) < 3:
        return []
    med = float(np.median(profile)) or 1.0
    out = []
    for i in range(1, len(profile) - 1):
        if profile[i] >= profile[i - 1] and profile[i] > profile[i + 1] and profile[i] > EDGE * med:
            out.append((i, float(profile[i] / med)))
    return sorted(out, key=lambda p: -p[1])[:limit]

def detect_facecam(target) -> dict:
    """Detects webcam position in a video, image list, or frame directory.
    Returns: {'detected': bool, 'box': {'x': .., 'y': .., 'w': .., 'h': ..}, 'confidence': float}
    """
    frames = None
    if isinstance(target, np.ndarray):
        frames = target
    elif isinstance(target, (list, tuple)):
        loaded = []
        from PIL import Image
        for item in target:
            try:
                im = Image.open(Path(item)).convert("L").resize((W, H))
                loaded.append(np.array(im, dtype=np.uint8))
            except Exception:
                pass
        if len(loaded) >= 2:
            frames = np.stack(loaded, axis=0)
    elif isinstance(target, (str, Path)):
        p = Path(target)
        if p.is_dir():
            img_files = sorted(p.glob("frame_*.jpg")) or sorted(p.glob("*.jpg"))
            if img_files:
                return detect_facecam(img_files)
        elif p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
            return detect_facecam([p])
        else:
            frames = _extract_frames(p)

    if frames is None or len(frames) < 2:
        return {"detected": False, "box": None, "confidence": 0.0}
    
    gx, gy = _profiles(frames)
    vpeaks = _peaks(gx)
    hpeaks = _peaks(gy)
    
    still = frames.astype(np.float32).std(axis=0)
    game_motion = float(np.median(still))
    light = frames.mean(axis=0)

    xs = sorted({0.0, float(W)} | {float(x) for x, _ in vpeaks})
    ys = sorted({0.0, float(H)} | {float(y) for y, _ in hpeaks})
    vs = {float(x): s for x, s in vpeaks}
    hs = {float(y): s for y, s in hpeaks}

    candidates = []
    for i, x0 in enumerate(xs):
        wx = [vs[x0]] if x0 in vs else []
        for x1 in xs[i + 1:]:
            wscore = wx + ([vs[x1]] if x1 in vs else [])
            for j, y0 in enumerate(ys):
                hy0 = [hs[y0]] if y0 in hs else []
                for y1 in ys[j + 1:]:
                    score = wscore + hy0 + ([hs[y1]] if y1 in hs else [])
                    if len(score) < 2:
                        continue
                    
                    bw, bh = (x1 - x0) / W, (y1 - y0) / H
                    if not (MIN_SIZE <= bw <= MAX_SIZE and MIN_SIZE <= bh <= MAX_SIZE):
                        continue
                    aspect = (bw * W) / max(1e-6, bh * H)
                    if not (ASPECT_MIN <= aspect <= ASPECT_MAX):
                        continue
                        
                    inside = still[int(y0):int(y1), int(x0):int(x1)]
                    if not inside.size:
                        continue
                    cut = max(STILL_MIN, STILL_FRAC * game_motion)
                    moving = float(np.median(inside))
                    if moving > cut or float((inside > cut).mean()) > STILL_SHARE:
                        continue
                    if float(light[int(y0):int(y1), int(x0):int(x1)].mean()) < 0.25 * float(light.mean()):
                        continue
                        
                    candidates.append({
                        "x": round(x0 / W, 4),
                        "y": round(y0 / H, 4),
                        "w": round((x1 - x0) / W, 4),
                        "h": round((y1 - y0) / H, 4),
                        "score": round(min(score), 2)
                    })

    if not candidates:
        return {"detected": False, "box": None, "confidence": 0.0}
        
    best = max(candidates, key=lambda c: c["score"])
    return {
        "detected": True,
        "box": {
            "x": best["x"],
            "y": best["y"],
            "w": best["w"],
            "h": best["h"]
        },
        "confidence": 0.92 if best["score"] > 3.0 else 0.75
    }
