# Clipiest ⚡
### The Ultimate Free & Open-Source AI Video Clipping Engine

> **"To all the clippers out there: this platform was built for you."**  
> Transform horizontal streams, podcasts, and gameplay VODs into viral 9:16 vertical shorts in seconds.  
> 100% free, runs locally on your PC, zero subscriptions, zero watermarks, zero cloud queues.

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue)](https://www.python.org/)
[![Hardware: NVENC / QSV / CPU](https://img.shields.io/badge/Hardware-NVIDIA%20NVENC%20%7C%20Intel%20QSV-green)](https://ffmpeg.org)
[![Local AI: LM Studio / Ollama](https://img.shields.io/badge/Local%20AI-LM%20Studio%20%7C%20Ollama-orange)](https://lmstudio.ai)
[![Social: Shorts / TikTok / Reels](https://img.shields.io/badge/Direct%20Publish-Shorts%20%7C%20TikTok%20%7C%20Reels-ff2fa6)](https://github.com/sajjadalinaqvi/clipiest)

---

## 📖 Complete Setup Guides & Resources

- 📥 **[Download Complete 15-Page Setup Guide (PDF)](https://drive.google.com/file/d/1BSyUjU2Lwxtuc3aLOLvrJRtJzXklNC36/view?usp=sharing)** — Step-by-step visual handbook hosted on Google Drive.
- 🎨 **[Open Live A4 Setup Cards in Canva](https://canva.link/z47fizkxd4g7fee)** — Official Canva design cards formatted to standard ISO A4 portrait dimensions.

---

## 🌟 Why Clipiest? (Feature Comparison)

| Capability | Commercial SaaS ($30–$50/mo) | Standard Open-Source | **Clipiest (Unified)** |
| :--- | :---: | :---: | :---: |
| **Pricing & Subscriptions** | ❌ $30 to $50/month | ⚠️ Varied / Limited | ✅ **100% Free & Open-Source forever** |
| **Watermarks & Quality** | ❌ Watermarks on low tiers | ⚠️ Often basic | ✅ **Zero watermarks — crisp 1080x1920 60FPS** |
| **Processing Limits** | ❌ 60–120 mins/month | ⚠️ Cloud bottlenecks | ✅ **Unlimited video processing on your hardware** |
| **Data Privacy** | ❌ Streams uploaded to cloud | ⚠️ Telemetry dependent | ✅ **100% Local & Private — zero data leaves your PC** |
| **Speech Recognition (ASR)** | ❌ Cloud API rate limits | ⚠️ Heavy slow Whisper | ✅ **Faster-Whisper (CUDA GPU acceleration, 98% accuracy)** |
| **Viral Moment AI Discovery** | ❌ Rigid proprietary logic | ⚠️ Loudness only | ✅ **Dual-Judge: Audio energy + Local LLM (LM Studio / Ollama)** |
| **Vertical 9:16 Layouts** | ⚠️ 2–3 standard presets | ❌ Basic center crop | ✅ **11 Native Layouts (Stack, PiP, Blur, Side-by-Side, Circle)** |
| **Bounding Box Canvas** | ❌ Rigid automatic cuts | ❌ None | ✅ **Interactive Cyan (Facecam) & Purple (Action) Draggable Canvas** |
| **Dynamic Animated Subtitles** | ⚠️ Basic static text | ❌ Plain subtitles | ✅ **7 Kinetic ASS Styles (MrBeast bounce, neon glow, karaoke)** |
| **Opening Hook Badges** | ❌ None | ❌ None | ✅ **14 Opening Hooks (Hot Take, Reaction, Myth, 3 Steps)** |
| **Direct Social Publishing** | ⚠️ Third-party add-on | ❌ Manual upload only | ✅ **1-Click Upload to YouTube Shorts, TikTok, and Reels** |
| **Hardware Acceleration** | ❌ Remote queue wait | ❌ Software libx264 only | ✅ **Auto-detects NVIDIA NVENC, Intel QSV, or CPU fallback** |
| **Age-Gate & Cookies Bypass** | ❌ Fails on 18+ streams | ❌ Download error | ✅ **Built-in `cookies.txt` bypass for age-restricted videos** |
| **Self-Learning Feedback Loop** | ❌ Fixed model | ❌ Static weights | ✅ **Real-time Ridge regression adapts to your 1–5★ ratings** |

---

## 🚀 Quickstart

### Option A: One-Click Launchers (Recommended)

**On Windows:**
Double-click `start_clipiest.bat` in the repository root, or run:
```bat
start_clipiest.bat
```

**On Linux / macOS:**
Make executable and run:
```bash
chmod +x start_clipiest.sh
./start_clipiest.sh
```

*(Both scripts automatically locate Python 3, initialize a virtual environment (`.venv`), install all requirements, and launch the server).*

---

### Option B: Autonomous Agent Auto-Setup (Google Antigravity / Claude Code / Cursor)

Copy and paste this autonomous prompt directly into **Google Antigravity** (`Antigravity IDE` or `agy` CLI), Claude Code, Cursor, or Codex:

```text
You are Google Antigravity, the autonomous AI assistant. Install, configure, and smoke-test CLIPIEST on this computer now.

REPOSITORY: https://github.com/sajjadalinaqvi/clipiest.git
INSTALL FOLDER: C:\clipiest on Windows; ~/clipiest on macOS/Linux.

1. Check Python (3.10-3.12), Git, FFmpeg/ffprobe, and GPU encoders (NVENC/QSV).
2. Clone repository, create Python virtual environment (.venv), and install requirements.txt.
3. Configure AI provider: connect LM Studio on http://127.0.0.1:1234/v1 or set OPENAI_API_KEY.
4. Launch server: python backend/run.py and verify HTTP 200 at http://127.0.0.1:8780.
5. Verify sample clip export and report active status.
```

---

### Option C: Manual Terminal Setup

```bash
# 1. Clone repository
git clone https://github.com/sajjadalinaqvi/clipiest.git
cd clipiest

# 2. Create and activate virtual environment
python -m venv .venv

# Windows:
.\.venv\Scripts\activate
# Linux / macOS:
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Start the engine
cd backend
python run.py
```

Open your browser to: **[http://127.0.0.1:8780](http://127.0.0.1:8780)**

---

## 🧠 Universal AI Language Model Gateway

Clipiest decouples the video engine from cloud dependencies. Set up your AI brain in seconds via the in-studio configuration modal:

```
[⚡ Configure AI Language Model]
┌─────────────────────────────────────────────────────────────────┐
│ Select AI Provider:                                             │
│ [ 🖥️ LM Studio ]   [ 🦙 Ollama ]   [ ⚡ Gemini ]   [ 🤖 OpenAI ] │
│ [ 🧠 Claude ]      [ 🚀 Groq ]     [ 🌐 OpenRouter ] [ ⚙️ Custom ]│
│                                                                 │
│ Endpoint Base URL:  http://127.0.0.1:1234/v1                    │
│ Model Name:         meta-llama-3.1-8b-instruct   [🔄 Fetch]     │
│ Speech Model (ASR): small (Good Accuracy, 480MB, Local)         │
│                                                                 │
│         [ ⚡ Test LLM Connection ]  [ Save & Unlock Clipiest 🚀 ]│
└─────────────────────────────────────────────────────────────────┘
```

- **LM Studio (100% Free Local Offline)**: Run [LM Studio](https://lmstudio.ai) on port `1234` with `meta-llama-3.1-8b-instruct` or `qwen2.5-7b-instruct`.
- **Ollama (CLI Local Offline)**: Run `ollama run llama3.2:3b` at `http://127.0.0.1:11434/v1`.
- **Google Gemini (Free Cloud Tier)**: Paste your API key and use `gemini-2.5-flash` for instant sub-second scouting.
- **OpenAI (Cloud)**: Use your OpenAI API key with `gpt-4o-mini` ($0.001 per video).
- **Claude / Groq / OpenRouter / Custom**: Full support for Anthropic Claude, Groq Llama at 500+ tok/s, or any OpenAI-compatible API.

---

## 📐 11 Native 9:16 Vertical Layouts

1. **Stack (`stack`)**: Camera on top, action on bottom with split divider (Standard esports/gaming format).
2. **Bottom (`bottom`)**: Gameplay on top, camera on bottom.
3. **Blurred Fill (`blur`)**: Full 16:9 frame centered against a dynamic ambient blurred background.
4. **Fill Screen (`fill`)**: Cinematic 9:16 center crop filling the entire vertical screen.
5. **Gameplay Only (`game`)**: Direct crop focused strictly on the gameplay crosshair/action.
6. **PiP Bottom-Right (`pip_br`)**: Floating webcam inset in bottom-right corner.
7. **PiP Bottom-Left (`pip_bl`)**: Floating webcam inset in bottom-left corner.
8. **PiP Top-Right (`pip_tr`)**: Floating webcam inset in top-right corner.
9. **PiP Top-Left (`pip_tl`)**: Floating webcam inset in top-left corner.
10. **Circle Camera (`circle`)**: Floating circular-masked webcam overlay with smooth alpha gradient.
11. **Side by Side (`side`)**: Dual vertical columns with camera left and gameplay right.

---

## 🎨 7 Dynamic Subtitle Styles & 14 Hook Badges

### Subtitle Styles
- **Bounce**: High-energy active-word scale pump (112% zoom) with thick drop shadow (MrBeast style).
- **Hype**: Glowing electric karaoke pop with rhythm-timed word highlights.
- **GTA Neon**: Iconic Vice City magenta (`#ff2fa6`) and cyan (`#00e5ff`) borders.
- **Impact Bold**: High-contrast punchy typography with instant readability.
- **Hormozi**: Clean white baseline text with high-saturation yellow/cyan active word pops.
- **Karaoke**: Smooth progressive fill bar revealing words as the speaker talks.
- **Clean**: Elegant, minimalist subtitles for business, podcasts, and interviews.

### 14 Opening Hook Badges
Overlays in the opening seconds to stop the scroll on TikTok and Shorts:
`HOT TAKE` • `HOW TO` • `BREAKDOWN` • `REACTION` • `STORYTIME` • `BEFORE-AFTER` • `MISTAKE` • `MYTH` • `QUICK TIP` • `WARNING` • `TEST` • `3 STEPS` • `QUESTION` • `RESULT`.

---

## 🚀 Direct Social Media Publishing (Shorts, TikTok, Reels)

Publish your finished vertical clips directly without leaving the app:
1. Navigate to **LLM & Settings > Connected Accounts**.
2. Connect your credentials:
   - **YouTube Shorts:** OAuth2 Client ID / Secret or Channel Access Token (YouTube Data API v3).
   - **TikTok:** Developer Client Key & Access Token (Content Posting API).
   - **Instagram Reels:** Facebook Page Access Token & IG User ID (Meta Graph API).
3. In your **Library**, click the **🚀 Publish** button on any clip to send it directly to your channels with custom titles, descriptions, and hashtags.

---

## 🔒 Data & Storage Security

- **File Protection System:** Critical configuration files (`social_accounts.json`, `config.json`, `cookies.txt`, `weights.json`) are permanently locked and protected against accidental deletion in the Data & Storage manager.
- **Zero Cloud Leakage:** All video processing, transcription, face detection, and video rendering happen 100% on your local machine.

---

## 📁 Repository Architecture

```
Clipiest/
├── backend/
│   ├── run.py                     # Entrypoint CLI launcher (sys.path auto-resolver)
│   ├── requirements.txt           # Backend Python dependencies
│   ├── fonts/                     # SIL Open Font License fonts (Anton, ArchivoBlack, Poppins)
│   └── clipiest/
│       ├── config.py              # Environment & hardware detection (NVENC, QSV, CUDA)
│       ├── server.py              # FastAPI server (40+ REST API endpoints)
│       ├── social/
│       │   └── accounts.py        # YouTube Shorts, TikTok, and Instagram Reels direct publisher
│       ├── creators/
│       │   └── manager.py         # Multi-creator workspace profiles
│       ├── pipeline/
│       │   ├── orchestrator.py    # Master end-to-end extraction pipeline
│       │   ├── downloader.py      # Progressive audio extraction via yt-dlp & cross-correlation
│       │   └── queue.py           # Fair round-robin queue & host telemetry
│       ├── ai/
│       │   ├── brain.py           # LLM prompt engineering & sentence snapping
│       │   ├── games.py           # 25+ game detectors with viral hashtag injection
│       │   ├── providers.py       # Universal AI gateway (LM Studio, Ollama, Gemini, OpenAI, Claude, Groq)
│       │   └── learn.py           # Self-learning Ridge regression feedback loop
│       ├── vision/
│       │   ├── facecam.py         # CV edge gradient & stillness facecam detector
│       │   ├── action.py          # Farneback optical flow & strobe detection
│       │   └── previews.py        # Storyboard & seek frame extractor
│       ├── audio/
│       │   ├── highlights.py      # Loudness jump, shout band & candidate peak ranking
│       │   ├── transcribe.py      # Faster-Whisper local ASR & transcript scraper
│       │   └── excite.py          # Multilingual lexical excitement scoring
│       └── rendering/
│           ├── layouts.py         # 11 layouts geometry & FFmpeg filtergraphs
│           ├── captions.py        # 7 ASS/SRT caption styles & 14 hook badges
│           ├── translit.py        # Universal Romanization (Devanagari, Urdu, Cyrillic, Greek)
│           ├── render.py          # Hardware encoding (NVENC/QSV/libx264)
│           └── reedit.py          # Non-destructive saved clip re-framing studio
├── frontend/
│   ├── index.html                 # Dark neon creator studio UI
│   ├── style.css                  # Modern responsive design & layout wireframes
│   └── app.js                     # Interactive canvas crop editor & real-time phone simulator
├── tests/                         # 71 comprehensive unit & integration tests
│   ├── test_social.py             # Social account storage & direct publish tests
│   ├── test_cookies_and_age_gate.py# YouTube cookies bypass tests
│   ├── test_creators.py           # Creator profile workspace tests
│   ├── test_ai_providers.py       # LLM provider connectivity & model parsing tests
│   ├── test_layouts.py            # 11 layout geometry & filtergraph tests
│   ├── test_all_renders.py        # Full rendering passes across all 11 layouts & styles
│   └── test_server.py             # FastAPI API endpoint integration tests
├── requirements.txt               # Root pip dependencies
├── start_clipiest.bat             # 1-Click Windows starter (auto-venv + auto-pip)
├── start_clipiest.sh              # 1-Click Linux / macOS starter (auto-venv + auto-pip)
├── .env.example                   # Environment configuration template
├── .gitignore                     # Git ignore rules (protects data, models, and ./docs)
└── README.md
```

---

## 🧪 Automated Testing & Verification

To run the complete 71-test automated suite:
```bash
python -m unittest discover -s tests -v
```
All 71 tests verify layout geometries, Romanization, game rules, self-learning loops, cookies bypass, AI gateways, direct social publishing, and rendering passes.

---

## 📜 License & Acknowledgments

- **License:** Open-source software under the [Apache 2.0 License](LICENSE).
- **Fonts:** Licensed under the [SIL Open Font License (OFL)](http://scripts.sil.org/OFL).
- **Special Thanks:** Built with gratitude to the open-source communities powering [FFmpeg](https://ffmpeg.org/), [Faster-Whisper](https://github.com/SYSTRAN/faster-whisper), [yt-dlp](https://github.com/yt-dlp/yt-dlp), [FastAPI](https://fastapi.tiangolo.com/), and [LM Studio](https://lmstudio.ai/).