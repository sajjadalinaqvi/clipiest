"""Master AI viral clip scout, prompt engineering, sentence snapping, and fallback ranking for Clipiest."""
import re
import math
import numpy as np
from .providers import ask_llm
from .games import detect_game
from ..rendering.translit import to_roman

WINDOW_SEC = 15 * 60   # 15 min sliding windows for long streams
OVERLAP_SEC = 60       # 1 min overlap

CATEGORIES = {"funny", "fail", "clutch", "rage", "shock", "story", "hype", "other"}
_CTRL = re.compile(r"[\x00-\x1f\x7f]+")
_LINKS = re.compile(r"(?i)(?:https?://|www\.)\S+|\b[\w-]+\.(?:com|net|org|io|gg|tv|ly|me|co|xyz|app|link|shop)\b\S*|@\w+")

HEAD = """You are a master clip scout for short-form gaming and streaming videos (YouTube Shorts, Reels, TikTok).
Below is a timestamped transcript of a video. Each line starts with [seconds]. Lines marked (LOUD)
are where the audio got much louder than usual: shouting, laughing, explosive action, screaming, or hype.

Video Title: {title}
Channel: {uploader}
{game_rule}

Pick up to {n} moments that would work as standalone viral clips for someone who has never seen the stream:
funny moments, fails, clutch plays, rage, shock, hot takes, or a short story with a punchy payoff.
"""

RULES = """
Rules:
- Each clip is {min_len} to {max_len} seconds. Use the [seconds] values for start and end.
- Start on the setup line, not mid-sentence. End right after the payoff or reaction, on the last word of a complete sentence.
- Do not pick intros, sponsor reads, "like and subscribe", or dead air.
- Skip weak moments. Return empty array [] if nothing in this chunk is worth clipping.
- score: 0-100, how likely a stranger stops scrolling and watches the whole clip.
- hook: at most 5 words, ALL CAPS, displayed on the first 3s of the clip.
- title: at most 70 characters, punchy and engaging.
- description: 1-2 sentences summarizing the punchline or play.
- hashtags: 5 hashtags without the # symbol.
- highlight_words: 3 to 6 single punchy words spoken during the climax.
- category: one of funny, fail, clutch, rage, shock, story, hype, other.
- reason: one short sentence explaining why this clip goes viral.

Reply ONLY with a valid JSON array of objects following this structure:
[
  {{
    "start": 124.5,
    "end": 165.2,
    "score": 88,
    "hook": "NO WAY HE DID THIS",
    "title": "Insane Police Chase Escape",
    "description": "Streamer somehow dodges a 5-star wanted level in the final seconds.",
    "category": "clutch",
    "hashtags": ["gaming", "gta", "clutch", "viral", "escape"],
    "highlight_words": ["cops", "run", "omg", "escaped"],
    "reason": "Intense build-up followed by an unbelievable getaway payoff."
  }}
]

<transcript>
{transcript}
</transcript>
"""

SCOUT_PROMPT = """You pick viral vertical short-form clips (YouTube Shorts, Instagram Reels, TikTok) from gaming streams, podcasts, and videos.

Video Title: {title}
{game_rule}

Candidate Transcript:
\"\"\"{transcript}\"\"\"

Analyze this moment for viral hooks, shock, comedy, fails, clutch gameplay, or narrative payoff.
Reply ONLY with valid JSON with this exact structure:
{{
  "score": 1-100,
  "title": "Punchy title under 60 chars in English/Hinglish",
  "hook": "ALL CAPS hook 2-5 words shown on screen first 3s",
  "description": "Engaging 1-2 sentence description",
  "category": "funny | clutch | fail | shock | story | hype | other",
  "reason": "Why this moment hooks viewers"
}}
"""

def loud_zscore(db: np.ndarray) -> np.ndarray:
    """Computes audio loudness z-scores across seconds."""
    if len(db) < 5:
        return np.zeros(len(db))
    return (db - np.median(db)) / (db.std() + 1e-6)

def make_transcript_lines(words: list, loud: np.ndarray = None) -> list:
    """Groups word-timed transcript into coherent lines labeled with (LOUD) markers."""
    lines, cur = [], []

    def flush():
        if cur:
            s, e = cur[0]["start"], cur[-1]["end"]
            is_loud = False
            if loud is not None and len(loud):
                seg = loud[int(s): int(e) + 1]
                is_loud = bool(len(seg) and seg.max() > 1.5)
            txt = " ".join(w["text"] for w in cur)
            lines.append({"s": s, "e": e, "text": txt, "loud": is_loud})
            cur.clear()

    for w in words:
        st = float(w.get("start", w.get("s", 0)))
        en = float(w.get("end", w.get("e", 0)))
        txt = str(w.get("text", w.get("w", ""))).strip()
        if not txt:
            continue
        item = {"start": st, "end": en, "text": txt}
        if cur and (st - cur[-1]["end"] > 0.7 or st - cur[0]["start"] > 10 or (cur[-1]["text"][-1:] in ".?!" and len(cur) >= 4)):
            flush()
        cur.append(item)
    flush()
    return lines

def format_transcript_lines(lines: list, limit_chars: int = 12000) -> str:
    """Formats transcript lines with timestamps and (LOUD) indicators."""
    out = []
    total_len = 0
    for l in lines:
        prefix = f"[{l['s']:.1f}] {'(LOUD) ' if l.get('loud') else ''}"
        line_str = f"{prefix}{_clean_text(l['text'], 200)}"
        out.append(line_str)
        total_len += len(line_str) + 1
        if total_len >= limit_chars:
            break
    return "\n".join(out)

def _clean_text(v, limit=200):
    return _CTRL.sub(" ", str(v or "")).replace("<", "‹").strip()[:limit]

def _overlaps(s: float, e: float, others: list, threshold: float = 0.25) -> bool:
    """Returns True if the candidate segment significantly overlaps any existing clip."""
    for k in others:
        overlap = min(e, k["end"]) - max(s, k["start"])
        dur = e - s
        if dur > 0 and overlap / dur > threshold:
            return True
    return False

def snap_clip_to_sentences(clip: dict, words: list, min_len: float, max_len: float, duration: float = 999999.0):
    """Snaps clip start to speech onset (skips dead air > 2.0s) and clip end to punctuation / word boundaries."""
    if not words:
        return
    lead = words[0]["start"]
    if lead > 2.0:
        clip["start"] = round(clip["start"] + lead - 0.3, 2)
        for w in words:
            w["start"] = round(max(0.0, w["start"] - lead + 0.3), 3)
            w["end"] = round(max(0.0, w["end"] - lead + 0.3), 3)
            
    limit = clip["end"] - clip["start"]
    good_ends = [
        w["end"] for w in words
        if w["end"] <= min(limit, max_len) and str(w["text"]).rstrip()[-1:] in '.?!…।' and w["end"] >= min_len
    ]
    all_ends = [w["end"] for w in words if w["end"] <= min(limit, max_len)]
    
    pick = good_ends[-1] if good_ends else (all_ends[-1] if all_ends and all_ends[-1] >= min_len else None)
    if pick:
        clip["end"] = round(min(duration, clip["start"] + pick + 0.25), 2)
    else:
        clip["end"] = round(min(duration, clip["start"] + max(min_len, min(limit, max_len))), 2)

    dur = clip["end"] - clip["start"]
    words[:] = [w for w in words if w["start"] < dur]

def fallback_by_loudness(db: np.ndarray, words: list, count: int, min_len: float, max_len: float, duration: float) -> list:
    """Heuristic fallback: picks loudest stretches with verified speech when AI is unavailable."""
    z = loud_zscore(db) if len(db) else np.zeros(int(duration))
    order = np.argsort(-z)
    picks = []
    clip_len = min(duration, max_len)
    
    for sec in order:
        s = max(0.0, float(sec) - clip_len * 0.4)
        e = min(duration, s + clip_len)
        if any(min(e, p["end"]) - max(s, p["start"]) > 0 for p in picks):
            continue
        if words and not any(s <= w["start"] <= e for w in words):
            continue
        picks.append({
            "start": round(s, 2),
            "end": round(e, 2),
            "score": 65,
            "category": "hype",
            "hook": "WAIT FOR THIS",
            "title": "Stream Climax Moment",
            "description": "High excitement peak detected in audio stream.",
            "hashtags": ["viral", "gaming", "stream", "highlight"],
            "highlight_words": [],
            "reason": "Highest audio amplitude and action energy."
        })
        if len(picks) >= count:
            break
            
    if not picks:
        picks.append({
            "start": 0.0,
            "end": round(min(duration, clip_len), 2),
            "score": 50,
            "category": "other",
            "hook": "WATCH THIS",
            "title": "Stream Highlight",
            "description": "Stream action slice.",
            "hashtags": ["gaming", "shorts"],
            "highlight_words": [],
            "reason": "Default segment"
        })
    return picks

def find_viral_moments_ai(
    words: list,
    db: np.ndarray,
    duration: float,
    title: str = "",
    uploader: str = "",
    max_clips: int = 4,
    min_len: float = 25.0,
    max_len: float = 60.0,
    game_name: str = None,
    log=print
) -> list:
    """Full PeakCut-grade viral moment discovery engine.
    Slices long streams into 15-minute sliding windows with loudness marks and invokes LLM
    to scout, score, and isolate standalone viral clips."""
    z = loud_zscore(db) if len(db) else np.zeros(int(duration))
    lines = make_transcript_lines(words, z) if words else []
    
    if not lines:
        log("No speech transcript available. Prompting LLM for narrative moments from video title & game...")
        narrative_prompt = f"""You are a viral YouTube Shorts / TikTok editor.
Analyze this video:
Title: "{_clean_text(title, 100) or 'Video'}"
Channel/Creator: "{_clean_text(uploader, 50) or 'Creator'}"
Game/Topic: "{game_name or 'Gaming/Entertainment'}"
Duration: {int(duration)} seconds.

Recommend {max_clips} viral clip moments across the video duration (each between {int(min_len)}s and {int(max_len)}s).
For each moment, give a high-converting uppercase hook (max 4-5 words), clip title, category (action/funny/clutch/reaction/fail), and viral reason.

Format strictly as a JSON array of objects:
[
  {{
    "start": float,
    "end": float,
    "score": 85,
    "category": "action",
    "hook": "WAIT FOR THIS",
    "title": "Clip Title",
    "description": "Short explanation",
    "reason": "Why it's viral"
  }}
]"""
        try:
            raw_res = ask_llm(narrative_prompt)
            if isinstance(raw_res, dict) and "items" in raw_res:
                raw_res = raw_res["items"]
            if isinstance(raw_res, list) and raw_res:
                narrative_moments = []
                for c in raw_res:
                    if not isinstance(c, dict):
                        continue
                    st = max(0.0, min(duration - 5, float(c.get("start", 0))))
                    en = min(duration, max(st + 10, float(c.get("end", st + 45))))
                    cat = str(c.get("category", "action")).lower()
                    narrative_moments.append({
                        "start": round(st, 2),
                        "end": round(en, 2),
                        "score": max(50, min(100, int(c.get("score", 85)))),
                        "category": cat if cat in CATEGORIES else "action",
                        "hook": to_roman(str(c.get("hook", "WAIT FOR IT"))[:50]).upper(),
                        "title": to_roman(str(c.get("title", title[:40] or "Viral Moment"))[:70]),
                        "description": to_roman(str(c.get("description", ""))[:300]),
                        "hashtags": [re.sub(r"\W", "", str(h))[:25] for h in c.get("hashtags", []) if h][:6],
                        "highlight_words": [],
                        "reason": str(c.get("reason", "Narrative viral moment"))[:200]
                    })
                if narrative_moments:
                    return narrative_moments[:max_clips]
        except Exception as e:
            log(f"LLM narrative scouting failed: {e}")

        log("Using loudness/excitation energy fallback.")
        return fallback_by_loudness(db, words, max_clips, min_len, max_len, duration)

    windows = []
    t = 0.0
    while t < duration:
        windows.append((t, min(duration, t + WINDOW_SEC)))
        t += WINDOW_SEC - OVERLAP_SEC

    per_window = max(2, min(6, int(np.ceil(max_clips * 1.5 / max(1, len(windows)))) + 1))
    game_rule = f"This stream is {game_name}. Focus on plays, clutching, fails, or hilarious reactions." if game_name else ""
    
    found_moments = []
    ai_success = False

    for a, b in windows:
        chunk = [l for l in lines if a <= l["s"] < b]
        if len(chunk) < 3:
            continue
            
        fmt_chunk = format_transcript_lines(chunk, limit_chars=14000)
        prompt = (
            HEAD.format(title=_clean_text(title, 80) or "Video", uploader=_clean_text(uploader, 50) or "Channel", n=per_window, game_rule=game_rule)
            + RULES.format(min_len=int(min_len), max_len=int(max_len), transcript=fmt_chunk)
        )
        
        try:
            log(f"Querying LLM for viral moments in window {a:.0f}s - {b:.0f}s...")
            raw_res = ask_llm(prompt)
            if isinstance(raw_res, dict) and "items" in raw_res:
                raw_res = raw_res["items"]
            if isinstance(raw_res, list) and raw_res:
                for c in raw_res:
                    if not isinstance(c, dict):
                        continue
                    st = float(c.get("start", -1))
                    en = float(c.get("end", -1))
                    if st < 0 or en <= st:
                        continue
                    # Ensure times stay within allowed range
                    dur = en - st
                    if dur < min_len * 0.7:
                        en = st + min_len
                    elif dur > max_len * 1.3:
                        en = st + max_len
                    st = max(0.0, min(duration - 5, st))
                    en = min(duration, max(st + 5, en))
                    
                    cat = str(c.get("category", "other")).lower()
                    found_moments.append({
                        "start": round(st, 2),
                        "end": round(en, 2),
                        "score": max(10, min(100, int(c.get("score", 70)))),
                        "category": cat if cat in CATEGORIES else "other",
                        "hook": to_roman(str(c.get("hook", "WAIT FOR IT"))[:50]).upper(),
                        "title": to_roman(str(c.get("title", title[:40] or "Epic Moment"))[:70]),
                        "description": to_roman(str(c.get("description", ""))[:300]),
                        "hashtags": [re.sub(r"\W", "", str(h))[:25] for h in c.get("hashtags", []) if h][:6],
                        "highlight_words": [to_roman(str(hw)) for hw in c.get("highlight_words", []) if hw][:6],
                        "reason": str(c.get("reason", "Viral moment"))[:200]
                    })
                ai_success = True
        except Exception as e:
            log(f"AI scouting window {a:.0f}-{b:.0f}s failed: {e}")

    # Deduplicate and snap
    chosen = []
    found_moments.sort(key=lambda m: -m["score"])
    
    for m in found_moments:
        if _overlaps(m["start"], m["end"], chosen):
            continue
        # Sentence snapping for smooth boundaries
        chunk_words = [dict(w) for w in words if m["start"] - 1.0 <= w["start"] <= m["end"] + 1.0]
        if chunk_words:
            # Normalize word starts relative to m["start"]
            for w in chunk_words:
                w["start"] = max(0.0, w["start"] - m["start"])
                w["end"] = max(0.0, w["end"] - m["start"])
            snap_clip_to_sentences(m, chunk_words, min_len, max_len, duration)
            m["words"] = chunk_words
        chosen.append(m)
        if len(chosen) >= max_clips:
            break

    # If AI produced fewer clips than requested, backfill with loudness picks
    if len(chosen) < max_clips:
        extra_needed = max_clips - len(chosen)
        log(f"Backfilling {extra_needed} candidate(s) using loudness and excitation...")
        loud_picks = fallback_by_loudness(db, words, extra_needed * 2, min_len, max_len, duration)
        for lp in loud_picks:
            if not _overlaps(lp["start"], lp["end"], chosen):
                chunk_words = [dict(w) for w in words if lp["start"] - 1.0 <= w["start"] <= lp["end"] + 1.0]
                if chunk_words:
                    for w in chunk_words:
                        w["start"] = max(0.0, w["start"] - lp["start"])
                        w["end"] = max(0.0, w["end"] - lp["start"])
                    snap_clip_to_sentences(lp, chunk_words, min_len, max_len, duration)
                    lp["words"] = chunk_words
                chosen.append(lp)
                if len(chosen) >= max_clips:
                    break

    return chosen[:max_clips]

def evaluate_moment(transcript: str, title: str = "", game_name: str = None) -> dict:
    """Evaluates transcript slice using LLM."""
    if len(transcript.split()) < 4:
        return {
            "score": 40,
            "title": "Gameplay Moment",
            "hook": "WATCH THIS",
            "description": "Action highlight from stream.",
            "category": "other",
            "reason": "Auditory gameplay action"
        }
    
    game_rule = f"This stream is {game_name}. Focus on plays, deaths, clutching, or funny reactions." if game_name else ""
    prompt = SCOUT_PROMPT.format(title=title or "Video", game_rule=game_rule, transcript=transcript[:1800])
    try:
        res = ask_llm(prompt)
        if isinstance(res, list) and res:
            res = res[0]
        return {
            "score": int(res.get("score", 50)),
            "title": str(res.get("title", "Clip Moment"))[:70],
            "hook": str(res.get("hook", "WAIT FOR IT"))[:50].upper(),
            "description": str(res.get("description", ""))[:300],
            "category": str(res.get("category", "other")),
            "reason": str(res.get("reason", "Interesting clip"))[:200]
        }
    except Exception:
        return {
            "score": 60,
            "title": (title[:40] if title else "Clip Highlight"),
            "hook": "DONT MISS THIS",
            "description": "Stream highlight",
            "category": "other",
            "reason": "High audio/visual activity"
        }
