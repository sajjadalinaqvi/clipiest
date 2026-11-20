"""Visual action heuristics: optical flow motion, explosion flashes, siren strobes, and cuts."""
import os
import subprocess
import numpy as np
import cv2

NO_WINDOW = 0x08000000 if os.name == "nt" else 0

W, H, FPS = 160, 90, 6

def analyze_action(path, start: float, duration: float) -> dict:
    """Analyzes a candidate clip for visual action cues scaled from 0.0 to 1.0."""
    cmd = [
        "ffmpeg", "-v", "error",
        "-ss", f"{max(0, start):.2f}",
        "-t", f"{duration:.2f}",
        "-i", str(path),
        "-an",
        "-vf", f"fps={FPS},scale={W}:{H}",
        "-pix_fmt", "rgb24",
        "-f", "rawvideo", "pipe:1"
    ]
    raw = subprocess.run(cmd, capture_output=True, creationflags=NO_WINDOW).stdout
    size = W * H * 3
    n = len(raw) // size
    if n < 4:
        return {"motion": 0.0, "flash": 0.0, "strobe": 0.0, "cuts": 0.0}
    
    frames = np.frombuffer(raw[:n * size], np.uint8).reshape(n, H, W, 3)
    gray = frames.mean(axis=3).astype(np.uint8)
    lum = gray.reshape(n, -1).mean(axis=1)
    
    flows, cuts = [], 0
    for i in range(1, n):
        diff = float(np.mean(cv2.absdiff(gray[i], gray[i - 1])))
        if diff > 38:
            cuts += 1
            continue
        f = cv2.calcOpticalFlowFarneback(gray[i - 1], gray[i], None, 0.5, 2, 9, 2, 5, 1.1, 0)
        flows.append(float(np.percentile(np.hypot(f[..., 0], f[..., 1]), 90)))
        
    motion = float(np.mean(flows)) if flows else 0.0
    
    # Flash: Short bright burst followed by immediate drop
    d = np.diff(lum)
    flash_events = int(np.sum((d[:-1] > 26) & (d[1:] < -10)))
    
    # Fire/Orange explosion flash check
    r = frames[..., 0].astype(np.int16)
    g = frames[..., 1].astype(np.int16)
    b = frames[..., 2].astype(np.int16)
    orange = ((r > 200) & (g > 90) & (g < 190) & (b < 90)).reshape(n, -1).mean(axis=1)
    flash_events += int(np.sum(np.diff(orange) > 0.08))
    
    # Police light strobe (alternating red and blue dominance)
    red = ((r > 170) & (g < 90) & (b < 90)).reshape(n, -1).mean(axis=1)
    blue = ((b > 170) & (r < 90) & (g < 140)).reshape(n, -1).mean(axis=1)
    diff_rb = red - blue
    sign = np.where(diff_rb > 0.004, 1, np.where(diff_rb < -0.004, -1, 0))
    nz = sign[sign != 0]
    alternations = int(np.sum(nz[1:] != nz[:-1])) if len(nz) > 1 else 0
    
    secs = max(1.0, n / FPS)
    return {
        "motion": float(min(1.0, motion / 8.0)),
        "flash": float(min(1.0, flash_events / max(secs / 6.0, 1.0) / 3.0)),
        "strobe": float(min(1.0, alternations / max(secs, 1.0) / 1.5)),
        "cuts": float(min(1.0, cuts / max(secs / 4.0, 1.0)))
    }
