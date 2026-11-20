/**
 * Clipiest — Frontend Master Application
 */
const $ = (id) => document.getElementById(id);

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// Application State
const appState = {
  configured: false,
  activeProvider: 'lmstudio',
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
  currentImageSource: null,
  creators: [],
  activeCreatorId: null
};

// Provider Presets
const PROVIDER_PRESETS = {
  lmstudio: {
    name: 'LM Studio (Local)',
    url: 'http://127.0.0.1:1234/v1',
    hint: 'Make sure LM Studio local server is started on port 1234.',
    keyHint: 'Optional (leave blank for local LM Studio)',
    defaultModel: 'local-model'
  },
  ollama: {
    name: 'Ollama (Local)',
    url: 'http://127.0.0.1:11434/v1',
    hint: 'Make sure Ollama is running on port 11434.',
    keyHint: 'Optional (leave blank for local Ollama)',
    defaultModel: 'llama3.2:3b'
  },
  gemini: {
    name: 'Google Gemini',
    url: 'https://generativelanguage.googleapis.com/v1beta/models',
    hint: 'Google AI Studio REST endpoint.',
    keyHint: 'Enter your Gemini API key (starts with AIza...)',
    defaultModel: 'gemini-2.5-flash'
  },
  openai: {
    name: 'OpenAI',
    url: 'https://api.openai.com/v1',
    hint: 'Standard OpenAI API endpoint.',
    keyHint: 'Enter OpenAI API key (starts with sk-...)',
    defaultModel: 'gpt-4o-mini'
  },
  anthropic: {
    name: 'Anthropic Claude',
    url: 'https://api.anthropic.com/v1',
    hint: 'Anthropic Messages API endpoint.',
    keyHint: 'Enter Anthropic API key (starts with sk-ant-...)',
    defaultModel: 'claude-3-5-haiku-20241022'
  },
  groq: {
    name: 'Groq',
    url: 'https://api.groq.com/openai/v1',
    hint: 'Ultra-fast Llama & Mixtral inference.',
    keyHint: 'Enter Groq API key (starts with gsk_...)',
    defaultModel: 'llama-3.3-70b-versatile'
  },
  openrouter: {
    name: 'OpenRouter',
    url: 'https://openrouter.ai/api/v1',
    hint: 'Unified gateway to 100+ open-source and proprietary models.',
    keyHint: 'Enter OpenRouter API key (starts with sk-or-...)',
    defaultModel: 'meta-llama/llama-3.2-3b-instruct:free'
  },
  custom: {
    name: 'Custom OpenAI-Compatible API',
    url: 'http://127.0.0.1:1234/v1',
    hint: 'Custom OpenAI-compatible server base URL.',
    keyHint: 'API Key (if required by endpoint)',
    defaultModel: 'default-model'
  }
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
  setupConfigurationEvents();
  setupCreatorEvents();
  
  await Promise.all([
    checkInitialConfiguration(),
    loadLayouts(),
    loadCaptionStyles(),
    loadCreators(),
    updateTelemetry(),
    loadLibrary()
  ]);

  setInterval(updateTelemetry, 5000);
  requestAnimationFrame(renderLoop);
}

// -------------------------------------------------------------
// Configuration & Setup Gate
// -------------------------------------------------------------
function openConfigModal() {
  $('setup-gate-modal').hidden = false;
  $('cfg-status-msg').hidden = true;
}

function closeConfigModal() {
  if (!appState.configured) return;
  $('setup-gate-modal').hidden = true;
  document.querySelector('.app-layout').classList.remove('app-locked');
}

async function checkInitialConfiguration() {
  try {
    const data = await api('/api/config');
    appState.configured = !!data.configured;
    updateSettingsDisplay(data);
    
    if (!data.configured) {
      document.querySelector('.app-layout').classList.add('app-locked');
      openConfigModal();
    } else {
      document.querySelector('.app-layout').classList.remove('app-locked');
      $('setup-gate-modal').hidden = true;
    }
  } catch (e) {
    console.warn('Config check failed:', e);
  }
}

function updateSettingsDisplay(data) {
  const ai = data.ai || {};
  const wh = data.whisper || {};
  appState.activeProvider = ai.provider || 'lmstudio';

  // Update Settings Tab labels
  if ($('settings-provider-lbl')) $('settings-provider-lbl').textContent = (ai.provider || 'lmstudio').toUpperCase();
  if ($('settings-url-lbl')) $('settings-url-lbl').textContent = ai.base_url || 'http://127.0.0.1:1234/v1';
  if ($('settings-model-lbl')) $('settings-model-lbl').textContent = ai.model || 'local-model';
  if ($('settings-whisper-lbl')) $('settings-whisper-lbl').textContent = wh.model || 'large-v3-turbo';
  if ($('active-cfg-badge')) {
    $('active-cfg-badge').textContent = data.configured ? 'Configured & Active' : 'Setup Required';
    $('active-cfg-badge').style.background = data.configured ? 'var(--green)' : '#ef4444';
  }

  // Pre-fill inputs in setup modal
  $('cfg-base-url').value = ai.base_url || PROVIDER_PRESETS[appState.activeProvider]?.url || 'http://127.0.0.1:1234/v1';
  $('cfg-api-key').value = ai.api_key || '';
  $('cfg-model').value = ai.model || PROVIDER_PRESETS[appState.activeProvider]?.defaultModel || 'local-model';
  if (wh.model) $('cfg-whisper-model').value = wh.model;

  // Set active provider card
  document.querySelectorAll('#providers-selector .provider-card').forEach(card => {
    card.classList.toggle('active', card.dataset.provider === appState.activeProvider);
  });
}

function setupConfigurationEvents() {
  // Provider card click
  document.querySelectorAll('#providers-selector .provider-card').forEach(card => {
    card.onclick = () => {
      document.querySelectorAll('#providers-selector .provider-card').forEach(c => c.classList.remove('active'));
      card.classList.add('active');
      const p = card.dataset.provider;
      appState.activeProvider = p;
      const preset = PROVIDER_PRESETS[p] || PROVIDER_PRESETS.custom;
      $('cfg-base-url').value = preset.url;
      $('cfg-url-hint').textContent = preset.hint;
      $('cfg-key-hint').textContent = preset.keyHint;
      $('cfg-model').value = preset.defaultModel;
      $('cfg-models-dropdown').hidden = true;
    };
  });

  // Fetch Models button
  $('cfg-fetch-models-btn').onclick = async () => {
    const btn = $('cfg-fetch-models-btn');
    btn.disabled = true;
    btn.textContent = '⏳ Querying...';
    const statusBox = $('cfg-status-msg');
    statusBox.hidden = false;
    statusBox.className = 'cfg-status-box loading';
    statusBox.textContent = `Connecting to ${appState.activeProvider.toUpperCase()} on ${$('cfg-base-url').value} to fetch loaded models...`;

    try {
      const q = new URLSearchParams({
        provider: appState.activeProvider,
        base_url: $('cfg-base-url').value.trim(),
        api_key: $('cfg-api-key').value.trim()
      });
      const res = await api(`/api/llm/models?${q.toString()}`, { method: 'GET' });
      const models = res.models || [];
      if (models.length) {
        statusBox.className = 'cfg-status-box success';
        statusBox.textContent = `Found ${models.length} model(s) available on server!`;
        const dd = $('cfg-models-dropdown');
        dd.innerHTML = models.map(m => `<option value="${m}">${m}</option>`).join('');
        dd.hidden = false;
        $('cfg-model').value = models[0];
        dd.onchange = () => { $('cfg-model').value = dd.value; };
      } else {
        statusBox.className = 'cfg-status-box error';
        statusBox.textContent = `No models found. Ensure a model is loaded in LM Studio under Local Server.`;
      }
    } catch (e) {
      statusBox.className = 'cfg-status-box error';
      statusBox.textContent = `Could not fetch models: ${e.message}. For LM Studio, start the Local Server in LM Studio first.`;
    } finally {
      btn.disabled = false;
      btn.textContent = '🔄 Fetch Models';
    }
  };

  // Test LLM Connection button
  $('cfg-test-btn').onclick = async () => {
    const btn = $('cfg-test-btn');
    btn.disabled = true;
    const statusBox = $('cfg-status-msg');
    statusBox.hidden = false;
    statusBox.className = 'cfg-status-box loading';
    statusBox.textContent = 'Sending test prompt to LLM...';

    const payload = {
      provider: appState.activeProvider,
      base_url: $('cfg-base-url').value.trim(),
      api_key: $('cfg-api-key').value.trim(),
      model: $('cfg-model').value.trim()
    };

    try {
      const res = await api('/api/llm/test', { method: 'POST', body: JSON.stringify(payload) });
      if (res.success) {
        statusBox.className = 'cfg-status-box success';
        statusBox.textContent = `✓ ${res.message} (Model: ${res.model})`;
      } else {
        statusBox.className = 'cfg-status-box error';
        statusBox.textContent = `Connection failed: ${res.error}. Make sure your LM Studio server is running on ${payload.base_url}`;
      }
    } catch (e) {
      statusBox.className = 'cfg-status-box error';
      statusBox.textContent = `Connection error: ${e.message}`;
    } finally {
      btn.disabled = false;
    }
  };

  // Save & Launch button
  $('cfg-save-btn').onclick = async () => {
    const btn = $('cfg-save-btn');
    btn.disabled = true;
    const statusBox = $('cfg-status-msg');
    statusBox.hidden = false;
    statusBox.className = 'cfg-status-box loading';
    statusBox.textContent = 'Saving configuration...';

    const payload = {
      configured: true,
      ai: {
        provider: appState.activeProvider,
        base_url: $('cfg-base-url').value.trim(),
        api_key: $('cfg-api-key').value.trim(),
        model: $('cfg-model').value.trim() || 'local-model'
      },
      whisper: {
        engine: 'faster_whisper',
        model: $('cfg-whisper-model').value,
        use_cpu: false
      }
    };

    try {
      const res = await api('/api/config', { method: 'POST', body: JSON.stringify(payload) });
      appState.configured = true;
      updateSettingsDisplay(res.config || payload);
      statusBox.className = 'cfg-status-box success';
      statusBox.textContent = '✓ Configuration saved! Studio is now unlocked.';
      setTimeout(() => {
        closeConfigModal();
        statusBox.hidden = true;
        updateTelemetry();
      }, 700);
    } catch (e) {
      statusBox.className = 'cfg-status-box error';
      statusBox.textContent = `Save failed: ${e.message}`;
    } finally {
      btn.disabled = false;
    }
  };

  // Reopen Config buttons
  $('reopen-llm-btn').onclick = openConfigModal;
  if ($('tab-cfg-open-modal-btn')) $('tab-cfg-open-modal-btn').onclick = openConfigModal;
  if ($('settings-reconfigure-btn')) $('settings-reconfigure-btn').onclick = openConfigModal;
}

// -------------------------------------------------------------
// Navigation & Tabs
// -------------------------------------------------------------
function switchTab(tabName) {
  document.querySelectorAll('.nav-item').forEach(b => {
    b.classList.toggle('active', b.dataset.tab === tabName);
  });
  document.querySelectorAll('.tab-pane').forEach(p => {
    p.classList.toggle('active', p.id === 'tab-' + tabName);
  });
  appState.currentTab = tabName;
  if (tabName !== 'creator') {
    document.querySelectorAll('.sidebar-creator-item').forEach(el => el.classList.remove('active'));
  }
}

function setupNavigation() {
  document.querySelectorAll('.nav-item').forEach(btn => {
    btn.onclick = () => {
      switchTab(btn.dataset.tab);
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

  // URL Enter key shortcut
  $('video-url').onkeydown = (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      $('preview-btn').click();
    }
  };

  // Preview button
  $('preview-btn').onclick = async () => {
    const url = $('video-url').value.trim();
    if (!url) return alert('Enter a video URL first.');

    const btn = $('preview-btn');
    const origHtml = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<span class="spin">⟳</span> Fetching Preview...';

    const statusEl = $('import-status');
    statusEl.hidden = false;
    statusEl.className = 'status-message active-loading';
    statusEl.innerHTML = '<span class="status-icon spin">⟳</span> Contacting video stream, analyzing metadata, and extracting high-res preview frames...';

    const selectedCreator = $('job-creator-select')?.value || '';

    try {
      const res = await api('/preview/url', {
        method: 'POST',
        body: JSON.stringify({ url, creator: selectedCreator })
      });

      if (!res || !res.id) {
        throw new Error(res?.detail || res?.error || 'Failed to inspect video');
      }

      appState.sourceId = res.id;
      appState.sourceUrl = url;
      appState.duration = res.duration || 0;
      appState.sourceWidth = res.w || 1920;
      appState.sourceHeight = res.h || 1080;

      if (res.cam) {
        appState.rect.cam = res.cam;
      }

      // Update time inputs and hooks
      $('time-start').value = 0;
      $('time-end').value = Math.min(60, Math.round(res.duration || 30));
      if (res.title && !$('hook-input').value) {
        $('hook-input').value = res.title.slice(0, 50);
      }

      // Update badge
      const durStr = res.duration_formatted || `${Math.round(res.duration)}s`;
      $('source-status-badge').textContent = `${res.game || 'Video'} · ${durStr} · ${appState.sourceWidth}x${appState.sourceHeight}`;

      // Show success status
      statusEl.className = 'status-message active-success';
      statusEl.innerHTML = `✅ <strong>${escapeHtml(res.title)}</strong> (${durStr}) loaded! Interactive framing active.`;

      // Hide canvas placeholder
      $('canvas-placeholder').hidden = true;

      // Populate storyboard reel
      if (res.frames && res.frames.length) {
        $('storyboard-reel').hidden = false;
        const reel = $('reel-frames');
        reel.innerHTML = '';
        res.frames.forEach((frameRel, idx) => {
          const frameUrl = frameRel.startsWith('/media/') ? frameRel : `/media/${frameRel}`;
          const b = document.createElement('button');
          b.className = `reel-frame-btn ${idx === 0 ? 'active' : ''}`;
          b.title = `Frame #${idx + 1}`;
          b.innerHTML = `<img src="${frameUrl}" alt="Frame ${idx + 1}"><span class="reel-frame-badge">#${idx + 1}</span>`;
          b.onclick = () => {
            document.querySelectorAll('.reel-frame-btn').forEach(el => el.classList.remove('active'));
            b.classList.add('active');
            const img = new Image();
            img.src = frameUrl;
            img.onload = () => {
              appState.currentImageSource = img;
            };
          };
          reel.appendChild(b);
        });
      }

      // Load main thumbnail image into canvas immediately
      const thumbUrl = res.thumbnail.startsWith('/media/') ? res.thumbnail : `/media/${res.thumbnail}`;
      const img = new Image();
      img.src = thumbUrl;
      img.onload = () => {
        appState.currentImageSource = img;
      };

    } catch (e) {
      statusEl.className = 'status-message active-error';
      statusEl.innerHTML = `❌ Error fetching preview: ${escapeHtml(e.message)}`;
      alert('Could not fetch preview: ' + e.message);
    } finally {
      btn.disabled = false;
      btn.innerHTML = origHtml;
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
        const confPct = typeof res.confidence === 'number' ? Math.round(res.confidence * 100) : (res.confidence === 'high' ? 95 : 75);
        alert(`Facecam detected with ${confPct}% confidence!`);
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
  const selectedCreator = $('job-creator-select')?.value || '';
  if (selectedCreator) {
    formData.append('creator', selectedCreator);
  }
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
    game: appState.rect.game,
    creator_id: $('job-creator-select')?.value || undefined
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
    const videoSrc = clip.file?.startsWith('/') ? clip.file : `/media/${clip.file}`;
    card.innerHTML = `
      <div class="clip-video-wrap">
        <video src="${videoSrc}" controls preload="metadata"></video>
      </div>
      <div class="clip-info">
        <div class="clip-title-row">
          <h4>${clip.title || 'Clip'}</h4>
          <span class="viral-badge">Score: ${clip.score || 75}</span>
        </div>
        ${clip.hook ? `<div class="clip-hook">"${clip.hook}"</div>` : ''}
        <div class="clip-actions">
          <a href="${videoSrc}" download="clipiest-${clip.id}.mp4" class="btn-secondary btn-sm">↓ MP4</a>
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

// -------------------------------------------------------------
// Content Creator Workspaces
// -------------------------------------------------------------
async function loadCreators() {
  try {
    const list = await api('/api/creators');
    appState.creators = Array.isArray(list) ? list : [];
    renderSidebarCreators();
    updateCreatorSelectOptions();
  } catch (e) {
    console.warn('Failed to load creators:', e);
  }
}

function renderSidebarCreators() {
  const container = $('sidebar-creators-list');
  if (!container) return;
  container.innerHTML = '';

  if (appState.creators.length === 0) {
    const empty = document.createElement('div');
    empty.style.cssText = 'font-size:11px;color:var(--text-muted);padding:6px 8px;';
    empty.textContent = 'No creators yet. Click ＋ to add.';
    container.appendChild(empty);
    return;
  }

  appState.creators.forEach(c => {
    const item = document.createElement('button');
    item.className = 'sidebar-creator-item' + (appState.activeCreatorId === c.id ? ' active' : '');
    item.dataset.cid = c.id;
    const initial = (c.name || 'C').charAt(0).toUpperCase();
    item.innerHTML = `
      <div class="sidebar-creator-avatar">${initial}</div>
      <span class="sidebar-creator-name">${c.name}</span>
      <span class="sidebar-creator-badge">${c.clip_count || 0}</span>
    `;
    item.onclick = () => openCreatorWorkspace(c.id);
    container.appendChild(item);
  });
}

function updateCreatorSelectOptions() {
  const sel = $('job-creator-select');
  if (!sel) return;
  const curVal = sel.value;
  sel.innerHTML = '<option value="">🌐 Global Workspace (No Creator)</option>';

  appState.creators.forEach(c => {
    const opt = document.createElement('option');
    opt.value = c.id;
    opt.textContent = `👤 ${c.name} (${c.clip_count || 0} clips)`;
    sel.appendChild(opt);
  });

  if (curVal && appState.creators.some(c => c.id === curVal)) {
    sel.value = curVal;
  }
}

function onJobCreatorSelectChange() {
  const sel = $('job-creator-select');
  const hint = $('creator-workspace-hint');
  if (!sel || !hint) return;
  const cid = sel.value;
  if (!cid) {
    hint.textContent = 'Videos & clips will be saved in data/';
    return;
  }
  const creator = appState.creators.find(c => c.id === cid);
  if (creator) {
    hint.textContent = `Saved in data/creators/${cid}/ (videos/ & clips/)`;
    if (creator.default_layout) {
      appState.layout = creator.default_layout;
      document.querySelectorAll('.layout-card').forEach(c => c.classList.toggle('active', c.dataset.layout === creator.default_layout));
    }
    if (creator.default_caption_style) {
      appState.captionStyle = creator.default_caption_style;
      document.querySelectorAll('.style-card').forEach(c => c.classList.toggle('active', c.dataset.style === creator.default_caption_style));
    }
  }
}

async function openCreatorWorkspace(cid) {
  appState.activeCreatorId = cid;
  switchTab('creator');
  document.querySelectorAll('.sidebar-creator-item').forEach(el => {
    el.classList.toggle('active', el.dataset.cid === cid);
  });

  try {
    const c = await api(`/api/creators/${cid}`);
    $('creator-hero-name').textContent = c.name;
    $('creator-hero-avatar').textContent = (c.name || 'C').charAt(0).toUpperCase();
    $('creator-folder-label').textContent = `creators/${c.id}`;
    $('creator-layout-label').textContent = c.default_layout || 'stack';
    $('creator-style-label').textContent = c.default_caption_style || 'bounce';
    $('creator-clips-count').textContent = c.clip_count || 0;
    $('creator-sub-clips-count').textContent = c.clip_count || 0;
    $('creator-videos-count').textContent = c.video_count || 0;
    $('creator-sub-videos-count').textContent = c.video_count || 0;
    $('creator-disk-label').textContent = `${c.disk_mb || 0} MB`;
    $('creator-hero-game').textContent = c.game || 'Content Creator';

    const chLink = $('creator-hero-channel');
    if (c.channel) {
      chLink.href = c.channel;
      chLink.hidden = false;
    } else {
      chLink.hidden = true;
    }

    $('creator-hero-notes').textContent = c.notes || `Dedicated workspace for ${c.name}. Source videos and rendered clips are organized into separate folders.`;

    await Promise.all([
      loadCreatorClips(cid),
      loadCreatorVideos(cid),
      loadCreatorLogs(cid)
    ]);
  } catch (e) {
    alert('Failed to load creator workspace: ' + e.message);
  }
}

async function loadCreatorClips(cid) {
  const container = $('creator-clips-grid');
  if (!container) return;
  container.innerHTML = '<div style="color:var(--text-muted);padding:16px;">Loading clips...</div>';

  try {
    const clips = await api(`/api/creators/${cid}/clips`);
    $('creator-clips-count').textContent = clips.length;
    $('creator-sub-clips-count').textContent = clips.length;
    container.innerHTML = '';

    if (clips.length === 0) {
      container.innerHTML = `
        <div style="grid-column: 1 / -1; text-align: center; padding: 40px; color: var(--text-muted);">
          <div style="font-size: 32px; margin-bottom: 8px;">🎬</div>
          <p>No clips generated yet in this creator's workspace.</p>
          <button class="btn-primary btn-sm" style="margin-top: 10px;" onclick="$('creator-clip-now-btn').click();">⚡ Make Clips for this Creator</button>
        </div>
      `;
      return;
    }

    clips.forEach(clip => {
      const card = document.createElement('div');
      card.className = 'clip-card';
      const videoSrc = clip.file.startsWith('/') ? clip.file : `/media/${clip.file}`;
      card.innerHTML = `
        <div class="clip-video-wrap">
          <video src="${videoSrc}" controls preload="metadata"></video>
        </div>
        <div class="clip-info">
          <div class="clip-title-row">
            <h4>${clip.title || 'Clip'}</h4>
            <span class="viral-badge">${(clip.duration || 0).toFixed(0)}s</span>
          </div>
          ${clip.hook ? `<div class="clip-hook">"${clip.hook}"</div>` : ''}
          <div class="clip-actions">
            <a href="${videoSrc}" download="clipiest-${clip.id}.mp4" class="btn-secondary btn-sm">↓ MP4</a>
            <button class="btn-ghost btn-sm re-edit-btn" data-id="${clip.id}">Re-edit</button>
            <button class="btn-ghost btn-sm btn-danger del-clip-btn" data-id="${clip.id}">✕</button>
          </div>
        </div>
      `;

      card.querySelector('.re-edit-btn').onclick = () => openSavedClip(clip.id);
      card.querySelector('.del-clip-btn').onclick = async () => {
        if (!confirm('Delete this clip?')) return;
        await api(`/api/library/${clip.id}`, { method: 'DELETE' });
        card.remove();
        loadCreatorClips(cid);
        loadCreators();
      };

      container.appendChild(card);
    });
  } catch (e) {
    container.innerHTML = `<div style="color:#ef4444;padding:16px;">Failed to load clips: ${e.message}</div>`;
  }
}

async function loadCreatorVideos(cid) {
  const container = $('creator-videos-list');
  if (!container) return;
  container.innerHTML = '<div style="color:var(--text-muted);padding:16px;">Loading source videos...</div>';

  try {
    const videos = await api(`/api/creators/${cid}/videos`);
    $('creator-videos-count').textContent = videos.length;
    $('creator-sub-videos-count').textContent = videos.length;
    container.innerHTML = '';

    if (videos.length === 0) {
      container.innerHTML = `
        <div style="text-align: center; padding: 40px; color: var(--text-muted);">
          <div style="font-size: 32px; margin-bottom: 8px;">📼</div>
          <p>No archive videos in this creator's <code>videos/</code> folder yet.</p>
          <p style="font-size: 12px; margin-top: 6px;">Upload footage with this creator selected to archive it in their dedicated folder.</p>
        </div>
      `;
      return;
    }

    videos.forEach(v => {
      const row = document.createElement('div');
      row.className = 'creator-video-row';
      const modDate = new Date(v.modified * 1000).toLocaleString();
      row.innerHTML = `
        <div>
          <div class="creator-video-title">${v.name}</div>
          <div class="creator-video-meta">${v.size_mb} MB · Modified ${modDate}</div>
        </div>
        <div>
          <button class="btn-secondary btn-sm clip-this-vid-btn">✂️ Clip This Video</button>
        </div>
      `;

      row.querySelector('.clip-this-vid-btn').onclick = () => {
        appState.sourceId = v.stem;
        $('job-creator-select').value = cid;
        onJobCreatorSelectChange();
        $('canvas-placeholder').hidden = true;
        $('source-status-badge').textContent = `Creator Video: ${v.name}`;
        switchTab('create');
        loadStoryboard(v.stem);
      };

      container.appendChild(row);
    });
  } catch (e) {
    container.innerHTML = `<div style="color:#ef4444;padding:16px;">Failed to load videos: ${e.message}</div>`;
  }
}

async function loadCreatorLogs(cid) {
  const container = $('creator-logs-list');
  if (!container) return;
  container.innerHTML = '<div style="color:var(--text-muted);padding:16px;">Loading logs...</div>';

  try {
    const logs = await api(`/api/creators/${cid}/logs`);
    container.innerHTML = '';

    if (logs.length === 0) {
      container.innerHTML = '<div style="color:var(--text-muted);padding:16px;">No activity logged yet.</div>';
      return;
    }

    logs.forEach(l => {
      const item = document.createElement('div');
      item.className = 'creator-log-item';
      const timeStr = new Date(l.time * 1000).toLocaleTimeString();
      item.innerHTML = `
        <span class="creator-log-time">${timeStr}</span>
        <span class="creator-log-action">${l.action || 'INFO'}</span>
        <span class="creator-log-msg">${l.msg}</span>
      `;
      container.appendChild(item);
    });
  } catch (e) {
    container.innerHTML = `<div style="color:#ef4444;padding:16px;">Failed to load logs: ${e.message}</div>`;
  }
}

function openCreatorModal(creatorData = null) {
  const layoutSel = $('creator-input-layout');
  layoutSel.innerHTML = '';
  appState.layoutsCatalog.forEach(l => {
    const opt = document.createElement('option');
    opt.value = l.id;
    opt.textContent = `${l.icon || ''} ${l.name}`;
    layoutSel.appendChild(opt);
  });

  const styleSel = $('creator-input-style');
  styleSel.innerHTML = '';
  appState.captionStylesList.forEach(s => {
    const opt = document.createElement('option');
    opt.value = s.id;
    opt.textContent = `${s.icon || ''} ${s.name}`;
    styleSel.appendChild(opt);
  });

  if (creatorData) {
    $('creator-modal-title').textContent = 'Edit Content Creator Workspace';
    $('creator-edit-id').value = creatorData.id;
    $('creator-input-name').value = creatorData.name || '';
    $('creator-input-channel').value = creatorData.channel || '';
    $('creator-input-layout').value = creatorData.default_layout || 'stack';
    $('creator-input-style').value = creatorData.default_caption_style || 'bounce';
    $('creator-input-game').value = creatorData.game || '';
    $('creator-input-triggers').value = creatorData.trigger_words || '';
    $('creator-input-notes').value = creatorData.notes || '';
  } else {
    $('creator-modal-title').textContent = 'Create Content Creator Workspace';
    $('creator-edit-id').value = '';
    $('creator-input-name').value = '';
    $('creator-input-channel').value = '';
    $('creator-input-layout').value = 'stack';
    $('creator-input-style').value = 'bounce';
    $('creator-input-game').value = '';
    $('creator-input-triggers').value = 'clip that, clip it, insane, clutch, omg';
    $('creator-input-notes').value = '';
  }

  $('creator-modal').hidden = false;
}

function closeCreatorModal() {
  $('creator-modal').hidden = true;
}

async function saveCreator() {
  const name = $('creator-input-name').value.trim();
  if (!name) return alert('Please enter a creator name.');

  const editId = $('creator-edit-id').value.trim();
  const payload = {
    name,
    channel: $('creator-input-channel').value.trim(),
    default_layout: $('creator-input-layout').value,
    default_caption_style: $('creator-input-style').value,
    game: $('creator-input-game').value.trim(),
    trigger_words: $('creator-input-triggers').value.trim(),
    notes: $('creator-input-notes').value.trim()
  };

  try {
    let result;
    if (editId) {
      result = await api(`/api/creators/${editId}`, { method: 'PUT', body: JSON.stringify(payload) });
    } else {
      result = await api('/api/creators', { method: 'POST', body: JSON.stringify(payload) });
    }

    closeCreatorModal();
    await loadCreators();
    if (result && result.id) {
      openCreatorWorkspace(result.id);
    }
  } catch (e) {
    alert('Failed to save creator: ' + e.message);
  }
}

async function deleteCreator(cid) {
  if (!confirm(`Delete creator workspace "${cid}" and its dedicated videos and clips?`)) return;
  try {
    await api(`/api/creators/${cid}`, { method: 'DELETE' });
    appState.activeCreatorId = null;
    await loadCreators();
    switchTab('create');
  } catch (e) {
    alert('Delete error: ' + e.message);
  }
}

async function openCreatorFolder(cid) {
  try {
    await api(`/api/creators/${cid}/open-folder`, { method: 'POST' });
  } catch (e) {
    alert('Could not open creator folder: ' + e.message);
  }
}

function switchCreatorSubtab(subtab) {
  document.querySelectorAll('.sub-tab-btn').forEach(b => {
    b.classList.toggle('active', b.dataset.subtab === `creator-${subtab}`);
  });
  document.querySelectorAll('#tab-creator .subpane').forEach(p => {
    p.hidden = (p.id !== `subpane-creator-${subtab}`);
  });
}

function setupCreatorEvents() {
  $('sidebar-add-creator-btn').onclick = () => openCreatorModal();
  $('quick-add-creator-btn').onclick = () => openCreatorModal();
  $('creator-modal-close').onclick = closeCreatorModal;
  $('creator-modal-cancel').onclick = closeCreatorModal;
  $('creator-modal-save').onclick = saveCreator;

  $('job-creator-select').onchange = onJobCreatorSelectChange;

  $('creator-open-folder-btn').onclick = () => {
    if (appState.activeCreatorId) openCreatorFolder(appState.activeCreatorId);
  };
  $('creator-edit-btn').onclick = () => {
    const c = appState.creators.find(x => x.id === appState.activeCreatorId);
    if (c) openCreatorModal(c);
  };
  $('creator-delete-btn').onclick = () => {
    if (appState.activeCreatorId) deleteCreator(appState.activeCreatorId);
  };
  $('creator-clip-now-btn').onclick = () => {
    if (appState.activeCreatorId) {
      $('job-creator-select').value = appState.activeCreatorId;
      onJobCreatorSelectChange();
      switchTab('create');
    }
  };

  $('subtab-btn-clips').onclick = () => switchCreatorSubtab('clips');
  $('subtab-btn-videos').onclick = () => switchCreatorSubtab('videos');
  $('subtab-btn-logs').onclick = () => switchCreatorSubtab('logs');
}

window.addEventListener('DOMContentLoaded', init);
