# Clipiest Architectural Design Document

## 1. System Overview

Clipiest is an intelligent local clipping engine that discovers viral moments in long-form gaming replays and live streams, automatically reframing and rendering them into vertical 9:16 format with word-timed animated typography.

Clipiest synthesizes the strongest components of **NeonClipping** and **PeakCut**:
- **Progressive Discovery (PeakCut)**: Scrapes YouTube word-timed captions or downloads small audio tracks first, avoiding massive 4GB video downloads for long replays.
- **Visual Intelligence (NeonClipping)**: Analyzes 6-FPS Farneback optical flow motion vectors, scene cut transitions, and RGB strobe colors (flashes, police sirens).
- **Computer Vision Facecam Detection (PeakCut)**: Automatically detects facecam regions using vertical/horizontal edge gradient profiles and temporal stillness variance to reject moving HUD elements.
- **Interactive Dual-Canvas Studio (NeonClipping)**: Provides draggable bounding boxes directly on source frames with live 9:16 phone simulator preview.
- **11 Native Layouts (NeonClipping)**: Supports Stack, Bottom, Blurred Fill, Fill Screen, Gameplay Crop, Picture-in-Picture (4 corners), Circle Camera, and Side-by-Side Split.
- **Self-Learning User Feedback Loop (NeonClipping)**: Ridge regression model tuning feature weights based on 1–5 star user feedback.
- **Universal Multi-Provider AI Gateway (PeakCut)**: Interfaces with Gemini, OpenAI, Claude, Groq, Grok, OpenRouter, or local Ollama instances.
- **Live Stream Chat Spike Clipper (NeonClipping)**: Continuously records live Twitch/YouTube streams and cuts moments based on chat message velocity spikes.

---

## 2. Core Subsystems

```
                                      ┌────────────────────────────────────────────────────────┐
                                      │                      Input Source                      │
                                      │         (YouTube, Twitch, Kick, or Local Video)        │
                                      └───────────────────────────┬────────────────────────────┘
                                                                  │
                                      ┌───────────────────────────▼────────────────────────────┐
                                      │             Progressive Audio-First Extractor          │
                                      │         yt-dlp ba[ext=m4a] + YouTube Caption JSON3     │
                                      └───────────────────────────┬────────────────────────────┘
                                                                  │
                   ┌──────────────────────────────────────────────┴──────────────────────────────────────────────┐
                   │                                                                                             │
                   ▼                                                                                             ▼
    ┌─────────────────────────────┐                                                               ┌─────────────────────────────┐
    │     Audio & Speech Signals  │                                                               │       Visual Heuristics     │
    │  - RMS Loudness Jumps       │                                                               │  - Farneback Optical Flow   │
    │  - 2-4 kHz Shouting Bands   │                                                               │  - Hard Scene Cuts          │
    │  - Lexical Excitement Words │                                                               │  - Flash & Strobe Detection │
    └──────────────┬──────────────┘                                                               └──────────────┬──────────────┘
                   │                                                                                             │
                   └──────────────────────────────────────────────┬──────────────────────────────────────────────┘
                                                                  │
                                      ┌───────────────────────────▼────────────────────────────┐
                                      │              Gaussian Smoothing & Peak Finder          │
                                      │         Ranks candidate highlight moments by energy   │
                                      └───────────────────────────┬────────────────────────────┘
                                                                  │
                                      ┌───────────────────────────▼────────────────────────────┐
                                      │                AI Semantic Evaluation                  │
                                      │         Sentence snapping & viral hook generation      │
                                      └───────────────────────────┬────────────────────────────┘
                                                                  │
                                      ┌───────────────────────────▼────────────────────────────┐
                                      │             Self-Learning Ridge Regression             │
                                      │         Tunes rank weights based on 1-5 star ratings   │
                                      └───────────────────────────┬────────────────────────────┘
                                                                  │
                                      ┌───────────────────────────▼────────────────────────────┐
                                      │         Exact Section Audio Cross-Correlation          │
                                      │         yt-dlp download-sections + FFT offset sync     │
                                      └───────────────────────────┬────────────────────────────┘
                                                                  │
                                      ┌───────────────────────────▼────────────────────────────┐
                                      │              Computer Vision Auto-Framing              │
                                      │         Edge profile stillness facecam detector        │
                                      └───────────────────────────┬────────────────────────────┘
                                                                  │
                                      ┌───────────────────────────▼────────────────────────────┐
                                      │             FFmpeg Hardware Vertical Renderer          │
                                      │         NVENC / QSV / libx264 + 11 Layout Filtergraphs │
                                      │         Word-timed ASS captions & loudnorm audio       │
                                      └───────────────────────────┬────────────────────────────┘
                                                                  │
                                      ┌───────────────────────────▼────────────────────────────┐
                                      │                    Output Products                     │
                                      │         9:16 Vertical MP4 + Word-Timed SRT & ASS       │
                                      └────────────────────────────────────────────────────────┘
```

---

## 3. Mathematical Foundations

### 3.1 Circular Alpha Equations for Layouts
The circular facecam overlay (`circle`) dynamically generates an analytical alpha mask directly within FFmpeg's `geq` filter without requiring auxiliary mask files:
$$\text{mask}(X, Y) = \begin{cases} 255 & \text{if } (X - W/2)^2 + (Y - H/2)^2 \le (\min(W, H)/2)^2 \\ 0 & \text{otherwise} \end{cases}$$

### 3.2 Ridge Regression Scoring Loop
Each candidate moment $i$ is scored by linear combination of normalized feature vectors:
$$\text{Rank}(i) = \sum_{j} w_j \cdot f_{i, j}$$
Where $f$ contains:
1. $f_{\text{loud}}$: RMS loudness jump
2. $f_{\text{shout}}$: 2–4 kHz shout band power
3. $f_{\text{words}}$: Lexical excitement score
4. $f_{\text{motion}}$: Average optical flow velocity
5. $f_{\text{flash}}$: Brightness jump delta
6. $f_{\text{strobe}}$: Red/blue color balance variance
7. $f_{\text{cuts}}$: Scene change frequency
8. $f_{\text{llm}}$: AI semantic score

When the user submits $N \ge 8$ ratings ($y \in [1, 5]$ normalized to $[0, 1]$), the weight vector $w$ is updated via Ridge regression with L2 regularization ($\lambda = 1.0$):
$$w = (X^T X + \lambda I)^{-1} X^T y$$

### 3.3 Audio Cross-Correlation Time Offset
When downloading a partial video section via `yt-dlp --download-sections`, keyframe rounding can cause timestamp drift. Clipiest calculates the cross-correlation between the isolated audio section and the reference audio:
$$R(t) = \mathcal{F}^{-1} \left( \mathcal{F}(A_{\text{section}}) \cdot \mathcal{F}^*(A_{\text{ref}}) \right)$$
The peak index of $R(t)$ determines the millisecond-accurate alignment offset $\Delta t$.

---

## 4. Verification and Reliability

- **Zero Mock Policy**: Every module executes real signal processing (FFT cross-correlation, Faster-Whisper ASR, Farneback optical flow, and FFmpeg filtergraphs).
- **Graceful Fallbacks**:
  - GPU NVENC $\rightarrow$ Intel QSV $\rightarrow$ CPU libx264.
  - Faster-Whisper CUDA $\rightarrow$ CPU int8.
  - Multi-LLM provider fallback $\rightarrow$ local Ollama.
  - Missing psutil $\rightarrow$ standard library fallback.
