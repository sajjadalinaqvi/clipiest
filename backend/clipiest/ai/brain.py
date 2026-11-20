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

SHORT-FORM VIRAL RETENTION FORMULA:
1. THE 2-SECOND HOOK: The clip MUST start with an immediate curiosity gap, bold statement, high stakes, funny blunder, or sudden chaotic action. Never start on dead air or greetings.
2. NARRATIVE MOMENTUM (Setup -> Escalation -> Climax -> Reaction):
   - Setup (first 3-8s): Hook the viewer so they stop scrolling.
   - Escalation (8-25s): The struggle, funny confusion, or impending chaos builds.
   - Climax & Payoff (last 5-15s): The kill, disaster, clutch, punchline, or unbelievable twist.
3. AUDIO ENERGY & (LOUD) SPIKES: Give heavy priority to timestamps labeled (LOUD)—these mark genuine screams, explosive reactions, hysterical laughter, and clutch gameplay.
4. STANDALONE ENTERTAINMENT: Must be completely understood and hilarious/exciting for a stranger scrolling their feed with zero prior context.
"""

RULES = """
Requirements:
- Recommend up to {n} distinct viral clips.
- Each clip must be between {min_len}s and {max_len}s long. Use exact seconds from the transcript brackets [seconds].
- "start": Timestamp of the setup line (start of speech, not dead air).
- "end": Timestamp right after the punchline or reaction (end of sentence).
- "hook": 3-5 uppercase words that grab immediate attention on screen (e.g. "BRO REGRETTED THIS IMMEDIATELY", "HE THOUGHT HE WAS SAFE", "LUCKIEST SHOT OF ALL TIME", "HIS REACTION IS UNREAL", "WAIT FOR THE KARMA").
- "title": Punchy, viral title under 70 characters.
- "score": 80-99 viral retention rating based on comedy, hype, or shock factor.
- "category": one of funny, fail, clutch, rage, shock, story, hype.
- "reason": Why a stranger on TikTok/Shorts will watch this clip to the very end.

Strictly format response as JSON array of objects:
[
  {{
    "start": float,
    "end": float,
    "score": 95,
    "hook": "HE THOUGHT HE WAS SAFE",
    "title": "Insane Police Chase Escape",
    "description": "Streamer somehow dodges a 5-star wanted level in the final seconds.",
    "category": "clutch",
    "hashtags": ["gaming", "gta", "clutch", "viral", "escape"],
    "highlight_words": ["cops", "run", "omg", "escaped"],
    "reason": "Intense build-up followed by an unbelievable getaway payoff with loud celebration."
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

def extract_high_energy_transcript(chunk: list, limit_chars: int = 5000) -> str:
    """Intelligently clusters transcript lines around loudness peaks, reaction words,
    and questions/exclamations to give the LLM full, coherent viral scenes (setup -> climax -> reaction)."""
    if not chunk:
        return ""
    if len(chunk) <= 45:
        return format_transcript_lines(chunk, limit_chars=limit_chars)
    
    # 1. Identify climaxes and explosive moments
    climax_indices = []
    hot_words = {"kill", "dead", "omg", "god", "bro", "clutch", "run", "no way", "what", "how", "wait", "look", "insane", "hacker", "aimbot", "shot", "fail", "win", "lost", "die"}
    for idx, l in enumerate(chunk):
        txt_l = l["text"].lower()
        is_hot = l.get("loud") or "!" in txt_l or "?" in txt_l or any(hw in txt_l for hw in hot_words)
        if is_hot:
            climax_indices.append(idx)
            
    if not climax_indices:
        return format_transcript_lines(chunk[:50], limit_chars=limit_chars)
        
    # 2. Build 30-50s context bubbles around the climaxes (setup 4 lines before, reaction 6 lines after)
    selected_indices = set()
    for ci in climax_indices:
        for offset in range(-4, 7):
            target = ci + offset
            if 0 <= target < len(chunk):
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

def fallback_by_loudness(db: np.ndarray, words: list, count: int, min_len: float, max_len: float, duration: float, title: str = "") -> list:
    """Heuristic fallback: picks loudest stretches with verified speech when AI is unavailable."""
    z = loud_zscore(db) if len(db) else np.zeros(int(duration))
    order = np.argsort(-z)
    picks = []
    clip_len = min(duration, max_len)
    base_t = (title or "Viral Highlight").split("(")[0].strip()[:35]
    hooks = ["WAIT FOR THIS", "YOU WON'T BELIEVE THIS", "WATCH TILL THE END", "INSTANT REGRET", "HE DID NOT SEE THIS COMING", "ABSOLUTELY UNREAL"]
    cats = ["hype", "shock", "clutch", "funny", "action", "rage"]
    
    for sec in order:
        s = max(0.0, float(sec) - clip_len * 0.4)
        e = min(duration, s + clip_len)
        if any(min(e, p["end"]) - max(s, p["start"]) > 0 for p in picks):
            continue
        if words and not any(s <= w["start"] <= e for w in words):
            continue
        idx = len(picks)
        picks.append({
            "start": round(s, 2),
            "end": round(e, 2),
            "score": max(70, min(92, 85 - idx * 3)),
            "category": cats[idx % len(cats)],
            "hook": hooks[idx % len(hooks)],
            "title": f"{base_t} - Peak #{idx + 1}",
            "description": f"High excitement peak detected at {int(s // 60)}m {int(s % 60)}s in audio stream.",
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
            "score": 75,
            "category": "action",
            "hook": "WATCH THIS",
            "title": f"{base_t} - Viral Moment",
            "description": "Featured stream action slice.",
            "hashtags": ["gaming", "shorts"],
            "highlight_words": [],
            "reason": "Top action segment"
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
        narrative_prompt = f"""You are a master viral video editor for YouTube Shorts, TikTok, and Instagram Reels.
Analyze this video to scout {max_clips} viral, high-retention moments with killer hooks:
Video Title: "{_clean_text(title, 100) or 'Video'}"
Channel/Creator: "{_clean_text(uploader, 50) or 'Creator'}"
Game/Topic: "{game_name or 'Gaming/Entertainment'}"
Total Duration: {int(duration)} seconds.

Identify {max_clips} distinct viral moments distributed across the video:
- Space clips across different phases (e.g. early curiosity hook at 10-20%, midpoint tension at 40-55%, peak climax at 70-85%, shocking finale at 90-95%).
- Each clip MUST be {int(min_len)} to {int(max_len)} seconds long (e.g. start: 120.0, end: 165.0).
- Provide high-curiosity viral hooks (ALL CAPS, 3-5 words) tailored specifically to the title "{_clean_text(title, 60)}".
- Assign realistic start and end timestamps within 0.0 to {duration:.1f} seconds.

Format strictly as a JSON array of objects:
[
  {{
    "start": float,
    "end": float,
    "score": 92,
    "category": "action",
    "hook": "HE DID NOT EXPECT THIS",
    "title": "Epic Gameplay Climax",
    "description": "High-stakes confrontation with a dramatic outcome.",
    "reason": "Instant visual hook with an explosive payoff."
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

    # Score each window by loudness energy, hype punctuation, and speech activity
    window_candidates = []
    for idx, (a, b) in enumerate(windows):
        chunk = [l for l in lines if a <= l["s"] < b]
        if len(chunk) < 3:
            continue
        loud_cnt = sum(1 for l in chunk if l.get("loud"))
        punc_cnt = sum(l["text"].count("!") + l["text"].count("?") for l in chunk)
        # Weight loud peaks heavily (4x) and energetic punctuation (2x)
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

    # Sort candidates by excitement; query at most the top 2 windows (or 1 if video is short/count is low)
    window_candidates.sort(key=lambda x: -x["score"])
    target_window_count = 1 if max_clips <= 4 and len(window_candidates) > 0 else min(2, len(window_candidates))
    selected_windows = sorted(window_candidates[:target_window_count], key=lambda x: x["a"])

    game_rule = f"This stream is {game_name}. Focus on plays, clutching, fails, or hilarious reactions." if game_name else ""
    found_moments = []
    ai_success = False

    for win in selected_windows:
        a, b, chunk = win["a"], win["b"], win["chunk"]
        # Intelligently cluster around climaxes, screams, and reaction lines (up to 2,500 characters for fast LLM inference)
        fmt_chunk = extract_high_energy_transcript(chunk, limit_chars=2500)
        prompt = (
            HEAD.format(title=_clean_text(title, 80) or "Video", uploader=_clean_text(uploader, 50) or "Channel", n=max_clips, game_rule=game_rule)
            + RULES.format(n=max_clips, min_len=int(min_len), max_len=int(max_len), transcript=fmt_chunk)
        )
        
        try:
            log(f"Querying LLM for {max_clips} viral moments in peak excitement window {a:.0f}s - {b:.0f}s...")
            raw_res = ask_llm(prompt, max_tokens=600, temperature=0.65)
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
                # If we've gathered enough strong moments, stop early and avoid redundant LLM calls
                if len(found_moments) >= max_clips:
                    break
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

    # If AI produced fewer clips than requested, backfill and enrich with LLM
    if len(chosen) < max_clips:
        extra_needed = max_clips - len(chosen)
        log(f"Backfilling {extra_needed} candidate(s) using loudness and excitation...")
        loud_picks = fallback_by_loudness(db, words, extra_needed * 2, min_len, max_len, duration, title=title)
        unpicked = [lp for lp in loud_picks if not _overlaps(lp["start"], lp["end"], chosen)][:extra_needed]
        
        # Try to enrich backfill moments with unique LLM titles & hooks
        if unpicked:
            try:
                enrich_prompt = f"""You are a master viral video editor.
Video Title: "{_clean_text(title, 80)}" ({uploader or 'Creator'})
Game/Topic: "{game_name or 'General'}"
For each timestamp interval below, generate a punchy viral hook (ALL CAPS, 3-5 words), engaging title (<60 chars), category (funny, clutch, fail, shock, hype, story), and viral score (80-98):
"""
                for idx, up in enumerate(unpicked, 1):
                    enrich_prompt += f"\nMoment #{idx}: {up['start']:.1f}s - {up['end']:.1f}s"
                enrich_prompt += """\n\nReply strictly with a JSON array:
[{"index": 1, "hook": "HE DID NOT EXPECT THIS", "title": "Insane Climax Moment", "category": "hype", "score": 90, "reason": "High retention spike"}]"""
                enriched = ask_llm(enrich_prompt, max_tokens=512, temperature=0.7)
                if isinstance(enriched, list):
                    e_map = {item.get("index", i + 1): item for i, item in enumerate(enriched) if isinstance(item, dict)}
                    for idx, up in enumerate(unpicked, 1):
                        info_e = e_map.get(idx)
                        if info_e:
                            up["hook"] = to_roman(str(info_e.get("hook", up["hook"]))[:50]).upper()
                            up["title"] = to_roman(str(info_e.get("title", up["title"]))[:70])
                            up["score"] = max(75, min(99, int(info_e.get("score", up["score"]))))
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
