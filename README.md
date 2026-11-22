# Clipiest ⚡
### The Ultimate AI Video & Gaming Clip Engine

> **Synthesized from the best of NeonClipping & PeakCut** — combining fast progressive audio extraction, dual-judge AI discovery, and multi-game heuristics with interactive bounding-box framing, 11 native 9:16 vertical layouts, self-learning Ridge regression, and dynamic animated ASS typography.

---

## 🌟 Why Clipiest?

| Feature | NeonClipping | PeakCut | **Clipiest (Unified)** |
| :--- | :---: | :---: | :---: |
| **Progressive Audio-First Extraction** | ❌ (Full video download) | ✅ (Fast M4A scrape) | ✅ **Instant section downloads via yt-dlp & cross-correlation** |
| **Visual Heuristics (Optical Flow / Flash / Strobes)** | ✅ (Farneback flow) | ❌ (Visual blindness) | ✅ **Full 6-FPS optical flow + flash & police strobe detector** |
| **Automated Facecam Detection (CV)** | ❌ (Manual drawing only) | ✅ (Edge gradient stillness) | ✅ **1-Click Auto-Detect Facecam + fine-tune draggable canvas** |
| **Framing & Vertical Layouts** | ✅ (11 Native layouts) | ❌ (Rigid Stack/Blur only) | ✅ **11 Layouts (Stack, Bottom, Blur, Fill, Game, PiP, Circle, Side)** |
| **Typography & Subtitle Animation** | Basic pop | 7 ASS styles | ✅ **7 Dynamic ASS styles (`bounce`, `hype`, `gta`, `bold`, etc.)** |
| **Multilingual Romanization** | Basic Hindi dictionary | Multilingual | ✅ **Devanagari, Urdu, Cyrillic, Greek & Korean to Hinglish/Latin** |
| **Self-Learning User Feedback** | ✅ (Ridge regression) | ❌ (Static weights) | ✅ **Real-time Ridge regression fitting based on 1–5★ user ratings** |
| **Live Stream Chat Velocity Clipper** | ✅ (Twitch / YouTube Live) | ❌ (No live buffers) | ✅ **Streamlink recording buffer + chat velocity spike clipper** |
| **Hardware Acceleration** | Software only | Auto NVENC / QSV | ✅ **Auto-detects NVIDIA NVENC, Intel QSV, or CPU libx264** |
| **Universal AI Gateway** | Ollama only | 8 Providers | ✅ **Gemini, OpenAI, Claude, Groq, Grok, OpenRouter, Ollama** |

---

## 🚀 Quickstart

### 1. Requirements
- Python 3.10+ (Tested on Python 3.12)
- [FFmpeg](https://ffmpeg.org/download.html) and `ffprobe` installed and on system PATH.
- (Optional) NVIDIA GPU with CUDA for NVENC acceleration and Faster-Whisper GPU inference.

### 2. One-Click Start

**On Windows:**
Double-click `start_clipiest.bat` in the repository root, or run:
```bat
start_clipiest.bat
```

**On Linux / macOS:**
Make executable and run `start_clipiest.sh`:
```bash
chmod +x start_clipiest.sh
./start_clipiest.sh
```

*(Both scripts automatically detect `.venv` or `venv`, or automatically initialize `.venv` and install all requirements before launching the server).*

### 3. Manual Startup
```bash
# Navigate to backend
cd backend

# Install dependencies
pip install -r requirements.txt

# Start master engine
python run.py
```
Open **[http://127.0.0.1:8780](http://127.0.0.1:8780)** in your browser.

---

## 📐 11 Native 9:16 Layouts

1. **Stack (`stack`)**: Camera on top, action on bottom (Standard gaming layout).
2. **Bottom (`bottom`)**: Gameplay on top, camera on bottom.
3. **Blurred Fill (`blur`)**: Complete 16:9 frame centered with aesthetic blurred ambient background fill.
4. **Fill Screen (`fill`)**: Cinematic 9:16 center crop filling the entire phone screen.
5. **Gameplay Only (`game`)**: Direct crop to your selected gameplay region.
6. **PiP Bottom-Right (`pip_br`)**: Floating webcam inset bottom-right.
7. **PiP Bottom-Left (`pip_bl`)**: Floating webcam inset bottom-left.
8. **PiP Top-Right (`pip_tr`)**: Floating webcam inset top-right.
9. **PiP Top-Left (`pip_tl`)**: Floating webcam inset top-left.
10. **Circle Camera (`circle`)**: Floating webcam masked with smooth circular alpha equations (`geq=r=...`).
11. **Side by Side (`side`)**: Split columns with camera left and gameplay right.

---

## 🎨 7 Dynamic Subtitle Styles

- **Bounce**: Energetic active-word scale pump (112% zoom) with thick drop-shadow.
- **Hype**: Intense glowing neon red/blue karaoke pop.
- **GTA Neon**: Iconic pink / cyan electric palette with glowing borders.
- **Impact Bold**: High-contrast punchy typography with instant readability.
- **Hormozi**: Clean white baseline text with high-saturation cyan/yellow pop.
- **MrBeast**: High-contrast yellow fill, orange secondary, and thick black outline.
- **Clean**: Minimalist, elegant subtitles.

---

## 🧠 Self-Learning Ridge Regression

Clipiest learns from what **you** consider a great clip:
- When you rate a clip 1 to 5 stars, Clipiest updates its Ridge regression model (`clipiest/ai/learn.py`).
- It fits weights across 5 key features:
  - Loudness spikes
  - 2–4 kHz shouting frequency energy
  - Lexical excitement (Hindi, Hinglish & English hype words)
  - Optical flow motion & action velocity
  - AI semantic viral score
- As you use Clipiest, the discovery ranking adapts to your creator channel and taste.

---

## 📁 Monorepo Structure

```
Clipiest/
├── backend/
│   ├── run.py                     # CLI launcher & startup banner
│   ├── requirements.txt           # Python dependencies
│   ├── fonts/                     # SIL Open Font License fonts (Anton, ArchivoBlack, Poppins)
│   └── clipiest/
│       ├── __init__.py
│       ├── config.py              # Environment & hardware detection (NVENC, QSV, CUDA)
│       ├── server.py              # FastAPI master API server (40 endpoints)
│       ├── pipeline/
│       │   ├── orchestrator.py    # Master end-to-end extraction pipeline
│       │   ├── downloader.py      # yt-dlp section downloader & audio cross-correlation
│       │   ├── queue.py           # Fair round-robin queue & host telemetry
│       │   └── quality.py         # Static screen & commercial filter
│       ├── ai/
│       │   ├── brain.py           # LLM prompt engineering & sentence snapping
│       │   ├── games.py           # 25+ game detectors with viral hashtag injection
│       │   ├── providers.py       # Universal AI gateway (Gemini, OpenAI, Claude, Ollama)
│       │   └── learn.py           # Self-learning Ridge regression feedback loop
│       ├── vision/
│       │   ├── facecam.py         # CV edge gradient & stillness facecam detector
│       │   ├── action.py          # Farneback optical flow & strobe detection
│       │   └── previews.py        # 4-frame storyboard & seek frame extractor
│       ├── audio/
│       │   ├── highlights.py      # Loudness jump, shout band & candidate peak ranking
│       │   ├── transcribe.py      # Faster-Whisper & YouTube transcript scraper
│       │   └── excite.py          # Multilingual lexical excitement scoring
│       ├── rendering/
│       │   ├── layouts.py         # 11 layouts geometry & FFmpeg filtergraphs
│       │   ├── captions.py        # 7 ASS/SRT caption styles & hook badges
│       │   ├── translit.py        # Universal Romanization (Devanagari, Urdu, Cyrillic, Greek)
│       │   ├── render.py          # Hardware encoding (NVENC/QSV/libx264)
│       │   └── reedit.py          # Fast non-destructive saved clip re-framing
│       ├── live/
│       │   ├── session.py         # Streamlink live recording buffer & spike clipper
│       │   └── chat.py            # Twitch IRC SSL & YouTube Live chat listener
│       └── storage/
│           └── manager.py         # Disk telemetry & OS explorer integration
├── frontend/
│   ├── index.html                 # Sleek dark neon studio UI
│   ├── style.css                  # Modern responsive design & layout wireframes
│   └── app.js                     # Interactive canvas crop editor & real-time phone simulator
├── tests/
│   ├── test_layouts.py            # Layout bounds & filtergraph tests
│   ├── test_translit.py           # Multilingual transliteration tests
│   ├── test_games.py              # Game detection & hashtag tests
│   ├── test_learn.py              # Ridge regression fitting tests
│   ├── test_reedit.py             # Non-destructive re-edit tests
│   └── test_server.py             # FastAPI API endpoint integration tests
├── .env.example                   # Environment configuration template
├── .gitignore
├── requirements.txt               # Root pip dependencies
├── start_clipiest.bat             # One-click Windows starter (auto-venv + auto-pip)
├── start_clipiest.sh              # One-click Linux / macOS starter (auto-venv + auto-pip)
├── README.md
```

---

## 🧪 Running Verifications

To run the full unit and integration test suite:
```bash
python -m unittest discover -s tests -v
```
All 26 automated tests verify layout geometries, Romanization, game rules, self-learning loops, and server endpoints.

---

## 📜 License
Clipiest is open-source software under the Apache 2.0 License.
Included fonts are licensed under the SIL Open Font License (OFL).
