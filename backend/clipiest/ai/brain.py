"""Master prompt engineering, sentence snapping, and caption repair for Clipiest."""
import re
from .providers import ask_llm
from .games import detect_game

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

def snap_clip_to_sentences(clip: dict, words: list, min_len: float, max_len: float):
    """Snaps clip start to speech onset (skips dead air > 2.5s) and clip end to punctuation."""
    if not words:
        return
    lead = words[0]["start"]
    if lead > 2.5:
        clip["start"] = round(clip["start"] + lead - 0.4, 2)
        for w in words:
            w["start"] = round(w["start"] - lead + 0.4, 3)
            w["end"] = round(w["end"] - lead + 0.4, 3)
            
    limit = clip["end"] - clip["start"]
    good_ends = [
        w["end"] for w in words
        if w["end"] <= min(limit, max_len) and str(w["text"]).rstrip()[-1:] in '.?!…।' and w["end"] >= min_len
    ]
    all_ends = [w["end"] for w in words if w["end"] <= min(limit, max_len)]
    
    pick = good_ends[-1] if good_ends else (all_ends[-1] if all_ends and all_ends[-1] >= min_len else None)
    clip["end"] = round(clip["start"] + (pick + 0.3 if pick else min(limit, max_len)), 2)

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
