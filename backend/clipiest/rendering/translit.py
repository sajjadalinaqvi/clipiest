"""Multilingual transliteration & Hinglish conversion with timing preservation.

Converts:
1. Devanagari (Hindi) -> Casual conversational Hinglish (hai, kya, nahi...) with Hindi schwa deletion.
2. Urdu / Arabic letters -> Roman transliteration.
3. Cyrillic (Russian, Kazakh, Ukrainian, etc.) -> Roman letters.
4. Greek & Korean Hangul -> Roman letters.
Keeps exact word-by-word timestamps intact for ASS/SRT burning.
"""
import re
import unicodedata

# Common conversational Hindi words
COMMON_HINDI = {
    'है': 'hai', 'हैं': 'hain', 'हूँ': 'hoon', 'हूं': 'hoon', 'था': 'tha', 'थी': 'thi', 'थे': 'the', 'हो': 'ho', 'होगा': 'hoga', 'होगी': 'hogi',
    'में': 'mein', 'मैं': 'main', 'मे': 'mein', 'का': 'ka', 'की': 'ki', 'के': 'ke', 'को': 'ko', 'से': 'se', 'पर': 'par', 'ने': 'ne', 'तक': 'tak',
    'यह': 'yeh', 'ये': 'ye', 'वह': 'woh', 'वो': 'woh', 'यहाँ': 'yahan', 'यहां': 'yahan', 'वहाँ': 'wahan', 'वहां': 'wahan', 'कहाँ': 'kahan', 'कहां': 'kahan',
    'और': 'aur', 'या': 'ya', 'कि': 'ki', 'जो': 'jo', 'तो': 'toh', 'ही': 'hi', 'भी': 'bhi', 'नहीं': 'nahin', 'ना': 'na', 'न': 'na', 'मत': 'mat',
    'क्या': 'kya', 'कैसे': 'kaise', 'कैसा': 'kaisa', 'कौन': 'kaun', 'कब': 'kab', 'क्यों': 'kyun', 'कितना': 'kitna', 'कुछ': 'kuch', 'कोई': 'koi',
    'नमस्ते': 'namaste', 'नमस्कार': 'namaskar', 'धन्यवाद': 'dhanyawad',
    'तुम': 'tum', 'तू': 'tu', 'तुम्हें': 'tumhe', 'तुम्हारा': 'tumhara', 'आप': 'aap', 'हम': 'hum', 'हमें': 'hame', 'हमारे': 'hamare', 'हमारा': 'hamara',
    'मुझे': 'mujhe', 'मेरा': 'mera', 'मेरी': 'meri', 'मेरे': 'mere', 'तेरा': 'tera', 'तेरी': 'teri', 'उसे': 'use', 'इसे': 'ise', 'उसका': 'uska', 'उसकी': 'uski',
    'इस': 'is', 'उस': 'us', 'इन': 'in', 'उन': 'un', 'अब': 'ab', 'अभी': 'abhi', 'फिर': 'phir', 'जब': 'jab', 'तब': 'tab', 'सब': 'sab', 'बस': 'bas',
    'कर': 'kar', 'करो': 'karo', 'करना': 'karna', 'करता': 'karta', 'करती': 'karti', 'करते': 'karte', 'किया': 'kiya', 'कहा': 'kaha', 'देखो': 'dekho',
    'रहा': 'raha', 'रही': 'rahi', 'रहे': 'rahe', 'गया': 'gaya', 'गई': 'gayi', 'गए': 'gaye', 'लिए': 'liye', 'साथ': 'saath', 'बहुत': 'bahut',
    'अच्छा': 'accha', 'ठीक': 'theek', 'सही': 'sahi', 'गलत': 'galat', 'भाई': 'bhai', 'यार': 'yaar', 'दोस्तो': 'dosto', 'चलो': 'chalo', 'चल': 'chal',
    'ओके': 'okay', 'हाँ': 'haan', 'हां': 'haan', 'अरे': 'arre', 'वाह': 'wah', 'मतलब': 'matlab', 'बिल्कुल': 'bilkul', 'लेकिन': 'lekin',
    'एक': 'ek', 'दो': 'do', 'तीन': 'teen', 'चार': 'char', 'पाँच': 'paanch', 'सच': 'sach', 'बात': 'baat', 'लोग': 'log', 'लोगों': 'logon', 'वीडियो': 'video',
    'गेम': 'game', 'प्लीज': 'please', 'सॉरी': 'sorry', 'थैंक्स': 'thanks', 'हेलो': 'hello', 'सब्सक्राइब': 'subscribe', 'चैनल': 'channel',
}

CONS = {'क': 'k', 'ख': 'kh', 'ग': 'g', 'घ': 'gh', 'ङ': 'ng', 'च': 'ch', 'छ': 'chh', 'ज': 'j', 'झ': 'jh', 'ञ': 'n', 'ट': 't', 'ठ': 'th', 'ड': 'd', 'ढ': 'dh',
        'ण': 'n', 'त': 't', 'थ': 'th', 'द': 'd', 'ध': 'dh', 'न': 'n', 'प': 'p', 'फ': 'ph', 'ब': 'b', 'भ': 'bh', 'म': 'm', 'य': 'y', 'र': 'r', 'ल': 'l',
        'व': 'v', 'श': 'sh', 'ष': 'sh', 'स': 's', 'ह': 'h', 'ळ': 'l', 'क्ष': 'ksh', 'ज्ञ': 'gy'}
NUKTA = {'क': 'q', 'ख': 'kh', 'ग': 'g', 'ज': 'z', 'ड': 'd', 'ढ': 'rh', 'फ': 'f'}
VOWELS = {'अ': 'a', 'आ': 'aa', 'इ': 'i', 'ई': 'ee', 'उ': 'u', 'ऊ': 'oo', 'ऋ': 'ri', 'ए': 'e', 'ऐ': 'ai', 'ओ': 'o', 'औ': 'au', 'ऑ': 'o', 'ऍ': 'e'}
MATRAS = {'ा': 'aa', 'ि': 'i', 'ी': 'ee', 'ु': 'u', 'ू': 'oo', 'ृ': 'ri', 'े': 'e', 'ै': 'ai', 'ो': 'o', 'ौ': 'au', 'ॉ': 'o', 'ॅ': 'e'}
VIRAMA, NUKTA_C, ANUSVARA, CHANDRA = '्', '़', 'ं', 'ँ'

DEVA = re.compile(r'[ऀ-ॿ]')
URDU = re.compile(r'[\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF]')
CYRILLIC_GREEK_KOREAN = re.compile(r'[\u0370-\u03FF\u0400-\u04FF\uAC00-\uD7A3]')

_CYR = {"а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo", "ж": "zh", "з": "z", "и": "i", "й": "y",
        "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f",
        "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch", "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu",
        "я": "ya", "є": "ye", "і": "i", "ї": "yi", "ґ": "g", "ў": "u", "ђ": "dj", "ј": "j", "љ": "lj", "њ": "nj"}

_GRK = {"α": "a", "β": "v", "γ": "g", "δ": "d", "ε": "e", "ζ": "z", "η": "i", "θ": "th", "ι": "i", "κ": "k", "λ": "l",
        "μ": "m", "ν": "n", "ξ": "x", "ο": "o", "π": "p", "ρ": "r", "σ": "s", "ς": "s", "τ": "t", "υ": "y", "φ": "f", "χ": "ch", "ψ": "ps", "ω": "o"}

_URDU_WORDS = {"کیا": "kya", "ہے": "hai", "ہیں": "hain", "نہیں": "nahi", "یار": "yaar", "بھائی": "bhai", "اور": "aur", "میں": "mein", "آپ": "aap", "تم": "tum"}

_K_FIRST = ["g", "kk", "n", "d", "tt", "r", "m", "b", "pp", "s", "ss", "", "j", "jj", "ch", "k", "t", "p", "h"]
_K_VOWEL = ["a", "ae", "ya", "yae", "eo", "e", "yeo", "ye", "o", "wa", "wae", "oe", "yo", "u", "wo", "we", "wi", "yu", "eu", "ui", "i"]
_K_LAST = ["", "k", "k", "k", "n", "n", "n", "t", "l", "k", "m", "l", "l", "l", "p", "l", "m", "p", "p", "t", "t", "ng", "t", "t", "k", "t", "p", "t"]

PUNCT = set('.,!?;:"()[]{}-_') | {chr(c) for c in (0x27, 0x2026, 0x964, 0x965, 0x2013, 0x2014, 0x201c, 0x201d, 0x2018, 0x2019)}

def _syllables(word):
    out, i, n = [], 0, len(word)
    while i < n:
        ch = word[i]
        if ch in VOWELS:
            out.append(['', VOWELS[ch], '']); i += 1
        elif ch in CONS or word[i:i + 3] in ('क्ष', 'ज्ञ'):
            cluster = ''
            while i < n:
                if word[i:i + 3] in ('क्ष', 'ज्ञ'):
                    c = CONS[word[i:i + 3]]; i += 3
                elif word[i] in CONS:
                    c = CONS[word[i]]; i += 1
                    if i < n and word[i] == NUKTA_C:
                        c = NUKTA.get(word[i - 1], c); i += 1
                else:
                    break
                cluster += c
                if i < n and word[i] == VIRAMA:
                    i += 1; continue
                break
            vowel = None
            if i < n and word[i] in MATRAS:
                vowel = MATRAS[word[i]]; i += 1
            out.append([cluster, vowel, ''])
        elif ch in (ANUSVARA, CHANDRA):
            if out: out[-1][2] = 'n'
            i += 1
        elif ch == 'ः':
            if out: out[-1][2] = 'h'
            i += 1
        else:
            i += 1
    return out

def _casual(w):
    if len(w) > 3: w = re.sub(r'aa$', 'a', w)
    w = re.sub(r'ee$', 'i', w)
    w = w.replace('ee', 'i') if len(w) > 4 else w
    return w

def devanagari_to_hinglish(word):
    if word in COMMON_HINDI:
        return COMMON_HINDI[word]
    syl = _syllables(word)
    if not syl:
        return word
    inherent = [s[1] is None and s[0] != '' for s in syl]
    delete = [False] * len(syl)
    if len(syl) > 1 and inherent[-1]:
        delete[-1] = True
    for i in range(len(syl) - 2, 0, -1):
        if inherent[i] and not delete[i + 1]:
            delete[i] = True
    out = ''
    for i, (c, v, nas) in enumerate(syl):
        if v is None and c != '':
            v = '' if delete[i] else 'a'
        out += c + (v or '') + nas
    return _casual(out)

def _korean(run: str) -> str:
    out = []
    for ch in run:
        n = ord(ch) - 0xAC00
        if 0 <= n < 11172:
            out.append(_K_FIRST[n // 588] + _K_VOWEL[n % 588 // 28] + _K_LAST[n % 28])
        else:
            out.append(ch)
    return "".join(out)

def _cyr_greek(run: str) -> str:
    out = []
    for ch in unicodedata.normalize("NFD", run):
        if unicodedata.combining(ch):
            continue
        low = ch.lower()
        r = _CYR.get(low, _GRK.get(low))
        if r is None:
            out.append(ch)
        else:
            out.append(r.capitalize() if ch != low else r)
    return "".join(out)

def to_roman(token: str) -> str:
    """Converts a token in Hindi, Urdu, Cyrillic, Greek, or Korean to clean Latin script."""
    if not token:
        return ""
    a, b = 0, len(token)
    while a < b and token[a] in PUNCT: a += 1
    while b > a and token[b - 1] in PUNCT: b -= 1
    lead, core, tail = token[:a], token[a:b], token[b:]
    if not core:
        return token

    # Check Hindi (Devanagari)
    if DEVA.search(core):
        parts = re.split(r'([^ऀ-ॿ]+)', core)
        res = ''.join(devanagari_to_hinglish(p) if DEVA.search(p) else p for p in parts)
        return lead + res + tail
    
    # Check Urdu
    if URDU.search(core):
        if core in _URDU_WORDS:
            return lead + _URDU_WORDS[core] + tail
        return lead + core + tail
    
    # Check Cyrillic / Greek / Korean
    if CYRILLIC_GREEK_KOREAN.search(core):
        res = _cyr_greek(_korean(core))
        return lead + res + tail

    return token

def romanize_words(words: list) -> list:
    """Applies Romanization to a list of word dictionaries: [{'start': .., 'end': .., 'text'/'w': ..}]."""
    out = []
    for w in words:
        key = 'text' if 'text' in w else 'w'
        val = str(w.get(key, ''))
        new_w = dict(w)
        new_w[key] = to_roman(val)
        out.append(new_w)
    return out
