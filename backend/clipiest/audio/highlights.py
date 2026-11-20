"""Multi-signal highlight ranking: audio loudness jumps, 2-4kHz shout energy, cuts & optical flow."""
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
import numpy as np
import cv2

NO_WINDOW = 0x08000000 if os.name == "nt" else 0

FPS = 3
W, H = 160, 90
CUT_THRESH = 38.0

def _chunk_video(source, start, length, report_fn):
    cmd = [
        "ffmpeg", "-v", "error", "-ss", f"{start}", "-t", f"{length}", "-i", str(source), "-an",
        "-vf", f"fps={FPS},scale={W}:{H}", "-pix_fmt", "gray", "-f", "rawvideo", "pipe:1"
    ]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=W * H * 64, creationflags=NO_WINDOW)
    flow, cuts, prev = [], [], None
    try:
        while True:
            raw = p.stdout.read(W * H)
            while raw and len(raw) < W * H:
                more = p.stdout.read(W * H - len(raw))
                if not more: break
                raw += more
            if len(raw) != W * H: break
            cur = np.frombuffer(raw, np.uint8).reshape(H, W)
            if prev is None:
                flow.append(0.0); cuts.append(0.0)
            else:
                if float(np.mean(cv2.absdiff(cur, prev))) > CUT_THRESH:
                    flow.append(0.0); cuts.append(1.0)
                else:
                    f = cv2.calcOpticalFlowFarneback(prev, cur, None, 0.5, 2, 9, 2, 5, 1.1, 0)
                    flow.append(float(np.percentile(np.hypot(f[..., 0], f[..., 1]), 90)))
                    cuts.append(0.0)
            prev = cur
        p.wait()
    finally:
        if p.poll() is None: p.kill(); p.wait()
        p.stdout.close()
    report_fn(length)
    k = len(flow) // FPS * FPS
    f_arr = np.array(flow[:k]).reshape(-1, FPS).mean(1) if k else np.zeros(0)
    c_arr = np.array(cuts[:k]).reshape(-1, FPS).sum(1) if k else np.zeros(0)
    return f_arr, c_arr

def _optical_flow_parallel(source, duration, report_fn):
    workers = max(2, min(8, (os.cpu_count() or 4) - 1))
    size = max(60, int(np.ceil(duration / workers / 60) * 60))
    starts = list(range(0, int(np.ceil(duration)), size))
    done = [0.0]
    def rep(sec):
        done[0] += sec
        report_fn(min(done[0], duration))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        jobs = {pool.submit(_chunk_video, source, s, min(size, duration - s), rep): s for s in starts}
        parts = {jobs[j]: j.result() for j in as_completed(jobs)}
    f = np.concatenate([parts[s][0] for s in starts]) if starts else np.zeros(0)
    c = np.concatenate([parts[s][1] for s in starts]) if starts else np.zeros(0)
    return f, c

def _audio_profile(source):
    cmd = ["ffmpeg", "-v", "error", "-i", str(source), "-vn", "-ac", "1", "-ar", "8000", "-f", "s16le", "pipe:1"]
    raw = subprocess.run(cmd, capture_output=True, creationflags=NO_WINDOW).stdout
    x = np.frombuffer(raw[:len(raw) // 2 * 2], np.int16).astype(np.float32) / 32768
    n = len(x) // 8000
    if n == 0:
        return np.zeros(0), np.zeros(0)
    x = x[:n * 8000].reshape(n, 8000)
    rms = np.sqrt((x ** 2).mean(1))
    spec = np.abs(np.fft.rfft(x * np.hanning(8000), axis=1)) ** 2
    hf = spec[:, 2000:4000].sum(1) / (spec.sum(1) + 1e-9)
    return rms, hf

def _zscore(x, n, win=120):
    out = np.zeros(n)
    if not len(x):
        return out
    y = np.zeros(n)
    y[:min(n, len(x))] = x[:n]
    win = max(1, min(win, n))
    k = np.ones(win) / win
    mu = np.convolve(y, k, "same")
    sd = np.sqrt(np.maximum(np.convolve(y * y, k, "same") - mu * mu, 0)) + 1e-6
    return np.clip((y - mu) / sd / 3.5, 0, 1)

def rank_highlights(
    source,
    duration: float,
    count: int = 4,
    length: float = 30.0,
    report_fn=lambda s: None,
    motion_on: bool = True,
    extra_excite: np.ndarray = None
) -> list:
    """Returns top ranked moments based on audio jumps, shouts, motion flow and cuts."""
    with ThreadPoolExecutor(max_workers=2) as pool:
        m_fut = pool.submit(_optical_flow_parallel, source, duration, report_fn) if motion_on else pool.submit(lambda: (np.zeros(0), np.zeros(0)))
        a_fut = pool.submit(_audio_profile, source)
        (flow, cuts), (rms, hf) = m_fut.result(), a_fut.result()

    n = max(1, int(np.ceil(duration)))
    has_audio = len(rms) > 0
    motion = _zscore(flow, n)
    cut = _zscore(cuts, n)
    loud = _zscore(rms, n) if has_audio else np.zeros(n)
    shout = np.clip(_zscore(hf * rms, n) if has_audio else np.zeros(n), 0, 1)

    if motion_on and has_audio:
        sig = 0.35 * motion + 0.30 * loud + 0.20 * shout + 0.15 * cut
    elif has_audio:
        sig = 0.55 * loud + 0.45 * shout
    else:
        sig = 0.70 * motion + 0.30 * cut

    if extra_excite is not None and len(extra_excite):
        e = np.zeros(n)
        e[:min(n, len(extra_excite))] = extra_excite[:n]
        sig = 0.75 * sig + 0.25 * e

    width = min(n, 7)
    smooth = np.convolve(sig, np.ones(width) / width, "same")
    clip_len = min(float(length), duration)
    clips = []

    for center in np.argsort(smooth)[::-1]:
        start = max(0.0, min(float(center) - clip_len * 0.4, duration - clip_len))
        end = min(duration, start + clip_len)
        if any(min(end, c["end"]) - max(start, c["start"]) > 0 for c in clips):
            continue
        lo, hi = int(start), max(int(start) + 1, int(end))
        clips.append({
            "start": round(start, 2),
            "end": round(end, 2),
            "score": round(float(smooth[center]) * 100 / max(float(smooth.max()), 1e-6)),
            "features": {
                "loud": float(loud[lo:hi].mean()) if has_audio else 0.0,
                "shout": float(shout[lo:hi].mean()) if has_audio else 0.0,
                "motion": float(motion[lo:hi].mean()) if motion_on else 0.0,
                "cuts": float(cut[lo:hi].mean()) if motion_on else 0.0
            }
        })
        if len(clips) >= count:
            break

    if not clips:
        clips = [{"start": 0.0, "end": round(clip_len, 2), "score": 50, "features": {}}]
    return clips
