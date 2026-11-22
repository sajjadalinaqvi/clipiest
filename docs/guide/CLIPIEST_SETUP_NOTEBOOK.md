# THE CREATOR'S SETUP NOTEBOOK
# CLIPIEST: FROM LINK TO CLIP.

> **Install it. Connect local AI. Paste a video. Export a vertical clip.**  
> *Complete English Guide — GTA VI Vice City Edition*  
> *Author: Sajjad Ali Naqvi | Date: November 2026 | Desktop Edition*  
> *100% Free & Open-Source AI Video Clipping Engine*

![Clipiest GTA VI Edition Cover Artwork](clipiest_gta_vi_poster.jpg)

---

## TABLE OF CONTENTS

- **01 / THE ROUTE** — Your First Finished Clip in 5 Steps
- **02 / BEFORE INSTALLATION** — Give the Agent a Workspace
- **03 / AGENT PROMPT** — 1-Click Copy-Paste-Run Prompt (Parts 1, 2, 3)
- **04 / MAKE AI READY** — Connect LM Studio, Ollama, or Cloud API
- **05 / BRING A SOURCE** — Paste URL, Upload MP4, & YouTube Cookies Guide
- **06 / SHAPE THE RESULT** — 11 Layouts, Facecam Bounding Boxes, & ASS Captions
- **07 / EXPORT REVIEW** — Watch Before You Post & Re-Edit Studio
- **08 / DIRECT SOCIAL PUBLISHING** — 1-Click Upload to Shorts, TikTok, & Reels
- **09 / YOUR DAILY ROUTINE** — The Next Video is Simpler & Creator Workspaces
- **10 / MANUAL FALLBACK: WINDOWS** — PowerShell Terminal Walkthrough
- **11 / MANUAL FALLBACK: MACOS & LINUX** — Terminal Setup & Brew/APT Commands
- **12 / FIX A STUCK STEP** — Troubleshooting Matrix by Stage
- **13 / FROM CLIP TO CAMPAIGN** — Monetization & Creator Rewards Playbook

---

## 01 / THE ROUTE
### Your First Finished Clip

This field guide accompanies the recorded Clipiest workflow. Follow these five sequential milestones to go from a long video stream to a viral 9:16 vertical clip:

```
[1] INSTALL ONCE  --->  [2] CHECK AI  --->  [3] IMPORT & FRAME  --->  [4] REVIEW & EXPORT  --->  [5] REPEAT & EARN
```

1. **Install Once**  
   Use the master agent prompt in Section 03. It installs Clipiest, FFmpeg, the local faster-whisper speech model, and connects to your local or hosted AI model.

2. **Check AI**  
   Open `http://127.0.0.1:8780`. Choose your AI provider (LM Studio, Ollama, Gemini, OpenAI, Claude, Groq) and run **Save & Test**. Confirm the green **Ready** status.

3. **Import + Frame**  
   Paste a YouTube/Twitch/Kick URL or drag-and-drop an MP4. Drag the cyan **Facecam Box** and purple **Gameplay Box** directly over the video storyboard, select 1 of 11 layouts, and choose your caption style.

4. **Review + Download**  
   Inspect the AI-recommended viral moments scored 80–99 by retention. Watch the preview, fine-tune subtitle wording in the Re-Edit Studio, and export your 1080x1920 MP4.

5. **Repeat & Publish**  
   Publish directly to YouTube Shorts, TikTok, and Instagram Reels with 1 click using the new Connected Accounts feature, or download for manual submission to monetization campaigns.

> **💡 Zero Subscription Guarantee:**  
> Local processing has **no Clipiest subscription**. Everything runs on your machine using your hardware and local AI. No credits, no watermarks, no paywalls.

---

## 02 / BEFORE INSTALLATION
### Give the Agent a Workspace

Use a terminal-enabled coding agent on the computer that will process your videos.

1. **Open a Coding Agent**  
   Use Claude Code, Codex, Cursor, Gemini CLI, or any terminal-enabled AI agent with command-line execution and file-editing access. A web chat without terminal tools cannot clone repositories or install dependencies.

2. **Paste the Full Agent Prompt**  
   Copy the 3-part prompt from Section 03 or use the included `CLIPIEST-AUTO-SETUP-PROMPT.txt`. You can pass a target YouTube link immediately or leave it blank until the dashboard opens.

3. **Let it Verify the Machine**  
   The agent checks Python (3.10–3.12), Git, FFmpeg/ffprobe, free RAM, VRAM, and GPU hardware encoders (`h264_nvenc` for NVIDIA, `h264_qsv` for Intel).

4. **Keep a Permanent Folder**  
   - Windows: `C:\clipiest`  
   - macOS / Linux: `~/clipiest`  
   Avoid temporary desktop folders or deeply nested paths.

---

## 03 / MASTER AGENT PROMPT (COPY. PASTE. RUN.)

Paste all three parts together into your coding agent terminal in a single prompt:

```text
Install, configure and test Clipiest on this computer now. Execute the work using your terminal and browser tools. Continue through recoverable errors until a real clip exports.

INPUTS:
Source URL or local video path: [paste an allowed creator URL or leave blank]
Install folder: C:\clipiest on Windows; ~/clipiest on macOS/Linux.
Use local AI by default (LM Studio or Ollama, or Gemini API key). Keep publishing manual.

A. CHECK AND INSTALL
Read https://github.com/sajjadalinaqvi/clipiest.git and inspect this computer's OS, architecture, Python, Git, FFmpeg/ffprobe, RAM, GPU, free VRAM and disk space. Reuse working installs. Choose a supported Python interpreter (Python 3.11 or 3.12). Install missing prerequisites from official sources or package manager. Clone the repository into C:\clipiest (or ~/clipiest), create a virtual environment (.venv), and install requirements.txt.

B. CONFIGURE AI & WHISPER
Check if LM Studio is running on http://127.0.0.1:1234/v1 or Ollama on http://127.0.0.1:11434. Select an active model (e.g. meta-llama-3.1-8b-instruct or llama3.2:3b). Configure Clipiest via /api/config. Verify faster-whisper loads the small model locally. Run test connection and confirm green Ready status.

C. START SERVER AND TEST EXPORT
Start python backend/run.py with the project interpreter. Verify the Web UI at http://127.0.0.1:8780. Process the test video or sample clip through /api/clip with layout: stack, top: 0.32, caption_style: bounce. Verify exported MP4 with ffprobe for 1080x1920 dimensions and valid audio. Create a 1-click desktop restart launcher (Clipiest.bat). Report working URL and output path.
```

---

## 04 / MAKE AI READY
### Connect the Local Brain

Clipiest unifies **local offline AI** with optional **cloud LLMs** to scout high-retention moments:

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

1. **Option A: LM Studio (Recommended Local)**  
   - Download LM Studio from `lmstudio.ai`.
   - Load any instruction model (e.g., `meta-llama-3.1-8b-instruct`, `qwen2.5-7b`, or `mistral-7b-instruct`).
   - Start the Local Inference Server on port `1234`.
   - In Clipiest, click **LM Studio** and hit **⚡ Test LLM Connection**.

2. **Option B: Ollama (CLI Native Local)**  
   - Run `ollama run llama3.2:3b` or `ollama run qwen2.5:7b`.
   - In Clipiest, select **Ollama** (`http://127.0.0.1:11434/v1`).

3. **Option C: Google Gemini / Groq / OpenAI (Ultra-Fast Cloud)**  
   - Select **Google Gemini**, paste your free Gemini API key, and select `gemini-2.5-flash` for instant sub-second moment scouting.

---

## 05 / BRING A SOURCE
### Paste a Link. Or Upload.

Clipiest accepts virtually any source:
- **YouTube Links**: Videos, VODs, Podcasts, Premieres (`https://www.youtube.com/watch?v=...`)
- **Twitch & Kick Streams**: Channel VODs and recordings
- **Local Video Files**: MP4, MKV, MOV, WebM, AVI (drag & drop directly onto the upload zone)

### 🍪 YouTube Cookies Guide (For Age-Restricted & 18+ Videos)
If downloading an age-gated or private stream triggers sign-in warnings:
1. Install the Chrome/Firefox extension **"Get cookies.txt LOCALLY"**.
2. Open `YouTube.com` while signed in.
3. Click the extension icon and click **Export** to save `cookies.txt`.
4. In Clipiest, go to **LLM & Settings > YouTube Cookies** and upload your file. Clipiest will now bypass age-restriction checks automatically!

---

## 06 / SHAPE THE RESULT
### 11 Layouts, Facecam Bounding Boxes, & ASS Captions

Clipiest provides interactive visual cropping:

### The 11 Layout Geometries
1. **Face + Gameplay (`stack`)**: Camera above the gameplay action with split divider.
2. **Gameplay + Face (`bottom`)**: Camera below the gameplay action.
3. **Blurred Fill (`blur`)**: Complete 16:9 frame centered against aesthetic blurred background.
4. **Fill Screen (`fill`)**: Full-frame 9:16 center crop.
5. **Gameplay Only (`game`)**: Direct crop to the gameplay action area.
6. **Camera Top-Left (`pip_tl`)**: Floating webcam in top-left corner.
7. **Camera Top-Right (`pip_tr`)**: Floating webcam in top-right corner.
8. **Camera Bottom-Left (`pip_bl`)**: Floating webcam in bottom-left corner.
9. **Camera Bottom-Right (`pip_br`)**: Floating webcam in bottom-right corner.
10. **Circle Camera (`circle`)**: Circular masked webcam floating above gameplay.
11. **Side by Side (`side`)**: Split columns (camera on left, action on right).

### Moving the Bounding Boxes
- **Cyan Box (`FACECAM`)**: Drag and resize directly over the creator's face.
- **Purple Box (`GAMEPLAY`)**: Drag and resize over the main action, crosshair, or HUD.
- The 9:16 preview canvas shows your exact composition in real time!

### 7 Word-Timed ASS Caption Styles
- **Bounce Pop (`bounce`)**: Word-by-word bouncing cyan pop with dark outline (`#00f3ff`).
- **Hype Glow (`hype`)**: Intense red outline glow with high-energy typography (`#ff3c3c`).
- **Clean Minimal (`clean`)**: Elegant subtitle text for podcasts and storytelling (`#ffffff`).
- **GTA Neon (`gta`)**: Vice City magenta & cyan neon pulse (`#43ffee`).
- **Impact Bold (`bold`)**: Heavyweight Archivo Black for high-impact punchlines (`#cb3df3`).
- **Hormozi Cyan (`hormozi`)**: Yellow-to-cyan word pop for high-retention education (`#00ffff`).
- **MrBeast Yellow (`mrbeast`)**: High-contrast yellow & orange outline pop (`#ffff00`).

---

## 07 / EXPORT REVIEW & RE-EDIT STUDIO
### Watch Before You Post

Once the clip renders, open the **Clip Library** tab:
1. **Watch Full Playback**: Confirm audio levels, voice clarity, and hook punchline timing.
2. **⚡ Interactive Re-Edit Studio**:
   - Want to change from `stack` to `circle` camera? Click **⚡ Edit**.
   - Need to adjust word phrasing or fix an uncommon streamer name? Tweak subtitle timing words directly without re-downloading or re-running speech recognition.
   - Click **Save & Re-render** for an instant hardware-accelerated re-export in seconds!

---

## 08 / DIRECT SOCIAL PUBLISHING
### 1-Click Upload to Shorts, TikTok, & Reels

Clipiest includes a native multi-platform publishing engine:
1. Go to **Settings > Connected Accounts**.
2. Connect your **YouTube Shorts**, **TikTok**, and **Instagram Reels** accounts.
3. In the **Clip Library**, click the **`🚀 Publish`** button on any clip card:
   - Auto-populates the AI-scouted viral title, description, and hashtags (`#shorts #fyp #reels`).
   - Select your target destinations: `[✓] YouTube Shorts`, `[✓] TikTok`, `[✓] Instagram Reels`.
   - Set visibility to **Public** or **Unlisted** and click **Publish Now 🚀**!

---

## 09 / YOUR DAILY ROUTINE
### The Next Video is Simpler

Installation is a one-time process. For daily clipping sessions:
1. Double-click `Clipiest.bat` on your desktop.
2. Open `http://127.0.0.1:8780` in your browser.
3. Paste your video URL or drop an MP4.
4. Let the AI scout the top 4 viral moments.
5. Pick your favorite clips, re-edit if desired, and hit **Publish**!

---

## 10 / MANUAL FALLBACK: WINDOWS
### PowerShell Terminal Setup

If you prefer installing manually from terminal commands:

```powershell
# 1. Install prerequisites via Windows Package Manager
winget install --id Git.Git -e
winget install --id Python.Python.3.11 -e
winget install --id Gyan.FFmpeg -e

# 2. Clone Clipiest
git clone https://github.com/sajjadalinaqvi/clipiest.git C:\clipiest
cd C:\clipiest

# 3. Create virtual environment & install requirements
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt

# 4. Start Clipiest Server
.\.venv\Scripts\python.exe backend\run.py
```
Open `http://127.0.0.1:8780` in your browser.

---

## 11 / MANUAL FALLBACK: MACOS & LINUX
### Terminal Walkthrough

```bash
# macOS (using Homebrew)
brew install git python@3.11 ffmpeg

# Linux (Debian / Ubuntu)
sudo apt update && sudo apt install -y git python3 python3-venv python3-pip ffmpeg

# Clone & Setup
git clone https://github.com/sajjadalinaqvi/clipiest.git ~/clipiest
cd ~/clipiest
python3 -m venv .venv
./.venv/bin/pip install --upgrade pip
./.venv/bin/pip install -r backend/requirements.txt

# Start Clipiest
./.venv/bin/python backend/run.py
```

---

## 12 / FIX A STUCK STEP
### Troubleshooting Matrix by Stage

| Issue | Root Cause | Solution |
|---|---|---|
| **Port 8780 already in use** | An existing background server is running | Run `netstat -ano \| findstr :8780` and terminate the PID with `taskkill /F /PID <pid>`. |
| **CUDA / NVENC not detected** | NVIDIA drivers outdated or GPU absent | Clipiest automatically falls back to Intel QSV or CPU `libx264`. To enable NVENC, install NVIDIA driver 535+. |
| **YouTube 403 / Age-restricted error** | YouTube requires bot verification or 18+ sign-in | Export `cookies.txt` and upload in Settings > YouTube Cookies. |
| **LLM Connection Refused** | Local LLM server not started | In LM Studio, click **Start Server** on port 1234. In Ollama, run `ollama serve`. |
| **Whisper download stalled** | Slow internet during first model download | The 480MB Whisper model downloads once. Check disk space in `C:\Users\<user>\.cache\huggingface`. |
| **Captions off-center or clipping HUD** | Video has non-standard facecam position | Adjust the Cyan and Purple crop boxes and use the `caption_y` slider in Re-Edit. |

---

## 13 / FROM CLIP TO CAMPAIGN
### Monetization & Creator Rewards Playbook

Clipiest generates short-form vertical assets that qualify for creator payout programs:

1. **TikTok Creator Rewards Program**  
   - Requirement: 1-minute+ original clips with high completion rate.
   - Set Clipiest duration to `60s - 90s` and choose the `Bounce` or `MrBeast` caption style.

2. **YouTube Shorts Monetization**  
   - YouTube Shorts algorithm rewards 15s–30s fast-hook videos.
   - Use Clipiest's auto-generated viral hooks (e.g., `"WAIT FOR THIS"`, `"HE LOST HIS MIND"`) and enable `#Shorts` auto-tagging.

3. **Streamer Clipping Gigs & Campaigns (Whop, Vyro, Kick Creator Fund)**  
   - Gaming creators and esports teams pay clip editors per 1,000 views or per accepted highlight package.
   - Use Clipiest's **Creator Workspaces** to save unique layout presets for each streamer you edit for!

---

*Clipiest is 100% Free and Open-Source Software licensed under the MIT License.*  
*Repository: [https://github.com/sajjadalinaqvi/clipiest](https://github.com/sajjadalinaqvi/clipiest)*
