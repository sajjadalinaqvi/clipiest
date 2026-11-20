"""Word-timed typography, animated ASS/SRT caption styles, and hook badges for Clipiest."""
import re
import textwrap
from pathlib import Path
from ..config import FONTS_DIR
from .translit import to_roman

W, H = 1080, 1920
CAP_MAX_W = 940

# Styles definition:
# font_file, size, base_color (&HBBGGRR), active_color, outline_size, pop_pct, uppercase, per_group
STYLE_DEFINITIONS = {
    "bounce": {
        "name": "Bounce Pop", "color": "#00f3ff", "outline": "#000000",
        "font_file": "Poppins-ExtraBold.ttf", "font_name": "Poppins ExtraBold",
        "size": 78, "base": "&H00FFFFFF&", "active": "&H00FFF000&", "extra": r"\bord6\shad4\4c&H80000000&",
        "pop": 112, "upper": True, "per": 3
    },
    "hype": {
        "name": "Hype Glow", "color": "#ff3c3c", "outline": "#000000",
        "font_file": "Anton-Regular.ttf", "font_name": "Anton",
        "size": 86, "base": "&H00FFFFFF&", "active": "&H003C3CFF&", "extra": r"\bord7\3c&H00000000&\shad5",
        "pop": 115, "upper": True, "per": 2
    },
    "clean": {
        "name": "Clean Minimal", "color": "#ffffff", "outline": "#111111",
        "font_file": "Poppins-ExtraBold.ttf", "font_name": "Poppins ExtraBold",
        "size": 60, "base": "&H00FFFFFF&", "active": "&H006BD7FF&", "extra": r"\bord4\shad2",
        "pop": 0, "upper": False, "per": 4
    },
    "gta": {
        "name": "GTA Neon", "color": "#43ffee", "outline": "#310c56",
        "font_file": "Poppins-ExtraBold.ttf", "font_name": "Poppins ExtraBold",
        "size": 76, "base": "&H00EFFF43&", "active": "&H00A845FF&", "extra": r"\bord5\3c&H00560C31&\shad6\4c&H00FFCC00&\blur0.8",
        "pop": 110, "upper": True, "per": 3
    },
    "bold": {
        "name": "Impact Bold", "color": "#cb3df3", "outline": "#000000",
        "font_file": "ArchivoBlack-Regular.ttf", "font_name": "Archivo Black",
        "size": 76, "base": "&H00FFFFFF&", "active": "&H003DF3CB&", "extra": r"\bord7\shad4\4c&H80000000&",
        "pop": 112, "upper": True, "per": 3
    },
    "hormozi": {
        "name": "Hormozi Cyan", "color": "#00ffff", "outline": "#000000",
        "font_file": "Poppins-ExtraBold.ttf", "font_name": "Poppins ExtraBold",
        "size": 84, "base": "&H00FFFFFF&", "active": "&H00FFFF00&", "extra": r"\bord8\3c&H00000000&\shad5\4c&H80000000&",
        "pop": 115, "upper": True, "per": 3
    },
    "mrbeast": {
        "name": "MrBeast Yellow", "color": "#ffff00", "outline": "#ff6600",
        "font_file": "ArchivoBlack-Regular.ttf", "font_name": "Archivo Black",
        "size": 88, "base": "&H0000FFFF&", "active": "&H000066FF&", "extra": r"\bord9\3c&H00000000&\shad6\4c&H00000000&",
        "pop": 114, "upper": True, "per": 2
    }
}

HOOK_STYLES = {
    "banner": {"name": "Purple Banner", "primary": "&H00FFFFFF&", "outline": "&H00A845FF&", "bord": 12, "shad": 0, "blur": 1},
    "punch": {"name": "Yellow Punch", "primary": "&H0000FFFF&", "outline": "&H000000FF&", "bord": 14, "shad": 3, "blur": 1},
    "neon": {"name": "Cyan Neon", "primary": "&H00FFFFFF&", "outline": "&H00FFFF00&", "bord": 10, "shad": 0, "blur": 4},
    "fire": {"name": "Fire Flame", "primary": "&H00FFFFFF&", "outline": "&H000055FF&", "bord": 12, "shad": 4, "blur": 1},
    "minimal": {"name": "Clean Dark", "primary": "&H00FFFFFF&", "outline": "&H00202020&", "bord": 10, "shad": 0, "blur": 0},
    "comic": {"name": "Comic Pop", "primary": "&H0000F0FF&", "outline": "&H00000000&", "bord": 14, "shad": 6, "blur": 0},
}

STYLES = STYLE_DEFINITIONS

STYLE_NAMES = tuple(STYLE_DEFINITIONS.keys())

def safe_text(text: str) -> str:
    return str(text).replace("\\", "/").replace("{", "(").replace("}", ")").replace("\n", " ").strip()

def stamp(t: float, ass: bool = False) -> str:
    units = int(round(max(0, float(t)) * (100 if ass else 1000)))
    h, units = divmod(units, (360000 if ass else 3600000))
    m, units = divmod(units, (6000 if ass else 60000))
    s, u = divmod(units, (100 if ass else 1000))
    return f"{h}:{m:02}:{s:02}.{u:02}" if ass else f"{h:02}:{m:02}:{s:02},{u:03}"

def group_words(words: list, max_words: int = 3, max_chars: int = 24, gap: float = 0.45) -> list:
    """Groups words into short, rhythmic caption blocks following pauses and punctuation."""
    groups, cur = [], []
    for i, w in enumerate(words):
        cur.append(w)
        nxt = words[i + 1] if i + 1 < len(words) else None
        text = str(w.get("text", w.get("w", ""))).rstrip()
        chars = sum(len(str(x.get("text", x.get("w", "")))) + 1 for x in cur)
        
        stop = (
            nxt is None or
            len(cur) >= max_words or
            (len(cur) >= 2 and (text[-1:] in '.?!,;:।…' or (nxt and nxt.get("start", nxt.get("s", 0)) - w.get("end", w.get("e", 0)) > gap))) or
            (len(cur) >= 2 and nxt and chars + len(str(nxt.get("text", nxt.get("w", "")))) > max_chars)
        )
        if stop:
            groups.append(cur)
            cur = []
            
    if len(groups) > 1 and len(groups[-1]) == 1 and len(groups[-2]) < max_words:
        prev_end = groups[-2][-1].get("end", groups[-2][-1].get("e", 0))
        last_start = groups[-1][0].get("start", groups[-1][0].get("s", 0))
        if last_start - prev_end < gap:
            groups[-2].append(groups.pop()[0])
            
    return groups

def hook_lines(hook: str, width: int = 18, max_lines: int = 3) -> list:
    """Wraps hook text cleanly into 1-3 short lines."""
    clean = safe_text(hook)
    if len(clean) > 60:
        clean = clean[:60].rsplit(" ", 1)[0]
    lines = textwrap.wrap(clean, width=width) or [""]
    return lines[:max_lines]

def write_subtitles(
    words: list,
    style_key: str,
    out_dir: Path,
    name: str,
    hook: str = "",
    caption_y: int = 1450,
    hook_y: int = 260,
    hook_style: str = "banner"
) -> tuple:
    """Builds styled ASS and standard SRT files. Returns (ass_filename, srt_filename)."""
    st = STYLE_DEFINITIONS.get(style_key, STYLE_DEFINITIONS["bounce"])
    out_dir.mkdir(parents=True, exist_ok=True)
    
    # Normalize words format
    norm_words = []
    for w in words:
        s = float(w.get("start", w.get("s", 0)))
        e = float(w.get("end", w.get("e", 0)))
        t = to_roman(safe_text(w.get("text", w.get("w", ""))))
        if e > s and t:
            norm_words.append({"start": s, "end": e, "text": t})
            
    ass = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {W}",
        f"PlayResY: {H}",
        "WrapStyle: 2",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Main,{st['font_name']},{st['size']},{st['base']},{st['active']},&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,6,3,5,40,40,0,1",
        f"Style: Hook,{st['font_name']},78,&H00FFFFFF&,&H00FFFFFF&,&H00000000,&H90000000,-1,0,0,0,100,100,0,0,1,8,0,5,40,40,0,1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"
    ]
    
    srt = []
    groups = group_words(norm_words, max_words=st["per"], max_chars=int(CAP_MAX_W / (st["size"] * 0.6)))
    
    for i, group in enumerate(groups):
        if not group:
            continue
        begin = group[0]["start"]
        finish = group[-1]["end"]
        line_text = " ".join(w["text"] for w in group)
        srt.append(f"{i + 1}\n{stamp(begin)} --> {stamp(finish)}\n{line_text}\n")
        
        if st["pop"] == 0 or style_key == "clean":
            txt = line_text.upper() if st["upper"] else line_text
            ass.append(f"Dialogue: 1,{stamp(begin, True)},{stamp(finish, True)},Main,,0,0,0,,{{\\pos({W // 2},{caption_y})\\fs{st['size']}{st['extra']}}}{txt}")
        else:
            for n, word in enumerate(group):
                a = max(begin, word["start"])
                b = group[n + 1]["start"] if n + 1 < len(group) else finish
                if b <= a:
                    continue
                chunks = []
                for k, w in enumerate(group):
                    raw = w["text"].upper() if st["upper"] else w["text"]
                    if k == n:
                        pop = st["pop"]
                        chunks.append(r"{\c" + st["active"] + rf"\fscx100\fscy100\t(0,90,\fscx{pop}\fscy{pop})\t(90,190,\fscx100\fscy100)}}" + raw + r"{\fscx100\fscy100}")
                    else:
                        chunks.append(r"{\c" + st["base"] + r"}" + raw)
                dialogue_text = r"{\pos(" + str(W // 2) + r"," + str(caption_y) + r")\fs" + str(st["size"]) + st["extra"] + r"}" + " ".join(chunks)
                ass.append(f"Dialogue: 1,{stamp(a, True)},{stamp(b, True)},Main,,0,0,0,,{dialogue_text}")

    # Hook Title Overlay (shown in first 3.2 seconds)
    if hook.strip():
        lines = hook_lines(to_roman(hook))
        h_size = 78 if len(lines) == 1 else 70 if len(lines) == 2 else 62
        hook_text = r"\N".join(lines).upper()
        hs = HOOK_STYLES.get(hook_style, HOOK_STYLES["banner"])
        hook_tag = rf"{{\an8\pos({W // 2},{hook_y})\fs{h_size}\b1\c{hs['primary']}\3c{hs['outline']}\bord{hs['bord']}\shad{hs['shad']}\blur{hs['blur']}\fad(150,250)}}"
        ass.append(f"Dialogue: 2,0:00:00.00,0:00:03.20,Hook,,0,0,0,,{hook_tag}{hook_text}")

    ass_name = f"{name}.ass"
    srt_name = f"{name}.srt"
    (out_dir / ass_name).write_text("\n".join(ass), encoding="utf-8")
    (out_dir / srt_name).write_text("\n".join(srt), encoding="utf-8")
    return ass_name, srt_name
