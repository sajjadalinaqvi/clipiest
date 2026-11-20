"""Lexical excitement scoring: detects verbal hype, rage, panic, and exclamations."""
import re
import numpy as np

_LEX = [
    (r"oh my (god|gosh)|omg|oh shit|holy (shit|crap|fuck|hell)?|no way|what the (fuck|f|hell)|wtf|oh no+|nooo+|oh fuck|oh god", 3),
    (r"let'?s go+|lets go+|insane|crazy|bruh|yooo+|yoo+|ayo|bro+\b|dude|sheesh|goat|clip (it|that)|clutch", 2),
    (r"run|run run|go go|get out|watch out|behind you|help|police|cops?|chase|chasing|wanted|shoot|shot|gun|kill|killed|dead|die", 2),
    (r"boom|explo\w*|blast|blow|crash\w*|fire|bomb|rocket|jump|flip\w*|fall\w*|drop\w*|ahh+|aaa+h*", 2),
    (r"are+ yaar|arre+|are bhai|oye+|abe+|bhaag\w*|bhago|bachao|pulis|police wale|maar\w*|gaya|goli\w*|dhamaka|uff+|kya baat|zabardast|pagal|mast", 2),
    (r"अरे+|भागो|भाग|बचाओ|पुलिस|मार|मर गया|गोली|धमाका|ब्लास्ट|पागल|उफ़|ओए|यार", 2),
]
_RX = [(re.compile(p, re.I), w) for p, w in _LEX]
_WEAK = {'oh', 'ooh', 'whoa', 'woah', 'wow', 'yo', 'holy', 'damn', 'dang', 'ugh', 'aah', 'ahh', 'ah', 'bro', 'what', 'no', 'wait', 'stop', 'yes', 'yeah', 'arre', 'abe', 'oye'}

def word_weight(text: str) -> float:
    t = text.strip().lower()
    if not t:
        return 0.0
    w = 0.0
    for rx, wt in _RX:
        if rx.fullmatch(t) or (len(t) > 3 and rx.search(t) and rx.search(t).group(0) == t):
            w = max(w, wt)
    if w == 0 and t.strip(",.!?") in _WEAK:
        w = 0.7
    if t.endswith("!"):
        w += 1.0
    return w

def seconds_signal(words: list, duration: float) -> np.ndarray:
    """Per-second excitement score 0.0 to 1.0 across duration."""
    n = max(1, int(np.ceil(duration)))
    sig = np.zeros(n)
    for w in words:
        wt = word_weight(w.get("text", w.get("w", "")))
        if wt > 0:
            s = min(n - 1, int(w.get("start", w.get("s", 0))))
            sig[s] += wt
    sig = np.minimum(sig, 6.0)
    k = np.ones(5) / 5
    sm = np.convolve(sig, k, "same")
    peak = max(float(np.percentile(sm[sm > 0], 95)) if (sm > 0).any() else 1.0, 1.0)
    return np.clip(sm / peak, 0.0, 1.0)

def window_score(words: list, duration: float) -> float:
    """Calculates density of excitement words inside a clip window."""
    if not words or duration <= 0:
        return 0.0
    total = sum(word_weight(w.get("text", w.get("w", ""))) for w in words)
    density = total / max(duration / 8.0, 1.0)
    return float(min(1.0, density / 4.0))
