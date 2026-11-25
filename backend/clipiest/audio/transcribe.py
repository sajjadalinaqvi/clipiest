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

def _transcribe_wav_chunk(
    model,
    wav_path: Path,
    offset: float = 0.0,
    max_dur: float | None = None,
    beam_size: int = 5
) -> list:
    """Runs Faster-Whisper on a WAV file in strict English-only mode and returns word dicts."""
    segments, _ = model.transcribe(
        str(wav_path),
        beam_size=beam_size,
        word_timestamps=True,
        vad_filter=True,
        language="en"
    )
    words = []
    for s in segments:
        for w in (s.words or []):
            txt = w.word.strip()
            # Filter out any non-ASCII / non-Latin characters (reject Hindi/Devanagari)
            if re.search(r"[\u0900-\u097F]", txt):
                continue
            if txt and w.end > w.start:
                st = max(0.0, w.start)
                en = min(max_dur, w.end) if max_dur is not None else w.end
                if en > st:
                    words.append({
                        "start": round(offset + st, 3),
                        "end": round(offset + en, 3),
                        "text": txt
                    })
    return words


def transcribe_audio_segment(
    src_path: Path,
    start: float,
    end: float,
    data_dir: Path,
    language: str = "en",
    report_fn=lambda msg: None
) -> dict:
    """Transcribes audio slice with word timestamps using Faster-Whisper.
    Enforces strict English-only transcription. No other language is allowed.
    """
    report_fn("Transcribing audio segment in English...")
    out_wav = data_dir / f"temp_{src_path.stem}_{uuid.uuid4().hex[:8]}_{start:.1f}_{end:.1f}.wav"
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-ss", f"{start:.2f}", "-t", f"{end - start:.2f}",
             "-i", str(src_path), "-vn", "-ac", "1", "-ar", "16000", str(out_wav)],
            capture_output=True, check=True, timeout=120, creationflags=NO_WINDOW
        )
        model = get_whisper()
        words = _transcribe_wav_chunk(model, out_wav, offset=0.0, max_dur=end - start, beam_size=5)
        return {
            "words": words,
            "language": "en",
            "duration": end - start
        }
    finally:
        out_wav.unlink(missing_ok=True)


def transcribe_full_audio(
    src_path: Path,
    duration: float,
    data_dir: Path,
    chunk_sec: float = 900.0,
    log=print
) -> list:
    """Transcribes the entire audio track of a long video in safe WAV chunks using Faster-Whisper (English-only)."""
    if duration <= 0:
        try:
            probe = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", str(src_path)],
                capture_output=True, text=True, timeout=30, creationflags=NO_WINDOW
            )
            duration = float(probe.stdout.strip() or 0)
        except Exception:
            duration = 0.0

    if duration <= 0:
        return []

    data_dir.mkdir(parents=True, exist_ok=True)
    model = get_whisper()
    all_words = []
    t = 0.0
    total_chunks = max(1, int((duration + chunk_sec - 1) // chunk_sec))
    chunk_idx = 0

    while t < duration - 0.5:
        chunk_idx += 1
        seg_len = min(chunk_sec, duration - t)
        out_wav = data_dir / f"full_{src_path.stem}_{uuid.uuid4().hex[:8]}_{t:.0f}.wav"
        try:
            log(f"[Whisper] Transcribing chunk {chunk_idx}/{total_chunks} ({t:.0f}s - {t + seg_len:.0f}s / {duration:.0f}s)...")
            subprocess.run(
                ["ffmpeg", "-y", "-v", "error", "-ss", f"{t:.2f}", "-t", f"{seg_len:.2f}",
                 "-i", str(src_path), "-vn", "-ac", "1", "-ar", "16000", str(out_wav)],
                capture_output=True, check=True, timeout=240, creationflags=NO_WINDOW
            )
            if out_wav.exists() and out_wav.stat().st_size > 1000:
                chunk_words = _transcribe_wav_chunk(model, out_wav, offset=t, max_dur=seg_len, beam_size=2)
                all_words.extend(chunk_words)
        except Exception as e:
            log(f"[Whisper] Chunk {chunk_idx} ({t:.0f}s) warning: {e}")
        finally:
            out_wav.unlink(missing_ok=True)
        t += seg_len

    all_words.sort(key=lambda w: w["start"])
    return all_words

def youtube_words_from_info(info: dict) -> list | None:
    """Extracts YouTube's native word-timed auto-captions (json3) in ~1 second.
    Enforces strict English-only tracks (en, en-orig, en-US, etc.). Never captures Hindi or other languages.
    """
    auto = info.get("automatic_captions") or {}
    manual = info.get("subtitles") or {}

    # Strict English priority: never select Hindi or arbitrary foreign language tracks
    en_candidates = [
        "en-orig", "en", "en-US", "en-GB", "en-CA", "en-AU", "en-IN", "en-IE", "en-NZ"
    ]
    key = None
    group = None

    for cand in en_candidates:
        if cand in auto:
            key = cand
            group = auto
            break
        if cand in manual:
            key = cand
            group = manual
            break

    if not key:
        # Search for any track explicitly prefixed with 'en'
        for k in auto:
            if k.lower() == "en" or k.lower().startswith("en-"):
                key = k
                group = auto
                break
        if not key:
            for k in manual:
                if k.lower() == "en" or k.lower().startswith("en-"):
                    key = k
                    group = manual
                    break

    if not key or not group:
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
