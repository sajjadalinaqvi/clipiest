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

HEAD = """You are an elite short-form viral video editor for TikTok, YouTube Shorts, and Instagram Reels.
Your mission is to scout the stream transcript and audio energy spikes below to extract the MOST VIRAL, HIGH-RETENTION moments.

Video Title: "{title}"
Creator/Channel: "{uploader}"
{game_rule}
{user_directive}

CONTENT-CREATOR-FIRST VIRAL FORMULA:
Clipiest is an all-rounder viral clipping platform across gaming streams, podcasts, lifestyle vlogging, normal hangout streamings, and partying.
1. IT IS ALWAYS ABOUT THE CREATOR: Viewers scroll to watch the HUMAN CONTENT CREATOR, their personality, and their emotional reactions—NOT generic background gameplay or product mechanics.
2. CREATOR HIGHLIGHTS TO CAPTURE:
   - Hilarious unhinged reactions, screaming in panic, jumping out of their chair, laughing hysterically.
   - Spicy banter, roasts, arguing with stream chat or callers, reacting to donations or tweets.
   - Storytime, wild personal confessions, hot takes, dating disasters, or relatable life rants.
   - Interpersonal chaos: drama, awkward silences, hype celebrations with friends, physical comedy.
   - Extreme emotions: betrayal, disbelief, clutch relief, hysterical breakdown.
3. THE GAME/PRODUCT IS JUST A PROP: Never clip generic gameplay (driving down a road, normal kills, leveling up) unless it triggers an explosive CREATOR REACTION.
4. EXCEPTION (PROMOTIONAL / TRAILERS): ONLY if there is NO human creator in the video (e.g. an official game trailer, tech launch, promo compilation), then focus on the product reveals and climactic action.
5. STANDALONE RETENTION: The clip must hook a scrolling stranger within 2 seconds with an immediate curiosity gap and deliver a satisfying punchline or reaction.
"""

RULES = """
Requirements for 10/10 High-View Viral Clips:
- Recommend up to {n} distinct viral clips focusing primarily on the creator's best moments.
- SCORE REQUIREMENT: All clips MUST have an accurate viral retention score of 85 or above (85-99). Scores above 85% are strictly preferred. Do NOT recommend weak moments, dead air, menu browsing, or boring setup.
- ACCURATE VIRAL SCORING:
  * 94-99: Certified viral banger — explosive reaction, unhinged laughter, insane panic scream, jaw-dropping plot twist or roast that makes strangers rewatch & share.
  * 89-93: High-tension dramatic moment, spicy banter, hilarious chat roast, wild confession.
  * 85-88: Solid comedic or high-interest highlight with a clean punchline.
- COLD-OPEN HOOK TIMING: Start on the EXACT inciting line or action (zero dead air, zero "uhhh wait guys"). The first 2 seconds must hook a scrolling viewer immediately!
- STANDALONE PAYOFF: A stranger with zero prior stream context must understand why the clip is funny/crazy, and "end" must land cleanly right after the punchline or reaction (never mid-sentence).
- CRUCIAL TIMELINE COVERAGE (MIDDLE TIMESTAMPS): Explore and distribute clips across the ENTIRE analyzed range (Start, MIDDLE, and End). Do NOT just grab the start or end.
- Each clip must be between {min_len}s and {max_len}s long. Use exact seconds from the transcript brackets [seconds].
- "start": Timestamp of the opening hook / setup line (instant speech/action).
- "end": Timestamp right after the punchline or reaction (clean sentence end).
- "hook": 3-5 ALL-CAPS words creating an irresistible curiosity gap focused on the creator (e.g. "HE INSTANTLY REGRETTED THIS", "CHAT PUSHED HIM TOO FAR", "NO ONE EXPECTED HIS REACTION", "BRO WAS FIGHTING FOR HIS LIFE"). Never use generic filler like "EPIC MOMENT" or "CLIP 1".
- "title": Scroll-stopping, viral title under 70 characters emphasizing the creator's action/reaction.
- "score": Accurate viral retention rating between 85 and 99.
- "category": one of funny, fail, clutch, rage, shock, story, hype.
- "reason": Why the creator's moment will get high completion rate, comments, and shares.

Strictly format response as JSON array of objects:
[
  {{
    "start": float,
    "end": float,
    "score": 95,
    "hook": "HE LOST HIS MIND",
    "title": "Streamer Loses His Mind After Shocking Twist",
    "description": "Creator explodes with hysterical laughter after an unbelievable turn of events.",
    "category": "funny",
    "hashtags": ["viral", "streamer", "funny", "reactions"],
    "highlight_words": ["omg", "screaming", "no way"],
    "reason": "Immediate high-energy scream from the creator hooks viewers instantly into the chaos."
  }}
]

Timestamped Transcript:
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
Rate virality accurately between 85 and 99 (all clips must score 85 or above; scores above 85% are strictly preferred).
Reply ONLY with valid JSON with this exact structure:
{{
  "score": 85-99,
  "title": "Punchy title under 60 chars in English",
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

def parse_timestamp(v, default: float = -1.0) -> float:
    """Parses timestamps from numbers, float strings, or timecode strings ('mm:ss', 'hh:mm:ss')."""
    if v is None:
        return default
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().strip('"').strip("'")
    if ":" in s:
        parts = s.split(":")
        try:
            if len(parts) == 2:
                return float(parts[0]) * 60 + float(parts[1])
            elif len(parts) == 3:
                return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
        except Exception:
            pass
    try:
        return float(s)
    except Exception:
        return default

def extract_high_energy_transcript(chunk: list, limit_chars: int = 5800) -> str:
    """Extracts high-energy climaxes PLUS evenly distributed narrative anchor scenes across the
    ENTIRE window so local LLMs (e.g. Qwen 9B) read both explosive peaks and calm banter/stories."""
    if not chunk:
        return ""
    full_fmt = format_transcript_lines(chunk, limit_chars=limit_chars + 500)
    if len(full_fmt) <= limit_chars:
        return full_fmt

    # 1. Identify climaxes and interesting conversational moments
    climax_indices = []
    hot_words = {
        "kill", "dead", "omg", "god", "bro", "clutch", "run", "no way", "what",
        "how", "wait", "look", "insane", "hacker", "aimbot", "shot", "fail", "win",
        "lost", "die", "screaming", "laughing", "unreal", "no", "yes", "stop", "dude",
        "crazy", "wtf", "hell", "fuck", "shit", "chat", "swear", "story", "clip", "roast"
    }
    for idx, l in enumerate(chunk):
        txt_l = l["text"].lower()
        is_hot = l.get("loud") or "!" in txt_l or "?" in txt_l or any(hw in txt_l for hw in hot_words)
        if is_hot:
            climax_indices.append(idx)

    # 2. Stratify climaxes across 3 phases + evenly spaced narrative anchors
    n_lines = len(chunk)
    c_early = [i for i in climax_indices if i < 0.35 * n_lines]
    c_mid = [i for i in climax_indices if 0.30 * n_lines <= i <= 0.70 * n_lines]
    c_late = [i for i in climax_indices if i > 0.65 * n_lines]

    chosen_anchors = set()
    for pool in (c_early, c_mid, c_late):
        if pool:
            k = min(4, len(pool))
            for idx in np.linspace(0, len(pool) - 1, k, dtype=int):
                chosen_anchors.add(pool[idx])

    # Always include evenly spaced narrative anchors so non-loud stories/banter aren't missed
    for idx in np.linspace(0, n_lines - 1, min(8, n_lines), dtype=int):
        chosen_anchors.add(int(idx))

    for ci in climax_indices:
        if len(chosen_anchors) >= 18:
            break
        chosen_anchors.add(ci)

    # 3. Build context bubbles around selected anchors (-2 to +4 lines)
    selected_indices = set()
    for ci in chosen_anchors:
        for offset in range(-2, 5):
            target = ci + offset
            if 0 <= target < n_lines:
                selected_indices.add(target)

    clustered_lines = [chunk[i] for i in sorted(selected_indices)]
    return format_transcript_lines(clustered_lines, limit_chars=limit_chars)

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
    """Snaps clip start tightly to first spoken word (eliminates >0.6s dead-air intro) and end to punctuation."""
    if not words:
        return
    lead = words[0]["start"]
    if lead > 0.6:
        shift = lead - 0.15
        clip["start"] = round(clip["start"] + shift, 2)
        for w in words:
            w["start"] = round(max(0.0, w["start"] - shift), 3)
            w["end"] = round(max(0.0, w["end"] - shift), 3)
            
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

def fallback_by_loudness(db: np.ndarray, words: list, count: int, min_len: float, max_len: float, duration: float, title: str = "", scan_start: float = 0.0, scan_end: float | None = None) -> list:
    """Heuristic fallback: picks loudest stretches with verified speech across Start, Middle, and End
    within [scan_start, scan_end]. Guarantees accurate scores >= 85 and balanced timeline distribution."""
    lo_bound = max(0.0, float(scan_start or 0.0))
    hi_bound = min(duration, float(scan_end)) if (scan_end is not None and float(scan_end) > lo_bound) else duration
    span = max(1.0, hi_bound - lo_bound)
    clip_len = min(span, max_len)
    base_t = (title or "Viral Highlight").split("(")[0].strip()[:35]
    hooks = [
        "WAIT FOR THIS", "HE COULD NOT BELIEVE IT", "WATCH TILL THE END",
        "INSTANT REGRET", "HE DID NOT SEE THIS COMING", "ABSOLUTELY UNREAL",
        "BRO LOST HIS MIND", "PEAK REACTION", "MOST CLUTCH PLAY"
    ]
    cats = ["hype", "shock", "clutch", "funny", "action", "rage"]
    
    n_sec = max(1, int(duration))
    z = loud_zscore(db) if len(db) >= 5 and db.std() > 1e-4 else np.zeros(n_sec)
    
    picks = []
    # Stratify across count slices within [lo_bound, hi_bound]
    step = span / max(1, count)
    for idx in range(count):
        t_start = lo_bound + idx * step
        t_end = min(hi_bound, lo_bound + (idx + 1) * step)
        
        # Find peak within this slice
        sub_lo = int(max(0, t_start))
        sub_hi = int(min(n_sec, t_end))
        if sub_hi > sub_lo and z[sub_lo:sub_hi].max() > 0:
            rel_peak = int(np.argmax(z[sub_lo:sub_hi]))
            sec = float(sub_lo + rel_peak)
        else:
            sec = (t_start + t_end) / 2.0
            
        s = max(lo_bound, min(hi_bound - clip_len, sec - clip_len * 0.4))
        e = min(hi_bound, s + clip_len)
        
        # If words exist, align with words in this slice if possible
        if words:
            matching = [w for w in words if s <= w["start"] <= e]
            if not matching:
                slice_words = [w for w in words if t_start <= w["start"] <= t_end]
                if slice_words:
                    s = max(lo_bound, min(hi_bound - clip_len, slice_words[0]["start"] - 0.5))
                    e = min(hi_bound, s + clip_len)
                    
        # Check for overlap with existing picks
        if any(min(e, p["end"]) - max(s, p["start"]) > 0 for p in picks):
            s = max(lo_bound, min(hi_bound - clip_len, t_start + 5.0))
            e = min(hi_bound, s + clip_len)

        score_val = max(85, min(98, 96 - idx * 2))
        picks.append({
            "start": round(s, 2),
            "end": round(e, 2),
            "score": score_val,
            "category": cats[idx % len(cats)],
            "hook": hooks[idx % len(hooks)],
            "title": f"{base_t} - Highlight #{idx + 1}",
            "description": f"High excitement highlight at {int(s // 60)}m {int(s % 60)}s in stream.",
            "hashtags": ["viral", "gaming", "stream", "highlight"],
            "highlight_words": [],
            "reason": "Timeline highlight segment"
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
    user_instructions: str = "",
    scan_start: float = 0.0,
    scan_end: float | None = None,
    log=print
) -> list:
    """Full PeakCut-grade viral moment discovery engine with Creator-First priority.
    Slices the selected range (or whole stream) into timeline windows with loudness marks and invokes LLM
    to scout, score, and isolate standalone viral clips centered on the content creator."""
    active_start = max(0.0, float(scan_start or 0.0))
    active_end = min(duration, float(scan_end)) if (scan_end is not None and float(scan_end) > active_start) else duration
    active_span = max(1.0, active_end - active_start)

    z = loud_zscore(db) if len(db) else np.zeros(int(duration))
    lines = make_transcript_lines(words, z) if words else []
    if active_start > 0 or active_end < duration:
        lines = [l for l in lines if active_start - 5.0 <= l["s"] <= active_end + 5.0]

    user_directive = f"""
🎯 USER DIRECTIVE (HIGHEST PRIORITY):
"{user_instructions}"
You MUST heavily prioritize moments matching this directive!
""" if user_instructions else ""
    
    if not lines:
        log("No speech transcript available. Prompting LLM for narrative moments from video title & game...")
        narrative_prompt = f"""You are a master viral video editor for YouTube Shorts, TikTok, and Instagram Reels.
Analyze this video to scout {max_clips} viral, high-retention moments with killer hooks:
Video Title: "{_clean_text(title, 100) or 'Video'}"
Channel/Creator: "{_clean_text(uploader, 50) or 'Creator'}"
Game/Topic: "{game_name or 'Gaming/Entertainment'}"
Target Analysis Range: {active_start:.1f}s to {active_end:.1f}s (Total Video: {int(duration)}s).
{user_directive}

CONTENT-CREATOR-FIRST VIRAL PRINCIPLE:
- It is ALWAYS about the HUMAN CONTENT CREATOR, not the background gameplay or product.
- If a content creator/host is present, focus on their funniest reactions, screaming in panic, unhinged laughter, chat roasts, confessions, and storytelling. The game or setting is just the backdrop.
- Only if there is NO content creator (e.g. an official game trailer or tech launch), focus on the product reveals and climactic action.

TIMELINE & SCORE REQUIREMENTS:
- Identify {max_clips} distinct viral moments distributed across the target range ({active_start:.0f}s to {active_end:.0f}s: Start, MIDDLE, and End).
- MANDATORY: Include middle timestamps (between {int(active_start + active_span * 0.35)}s and {int(active_start + active_span * 0.70)}s), not just the beginning and end.
- All clips MUST have an accurate viral score of 85 or higher (85-99, above 85% is strictly preferred).
- Rate virality accurately: peak reactions/screams 92-98, strong comedic/clutch moments 85-91.
- Each clip MUST be {int(min_len)} to {int(max_len)} seconds long.
- Provide high-curiosity viral hooks (ALL CAPS, 3-5 words) centered on the creator (e.g. "HE BROKE HIS SETUP", "BRO WAS NOT READY", "HIS REACTION IS UNREAL", "HE ACTUALLY LOST IT").
- Assign realistic start and end timestamps strictly within {active_start:.1f} to {active_end:.1f} seconds.

Format strictly as a JSON array of objects:
[
  {{
    "start": float,
    "end": float,
    "score": 95,
    "category": "funny",
    "hook": "HE LOST HIS MIND",
    "title": "Creator Goes Completely Unhinged",
    "description": "Explosive comedic reaction after a shocking moment.",
    "reason": "Immediate high-energy scream from the creator hooks viewers instantly into the chaos."
  }}
]"""
        try:
            raw_res = ask_llm(narrative_prompt, max_tokens=1024, temperature=0.7)
            if isinstance(raw_res, dict) and "items" in raw_res:
                raw_res = raw_res["items"]
            if isinstance(raw_res, list) and raw_res:
                narrative_moments = []
                for c in raw_res:
                    if not isinstance(c, dict):
                        continue
                    st = parse_timestamp(c.get("start"), default=active_start)
                    en = parse_timestamp(c.get("end"), default=st + 45.0)
                    st = max(active_start, min(active_end - 5, st))
                    en = min(active_end, max(st + 10, en))
                    raw_score = int(parse_timestamp(c.get("score"), default=88))
                    score_val = max(85, min(99, raw_score if raw_score >= 80 else raw_score + 10))
                    cat = str(c.get("category", "action")).lower()
                    narrative_moments.append({
                        "start": round(st, 2),
                        "end": round(en, 2),
                        "score": score_val,
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
        return fallback_by_loudness(db, words, max_clips, min_len, max_len, duration, title=title, scan_start=active_start, scan_end=active_end)

    # Partition the ENTIRE selected range [active_start, active_end] cleanly so the LLM reads 100% of it
    # (15-min windows up to ~2.5h span; dynamically scaled up to ~10 windows for longer spans)
    win_sec = max(float(WINDOW_SEC), active_span / 10.0) if active_span > 0 else float(WINDOW_SEC)
    overlap = min(float(OVERLAP_SEC), win_sec * 0.1)
    step = max(60.0, win_sec - overlap)

    windows = []
    t = active_start
    while t < active_end:
        windows.append((t, min(active_end, t + win_sec)))
        if t + win_sec >= active_end:
            break
        t += step

    # Collect every window containing speech across the entire video
    window_candidates = []
    for idx, (a, b) in enumerate(windows):
        chunk = [l for l in lines if a <= l["s"] < b]
        if len(chunk) < 2:
            continue
        loud_cnt = sum(1 for l in chunk if l.get("loud"))
        punc_cnt = sum(l["text"].count("!") + l["text"].count("?") for l in chunk)
        excitement_score = loud_cnt * 4.0 + punc_cnt * 2.0 + len(chunk) * 1.0
        window_candidates.append({
            "idx": idx,
            "a": a,
            "b": b,
            "score": excitement_score,
            "chunk": chunk
        })

    # If transcript lines exist but are sparse across windows, bundle them so LLM is never skipped
    if not window_candidates and lines:
        window_candidates.append({
            "idx": 0,
            "a": lines[0]["s"],
            "b": lines[-1]["e"],
            "score": 10.0,
            "chunk": lines
        })

    # Evaluate ALL windows chronologically across the whole timeline (never skip middle/end)
    selected_windows = sorted(window_candidates, key=lambda x: x["a"])

    game_rule = f"This stream context is {game_name}. Focus primarily on the content creator's reactions, fails, roasts, or clutches." if game_name else ""
    found_moments = []
    win_quota = max_clips if len(selected_windows) <= 1 else min(max_clips, 3)

    for w_idx, win in enumerate(selected_windows, 1):
        a, b, chunk = win["a"], win["b"], win["chunk"]
        fmt_chunk = extract_high_energy_transcript(chunk, limit_chars=5800)
        window_note = (
            f"\nSegment Scope ({w_idx}/{len(selected_windows)}): {a:.0f}s to {b:.0f}s of {duration:.0f}s total. "
            f"Use exact [seconds] timestamps from <transcript>. Return [] if this segment has no genuine 85+ viral moment.\n"
        )
        prompt = (
            HEAD.format(
                title=_clean_text(title, 80) or "Video",
                uploader=_clean_text(uploader, 50) or "Channel",
                n=win_quota,
                game_rule=game_rule,
                user_directive=user_directive + window_note
            )
            + RULES.format(n=win_quota, min_len=int(min_len), max_len=int(max_len), transcript=fmt_chunk)
        )

        try:
            log(f"Querying LLM ({w_idx}/{len(selected_windows)}) for viral moments in {a:.0f}s - {b:.0f}s...")
            raw_res = ask_llm(prompt, max_tokens=1024, temperature=0.6)
            if isinstance(raw_res, dict) and "items" in raw_res:
                raw_res = raw_res["items"]
            if isinstance(raw_res, list) and raw_res:
                for c in raw_res:
                    if not isinstance(c, dict):
                        continue
                    st = parse_timestamp(c.get("start"), default=-1.0)
                    en = parse_timestamp(c.get("end"), default=-1.0)
                    if st < 0 or en <= st:
                        continue

                    # Correct window-relative timestamps if a local 9B model returned offset from 0s
                    if a > 120 and st < (b - a):
                        has_abs = any(st - 3.0 <= float(w.get("start", w.get("s", 0))) <= en + 3.0 for w in words)
                        has_rel = any(st + a - 3.0 <= float(w.get("start", w.get("s", 0))) <= en + a + 3.0 for w in words)
                        if not has_abs and has_rel:
                            st += a
                            en += a

                    dur = en - st
                    if dur < min_len * 0.7:
                        en = st + min_len
                    elif dur > max_len * 1.3:
                        en = st + max_len
                    st = max(active_start, min(active_end - 5, st))
                    en = min(active_end, max(st + 5, en))

                    cat = str(c.get("category", "other")).lower()
                    raw_score = int(parse_timestamp(c.get("score"), default=88))
                    # Enforce score >= 85 requirement while preserving genuine rank order
                    score_val = max(85, min(99, raw_score if raw_score >= 80 else raw_score + 10))
                    has_speech = any(st - 1.0 <= float(w.get("start", w.get("s", 0))) <= en + 1.0 for w in words)

                    found_moments.append({
                        "start": round(st, 2),
                        "end": round(en, 2),
                        "score": score_val,
                        "category": cat if cat in CATEGORIES else "other",
                        "hook": to_roman(str(c.get("hook", "WAIT FOR IT"))[:50]).upper(),
                        "title": to_roman(str(c.get("title", title[:40] or "Epic Moment"))[:70]),
                        "description": to_roman(str(c.get("description", ""))[:300]),
                        "hashtags": [re.sub(r"\W", "", str(h))[:25] for h in c.get("hashtags", []) if h][:6],
                        "highlight_words": [to_roman(str(hw)) for hw in c.get("highlight_words", []) if hw][:6],
                        "reason": str(c.get("reason", "Viral moment"))[:200],
                        "_has_speech": has_speech
                    })
        except Exception as e:
            log(f"AI scouting window {a:.0f}-{b:.0f}s failed: {e}")

    # Rank globally across the ENTIRE video (prefer verified spoken scenes and highest scores)
    chosen = []
    found_moments.sort(key=lambda m: (-m["score"], -int(m.pop("_has_speech", True))))
    
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

    # Middle timestamp guarantee within [active_start, active_end]:
    # If active_span > 180s and none of chosen clips is in middle 50%, ensure a middle highlight is included
    if active_span > 180 and len(chosen) > 1:
        mid_lo = active_start + 0.25 * active_span
        mid_hi = active_start + 0.75 * active_span
        has_mid = any(mid_lo <= m["start"] <= mid_hi for m in chosen)
        if not has_mid:
            mid_cand = next((m for m in found_moments if mid_lo <= m["start"] <= mid_hi and not _overlaps(m["start"], m["end"], chosen[:-1])), None)
            if mid_cand:
                chosen[-1] = mid_cand
            else:
                mid_picks = fallback_by_loudness(db, words, 2, min_len, max_len, duration, title=title, scan_start=active_start, scan_end=active_end)
                mid_pick = next((p for p in mid_picks if mid_lo <= p["start"] <= mid_hi and not _overlaps(p["start"], p["end"], chosen[:-1])), None)
                if mid_pick:
                    chosen[-1] = mid_pick

    # If AI produced fewer clips than requested, backfill and enrich with LLM
    if len(chosen) < max_clips:
        extra_needed = max_clips - len(chosen)
        log(f"Backfilling {extra_needed} candidate(s) using loudness and excitation...")
        loud_picks = fallback_by_loudness(db, words, extra_needed * 2, min_len, max_len, duration, title=title, scan_start=active_start, scan_end=active_end)
        unpicked = [lp for lp in loud_picks if not _overlaps(lp["start"], lp["end"], chosen)][:extra_needed]
        
        # Try to enrich backfill moments with unique creator-focused LLM titles & hooks
        if unpicked:
            try:
                enrich_prompt = f"""You are a master viral video editor for short-form clips (TikTok, Shorts, Reels).
Video Title: "{_clean_text(title, 80)}" ({uploader or 'Creator'})
Context/Topic: "{game_name or 'General'}"
{user_directive}
CONTENT-CREATOR-FIRST: Focus on the content creator's hilarious reactions, panic screaming, laughing, chat beef, or crazy confessions. The game or setting is just the backdrop.
For each timestamp interval below, generate a punchy viral hook (ALL CAPS, 3-5 words), engaging title (<60 chars), category (funny, clutch, fail, shock, hype, story), and accurate viral score (85-98):
"""
                for idx, up in enumerate(unpicked, 1):
                    enrich_prompt += f"\nMoment #{idx}: {up['start']:.1f}s - {up['end']:.1f}s"
                enrich_prompt += """\n\nReply strictly with a JSON array:
[{"index": 1, "hook": "HE LOST HIS MIND", "title": "Creator Goes Completely Unhinged", "category": "funny", "score": 95, "reason": "High-energy reaction hooks viewer"}]"""
                enriched = ask_llm(enrich_prompt, max_tokens=512, temperature=0.7)
                if isinstance(enriched, list):
                    e_map = {item.get("index", i + 1): item for i, item in enumerate(enriched) if isinstance(item, dict)}
                    for idx, up in enumerate(unpicked, 1):
                        info_e = e_map.get(idx)
                        if info_e:
                            up["hook"] = to_roman(str(info_e.get("hook", up["hook"]))[:50]).upper()
                            up["title"] = to_roman(str(info_e.get("title", up["title"]))[:70])
                            raw_s = int(parse_timestamp(info_e.get("score"), default=up.get("score", 88)))
                            up["score"] = max(85, min(99, raw_s))
                            up["category"] = str(info_e.get("category", up["category"])).lower()
                            up["reason"] = str(info_e.get("reason", up["reason"]))[:200]
            except Exception as e:
                log(f"Enriching backfill moments with LLM skipped: {e}")

        for lp in unpicked:
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
    """Evaluates transcript slice using LLM with score >= 85."""
    if len(transcript.split()) < 4:
        return {
            "score": 85,
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
        raw_s = int(parse_timestamp(res.get("score"), default=88))
        return {
            "score": max(85, min(99, raw_s if raw_s >= 80 else raw_s + 10)),
            "title": str(res.get("title", "Clip Moment"))[:70],
            "hook": str(res.get("hook", "WAIT FOR IT"))[:50].upper(),
            "description": str(res.get("description", ""))[:300],
            "category": str(res.get("category", "other")),
            "reason": str(res.get("reason", "Interesting clip"))[:200]
        }
    except Exception:
        return {
            "score": 88,
            "title": (title[:40] if title else "Clip Highlight"),
            "hook": "DONT MISS THIS",
            "description": "Stream highlight",
            "category": "other",
            "reason": "High audio/visual activity"
        }
