"""Unified Speech-to-Text for Clipiest: Faster-Whisper and YouTube JSON3 auto-captions."""
import json
import os
import re
import subprocess
import threading
import urllib.request
import uuid
from pathlib import Path
from ..config import MODELS_DIR, USE_CPU, WHISPER_MODEL
from ..rendering.translit import to_roman

NO_WINDOW = 0x08000000 if os.name == "nt" else 0

_LOCK = threading.Lock()
_WHISPER_INSTANCES = {}

def get_whisper(model_size: str = WHISPER_MODEL):
    with _LOCK:
        if model_size in _WHISPER_INSTANCES:
            return _WHISPER_INSTANCES[model_size]
        from faster_whisper import WhisperModel
        device = "cpu" if USE_CPU else "cuda"
        compute_type = "int8" if USE_CPU else "int8_float16"
        try:
            m = WhisperModel(model_size, device=device, compute_type=compute_type, download_root=str(MODELS_DIR))
            # Test small run to verify cuDNN/cuBLAS
            list(m.transcribe(__import__("numpy").zeros(16000, dtype="float32"))[0])
        except Exception:
            # Fallback to CPU int8
            m = WhisperModel(model_size, device="cpu", compute_type="int8", download_root=str(MODELS_DIR))
        _WHISPER_INSTANCES[model_size] = m
        return m

def transcribe_audio_segment(
    src_path: Path,
    start: float,
    end: float,
    data_dir: Path,
    language: str = None,
    report_fn=lambda msg: None
) -> dict:
    """Transcribes audio slice with word timestamps using Faster-Whisper."""
    report_fn("Transcribing audio segment...")
    out_wav = data_dir / f"temp_{src_path.stem}_{uuid.uuid4().hex[:8]}_{start:.1f}_{end:.1f}.wav"
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-ss", f"{start:.2f}", "-t", f"{end - start:.2f}",
             "-i", str(src_path), "-vn", "-ac", "1", "-ar", "16000", str(out_wav)],
            capture_output=True, check=True, timeout=120, creationflags=NO_WINDOW
        )
        model = get_whisper()
        lang_arg = "hi" if language == "hinglish" else language
        segments, info = model.transcribe(
            str(out_wav),
            beam_size=5,
            word_timestamps=True,
            vad_filter=True,
            language=lang_arg
        )
        words = []
        for s in segments:
            for w in (s.words or []):
                txt = w.word.strip()
                if language == "hinglish":
                    txt = to_roman(txt)
                if txt and w.end > w.start:
                    words.append({
                        "start": round(max(0.0, w.start), 3),
                        "end": round(min(end - start, w.end), 3),
                        "text": txt
                    })
        return {
            "words": words,
            "language": info.language,
            "duration": end - start
        }
    finally:
        out_wav.unlink(missing_ok=True)

def youtube_words_from_info(info: dict) -> list | None:
    """Extracts YouTube's native word-timed auto-captions (json3) in ~1 second."""
    auto = info.get("automatic_captions") or {}
    manual = info.get("subtitles") or {}
    lang = info.get("language") or ""
    
    key = None
    if lang and f"{lang}-orig" in auto:
        key = f"{lang}-orig"
    elif lang and lang in auto:
        key = lang
    elif "en-orig" in auto:
        key = "en-orig"
    elif auto:
        key = next(iter(auto))
        
    group = auto
    if not key and manual:
        key = next(iter(manual))
        group = manual
        
    if not key:
        return None
        
    track = next((f for f in group.get(key, []) if f.get("ext") == "json3" and f.get("url")), None)
    if not track:
        return None
        
    try:
        req = urllib.request.Request(track["url"], headers={"User-Agent": "Mozilla/5.0"})
        data = json.loads(urllib.request.urlopen(req, timeout=25).read(40_000_000))
        out = []
        skipping = False
        for ev in data.get("events", []):
            segs = [x for x in ev.get("segs", []) if (x.get("utf8") or "").strip()]
            if not segs:
                continue
            t0, dur = float(ev.get("tStartMs") or 0), float(ev.get("dDurationMs") or 0)
            timed = len(segs) > 1 or "tOffsetMs" in segs[0]
            for x in segs:
                parts = x["utf8"].split()
                for n, w in enumerate(parts):
                    if skipping:
                        if w.endswith(("]", ")")): skipping = False
                        continue
                    if w[:1] in "[(" and not re.fullmatch(r"[\[(].*[\])]", w):
                        skipping = True; continue
                    if re.fullmatch(r"[\[(].*[\])]", w) or w in ("[", "]", "__", ">>", "-"):
                        continue
                    at = t0 + float(x.get("tOffsetMs") or 0) if timed else t0 + dur * n / max(1, len(parts))
                    out.append({"start": round(at / 1000, 2), "text": w})
        out.sort(key=lambda w: w["start"])
        for n, w in enumerate(out):
            nxt = out[n + 1]["start"] if n + 1 < len(out) else w["start"] + 0.4
            w["end"] = round(max(w["start"] + 0.08, min(nxt, w["start"] + 0.6)), 2)
        return out or None
    except Exception:
        return None

def window_words(words: list, start: float, end: float) -> list:
    """Returns words inside [start, end) normalized relative to start."""
    return [
        {
            "start": round(w["start"] - start, 3),
            "end": round(min(w["end"], end) - start, 3),
            "text": w["text"]
        }
        for w in words if start <= w["start"] < end
    ]
