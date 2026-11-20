/**
 * Clipiest — Frontend Master Application
 */
const $ = (id) => document.getElementById(id);

// Application State
const appState = {
  currentTab: 'create',
  sourceId: null,
  sourceUrl: '',
  sourceWidth: 0,
  sourceHeight: 0,
  duration: 0,
  activeTool: 'cam', // 'cam' | 'game'
  layout: 'stack',
  layoutsCatalog: [],
  captionStyle: 'bounce',
  captionStylesList: [],
  topH: 0.32,
  rect: {
    cam: { x: 0.0, y: 0.0, w: 0.25, h: 0.30 },
    game: { x: 0.25, y: 0.0, w: 0.75, h: 1.0 }
  },
  dragInfo: null,
  activeJobId: null,
  pollTimer: null,
  liveSessionId: null,
  livePollTimer: null,
  currentImageSource: null
};

// Canvas references
const sourceCanvas = $('source-canvas');
const sourceCtx = sourceCanvas.getContext('2d');
const previewCanvas = $('preview-canvas');
const previewCtx = previewCanvas.getContext('2d');
const sourceVideo = $('source-video');

// Presets
const PRESETS = {
  tl: { cam: { x: 0.0, y: 0.0, w: 0.25, h: 0.32 }, game: { x: 0.25, y: 0.0, w: 0.75, h: 1.0 } },
  tr: { cam: { x: 0.75, y: 0.0, w: 0.25, h: 0.32 }, game: { x: 0.0, y: 0.0, w: 0.75, h: 1.0 } },
  bl: { cam: { x: 0.0, y: 0.68, w: 0.25, h: 0.32 }, game: { x: 0.25, y: 0.0, w: 0.75, h: 1.0 } },
  br: { cam: { x: 0.75, y: 0.68, w: 0.25, h: 0.32 }, game: { x: 0.0, y: 0.0, w: 0.75, h: 1.0 } },
  bc: { cam: { x: 0.37, y: 0.68, w: 0.26, h: 0.32 }, game: { x: 0.0, y: 0.0, w: 1.0, h: 0.68 } }
};

// API Helper
async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || err.error || 'Request failed');
  }
  return res.json();
}

// -------------------------------------------------------------
// Initialization
// -------------------------------------------------------------
async function init() {
  setupNavigation();
  setupCanvasEvents();
  setupControls();
  
  await Promise.all([
    loadLayouts(),
    loadCaptionStyles(),
    updateTelemetry(),
    loadLibrary()
  ]);

  setInterval(updateTelemetry, 5000);
  requestAnimationFrame(renderLoop);
}

// -------------------------------------------------------------
// Navigation & Tabs
// -------------------------------------------------------------
function setupNavigation() {
  document.querySelectorAll('.nav-item').forEach(btn => {
    btn.onclick = () => {
      document.querySelectorAll('.nav-item').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
      
      btn.classList.add('active');
      const tabId = 'tab-' + btn.dataset.tab;
      $(tabId).classList.add('active');
      appState.currentTab = btn.dataset.tab;

      if (btn.dataset.tab === 'library') {
        loadLibrary();
      }
    };
  });

  $('open-folder-btn').onclick = async () => {
    try {
      await api('/api/open-folder');
    } catch (e) {
      alert('Could not open folder: ' + e.message);
    }
  };
}

// -------------------------------------------------------------
// Telemetry & Hardware Status
// -------------------------------------------------------------
async function updateTelemetry() {
  try {
    const data = await api('/api/telemetry');
    $('stat-cpu').textContent = data.cpu_percent + '%';
    $('stat-ram').textContent = data.ram_percent + '%';
    $('stat-disk').textContent = data.disk.free_gb + ' GB';
    $('sys-pill').textContent = `${data.cpu_percent}% / ${data.ram_percent}%`;

    const hw = data.hardware || {};
    $('stat-nvenc').textContent = hw.nvenc ? 'Available (Active)' : 'Not detected';
    $('stat-qsv').textContent = hw.qsv ? 'Available' : 'Not detected';
    $('stat-whisper').textContent = hw.whisper_model || 'faster-whisper';
    $('gpu-pill').textContent = hw.nvenc ? 'NVENC ON' : (hw.qsv ? 'QSV ON' : 'CPU');

    $('stat-ai-provider').textContent = hw.ai_provider?.toUpperCase() || 'GEMINI';
    $('stat-ai-models').textContent = (hw.ai_models || []).join(', ');
    $('ai-pill').textContent = hw.ai_provider?.toUpperCase() || 'GEMINI';

    // Weights display
    loadWeights();
  } catch (e) {
    console.warn('Telemetry error:', e);
  }
}

async function loadWeights() {
  try {
    const data = await api('/api/feedback', { method: 'POST', body: JSON.stringify({ rating: 0 }) });
    const weights = data.weights || {};
    const container = $('weights-display');
    if (!container) return;
    container.innerHTML = Object.entries(weights)
      .map(([k, v]) => `<div class="weight-pill"><span>${k}:</span> <b>${Number(v).toFixed(3)}</b></div>`)
      .join('');
  } catch (_) {}
}

// -------------------------------------------------------------
// Layouts & Styling Cards
// -------------------------------------------------------------
async function loadLayouts() {
  const layouts = await api('/api/layouts?top=' + appState.topH);
  appState.layoutsCatalog = layouts;
  const container = $('layouts-grid');
  container.innerHTML = '';

  layouts.forEach(l => {
    const card = document.createElement('div');
    card.className = `layout-card ${l.id === appState.layout ? 'active' : ''}`;
    card.dataset.layout = l.id;

    // Mini wireframe
    let miniContent = '';
    if (l.mode === 'blur') {
      miniContent = `<div class="layout-blur-bg"></div><div class="layout-blur-inset"></div>`;
    } else {
      miniContent = (l.layers || []).map(layer => {
        const isCircle = layer.circle ? 'layer-circle' : '';
        const srcCls = layer.source === 'cam' ? 'layer-cam' : 'layer-game';
        const left = (layer.x / 1080 * 100).toFixed(1) + '%';
        const top = (layer.y / 1920 * 100).toFixed(1) + '%';
        const width = (layer.w / 1080 * 100).toFixed(1) + '%';
        const height = (layer.h / 1920 * 100).toFixed(1) + '%';
        return `<div class="layout-layer ${srcCls} ${isCircle}" style="left:${left};top:${top};width:${width};height:${height};"></div>`;
      }).join('');
    }

    card.innerHTML = `
      <div class="layout-mini">${miniContent}</div>
      <b>${l.name}</b>
      <small>${l.description}</small>
    `;

    card.onclick = () => {
      document.querySelectorAll('.layout-card').forEach(c => c.classList.remove('active'));
      card.classList.add('active');
      appState.layout = l.id;
      $('top-h-field').hidden = ['blur', 'fill', 'game'].includes(l.id);
    };

    container.appendChild(card);
  });
}

async function loadCaptionStyles() {
  const styles = await api('/api/caption-styles');
  appState.captionStylesList = styles;
  const container = $('styles-grid');
  container.innerHTML = '';

  styles.forEach(s => {
    const card = document.createElement('div');
    card.className = `style-card ${s.id === appState.captionStyle ? 'active' : ''}`;
    card.dataset.style = s.id;
    card.innerHTML = `
      <div class="style-preview-text" style="color:${s.color}">SAMPLE TEXT</div>
      <b>${s.name}</b>
    `;
    card.onclick = () => {
      document.querySelectorAll('.style-card').forEach(c => c.classList.remove('active'));
      card.classList.add('active');
      appState.captionStyle = s.id;
    };
    container.appendChild(card);
  });
}

// -------------------------------------------------------------
// Video Import & Previews
// -------------------------------------------------------------
function setupControls() {
  // Preset Chips
  document.querySelectorAll('[data-preset]').forEach(chip => {
    chip.onclick = () => {
      document.querySelectorAll('[data-preset]').forEach(c => c.classList.remove('active'));
      chip.classList.add('active');
      const p = chip.dataset.preset;
      if (p === 'none') {
        appState.layout = 'blur';
        document.querySelector('[data-layout="blur"]')?.click();
      } else if (PRESETS[p]) {
        appState.rect = JSON.parse(JSON.stringify(PRESETS[p]));
        document.querySelector('[data-layout="stack"]')?.click();
      }
    };
  });

  // Tools toggle (Cam vs Game)
  $('tool-cam').onclick = () => {
    appState.activeTool = 'cam';
    $('tool-cam').classList.add('active');
    $('tool-game').classList.remove('active');
  };
  $('tool-game').onclick = () => {
    appState.activeTool = 'game';
    $('tool-game').classList.add('active');
    $('tool-cam').classList.remove('active');
  };

  // Facecam height slider
  $('top-h-slider').oninput = (e) => {
    appState.topH = Number(e.target.value) / 100;
    $('top-h-val').textContent = e.target.value + '%';
    loadLayouts();
  };

  // Upload trigger
  $('browse-btn').onclick = () => $('file-input').click();
  $('upload-zone').ondragover = (e) => { e.preventDefault(); $('upload-zone').style.borderColor = 'var(--primary)'; };
  $('upload-zone').ondragleave = () => { $('upload-zone').style.borderColor = 'var(--border)'; };
  $('upload-zone').ondrop = (e) => {
    e.preventDefault();
    $('upload-zone').style.borderColor = 'var(--border)';
    if (e.dataTransfer.files?.length) {
      handleFileUpload(e.dataTransfer.files[0]);
    }
  };
  $('file-input').onchange = (e) => {
    if (e.target.files?.length) {
      handleFileUpload(e.target.files[0]);
    }
  };

  // Preview button
  $('preview-btn').onclick = async () => {
    const url = $('video-url').value.trim();
    if (!url) return alert('Enter a video URL first.');
    $('import-status').hidden = false;
    $('import-status').textContent = 'Fetching video information...';
    try {
      // Create quick pipeline job to fetch metadata
      appState.sourceUrl = url;
      $('import-status').textContent = 'Link set. Ready to process clips.';
      $('source-status-badge').textContent = 'URL Linked';
    } catch (e) {
      $('import-status').textContent = 'Error: ' + e.message;
    }
  };

  // Auto-Detect Facecam
  $('autocam-btn').onclick = async () => {
    if (!appState.sourceId) {
      return alert('Upload a video or link a source to run automatic facecam detection.');
    }
    try {
      $('autocam-btn').textContent = 'Scanning frames...';
      const res = await api(`/preview/${appState.sourceId}/autocam`, { method: 'POST' });
      if (res.detected && res.box) {
        appState.rect.cam = res.box;
        alert(`Facecam detected with ${(res.confidence * 100).toFixed(0)}% confidence!`);
      } else {
        alert('No static facecam region detected in video.');
      }
    } catch (e) {
      alert('Detection failed: ' + e.message);
    } finally {
      $('autocam-btn').textContent = '✦ Auto-Detect Facecam (CV)';
    }
  };

  // Make Clips Trigger
  $('make-btn').onclick = triggerMakeClips;
  $('make-btn-bottom').onclick = triggerMakeClips;

  // Manual Export Trigger
  $('manual-export-btn').onclick = triggerManualExport;

  // Live Stream Controls
  $('live-start-btn').onclick = startLiveStream;
  $('live-stop-btn').onclick = stopLiveStream;
  $('clip-30s-btn').onclick = () => instantLiveClip(30);
  $('clip-60s-btn').onclick = () => instantLiveClip(60);

  // Refresh Library Button
  $('refresh-lib-btn').onclick = loadLibrary;
}

async function handleFileUpload(file) {
  const formData = new FormData();
  formData.append('file', file);
  $('import-status').hidden = false;
  $('import-status').textContent = 'Uploading video file...';

  try {
    const res = await fetch('/upload', { method: 'POST', body: formData });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Upload failed');

    appState.sourceId = data.id;
    appState.sourceWidth = data.w;
    appState.sourceHeight = data.h;
    appState.duration = data.duration;

    $('time-end').value = Math.min(30, data.duration);
    $('source-status-badge').textContent = `${data.w}x${data.h} · ${(data.duration).toFixed(1)}s`;
    $('import-status').textContent = 'Upload complete!';
    $('canvas-placeholder').hidden = true;

    // Load storyboard frames
    loadStoryboard(data.id);
  } catch (e) {
    $('import-status').textContent = 'Upload error: ' + e.message;
  }
}

async function loadStoryboard(sourceId) {
  try {
    const sb = await api(`/preview/${sourceId}/storyboard`);
    if (sb.frames?.length) {
      $('storyboard-reel').hidden = false;
      const reel = $('reel-frames');
      reel.innerHTML = '';
      sb.frames.forEach((frameFile, idx) => {
        const btn = document.createElement('button');
        btn.className = `reel-frame-btn ${idx === 0 ? 'active' : ''}`;
        btn.innerHTML = `<img src="/media/${frameFile}" alt="Frame">`;
        btn.onclick = () => {
          document.querySelectorAll('.reel-frame-btn').forEach(b => b.classList.remove('active'));
          btn.classList.add('active');
          const img = new Image();
          img.src = `/media/${frameFile}`;
          img.onload = () => { appState.currentImageSource = img; };
        };
        reel.appendChild(btn);
        if (idx === 0) {
          const img = new Image();
          img.src = `/media/${frameFile}`;
          img.onload = () => { appState.currentImageSource = img; };
        }
      });
    }
  } catch (_) {}
}

// -------------------------------------------------------------
// Interactive Canvas Drawing & Dragging
// -------------------------------------------------------------
function setupCanvasEvents() {
  function getCanvasCoords(e) {
    const rect = sourceCanvas.getBoundingClientRect();
    return {
      x: Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width)),
      y: Math.max(0, Math.min(1, (e.clientY - rect.top) / rect.height))
    };
  }

  sourceCanvas.onpointerdown = (e) => {
    appState.dragInfo = getCanvasCoords(e);
    sourceCanvas.setPointerCapture(e.pointerId);
  };

  sourceCanvas.onpointermove = (e) => {
    if (!appState.dragInfo) return;
    const cur = getCanvasCoords(e);
    const box = appState.rect[appState.activeTool];
    box.x = Math.min(cur.x, appState.dragInfo.x);
    box.y = Math.min(cur.y, appState.dragInfo.y);
    box.w = Math.max(0.02, Math.abs(cur.x - appState.dragInfo.x));
    box.h = Math.max(0.02, Math.abs(cur.y - appState.dragInfo.y));
  };

  sourceCanvas.onpointerup = () => { appState.dragInfo = null; };
  sourceCanvas.onpointercancel = () => { appState.dragInfo = null; };
}

function renderLoop() {
  // 1. Draw Source Canvas
  sourceCtx.fillStyle = '#000';
  sourceCtx.fillRect(0, 0, sourceCanvas.width, sourceCanvas.height);

  if (appState.currentImageSource) {
    sourceCtx.drawImage(appState.currentImageSource, 0, 0, sourceCanvas.width, sourceCanvas.height);
  }

  // Draw crop rectangles
  const cw = sourceCanvas.width;
  const ch = sourceCanvas.height;

  // Gameplay box (Cyan)
  const g = appState.rect.game;
  sourceCtx.strokeStyle = '#06b6d4';
  sourceCtx.lineWidth = 3;
  sourceCtx.strokeRect(g.x * cw, g.y * ch, g.w * cw, g.h * ch);
  sourceCtx.fillStyle = 'rgba(6, 182, 212, 0.15)';
  sourceCtx.fillRect(g.x * cw, g.y * ch, g.w * cw, g.h * ch);

  // Facecam box (Magenta)
  const c = appState.rect.cam;
  sourceCtx.strokeStyle = '#ec4899';
  sourceCtx.lineWidth = 3;
  sourceCtx.strokeRect(c.x * cw, c.y * ch, c.w * cw, c.h * ch);
  sourceCtx.fillStyle = 'rgba(236, 72, 153, 0.2)';
  sourceCtx.fillRect(c.x * cw, c.y * ch, c.w * cw, c.h * ch);

  // 2. Draw 9:16 Vertical Phone Simulator
  drawPhonePreview();

  requestAnimationFrame(renderLoop);
}

function drawPhonePreview() {
  const pw = previewCanvas.width;  // 540
  const ph = previewCanvas.height; // 960

  previewCtx.fillStyle = '#000';
  previewCtx.fillRect(0, 0, pw, ph);

  const spec = appState.layoutsCatalog.find(l => l.id === appState.layout);
  if (!spec || !appState.currentImageSource) {
    // Placeholder pattern
    previewCtx.fillStyle = '#1e2238';
    previewCtx.fillRect(0, 0, pw, ph);
  } else if (spec.mode === 'blur') {
    previewCtx.save();
    previewCtx.filter = 'blur(12px)';
    previewCtx.drawImage(appState.currentImageSource, -20, -20, pw + 40, ph + 40);
    previewCtx.restore();

    // Center sharp inset
    const ratio = Math.min(pw / appState.currentImageSource.naturalWidth, ph / appState.currentImageSource.naturalHeight);
    const w = appState.currentImageSource.naturalWidth * ratio;
    const h = appState.currentImageSource.naturalHeight * ratio;
    previewCtx.drawImage(appState.currentImageSource, (pw - w) / 2, (ph - h) / 2, w, h);
  } else {
    // Draw stacked or pip layers
    for (const layer of spec.layers || []) {
      previewCtx.save();
      const lx = layer.x / 2;
      const ly = layer.y / 2;
      const lw = layer.w / 2;
      const lh = layer.h / 2;

      if (layer.circle) {
        previewCtx.beginPath();
        previewCtx.arc(lx + lw / 2, ly + lh / 2, Math.min(lw, lh) / 2, 0, Math.PI * 2);
        previewCtx.clip();
      }

      const box = layer.source === 'cam' ? appState.rect.cam : appState.rect.game;
      const img = appState.currentImageSource;
      const sx = box.x * img.naturalWidth;
      const sy = box.y * img.naturalHeight;
      const sw = box.w * img.naturalWidth;
      const sh = box.h * img.naturalHeight;

      previewCtx.drawImage(img, sx, sy, sw, sh, lx, ly, lw, lh);
      previewCtx.restore();
    }
  }

  // Safe zones overlay
  if ($('safe-zones-chk').checked) {
    previewCtx.fillStyle = 'rgba(236, 72, 153, 0.2)';
    previewCtx.fillRect(0, 0, pw, 48);          // Top status bar
    previewCtx.fillRect(0, 840, pw, 120);        // Bottom controls & caption
    previewCtx.fillRect(470, 250, 70, 590);      // Right engagement icons
  }

  // Draw Sample Subtitles
  const hook = $('hook-input').value.trim();
  if (hook) {
    previewCtx.save();
    previewCtx.fillStyle = '#ffcc00';
    previewCtx.font = 'bold 24px Plus Jakarta Sans';
    previewCtx.textAlign = 'center';
    previewCtx.fillText(hook, pw / 2, 100);
    previewCtx.restore();
  }

  const subY = Number($('caption-y-slider').value) / 2;
  previewCtx.save();
  previewCtx.textAlign = 'center';
  previewCtx.font = '900 32px Plus Jakarta Sans';
  previewCtx.lineWidth = 6;
  previewCtx.strokeStyle = '#000';
  previewCtx.strokeText('CLIPIEST AI MOMENT', pw / 2, subY);
  previewCtx.fillStyle = '#fff';
  previewCtx.fillText('CLIPIEST AI MOMENT', pw / 2, subY);
  previewCtx.restore();
}

// -------------------------------------------------------------
// Clip Creation Pipeline
// -------------------------------------------------------------
async function triggerMakeClips() {
  const url = $('video-url').value.trim();
  if (!url && !appState.sourceId) {
    return alert('Please paste a video URL or upload a file first.');
  }

  const payload = {
    url: url || undefined,
    id: appState.sourceId || undefined,
    count: Number($('clip-count').value),
    min_len: Number($('min-len').value),
    max_len: Number($('max-len').value),
    mode: $('mode-select').value,
    layout: appState.layout,
    caption_style: appState.captionStyle,
    top: appState.topH,
    cam: appState.rect.cam,
    game: appState.rect.game
  };

  $('execution-panel').hidden = false;
  $('results-grid').innerHTML = '';
  $('job-progress-bar').style.width = '5%';
  $('job-stage').textContent = 'Queued';

  try {
    const res = await api('/make', { method: 'POST', body: JSON.stringify(payload) });
    appState.activeJobId = res.job_id;
    pollJob(res.job_id);
  } catch (e) {
    alert('Failed to start job: ' + e.message);
  }
}

async function triggerManualExport() {
  if (!appState.sourceId) {
    return alert('Upload a video file first to export a custom slice.');
  }

  const payload = {
    id: appState.sourceId,
    start: Number($('time-start').value),
    end: Number($('time-end').value),
    layout: appState.layout,
    top: appState.topH,
    caption_style: appState.captionStyle,
    cam: appState.rect.cam,
    game: appState.rect.game,
    hook: $('hook-input').value.trim()
  };

  $('execution-panel').hidden = false;
  $('job-stage').textContent = 'Rendering custom cut...';
  $('job-progress-bar').style.width = '30%';

  try {
    const res = await api('/export', { method: 'POST', body: JSON.stringify(payload) });
    pollJob(res.job_id);
  } catch (e) {
    alert('Export error: ' + e.message);
  }
}

function pollJob(jobId) {
  if (appState.pollTimer) clearInterval(appState.pollTimer);

  appState.pollTimer = setInterval(async () => {
    try {
      const data = await api(`/jobs/${jobId}`);
      $('job-stage').textContent = data.stage || data.status;
      $('job-progress-bar').style.width = Math.max(5, (data.progress || 0) * 100) + '%';

      if (data.clips?.length) {
        renderClipCards(data.clips, $('results-grid'));
      }

      if (data.status === 'done' || data.status === 'error') {
        clearInterval(appState.pollTimer);
        appState.pollTimer = null;
        loadLibrary();
      }
    } catch (_) {}
  }, 1200);
}

function renderClipCards(clips, container) {
  container.innerHTML = '';
  clips.forEach(clip => {
    const card = document.createElement('div');
    card.className = 'clip-card';
    card.innerHTML = `
      <div class="clip-video-wrap">
        <video src="/media/${clip.file}" controls preload="metadata"></video>
      </div>
      <div class="clip-info">
        <div class="clip-title-row">
          <h4>${clip.title || 'Clip'}</h4>
          <span class="viral-badge">Score: ${clip.score || 75}</span>
        </div>
        ${clip.hook ? `<div class="clip-hook">"${clip.hook}"</div>` : ''}
        <div class="clip-actions">
          <a href="/media/${clip.file}" download="clipiest-${clip.id}.mp4" class="btn-secondary btn-sm">↓ MP4</a>
          <a href="/text/${clip.id}/srt" class="btn-secondary btn-sm">↓ SRT</a>
        </div>
        <div class="stars-rating" data-id="${clip.id}">
          <span style="font-size:11px;color:var(--text-muted);margin-right:6px;">Tune AI:</span>
          ${[1, 2, 3, 4, 5].map(n => `<button class="star-btn" data-star="${n}">★</button>`).join('')}
        </div>
      </div>
    `;

    // Star rating
    card.querySelectorAll('.star-btn').forEach(star => {
      star.onclick = async () => {
        const rating = Number(star.dataset.star);
        await api('/api/feedback', {
          method: 'POST',
          body: JSON.stringify({ clip_id: clip.id, rating, features: clip.features })
        });
        card.querySelectorAll('.star-btn').forEach((s, i) => {
          s.classList.toggle('on', i < rating);
        });
      };
    });

    container.appendChild(card);
  });
}

// -------------------------------------------------------------
// Live Stream Ingestion
// -------------------------------------------------------------
async function startLiveStream() {
  const url = $('live-stream-url').value.trim();
  if (!url) return alert('Enter a Twitch or YouTube Live URL.');

  try {
    const res = await api('/api/live/start', {
      method: 'POST',
      body: JSON.stringify({
        url,
        layout: appState.layout,
        caption_style: appState.captionStyle,
        cam: appState.rect.cam,
        game: appState.rect.game
      })
    });

    appState.liveSessionId = res.session_id;
    $('live-start-btn').hidden = true;
    $('live-stop-btn').hidden = false;
    $('live-monitor-box').hidden = false;

    pollLiveStatus();
  } catch (e) {
    alert('Failed to start live session: ' + e.message);
  }
}

async function stopLiveStream() {
  if (!appState.liveSessionId) return;
  try {
    await api('/api/live/stop', {
      method: 'POST',
      body: JSON.stringify({ session_id: appState.liveSessionId })
    });
    $('live-start-btn').hidden = false;
    $('live-stop-btn').hidden = true;
    if (appState.livePollTimer) clearInterval(appState.livePollTimer);
  } catch (e) {
    alert('Stop error: ' + e.message);
  }
}

function pollLiveStatus() {
  if (appState.livePollTimer) clearInterval(appState.livePollTimer);
  appState.livePollTimer = setInterval(async () => {
    try {
      const data = await api(`/api/live/status?session_id=${appState.liveSessionId}`);
      $('live-chat-speed').textContent = data.chat_speed + ' msgs/10s';
      $('live-spikes').textContent = data.spikes_detected || 0;
      const mm = Math.floor(data.buffer_seconds / 60);
      const ss = Math.floor(data.buffer_seconds % 60);
      $('live-buffer-len').textContent = `${String(mm).padStart(2, '0')}:${String(ss).padStart(2, '0')}`;
    } catch (_) {}
  }, 2000);
}

async function instantLiveClip(duration) {
  if (!appState.liveSessionId) return alert('No active stream buffer.');
  try {
    const res = await api('/api/live/clip', {
      method: 'POST',
      body: JSON.stringify({ session_id: appState.liveSessionId, duration })
    });
    alert('Clip created: ' + res.file);
    loadLibrary();
  } catch (e) {
    alert('Live clip error: ' + e.message);
  }
}

// -------------------------------------------------------------
// Clip Library
// -------------------------------------------------------------
async function loadLibrary() {
  try {
    const clips = await api('/api/library');
    $('library-badge').textContent = clips.length;
    const container = $('library-grid');
    if (!clips.length) {
      container.innerHTML = '<div class="empty-state">No clips in library yet. Export or discover clips to see them here.</div>';
      return;
    }

    container.innerHTML = '';
    clips.forEach(clip => {
      const card = document.createElement('div');
      card.className = 'clip-card';
      card.innerHTML = `
        <div class="clip-video-wrap">
          <video src="${clip.file}" controls preload="metadata"></video>
        </div>
        <div class="clip-info">
          <div class="clip-title-row">
            <h4>${clip.title}</h4>
            <span class="viral-badge">${clip.layout}</span>
          </div>
          <small style="color:var(--text-muted);font-size:11px;">${new Date(clip.created * 1000).toLocaleString()}</small>
          <div class="clip-actions">
            <a href="${clip.file}" download="clipiest-${clip.id}.mp4" class="btn-secondary btn-sm">↓ MP4</a>
            <a href="${clip.srt}" class="btn-secondary btn-sm">↓ SRT</a>
            <button class="btn-secondary btn-sm reedit-btn">⚡ Edit</button>
            <button class="btn-danger btn-sm del-btn">🗑</button>
          </div>
        </div>
      `;

      card.querySelector('.reedit-btn').onclick = () => openSavedClip(clip.id);
      card.querySelector('.del-btn').onclick = async () => {
        if (!confirm('Permanently delete this clip?')) return;
        await api(`/api/library/${clip.id}`, { method: 'DELETE' });
        card.remove();
        $('library-badge').textContent = Math.max(0, Number($('library-badge').textContent) - 1);
      };

      container.appendChild(card);
    });
  } catch (_) {}
}

async function openSavedClip(clipId) {
  try {
    const data = await api(`/api/clips/${clipId}/edit`);
    const s = data.settings;
    document.querySelector('[data-tab="create"]').click();
    appState.sourceId = data.source.id;
    appState.sourceWidth = data.source.w;
    appState.sourceHeight = data.source.h;
    appState.duration = data.source.duration;
    
    if (s.cam) appState.rect.cam = s.cam;
    if (s.game) appState.rect.game = s.game;
    if (s.layout) {
      appState.layout = s.layout;
      document.querySelectorAll('.layout-card').forEach(c => c.classList.toggle('active', c.dataset.layout === s.layout));
    }
    if (s.top) {
      appState.topH = s.top;
      $('top-h-slider').value = Math.round(s.top * 100);
      $('top-h-val').textContent = Math.round(s.top * 100) + '%';
    }
    if (s.caption_style) {
      appState.captionStyle = s.caption_style;
      document.querySelectorAll('.style-card').forEach(c => c.classList.toggle('active', c.dataset.style === s.caption_style));
    }
    if (s.hook) $('hook-input').value = s.hook;
    if (s.start !== undefined) $('time-start').value = s.start;
    if (s.end !== undefined) $('time-end').value = s.end;

    $('source-status-badge').textContent = `Re-editing: ${clipId}`;
    $('import-status').hidden = false;
    $('import-status').textContent = `Loaded clip ${clipId} for non-destructive re-framing.`;
    
    loadStoryboard(data.source.id);
  } catch (e) {
    alert('Failed to load clip for re-editing: ' + e.message);
  }
}

window.addEventListener('DOMContentLoaded', init);
