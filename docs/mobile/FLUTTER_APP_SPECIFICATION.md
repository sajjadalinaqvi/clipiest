# Clipiest Mobile App — Flutter Specification (iOS & Android)

A complete architectural, UI/UX, and technical specification for building the cross-platform mobile client for **Clipiest** using **Flutter 3.x (Dart 3)**.

---

## 1. System Architecture & Compute Model

Clipiest Mobile uses a **Hybrid Client-Server Architecture**:

```
+---------------------------------------------------------------------------------------+
|                              FLUTTER CLIENT (iOS & Android)                          |
|                                                                                       |
|  +---------------------------+  +-------------------------+  +---------------------+  |
|  |  Interactive Touch Crop   |  | Word Subtitle Re-Editor |  | 9:16 Layout Canvas  |  |
|  |  (Facecam / Game Boxes)   |  |   (Tap / Split / Time)  |  |  Compositor (60fps) |  |
|  +---------------------------+  +-------------------------+  +---------------------+  |
|               ^                              ^                          ^             |
|               |                              |                          |             |
|  +---------------------------------------------------------------------------------+  |
|  | State Layer: Riverpod 2.x Notifiers + CodeGen (StreamProviders for SSE)         |  |
|  | Media Player: media_kit (libmpv Hardware-Accelerated Video Surface)             |  |
|  | On-Device ML: google_mlkit_face_detection (Instant Auto-Frame Heuristic)       |  |
|  +---------------------------------------------------------------------------------+  |
+---------------------------------------------------------------------------------------+
                                           |
                         REST API + Server-Sent Events (SSE)
                                           v
+---------------------------------------------------------------------------------------+
|                              CLIPIEST BACKEND SERVER                                  |
|                                                                                       |
|  - Fast stream extraction & chunking (yt-dlp)                                         |
|  - High-precision speech-to-text with word timestamps (faster-whisper)                |
|  - AI viral retention scoring & moment scout (LM Studio, Ollama, Gemini, OpenAI, etc.)|
|  - Master FFmpeg Hardware Render Engine (11 layouts, ASS typography, NVENC / QSV)     |
+---------------------------------------------------------------------------------------+
```

### Why Flutter?
- **Single Unified Codebase**: 100% feature and visual parity on iPhone and Android.
- **Hardware-Accelerated Canvas**: Flutter's Impeller / Skia engine enables zero-latency real-time video cropping and layer composition on mobile screens without waiting for server renders.
- **Rich Touch & Haptic Ecosystem**: Fluid gestures for video timeline scrubbing and bounding box adjustments.

---

## 2. Mobile UI/UX Design System (Cyberpunk Dark Neon)

### 2.1 Color Palette & Theme Tokens
```dart
class ClipColors {
  // Backgrounds
  static const Color background = Color(0xFF07090E);
  static const Color surface = Color(0xFF0F1322);
  static const Color surfaceLight = Color(0xFF161B2E);
  static const Color border = Color(0x337C3AED);

  // Accents & Neon Glows
  static const Color primary = Color(0xFF7C3AED);        // Electric Violet
  static const Color primaryGlow = Color(0x737C3AED);
  static const Color cyan = Color(0xFF00F3FF);           // Cyber Cyan (Facecam Box)
  static const Color cyanGlow = Color(0x6600F3FF);
  static const Color accentRed = Color(0xFFFF3366);       // Hype / Retention Badge
  static const Color accentYellow = Color(0xFFFFDD00);    // Punch / MrBeast Yellow
  static const Color textMain = Color(0xFFF1F5F9);
  static const Color textMuted = Color(0xFF94A3B8);
}
```

### 2.2 Typography
- **UI Elements & Navigation**: `Plus Jakarta Sans`
- **Dynamic Captions & Badges**: Bundled TrueType Fonts (`Poppins-ExtraBold.ttf`, `Anton-Regular.ttf`, `ArchivoBlack-Regular.ttf`)
- **Timestamps & Technical Badges**: `JetBrains Mono`

### 2.3 Navigation Shell (Bottom Navigation Bar)
Fixed bottom bar with 5 destinations (minimum 48dp touch targets):
1. **Studio** (`icon: Icons.dashboard_customize_rounded`): Video input, storyboard scrub, layout picker, crop box handles, export.
2. **Moments** (`icon: Icons.bolt_rounded`): LLM-scouted viral recommendations with score chips (e.g. `🔥 95/100`), 1-tap select.
3. **Live** (`icon: Icons.sensors_rounded`): Real-time Twitch/YouTube live stream monitor with audio energy spikes.
4. **Library** (`icon: Icons.video_library_rounded`): Vertical TikTok-style feed of rendered 9:16 clips with one-tap Re-Edit.
5. **Settings** (`icon: Icons.tune_rounded`): Multi-provider LLM settings, YouTube cookies upload, safe storage manager.

---

## 3. Flutter Core Components & Code Implementation

### 3.1 Real-Time 9:16 Preview Canvas (`ClipCompositor`)
Renders the 16:9 source video cropped and split into 9:16 format in real time while editing, without placing any load on the backend.

```dart
import 'package:flutter/material.dart';
import 'package:media_kit_video/media_kit_video.dart';

enum ClipLayoutMode { stack, bottom, blur, fill, game, circle, pipBr, side }

class ClipCompositorWidget extends StatelessWidget {
  final VideoController controller;
  final ClipLayoutMode layout;
  final Rect facecamRect;   // Normalized (0.0 - 1.0)
  final Rect gameplayRect;  // Normalized (0.0 - 1.0)
  final double topHeightRatio; // e.g. 0.32
  final String? activeHookText;
  final String? activeCaptionText;

  const ClipCompositorWidget({
    super.key,
    required this.controller,
    required this.layout,
    required this.facecamRect,
    required this.gameplayRect,
    this.topHeightRatio = 0.32,
    this.activeHookText,
    this.activeCaptionText,
  });

  @override
  Widget build(BuildContext context) {
    return AspectRatio(
      aspectRatio: 9 / 16,
      child: Container(
        decoration: BoxDecoration(
          color: Colors.black,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: const Color(0xFF7C3AED).withOpacity(0.5), width: 1.5),
          boxShadow: [
            BoxShadow(
              color: const Color(0xFF7C3AED).withOpacity(0.2),
              blurRadius: 24,
              spreadRadius: 2,
            ),
          ],
        ),
        clipBehavior: Clip.antiAlias,
        child: Stack(
          children: [
            // Layer 1: Gameplay Video Region
            Positioned.fill(
              child: Video(
                controller: controller,
                controls: NoVideoControls,
                fit: BoxFit.cover,
              ),
            ),

            // Layer 2: Custom Layout Masking (Facecam Stack / PiP / Circle)
            if (layout == ClipLayoutMode.stack)
              Align(
                alignment: Alignment.topCenter,
                child: FractionallySizedBox(
                  heightFactor: topHeightRatio,
                  widthFactor: 1.0,
                  child: Container(
                    decoration: const BoxDecoration(
                      border: Border(bottom: BorderSide(color: Color(0xFF7C3AED), width: 2)),
                    ),
                    child: Video(
                      controller: controller,
                      controls: NoVideoControls,
                      fit: BoxFit.cover,
                    ),
                  ),
                ),
              ),

            // Layer 3: Hook Banner Badge Overlay
            if (activeHookText != null && activeHookText!.isNotEmpty)
              Positioned(
                top: 24,
                left: 16,
                right: 16,
                child: Center(
                  child: Container(
                    padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                    decoration: BoxDecoration(
                      color: const Color(0xFF7C3AED),
                      borderRadius: BorderRadius.circular(8),
                      boxShadow: [
                        BoxShadow(
                          color: const Color(0xFF7C3AED).withOpacity(0.6),
                          blurRadius: 16,
                        ),
                      ],
                    ),
                    child: Text(
                      activeHookText!,
                      textAlign: TextAlign.center,
                      style: const TextStyle(
                        fontFamily: 'Poppins',
                        fontWeight: FontWeight.w800,
                        fontSize: 18,
                        color: Colors.white,
                        letterSpacing: 0.5,
                      ),
                    ),
                  ),
                ),
              ),

            // Layer 4: Dynamic Subtitles
            if (activeCaptionText != null && activeCaptionText!.isNotEmpty)
              Positioned(
                bottom: 48,
                left: 16,
                right: 16,
                child: Text(
                  activeCaptionText!,
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    fontFamily: 'Poppins',
                    fontWeight: FontWeight.w900,
                    fontSize: 22,
                    color: const Color(0xFF00F3FF),
                    shadows: [
                      Shadow(
                        color: Colors.black.withOpacity(0.9),
                        offset: const Offset(2, 2),
                        blurRadius: 4,
                      ),
                    ],
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}
```

### 3.2 Multi-Touch Crop Box Controller (`InteractiveCropOverlay`)
Allows the user to drag and resize the Facecam (Cyan) and Gameplay (Purple) bounding boxes with magnetic snapping.

```dart
class CropBoxOverlay extends StatefulWidget {
  final Rect initialFacecam;
  final Rect initialGameplay;
  final Function(Rect facecam, Rect gameplay) onCropChanged;

  const CropBoxOverlay({
    super.key,
    required this.initialFacecam,
    required this.initialGameplay,
    required this.onCropChanged,
  });

  @override
  State<CropBoxOverlay> createState() => _CropBoxOverlayState();
}

class _CropBoxOverlayState extends State<CropBoxOverlay> {
  late Rect _facecam;
  late Rect _gameplay;
  int _activeBox = 0; // 0 = Facecam, 1 = Gameplay

  @override
  void initState() {
    super.initState();
    _facecam = widget.initialFacecam;
    _gameplay = widget.initialGameplay;
  }

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final w = constraints.maxWidth;
        final h = constraints.maxHeight;

        return Stack(
          children: [
            // Gameplay Box (Purple)
            _buildBox(
              rect: _gameplay,
              width: w,
              height: h,
              color: const Color(0xFF7C3AED),
              label: "GAMEPLAY BOX",
              isSelected: _activeBox == 1,
              onTap: () => setState(() => _activeBox = 1),
              onPanUpdate: (delta) {
                setState(() {
                  _gameplay = _clampRect(_gameplay.shift(Offset(delta.dx / w, delta.dy / h)));
                });
                widget.onCropChanged(_facecam, _gameplay);
              },
            ),

            // Facecam Box (Cyan)
            _buildBox(
              rect: _facecam,
              width: w,
              height: h,
              color: const Color(0xFF00F3FF),
              label: "FACECAM BOX",
              isSelected: _activeBox == 0,
              onTap: () => setState(() => _activeBox = 0),
              onPanUpdate: (delta) {
                setState(() {
                  _facecam = _clampRect(_facecam.shift(Offset(delta.dx / w, delta.dy / h)));
                });
                widget.onCropChanged(_facecam, _gameplay);
              },
            ),
          ],
        );
      },
    );
  }

  Rect _clampRect(Rect r) {
    double left = r.left.clamp(0.0, 1.0 - r.width);
    double top = r.top.clamp(0.0, 1.0 - r.height);
    return Rect.fromLTWH(left, top, r.width, r.height);
  }

  Widget _buildBox({
    required Rect rect,
    required double width,
    required double height,
    required Color color,
    required String label,
    required bool isSelected,
    required VoidCallback onTap,
    required Function(Offset) onPanUpdate,
  }) {
    return Positioned(
      left: rect.left * width,
      top: rect.top * height,
      width: rect.width * width,
      height: rect.height * height,
      child: GestureDetector(
        onTap: onTap,
        onPanUpdate: (details) => onPanUpdate(details.delta),
        child: Container(
          decoration: BoxDecoration(
            border: Border.all(
              color: color,
              width: isSelected ? 2.5 : 1.5,
            ),
            color: color.withOpacity(isSelected ? 0.18 : 0.08),
            borderRadius: BorderRadius.circular(4),
          ),
          child: Align(
            alignment: Alignment.topLeft,
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
              color: color,
              child: Text(
                label,
                style: const TextStyle(
                  color: Colors.black,
                  fontSize: 10,
                  fontWeight: FontWeight.bold,
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
```

### 3.3 Riverpod State Architecture & SSE Job Tracking

```dart
import 'dart:convert';
import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

// State model for export pipeline
class ClipJobState {
  final String jobId;
  final String status;
  final double progress;
  final String stage;
  final List<String> clipFiles;

  ClipJobState({
    required this.jobId,
    required this.status,
    required this.progress,
    required this.stage,
    required this.clipFiles,
  });

  ClipJobState.initial()
      : jobId = '',
        status = 'idle',
        progress = 0.0,
        stage = 'Ready',
        clipFiles = [];
}

class StudioNotifier extends StateNotifier<ClipJobState> {
  final Dio _dio;

  StudioNotifier(this._dio) : super(ClipJobState.initial());

  Future<void> startExport(Map<String, dynamic> exportPayload) async {
    state = ClipJobState(
      jobId: '',
      status: 'starting',
      progress: 0.02,
      stage: 'Submitting job to Clipiest engine...',
      clipFiles: [],
    );

    try {
      final res = await _dio.post('/api/clip', data: exportPayload);
      final jobId = res.data['job_id'];

      // Connect to Server-Sent Events (SSE) for live 0-100% progress
      _listenToJobProgress(jobId);
    } catch (e) {
      state = ClipJobState(
        jobId: '',
        status: 'error',
        progress: 0.0,
        stage: 'Failed: $e',
        clipFiles: [],
      );
    }
  }

  void _listenToJobProgress(String jobId) async {
    final response = await _dio.get<ResponseBody>(
      '/api/jobs/$jobId/events',
      options: Options(responseType: ResponseType.stream),
    );

    response.data?.stream
        .cast<List<int>>()
        .transform(utf8.decoder)
        .listen((line) {
      if (line.startsWith('data:')) {
        final rawJson = line.substring(5).trim();
        if (rawJson.isNotEmpty) {
          final data = jsonDecode(rawJson);
          state = ClipJobState(
            jobId: jobId,
            status: data['status'] ?? 'running',
            progress: (data['progress'] ?? 0.0).toDouble(),
            stage: data['stage'] ?? 'Processing...',
            clipFiles: List<String>.from(data['clips'] ?? []),
          );
        }
      }
    });
  }
}
```

---

## 4. Dependencies (`pubspec.yaml`)

```yaml
dependencies:
  flutter:
    sdk: flutter

  # State Management & Architecture
  flutter_riverpod: ^2.5.1
  riverpod_annotation: ^2.3.5

  # Video Engine & Audio
  media_kit: ^1.1.10
  media_kit_video: ^1.2.4

  # Networking & Real-Time Events
  dio: ^5.4.3+1
  fetch_client: ^1.6.0

  # Local Persistence & Caching
  drift: ^2.16.0
  shared_preferences: ^2.2.3
  cached_network_image: ^3.3.1

  # On-Device Intelligence & Touch
  google_mlkit_face_detection: ^0.10.0
  flutter_vibrate: ^1.3.0

  # UI & Animation
  google_fonts: ^6.2.1
  flutter_animate: ^4.5.0
```

---

## 5. Complete Flutter Project Structure

```
clipiest_flutter/
├── android/
├── ios/
├── assets/
│   ├── fonts/
│   │   ├── Poppins-ExtraBold.ttf
│   │   ├── Anton-Regular.ttf
│   │   └── ArchivoBlack-Regular.ttf
│   └── icons/
│       └── logo.svg
├── lib/
│   ├── main.dart
│   ├── app.dart
│   ├── core/
│   │   ├── constants/
│   │   │   ├── api_endpoints.dart
│   │   │   └── layout_catalog.dart     # 11 layouts geometry definition
│   │   ├── theme/
│   │   │   ├── colors.dart
│   │   │   └── typography.dart
│   │   └── network/
│   │       ├── api_client.dart
│   │       └── sse_client.dart
│   ├── data/
│   │   ├── models/
│   │   │   ├── clip_model.dart
│   │   │   ├── viral_moment_model.dart
│   │   │   └── word_timing_model.dart
│   │   └── repositories/
│   │       ├── studio_repo.dart
│   │       ├── moments_repo.dart
│   │       └── library_repo.dart
│   ├── logic/
│   │   ├── studio_provider.dart
│   │   ├── moments_provider.dart
│   │   └── reedit_provider.dart
│   └── presentation/
│       ├── navigation/
│       │   └── bottom_nav_shell.dart
│       ├── studio/
│       │   ├── studio_screen.dart
│       │   ├── widgets/
│       │   │   ├── clip_compositor.dart
│       │   │   ├── crop_overlay.dart
│       │   │   ├── storyboard_scrub_bar.dart
│       │   │   └── layout_selector.dart
│       ├── moments/
│       │   ├── moments_screen.dart
│       │   └── widgets/
│       │       └── viral_moment_card.dart
│       ├── reedit/
│       │   ├── reedit_screen.dart
│       │   └── widgets/
│       │       └── word_chip_editor.dart
│       └── library/
│           ├── library_screen.dart
│           └── widgets/
│               └── vertical_clip_player.dart
```

---

## 6. Implementation Roadmap
1. **Phase 1**: Setup project, theming, `media_kit` hardware player integration, and REST/SSE networking.
2. **Phase 2**: Implement `ClipCompositorWidget` and `CropBoxOverlay` with 11 layout geometries.
3. **Phase 3**: Build Storyboard scrubbing bar with excitation waveform and viral moment cards.
4. **Phase 4**: Add word-level Re-Edit studio and TikTok-style Library player.
5. **Phase 5**: Build and publish to Google Play Store & Apple App Store.
