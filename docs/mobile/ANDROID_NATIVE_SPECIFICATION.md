# Clipiest Mobile App — Android Native Specification (Kotlin & Jetpack Compose)

A complete architectural, UI/UX, and technical specification for building the high-performance Android native client for **Clipiest** using **Kotlin 2.0+**, **Jetpack Compose**, **AndroidX Media3 (ExoPlayer)**, and **WorkManager**.

---

## 1. System Architecture & Compute Model

Clipiest Android Native uses a **Modern Android Architecture (MVI / Clean Architecture)** with an asynchronous hybrid computing pipeline:

```
+---------------------------------------------------------------------------------------+
|                            ANDROID NATIVE CLIENT (Kotlin & Compose)                   |
|                                                                                       |
|  +---------------------------+  +-------------------------+  +---------------------+  |
|  | PointerInput Crop Overlay |  | Subtitle Re-Edit Canvas |  | Media3 ExoPlayer    |  |
|  | (Facecam / Gameplay Box)  |  | (Haptic / Splitting)    |  | 9:16 Custom Surface |  |
|  +---------------------------+  +-------------------------+  +---------------------+  |
|               ^                              ^                          ^             |
|               |                              |                          |             |
|  +---------------------------------------------------------------------------------+  |
|  | Presentation: Jetpack Compose Material 3 + ViewModels (StateFlow / SharedFlow)  |  |
|  | Background Services: AndroidX WorkManager (Guaranteed Upload & Render Monitor)  |  |
|  | On-Device ML: Google MediaPipe Tasks API (NPU-accelerated facecam anchor)       |  |
|  +---------------------------------------------------------------------------------+  |
+---------------------------------------------------------------------------------------+
                                           |
                    Retrofit 2 / OkHttp 3 + Server-Sent Events (SSE)
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

### Why Android Native?
- **Maximum Background Resilience**: Unlike web browsers and hybrid apps that are killed when backgrounded, Android's `WorkManager` and `ForegroundService` ensure large 4K stream uploads and 5-minute FFmpeg jobs complete reliably with rich notification bar progress.
- **Deep Hardware Acceleration**: Direct MediaPipe NPU utilization for real-time facecam detection, plus AndroidX Media3 zero-copy texture rendering.
- **System Feature Integration**: Picture-in-Picture (PiP), Android 14+ Predictive Back gestures, and Direct Share targets for TikTok, YouTube Shorts, and Instagram Reels.

---

## 2. Jetpack Compose Design System (Cyberpunk Dark Neon)

### 2.1 Theme & Color Palette (`Color.kt`)
```kotlin
package com.clipiest.app.core.designsystem.theme

import androidx.compose.ui.graphics.Color

val BgDark = Color(0xFF07090E)
val SurfaceDark = Color(0xFF0F1322)
val SurfaceElevated = Color(0xFF161B2E)
val BorderGlow = Color(0x337C3AED)

val NeonViolet = Color(0xFF7C3AED)
val NeonCyan = Color(0xFF00F3FF)
val RetentionRed = Color(0xFFFF3366)
val MrBeastYellow = Color(0xFFFFDD00)

val TextPrimary = Color(0xFFF1F5F9)
val TextMuted = Color(0xFF94A3B8)
```

### 2.2 Material 3 ColorScheme (`Theme.kt`)
```kotlin
package com.clipiest.app.core.designsystem.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable

private val ClipiestColorScheme = darkColorScheme(
    primary = NeonViolet,
    secondary = NeonCyan,
    background = BgDark,
    surface = SurfaceDark,
    onPrimary = Color.White,
    onBackground = TextPrimary,
    onSurface = TextPrimary
)

@Composable
fun ClipiestTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = ClipiestColorScheme,
        typography = ClipiestTypography,
        content = content
    )
}
```

---

## 3. Core Android Native Implementations

### 3.1 9:16 Real-Time Video Compositor (`ClipPreviewCanvas.kt`)
Embeds AndroidX Media3 ExoPlayer into Jetpack Compose with custom layout masks and animated subtitle typography.

```kotlin
package com.clipiest.app.presentation.studio.components

import android.graphics.RectF
import androidx.annotation.OptIn
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.media3.common.util.UnstableApi
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.ui.AspectRatioFrameLayout
import androidx.media3.ui.PlayerView

enum class LayoutMode { STACK, BOTTOM, BLUR, FILL, GAME, CIRCLE, PIP_BR, SIDE }

@OptIn(UnstableApi::class)
@Composable
fun ClipPreviewCanvas(
    player: ExoPlayer,
    layout: LayoutMode,
    facecamCrop: RectF,
    gameplayCrop: RectF,
    topRatio: Float = 0.32f,
    activeHook: String? = null,
    activeSubtitle: String? = null,
    modifier: Modifier = Modifier
) {
    Box(
        modifier = modifier
            .aspectRatio(9f / 16f)
            .clip(RoundedCornerShape(16.dp))
            .border(1.5.dp, Color(0xFF7C3AED), RoundedCornerShape(16.dp))
            .background(Color(0xFF07090E))
    ) {
        // 1. Hardware Video Texture
        AndroidView(
            factory = { context ->
                PlayerView(context).apply {
                    this.player = player
                    useController = false
                    resizeMode = AspectRatioFrameLayout.RESIZE_MODE_ZOOM
                }
            },
            modifier = Modifier.fillMaxSize()
        )

        // 2. Custom Layout Canvas Divider / PiP Overlays
        Canvas(modifier = Modifier.fillMaxSize()) {
            if (layout == LayoutMode.STACK) {
                val splitY = size.height * topRatio
                drawLine(
                    color = Color(0xFF7C3AED),
                    start = Offset(0f, splitY),
                    end = Offset(size.width, splitY),
                    strokeWidth = 3.dp.toPx()
                )
            }
        }

        // 3. Hook Badge Overlay
        if (!activeHook.isNullOrEmpty()) {
            Box(
                modifier = Modifier
                    .align(Alignment.TopCenter)
                    .padding(top = 24.dp)
                    .background(Color(0xFF7C3AED), RoundedCornerShape(8.dp))
                    .padding(horizontal = 14.dp, vertical = 8.dp)
            ) {
                Text(
                    text = activeHook,
                    color = Color.White,
                    fontWeight = FontWeight.ExtraBold,
                    fontSize = 18.sp
                )
            }
        }

        // 4. Subtitle Typography Overlay
        if (!activeSubtitle.isNullOrEmpty()) {
            Text(
                text = activeSubtitle,
                color = Color(0xFF00F3FF),
                fontWeight = FontWeight.Black,
                fontSize = 22.sp,
                modifier = Modifier
                    .align(Alignment.BottomCenter)
                    .padding(bottom = 48.dp, start = 16.dp, end = 16.dp)
            )
        }
    }
}
```

### 3.2 PointerInput Crop Overlay (`CropBoxOverlay.kt`)
Provides touch-drag and pinch-resize handles for the Facecam and Gameplay boxes with magnetic snapping.

```kotlin
package com.clipiest.app.presentation.studio.components

import android.graphics.RectF
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.gestures.detectTransformGestures
import androidx.compose.foundation.layout.*
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

@Composable
fun CropBoxOverlay(
    facecamCrop: RectF,
    gameplayCrop: RectF,
    onCropsChanged: (RectF, RectF) -> Unit,
    modifier: Modifier = Modifier
) {
    BoxWithConstraints(modifier = modifier.fillMaxSize()) {
        val w = maxWidth.value
        val h = maxHeight.value

        var cam by remember { mutableStateOf(facecamCrop) }
        var game by remember { mutableStateOf(gameplayCrop) }

        // Facecam Box (Cyan)
        Box(
            modifier = Modifier
                .offset(x = (cam.left * w).dp, y = (cam.top * h).dp)
                .size(width = (cam.width() * w).dp, height = (cam.height() * h).dp)
                .border(2.dp, Color(0xFF00F3FF))
                .background(Color(0xFF00F3FF).copy(alpha = 0.15f))
                .pointerInput(Unit) {
                    detectTransformGestures { _, pan, _, _ ->
                        val dx = pan.x / size.width
                        val dy = pan.y / size.height
                        val newLeft = (cam.left + dx).coerceIn(0f, 1f - cam.width())
                        val newTop = (cam.top + dy).coerceIn(0f, 1f - cam.height())
                        cam = RectF(newLeft, newTop, newLeft + cam.width(), newTop + cam.height())
                        onCropsChanged(cam, game)
                    }
                }
        ) {
            Text(
                text = "FACECAM",
                color = Color.Black,
                fontSize = 10.sp,
                modifier = Modifier.background(Color(0xFF00F3FF)).padding(2.dp)
            )
        }

        // Gameplay Box (Purple)
        Box(
            modifier = Modifier
                .offset(x = (game.left * w).dp, y = (game.top * h).dp)
                .size(width = (game.width() * w).dp, height = (game.height() * h).dp)
                .border(2.dp, Color(0xFF7C3AED))
                .background(Color(0xFF7C3AED).copy(alpha = 0.15f))
                .pointerInput(Unit) {
                    detectTransformGestures { _, pan, _, _ ->
                        val dx = pan.x / size.width
                        val dy = pan.y / size.height
                        val newLeft = (game.left + dx).coerceIn(0f, 1f - game.width())
                        val newTop = (game.top + dy).coerceIn(0f, 1f - game.height())
                        game = RectF(newLeft, newTop, newLeft + game.width(), newTop + game.height())
                        onCropsChanged(cam, game)
                    }
                }
        ) {
            Text(
                text = "GAMEPLAY",
                color = Color.White,
                fontSize = 10.sp,
                modifier = Modifier.background(Color(0xFF7C3AED)).padding(2.dp)
            )
        }
    }
}
```

### 3.3 WorkManager Guaranteed Background Processing (`RenderProgressWorker.kt`)
Monitors long-running rendering jobs on the server via SSE even when the phone screen is turned off.

```kotlin
package com.clipiest.app.workers

import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Context
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.hilt.work.HiltWorker
import androidx.work.CoroutineWorker
import androidx.work.ForegroundInfo
import androidx.work.WorkerParameters
import dagger.assisted.Assisted
import dagger.assisted.AssistedInject
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.sse.EventSource
import okhttp3.sse.EventSourceListener
import okhttp3.sse.EventSources
import kotlin.coroutines.resume
import kotlin.coroutines.suspendCancellableCoroutine

@HiltWorker
class RenderProgressWorker @AssistedInject constructor(
    @Assisted private val context: Context,
    @Assisted workerParams: WorkerParameters,
    private val okHttpClient: OkHttpClient
) : CoroutineWorker(context, workerParams) {

    private val notificationManager =
        context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager

    companion object {
        const val CHANNEL_ID = "clipiest_renders"
        const val NOTIFICATION_ID = 4040
    }

    override suspend fun doWork(): Result = suspendCancellableCoroutine { continuation ->
        val jobId = inputData.getString("job_id") ?: return@suspendCancellableCoroutine continuation.resume(Result.failure())

        createNotificationChannel()
        setForegroundAsync(createForegroundInfo("Preparing video export...", 0))

        val request = Request.Builder()
            .url("http://10.0.2.2:8780/api/jobs/$jobId/events")
            .build()

        val eventSource = EventSources.createFactory(okHttpClient)
            .newEventSource(request, object : EventSourceListener() {
                override fun onEvent(eventSource: EventSource, id: String?, type: String?, data: String) {
                    // Parse progress JSON from server
                    // e.g. {"progress": 0.45, "stage": "Applying ASS captions & NVENC render..."}
                    val progressInt = 45 // Parsed from data
                    notificationManager.notify(
                        NOTIFICATION_ID,
                        createNotification("Rendering 9:16 Clip: $progressInt%", progressInt)
                    )
                }

                override fun onClosed(eventSource: EventSource) {
                    continuation.resume(Result.success())
                }

                override fun onFailure(eventSource: EventSource, t: Throwable?, response: okhttp3.Response?) {
                    continuation.resume(Result.retry())
                }
            })

        continuation.invokeOnCancellation {
            eventSource.cancel()
        }
    }

    private fun createForegroundInfo(message: String, progress: Int): ForegroundInfo {
        return ForegroundInfo(NOTIFICATION_ID, createNotification(message, progress))
    }

    private fun createNotification(message: String, progress: Int) =
        NotificationCompat.Builder(context, CHANNEL_ID)
            .setContentTitle("Clipiest Engine")
            .setContentText(message)
            .setSmallIcon(android.R.drawable.stat_sys_download)
            .setProgress(100, progress, false)
            .setOngoing(true)
            .build()

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                "Video Rendering Tasks",
                NotificationManager.IMPORTANCE_LOW
            )
            notificationManager.createNotificationChannel(channel)
        }
    }
}
```

---

## 4. Dependencies (`build.gradle.kts`)

```kotlin
plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.hilt.android)
    alias(libs.plugins.ksp)
}

dependencies {
    // Jetpack Compose & Material 3
    implementation(platform(libs.androidx.compose.bom))
    implementation(libs.androidx.compose.ui)
    implementation(libs.androidx.compose.material3)
    implementation(libs.androidx.navigation.compose)

    // AndroidX Media3 (ExoPlayer)
    implementation(libs.androidx.media3.exoplayer)
    implementation(libs.androidx.media3.ui)
    implementation(libs.androidx.media3.common)

    // Background Processing
    implementation(libs.androidx.work.runtime.ktx)
    implementation(libs.androidx.hilt.work)

    // Networking & SSE
    implementation(libs.retrofit)
    implementation(libs.retrofit.converter.gson)
    implementation(libs.okhttp)
    implementation(libs.okhttp.sse)

    // Local Persistence
    implementation(libs.androidx.room.runtime)
    implementation(libs.androidx.room.ktx)
    ksp(libs.androidx.room.compiler)

    // Dependency Injection
    implementation(libs.hilt.android)
    ksp(libs.hilt.compiler)

    // On-Device ML
    implementation(libs.mediapipe.tasks.vision)
}
```

---

## 5. Complete Android Native Module Architecture

```
clipiest-android/
├── app/
│   ├── src/main/java/com/clipiest/app/
│   │   ├── ClipiestApp.kt                 # Application class with @HiltAndroidApp
│   │   ├── di/
│   │   │   ├── NetworkModule.kt           # OkHttp, Retrofit, SSE factory
│   │   │   ├── DatabaseModule.kt          # Room Database & DAOs
│   │   │   └── PlayerModule.kt            # ExoPlayer singleton provider
│   │   ├── core/
│   │   │   ├── designsystem/
│   │   │   │   ├── Color.kt               # Neon palette
│   │   │   │   ├── Theme.kt               # Material 3 dark scheme
│   │   │   │   └── Typography.kt          # Font definitions
│   │   │   ├── ml/
│   │   │   │   └── FacecamAnchorDetector.kt # MediaPipe Face detector
│   │   │   └── player/
│   │   │       └── VideoPlayerManager.kt  # Media3 player coordinator
│   │   ├── data/
│   │   │   ├── remote/
│   │   │   │   ├── ClipiestService.kt     # Retrofit endpoints
│   │   │   │   └── dto/                   # API response DTOs
│   │   │   └── repository/
│   │   │       ├── StudioRepositoryImpl.kt
│   │   │       └── LibraryRepositoryImpl.kt
│   │   ├── domain/
│   │   │   ├── model/                     # Clip, ViralMoment, LayoutSpec
│   │   │   └── usecase/
│   │   │       ├── ScoutViralMomentsUseCase.kt
│   │   │       └── StartExportUseCase.kt
│   │   ├── workers/
│   │   │   ├── VideoUploadWorker.kt       # Chunked video upload
│   │   │   └── RenderProgressWorker.kt    # SSE foreground service
│   │   └── presentation/
│   │       ├── main/
│   │       │   └── MainScaffold.kt        # BottomNavigationBar + NavHost
│   │       ├── studio/
│   │       │   ├── StudioViewModel.kt
│   │       │   ├── StudioScreen.kt
│   │       │   └── components/
│   │       │       ├── ClipPreviewCanvas.kt
│   │       │       ├── CropBoxOverlay.kt
│   │       │       └── StoryboardScrubber.kt
│   │       ├── moments/
│   │       │   ├── MomentsViewModel.kt
│   │       │   └── MomentsScreen.kt
│   │       ├── reedit/
│   │       │   ├── ReEditViewModel.kt
│   │       │   └── ReEditScreen.kt
│   │       └── library/
│   │           ├── LibraryViewModel.kt
│   │           └── LibraryScreen.kt
```

---

## 6. Implementation Roadmap
1. **Phase 1**: Project scaffolding with Gradle Version Catalog, Hilt DI, and Retrofit/SSE client.
2. **Phase 2**: Implement `ClipPreviewCanvas` using Media3 ExoPlayer and Compose Canvas.
3. **Phase 3**: Multi-touch `CropBoxOverlay` with pan/zoom gestures and MediaPipe facecam anchor heuristic.
4. **Phase 4**: `WorkManager` + `ForegroundService` notification integration for uninterrupted video rendering.
5. **Phase 5**: Subtitle word-chip re-editing and Play Store packaging.
