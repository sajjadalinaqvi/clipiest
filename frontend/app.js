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

function formatTime(seconds) {
  if (isNaN(seconds) || seconds === null || seconds === undefined) return '00:00';
  const total = Math.max(0, Math.round(seconds));
  const m = Math.floor(total / 60);
  const s = total % 60;
  if (m >= 60) {
    const h = Math.floor(m / 60);
    const remM = m % 60;
    return `${h}:${String(remM).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  }
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
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
  activeCreatorId: null,
  moments: [],
  selectedMoment: null,
  fetchedSliceId: null,
  fetchedSlicePath: null,
  sliceWords: [],
  sliceWordsSliceId: null,
  sliceWordsSourceId: null,
  sliceWordsUrl: null,
  hookStyle: 'banner',
  hookY: 260,
  storageFiles: [],
  storageCategoryFilter: 'all',
  storageSearchQuery: ''
};

// Provider Presets
const PROVIDER_PRESETS = {
  lmstudio: {
    name: 'LM Studio (Local)',
    url: 'http://localhost:1235/v1',
    hint: 'Make sure LM Studio local server is started (port 1235 or 1234).',
    keyHint: 'Optional (leave blank or use lm-studio)',
    defaultModel: 'qwen/qwen3.5-9b'
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
    url: 'http://localhost:1235/v1',
    hint: 'Custom OpenAI-compatible server base URL.',
    keyHint: 'API Key (if required by endpoint)',
    defaultModel: 'qwen/qwen3.5-9b'
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
  setupStudioWorkflow();
  setupStorageManager();
  setupCookiesManager();
  setupConfigurationEvents();
  setupCreatorEvents();

  await Promise.all([
    checkInitialConfiguration(),
    checkLLMStatus(),
    loadLayouts(),
    loadCaptionStyles(),
    loadCreators(),
    updateTelemetry(),
    loadLibrary()
  ]);

  setInterval(updateTelemetry, 5000);
  setInterval(checkLLMStatus, 30000);
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
      if (res.base_url) {
        $('cfg-base-url').value = res.base_url;
      }
      if (models.length) {
        statusBox.className = 'cfg-status-box success';
        statusBox.textContent = `Found ${models.length} model(s) available on ${$('cfg-base-url').value}!`;
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
      if (btn.dataset.tab === 'settings') {
        loadCookieStatus();
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
  } catch (_) { }
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
  $('tool-cam').onclick = () => setActiveTool('cam');
  $('tool-game').onclick = () => setActiveTool('game');

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

      // Invalidate previous video's slice, captions, and moments!
      appState.fetchedSliceId = null;
      appState.fetchedSlicePath = null;
      appState.sliceWords = [];
      appState.sliceWordsSliceId = null;
      appState.sliceWordsSourceId = null;
      appState.sliceWordsUrl = null;
      appState.selectedMoment = null;
      appState.moments = [];

      if ($('captions-status-msg')) {
        $('captions-status-msg').hidden = true;
        $('captions-status-msg').innerHTML = '';
      }
      if ($('slice-status-msg')) {
        $('slice-status-msg').hidden = true;
        $('slice-status-msg').innerHTML = '';
      }
      if ($('moments-list')) {
        $('moments-list').innerHTML = '';
      }
      if ($('results-grid')) {
        $('results-grid').innerHTML = '';
      }

      if (res.cam) {
        appState.rect.cam = res.cam;
      }

      // Update time inputs and hooks
      $('time-start').value = 0;
      $('time-end').value = Math.min(60, Math.round(res.duration || 30));
      $('hook-input').value = res.title ? res.title.slice(0, 50) : '';

      // Update badge
      const durStr = res.duration_formatted || `${Math.round(res.duration)}s`;
      if ($('source-status-badge')) {
        $('source-status-badge').textContent = `${res.game || 'Video'} · ${durStr} · ${appState.sourceWidth}x${appState.sourceHeight}`;
      }

      // Notice banner for age-restricted / warnings
      if ($('source-notice-banner')) {
        if (res.notice) {
          $('source-notice-banner').hidden = false;
          $('source-notice-banner').innerHTML = `
            <strong>⚠️ ${escapeHtml(res.notice)}</strong><br>
            <span style="font-size:12px;opacity:0.9;">Configure YouTube cookies anytime in <button type="button" class="btn-link" onclick="document.querySelector('[data-tab=\\'settings\\']')?.click();">⚡ LLM &amp; Settings &gt; YouTube Cookies</button>.</span>
          `;
        } else {
          $('source-notice-banner').hidden = true;
          $('source-notice-banner').innerHTML = '';
        }
      }

      // Show success/warning status
      statusEl.className = res.notice ? 'status-message active-warning' : 'status-message active-success';
      statusEl.innerHTML = res.notice
        ? `⚠️ <strong>${escapeHtml(res.title)}</strong> (${durStr}) loaded via YouTube CDN! Review crop boxes or configure cookies to download slices.`
        : `✅ <strong>${escapeHtml(res.title)}</strong> (${durStr}) loaded! Click <strong>⚡ Start Video Analysis</strong> in Step 2 to scout viral moments with LLM.`;

      if ($('start-scout-btn')) $('start-scout-btn').disabled = false;
      if ($('studio-workflow-badge')) $('studio-workflow-badge').textContent = 'Step 2: Video Loaded · Ready for LLM Analysis';

      // Hide canvas placeholder
      if ($('canvas-placeholder')) $('canvas-placeholder').hidden = true;

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
            img.crossOrigin = "anonymous";
            img.src = frameUrl;
            img.onload = () => {
              setImageSource(img);
            };
          };
          reel.appendChild(b);
        });
      }

      // Load main thumbnail image into canvas immediately
      const thumbUrl = res.thumbnail.startsWith('/media/') ? res.thumbnail : `/media/${res.thumbnail}`;
      const img = new Image();
      img.crossOrigin = "anonymous";
      img.src = thumbUrl;
      img.onload = () => {
        setImageSource(img);
      };
      img.onerror = () => {
        updatePreviewFrame(0);
      };

    } catch (e) {
      const cleanMsg = (e.message || '')
        .replace(/(?:\x1b|\033|%;|\^\[)\[[0-9;]*[a-zA-Z]|\[[0-9]+[0-9;]*[a-zA-Z]/g, '')
        .trim();
      statusEl.className = 'status-message active-error';
      statusEl.innerHTML = `❌ Error fetching preview: ${escapeHtml(cleanMsg)}`;
      const lower = cleanMsg.toLowerCase();
      if (lower.includes('age-restricted') || lower.includes('confirm your age') || lower.includes('sign in') || lower.includes('cookies')) {
        alert('This video is age-restricted or requires YouTube sign-in.\n\nPlease upload cookies.txt in LLM & Settings > YouTube Cookies to access this video.');
      } else {
        alert('Could not fetch preview: ' + cleanMsg);
      }
    } finally {
      btn.disabled = false;
      btn.innerHTML = origHtml;
    }
  };

  // Auto-Detect Facecam (if present)
  if ($('autocam-btn')) {
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
  }

  // Make Clips Trigger (if present)
  if ($('make-btn')) $('make-btn').onclick = triggerMakeClips;
  if ($('make-btn-bottom')) $('make-btn-bottom').onclick = triggerMakeClips;

  // Manual Export Trigger (if present)
  if ($('manual-export-btn')) $('manual-export-btn').onclick = triggerManualExport;

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
    appState.sourceUrl = null;
    appState.sourceWidth = data.w;
    appState.sourceHeight = data.h;
    appState.duration = data.duration;

    // Invalidate previous video's slice, captions, and moments!
    appState.fetchedSliceId = null;
    appState.fetchedSlicePath = null;
    appState.sliceWords = [];
    appState.sliceWordsSliceId = null;
    appState.sliceWordsSourceId = null;
    appState.sliceWordsUrl = null;
    appState.selectedMoment = null;
    appState.moments = [];
    $('hook-input').value = file.name ? file.name.replace(/\.[^/.]+$/, "").slice(0, 50) : '';

    if ($('captions-status-msg')) {
      $('captions-status-msg').hidden = true;
      $('captions-status-msg').innerHTML = '';
    }
    if ($('slice-status-msg')) {
      $('slice-status-msg').hidden = true;
      $('slice-status-msg').innerHTML = '';
    }
    if ($('moments-list')) {
      $('moments-list').innerHTML = '';
    }
    if ($('results-grid')) {
      $('results-grid').innerHTML = '';
    }

    $('time-start').value = 0;
    $('time-end').value = Math.min(30, data.duration);
    if ($('source-status-badge')) {
      $('source-status-badge').textContent = `${data.w}x${data.h} · ${(data.duration).toFixed(1)}s`;
    }
    $('import-status').textContent = 'Upload complete! Click Start Video Analysis in Step 2.';
    if ($('canvas-placeholder')) $('canvas-placeholder').hidden = true;
    if ($('start-scout-btn')) $('start-scout-btn').disabled = false;
    if ($('studio-workflow-badge')) $('studio-workflow-badge').textContent = 'Step 2: Video Loaded · Ready for LLM Analysis';

    // Load storyboard frames
    loadStoryboard(data.id);
    updatePreviewFrame(0);
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
          img.onload = () => { setImageSource(img); };
        };
        reel.appendChild(btn);
        if (idx === 0) {
          const img = new Image();
          img.src = `/media/${frameFile}`;
          img.onload = () => { setImageSource(img); };
        }
      });
    }
  } catch (_) { }
}

// -------------------------------------------------------------
// Interactive Canvas Drawing & Dragging (Move, Resize Handles, Draw)
// -------------------------------------------------------------
function setImageSource(img) {
  if (!img) return;
  appState.currentImageSource = img;
  if ($('canvas-placeholder')) $('canvas-placeholder').hidden = true;
  if (img.naturalWidth && img.naturalHeight) {
    const nw = img.naturalWidth;
    const nh = img.naturalHeight;
    const ar = nw / nh;
    const container = $('source-container');
    if (container) {
      container.style.aspectRatio = `${nw} / ${nh}`;
    }
    sourceCanvas.width = 960;
    sourceCanvas.height = Math.round(960 / ar);
  }
}
function setActiveTool(tool) {
  appState.activeTool = tool;
  if ($('tool-cam')) $('tool-cam').classList.toggle('active', tool === 'cam');
  if ($('tool-game')) $('tool-game').classList.toggle('active', tool === 'game');
}

function setupCanvasEvents() {
  function getCanvasCoords(e) {
    const rect = sourceCanvas.getBoundingClientRect();
    return {
      x: Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width)),
      y: Math.max(0, Math.min(1, (e.clientY - rect.top) / rect.height))
    };
  }

  function getHitMode(pt) {
    const rect = sourceCanvas.getBoundingClientRect();
    const handleDistX = 14 / rect.width;
    const handleDistY = 14 / rect.height;

    // Check active box corners first
    const activeBox = appState.rect[appState.activeTool];
    const bx = activeBox.x, by = activeBox.y, bw = activeBox.w, bh = activeBox.h;

    if (Math.abs(pt.x - (bx + bw)) < handleDistX && Math.abs(pt.y - (by + bh)) < handleDistY) return 'resize-br';
    if (Math.abs(pt.x - bx) < handleDistX && Math.abs(pt.y - (by + bh)) < handleDistY) return 'resize-bl';
    if (Math.abs(pt.x - (bx + bw)) < handleDistX && Math.abs(pt.y - by) < handleDistY) return 'resize-tr';
    if (Math.abs(pt.x - bx) < handleDistX && Math.abs(pt.y - by) < handleDistY) return 'resize-tl';

    // Check inside active box
    if (pt.x >= bx && pt.x <= bx + bw && pt.y >= by && pt.y <= by + bh) {
      return 'move';
    }

    // Check inside the OTHER box (clicking it selects and switches to it)
    const otherTool = appState.activeTool === 'cam' ? 'game' : 'cam';
    const otherBox = appState.rect[otherTool];
    if (pt.x >= otherBox.x && pt.x <= otherBox.x + otherBox.w && pt.y >= otherBox.y && pt.y <= otherBox.y + otherBox.h) {
      return `switch-${otherTool}`;
    }

    return 'draw';
  }

  sourceCanvas.onpointermove = (e) => {
    const pt = getCanvasCoords(e);
    if (!appState.dragInfo) {
      const mode = getHitMode(pt);
      if (mode === 'resize-br' || mode === 'resize-tl') sourceCanvas.style.cursor = 'nwse-resize';
      else if (mode === 'resize-bl' || mode === 'resize-tr') sourceCanvas.style.cursor = 'nesw-resize';
      else if (mode === 'move') sourceCanvas.style.cursor = 'move';
      else if (mode.startsWith('switch')) sourceCanvas.style.cursor = 'pointer';
      else sourceCanvas.style.cursor = 'crosshair';
      return;
    }

    const { mode, startPt, origBox, tool } = appState.dragInfo;
    const box = appState.rect[tool];
    const dx = pt.x - startPt.x;
    const dy = pt.y - startPt.y;

    if (mode === 'move') {
      box.x = Math.max(0, Math.min(1 - origBox.w, origBox.x + dx));
      box.y = Math.max(0, Math.min(1 - origBox.h, origBox.y + dy));
    } else if (mode === 'resize-br') {
      box.w = Math.max(0.04, Math.min(1 - box.x, origBox.w + dx));
      box.h = Math.max(0.04, Math.min(1 - box.y, origBox.h + dy));
    } else if (mode === 'resize-tl') {
      const right = origBox.x + origBox.w;
      const bottom = origBox.y + origBox.h;
      box.x = Math.max(0, Math.min(right - 0.04, origBox.x + dx));
      box.y = Math.max(0, Math.min(bottom - 0.04, origBox.y + dy));
      box.w = right - box.x;
      box.h = bottom - box.y;
    } else if (mode === 'resize-tr') {
      const bottom = origBox.y + origBox.h;
      box.w = Math.max(0.04, Math.min(1 - box.x, origBox.w + dx));
      box.y = Math.max(0, Math.min(bottom - 0.04, origBox.y + dy));
      box.h = bottom - box.y;
    } else if (mode === 'resize-bl') {
      const right = origBox.x + origBox.w;
      box.x = Math.max(0, Math.min(right - 0.04, origBox.x + dx));
      box.w = right - box.x;
      box.h = Math.max(0.04, Math.min(1 - box.y, origBox.h + dy));
    } else if (mode === 'draw') {
      box.x = Math.min(pt.x, startPt.x);
      box.y = Math.min(pt.y, startPt.y);
      box.w = Math.max(0.04, Math.abs(pt.x - startPt.x));
      box.h = Math.max(0.04, Math.abs(pt.y - startPt.y));
    }
  };

  sourceCanvas.onpointerdown = (e) => {
    const pt = getCanvasCoords(e);
    let mode = getHitMode(pt);

    if (mode.startsWith('switch-')) {
      const targetTool = mode.replace('switch-', '');
      setActiveTool(targetTool);
      mode = 'move';
    }

    const curTool = appState.activeTool;
    const box = appState.rect[curTool];
    appState.dragInfo = {
      mode,
      startPt: pt,
      origBox: { ...box },
      tool: curTool
    };
    sourceCanvas.setPointerCapture(e.pointerId);
  };

  sourceCanvas.onpointerup = () => { appState.dragInfo = null; };
  sourceCanvas.onpointercancel = () => { appState.dragInfo = null; };
}

function renderLoop() {
  const cw = sourceCanvas.width;
  const ch = sourceCanvas.height;

  // 1. Draw Source Canvas background / image
  sourceCtx.fillStyle = '#0a0d14';
  sourceCtx.fillRect(0, 0, cw, ch);

  if (appState.currentImageSource) {
    sourceCtx.drawImage(appState.currentImageSource, 0, 0, cw, ch);
  } else {
    // Subtle grid pattern for framing studio before video load
    sourceCtx.strokeStyle = 'rgba(255, 255, 255, 0.04)';
    sourceCtx.lineWidth = 1;
    for (let x = 60; x < cw; x += 60) {
      sourceCtx.beginPath(); sourceCtx.moveTo(x, 0); sourceCtx.lineTo(x, ch); sourceCtx.stroke();
    }
    for (let y = 60; y < ch; y += 60) {
      sourceCtx.beginPath(); sourceCtx.moveTo(0, y); sourceCtx.lineTo(cw, y); sourceCtx.stroke();
    }
    sourceCtx.fillStyle = 'rgba(255, 255, 255, 0.25)';
    sourceCtx.font = '600 13px Plus Jakarta Sans, sans-serif';
    sourceCtx.textAlign = 'center';
    sourceCtx.fillText('Interactive 16:9 Framing Studio · Drag handles to position Gameplay & Facecam', cw / 2, ch / 2 - 8);
  }

  // Draw Gameplay box (Cyan)
  const g = appState.rect.game;
  const gx = g.x * cw, gy = g.y * ch, gw = g.w * cw, gh = g.h * ch;
  const isGameActive = appState.activeTool === 'game';

  sourceCtx.strokeStyle = '#06b6d4';
  sourceCtx.lineWidth = isGameActive ? 3 : 1.5;
  sourceCtx.strokeRect(gx, gy, gw, gh);
  sourceCtx.fillStyle = isGameActive ? 'rgba(6, 182, 212, 0.18)' : 'rgba(6, 182, 212, 0.08)';
  sourceCtx.fillRect(gx, gy, gw, gh);

  // Gameplay Label
  sourceCtx.fillStyle = isGameActive ? '#06b6d4' : 'rgba(6, 182, 212, 0.7)';
  sourceCtx.fillRect(gx, Math.max(0, gy - 20), Math.min(gw, 140), 20);
  sourceCtx.fillStyle = '#000';
  sourceCtx.font = 'bold 10px Plus Jakarta Sans, sans-serif';
  sourceCtx.textAlign = 'left';
  sourceCtx.fillText(isGameActive ? '★ GAMEPLAY (ACTIVE)' : 'GAMEPLAY', gx + 6, Math.max(14, gy - 6));

  if (isGameActive) {
    drawHandles(sourceCtx, gx, gy, gw, gh, '#06b6d4');
  }

  // Draw Facecam box (Magenta)
  const c = appState.rect.cam;
  const cx = c.x * cw, cy = c.y * ch, cw_box = c.w * cw, ch_box = c.h * ch;
  const isCamActive = appState.activeTool === 'cam';

  sourceCtx.strokeStyle = '#ec4899';
  sourceCtx.lineWidth = isCamActive ? 3 : 1.5;
  sourceCtx.strokeRect(cx, cy, cw_box, ch_box);
  sourceCtx.fillStyle = isCamActive ? 'rgba(236, 72, 153, 0.22)' : 'rgba(236, 72, 153, 0.09)';
  sourceCtx.fillRect(cx, cy, cw_box, ch_box);

  // Facecam Label
  sourceCtx.fillStyle = isCamActive ? '#ec4899' : 'rgba(236, 72, 153, 0.7)';
  sourceCtx.fillRect(cx, Math.max(0, cy - 20), Math.min(cw_box, 140), 20);
  sourceCtx.fillStyle = '#fff';
  sourceCtx.font = 'bold 10px Plus Jakarta Sans, sans-serif';
  sourceCtx.textAlign = 'left';
  sourceCtx.fillText(isCamActive ? '★ FACECAM (ACTIVE)' : 'FACECAM', cx + 6, Math.max(14, cy - 6));

  if (isCamActive) {
    drawHandles(sourceCtx, cx, cy, cw_box, ch_box, '#ec4899');
  }

  // 2. Draw 9:16 Vertical Phone Simulator
  drawPhonePreview();

  requestAnimationFrame(renderLoop);
}

function drawHandles(ctx, x, y, w, h, color) {
  const hs = 9;
  const corners = [
    [x, y],
    [x + w, y],
    [x, y + h],
    [x + w, y + h]
  ];
  corners.forEach(([px, py]) => {
    ctx.fillStyle = '#ffffff';
    ctx.strokeStyle = color;
    ctx.lineWidth = 2;
    ctx.fillRect(px - hs / 2, py - hs / 2, hs, hs);
    ctx.strokeRect(px - hs / 2, py - hs / 2, hs, hs);
  });
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
    const nw = appState.currentImageSource.naturalWidth || 1920;
    const nh = appState.currentImageSource.naturalHeight || 1080;

    // Aspect-ratio-preserved blurred background cover
    previewCtx.save();
    previewCtx.filter = 'blur(14px)';
    const bgScale = Math.max((pw + 40) / nw, (ph + 40) / nh);
    const bgW = nw * bgScale;
    const bgH = nh * bgScale;
    previewCtx.drawImage(appState.currentImageSource, (pw - bgW) / 2, (ph - bgH) / 2, bgW, bgH);
    previewCtx.restore();

    // Center sharp inset (aspect-ratio-preserved decrease fit, matches FFmpeg)
    const ratio = Math.min(pw / nw, ph / nh);
    const w = nw * ratio;
    const h = nh * ratio;
    previewCtx.drawImage(appState.currentImageSource, (pw - w) / 2, (ph - h) / 2, w, h);
  } else {
    // Draw stacked or pip layers with aspect-ratio-preserving cover (exact match to FFmpeg force_original_aspect_ratio=increase,crop=lw:lh)
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

      const box = layer.source === 'cam' ? appState.rect.cam : (layer.source === 'full' ? { x: 0, y: 0, w: 1, h: 1 } : appState.rect.game);
      const img = appState.currentImageSource;
      const nw = img.naturalWidth || 1920;
      const nh = img.naturalHeight || 1080;
      const sx = Math.max(0, box.x * nw);
      const sy = Math.max(0, box.y * nh);
      const sw = Math.max(1, Math.min(nw - sx, box.w * nw));
      const sh = Math.max(1, Math.min(nh - sy, box.h * nh));

      // Replicate FFmpeg scale=lw:lh:force_original_aspect_ratio=increase,crop=lw:lh
      // Scale source crop so it covers (lw, lh) while preserving aspect ratio (zero stretching)
      const scale = Math.max(lw / sw, lh / sh);
      const srcUsedW = Math.min(sw, lw / scale);
      const srcUsedH = Math.min(sh, lh / scale);
      const srcOffX = sx + (sw - srcUsedW) / 2;
      const srcOffY = sy + (sh - srcUsedH) / 2;

      previewCtx.drawImage(
        img,
        Math.max(0, srcOffX), Math.max(0, srcOffY),
        Math.min(nw - Math.max(0, srcOffX), srcUsedW), Math.min(nh - Math.max(0, srcOffY), srcUsedH),
        lx, ly, lw, lh
      );
      previewCtx.restore();
    }
  }

  // Safe zones overlay
  if ($('safe-zones-chk') && $('safe-zones-chk').checked) {
    previewCtx.fillStyle = 'rgba(236, 72, 153, 0.2)';
    previewCtx.fillRect(0, 0, pw, 48);          // Top status bar
    previewCtx.fillRect(0, 840, pw, 120);        // Bottom controls & caption
    previewCtx.fillRect(470, 250, 70, 590);      // Right engagement icons
  }

  // Draw Hook
  const hook = $('hook-input')?.value.trim();
  const hookY = $('hook-y-slider') ? Number($('hook-y-slider').value) / 2 : 130;
  const hookStyle = $('hook-style-select')?.value || 'banner';
  if (hook) {
    previewCtx.save();
    previewCtx.textAlign = 'center';
    previewCtx.textBaseline = 'middle';
    previewCtx.font = '800 22px Plus Jakarta Sans, sans-serif';

    // Measure and background banner
    const textWidth = previewCtx.measureText(hook.toUpperCase()).width;
    const padX = 18, padY = 8;
    const boxX = (pw - textWidth) / 2 - padX;
    const boxY = hookY - 14 - padY;
    const boxW = textWidth + padX * 2;
    const boxH = 28 + padY * 2;

    if (hookStyle === 'punch') {
      previewCtx.fillStyle = '#dc2626';
      previewCtx.fillRect(boxX, boxY, boxW, boxH);
      previewCtx.fillStyle = '#fef08a';
    } else if (hookStyle === 'neon') {
      previewCtx.fillStyle = 'rgba(6, 182, 212, 0.25)';
      previewCtx.strokeStyle = '#06b6d4';
      previewCtx.lineWidth = 2;
      previewCtx.strokeRect(boxX, boxY, boxW, boxH);
      previewCtx.fillRect(boxX, boxY, boxW, boxH);
      previewCtx.fillStyle = '#ffffff';
    } else if (hookStyle === 'fire') {
      previewCtx.fillStyle = '#ea580c';
      previewCtx.fillRect(boxX, boxY, boxW, boxH);
      previewCtx.fillStyle = '#ffffff';
    } else if (hookStyle === 'comic') {
      previewCtx.fillStyle = '#facc15';
      previewCtx.strokeStyle = '#000000';
      previewCtx.lineWidth = 3;
      previewCtx.strokeRect(boxX, boxY, boxW, boxH);
      previewCtx.fillRect(boxX, boxY, boxW, boxH);
      previewCtx.fillStyle = '#000000';
    } else if (hookStyle === 'minimal') {
      previewCtx.fillStyle = 'rgba(15, 23, 42, 0.85)';
      previewCtx.fillRect(boxX, boxY, boxW, boxH);
      previewCtx.fillStyle = '#ffffff';
    } else if (hookStyle === 'matrix') {
      previewCtx.fillStyle = '#052e16';
      previewCtx.strokeStyle = '#22c55e';
      previewCtx.lineWidth = 2;
      previewCtx.strokeRect(boxX, boxY, boxW, boxH);
      previewCtx.fillRect(boxX, boxY, boxW, boxH);
      previewCtx.fillStyle = '#4ade80';
    } else if (hookStyle === 'gold') {
      previewCtx.fillStyle = '#422006';
      previewCtx.strokeStyle = '#eab308';
      previewCtx.lineWidth = 2;
      previewCtx.strokeRect(boxX, boxY, boxW, boxH);
      previewCtx.fillRect(boxX, boxY, boxW, boxH);
      previewCtx.fillStyle = '#fde047';
    } else if (hookStyle === 'cyberpink') {
      previewCtx.fillStyle = '#831843';
      previewCtx.strokeStyle = '#ec4899';
      previewCtx.lineWidth = 2;
      previewCtx.strokeRect(boxX, boxY, boxW, boxH);
      previewCtx.fillRect(boxX, boxY, boxW, boxH);
      previewCtx.fillStyle = '#f472b6';
    } else if (hookStyle === 'danger') {
      previewCtx.fillStyle = '#991b1b';
      previewCtx.strokeStyle = '#ef4444';
      previewCtx.lineWidth = 2;
      previewCtx.strokeRect(boxX, boxY, boxW, boxH);
      previewCtx.fillRect(boxX, boxY, boxW, boxH);
      previewCtx.fillStyle = '#ffffff';
    } else if (hookStyle === 'ice') {
      previewCtx.fillStyle = '#082f49';
      previewCtx.strokeStyle = '#38bdf8';
      previewCtx.lineWidth = 2;
      previewCtx.strokeRect(boxX, boxY, boxW, boxH);
      previewCtx.fillRect(boxX, boxY, boxW, boxH);
      previewCtx.fillStyle = '#38bdf8';
    } else if (hookStyle === 'thunder') {
      previewCtx.fillStyle = '#172554';
      previewCtx.strokeStyle = '#eab308';
      previewCtx.lineWidth = 2;
      previewCtx.strokeRect(boxX, boxY, boxW, boxH);
      previewCtx.fillRect(boxX, boxY, boxW, boxH);
      previewCtx.fillStyle = '#facc15';
    } else if (hookStyle === 'arcade') {
      previewCtx.fillStyle = '#3b0764';
      previewCtx.strokeStyle = '#06b6d4';
      previewCtx.lineWidth = 2;
      previewCtx.strokeRect(boxX, boxY, boxW, boxH);
      previewCtx.fillRect(boxX, boxY, boxW, boxH);
      previewCtx.fillStyle = '#06b6d4';
    } else if (hookStyle === 'emerald') {
      previewCtx.fillStyle = '#064e3b';
      previewCtx.strokeStyle = '#10b981';
      previewCtx.lineWidth = 2;
      previewCtx.strokeRect(boxX, boxY, boxW, boxH);
      previewCtx.fillRect(boxX, boxY, boxW, boxH);
      previewCtx.fillStyle = '#6ee7b7';
    } else {
      // Default Purple Banner
      previewCtx.fillStyle = '#7c3aed';
      previewCtx.fillRect(boxX, boxY, boxW, boxH);
      previewCtx.fillStyle = '#ffffff';
    }

    previewCtx.fillText(hook.toUpperCase(), pw / 2, hookY);
    previewCtx.restore();
  }

  // Draw Sample or Transcribed Subtitles
  const subY = Number($('caption-y-slider')?.value || 1450) / 2;
  const sampleWords = appState.sliceWords && appState.sliceWords.length
    ? appState.sliceWords.slice(0, 3).map(w => w.text || w.w).join(' ').toUpperCase()
    : 'CLIPIEST AI MOMENT';
  previewCtx.save();
  previewCtx.textAlign = 'center';
  previewCtx.font = '900 28px Plus Jakarta Sans, sans-serif';
  previewCtx.lineWidth = 6;
  previewCtx.strokeStyle = '#000';
  previewCtx.strokeText(sampleWords, pw / 2, subY);
  previewCtx.fillStyle = appState.captionStyle === 'gta' ? '#ec4899' : (appState.captionStyle === 'hype' ? '#22c55e' : (appState.captionStyle === 'mrbeast' ? '#facc15' : '#ffffff'));
  previewCtx.fillText(sampleWords, pw / 2, subY);
  previewCtx.restore();
}

// -------------------------------------------------------------
// Interactive Studio Workflow (Steps 1, 2, 3, 4)
// -------------------------------------------------------------
async function checkLLMStatus() {
  const pill = $('llm-status-pill');
  const startBtn = $('start-scout-btn');
  if (!pill) return;
  // Never disrupt active LLM moment analysis with ambient health pings
  if (appState.scoutingInProgress) return;

  try {
    const pingRes = await api('/api/llm/ping').catch(() => ({ success: false }));

    if (pingRes.success) {
      pill.className = 'pill-badge pill-connected';
      pill.textContent = `● LLM Connected (${pingRes.model || 'Ready'})`;
      if (startBtn && (appState.sourceId || appState.sourceUrl)) {
        startBtn.disabled = false;
      }
    } else {
      pill.className = 'pill-badge pill-disconnected';
      pill.textContent = '● LLM Disconnected (Configure)';
    }
  } catch (e) {
    pill.className = 'pill-badge pill-disconnected';
    pill.textContent = '● LLM Offline';
  }
}

function setupStudioWorkflow() {
  // Step 2: Scout Viral Moments
  if ($('start-scout-btn')) $('start-scout-btn').onclick = startMomentScout;
  if ($('scout-configure-llm-btn')) $('scout-configure-llm-btn').onclick = openConfigModal;

  // Custom AI Instructions & Quick Presets
  const instInput = $('scout-instructions-input');
  const clearInstBtn = $('scout-instructions-clear-btn');
  if (clearInstBtn && instInput) {
    clearInstBtn.onclick = () => {
      instInput.value = '';
      document.querySelectorAll('.tag-chip').forEach(c => c.classList.remove('active'));
    };
  }
  document.querySelectorAll('.tag-chip').forEach(chip => {
    chip.onclick = () => {
      const text = chip.getAttribute('data-inst');
      if (instInput) {
        if (instInput.value === text) {
          instInput.value = '';
          chip.classList.remove('active');
        } else {
          instInput.value = text;
          document.querySelectorAll('.tag-chip').forEach(c => c.classList.remove('active'));
          chip.classList.add('active');
        }
      }
    };
  });

  // Step 3: Studio & Slice controls
  ['time-start', 'time-end'].forEach(id => {
    const el = $(id);
    if (el) {
      el.addEventListener('change', () => {
        appState.fetchedSliceId = null;
        appState.fetchedSlicePath = null;
        appState.sliceWords = [];
        appState.sliceWordsSliceId = null;
        if ($('captions-status-msg')) {
          $('captions-status-msg').hidden = true;
          $('captions-status-msg').innerHTML = '';
        }
        if ($('slice-status-msg')) {
          $('slice-status-msg').hidden = true;
          $('slice-status-msg').innerHTML = '';
        }
      });
    }
  });

  if ($('refresh-frame-btn')) {
    $('refresh-frame-btn').onclick = () => {
      const start = Number($('time-start')?.value || 0);
      const end = Number($('time-end')?.value || start + 30);
      updatePreviewFrame((start + end) / 2);
    };
  }
  if ($('fetch-slice-btn')) $('fetch-slice-btn').onclick = fetchSlice;
  if ($('generate-captions-btn')) $('generate-captions-btn').onclick = generateCaptionsAndHook;

  // Step 4: Final Clip Render & Download
  if ($('generate-final-clip-btn')) $('generate-final-clip-btn').onclick = generateFinalClip;

  // Sliders & Style Dropdowns
  if ($('hook-style-select')) {
    $('hook-style-select').onchange = (e) => {
      appState.hookStyle = e.target.value;
    };
  }
  if ($('hook-y-slider')) {
    $('hook-y-slider').oninput = (e) => {
      appState.hookY = Number(e.target.value);
    };
  }
}

async function startMomentScout() {
  const url = $('video-url')?.value.trim() || appState.sourceUrl;
  const id = appState.sourceId;
  if (!url && !id) {
    return alert('Please fetch or upload a video in Step 1 first.');
  }

  const btn = $('start-scout-btn');
  const origHtml = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = '<span class="spin">⟳</span> Scouting Viral Timestamps...';

  const progressWrap = $('scout-progress-wrap');
  const statusText = $('scout-status-text');
  const progressBar = $('scout-progress-bar');
  if (progressWrap) progressWrap.hidden = false;
  if (statusText) statusText.innerHTML = '<span class="spin">⟳</span> Analyzing audio energy peaks, loudness, and transcript with connected LLM...';
  if (progressBar) progressBar.style.width = '30%';

  appState.scoutingInProgress = true;
  try {
    const userInstructions = $('scout-instructions-input')?.value.trim();
    const payload = {
      url: url || undefined,
      id: id || undefined,
      count: Number($('clip-count')?.value || 4),
      min_len: Number($('min-len')?.value || 30),
      max_len: Number($('max-len')?.value || 60),
      instructions: userInstructions || undefined
    };

    if (progressBar) progressBar.style.width = '65%';
    const res = await api('/api/moments/scout', {
      method: 'POST',
      body: JSON.stringify(payload)
    });

    if (!res || !res.moments) {
      throw new Error(res?.detail || 'No moments returned by scout engine');
    }

    appState.moments = res.moments;
    if (progressBar) progressBar.style.width = '100%';
    const instNotice = userInstructions ? ` (Filtered for: "<em>${escapeHtml(userInstructions.slice(0, 35))}...</em>")` : '';
    if (statusText) {
      statusText.innerHTML = `✅ <strong>LLM Analysis Complete!</strong> Recommended <strong>${res.moments.length} viral moment timestamps</strong>${instNotice}. Select any card below to frame.`;
    }

    renderMomentsList(res.moments);

    if (res.moments.length > 0) {
      selectMoment(res.moments[0]);
    }

    if ($('studio-workflow-badge')) {
      $('studio-workflow-badge').textContent = 'Step 3: Moment Selected · Set Framing';
    }

  } catch (e) {
    const cleanMsg = (e.message || '').replace(/\x1b\[[0-9;]*[a-zA-Z]/g, '');
    if (statusText) statusText.innerHTML = `❌ Analysis Error: ${escapeHtml(cleanMsg)}`;
    if (cleanMsg.includes('age') || cleanMsg.includes('sign in') || cleanMsg.includes('cookies')) {
      alert('This YouTube video is age-restricted or requires sign-in.\n\nPlease upload cookies.txt in LLM & Settings > YouTube Cookies to access audio.');
    } else {
      alert('Moment analysis failed: ' + cleanMsg);
    }
  } finally {
    appState.scoutingInProgress = false;
    btn.disabled = false;
    btn.innerHTML = origHtml;
  }
}

function renderMomentsList(moments) {
  const container = $('moments-list');
  if (!container) return;
  container.innerHTML = '';

  if (!moments || !moments.length) {
    container.innerHTML = `
      <div class="empty-moments-state">
        <div class="empty-icon">⚠️</div>
        <p>No high-confidence moments found for this range. Try adjusting Min/Max length or clip count.</p>
      </div>
    `;
    return;
  }

  moments.forEach((m, idx) => {
    const card = document.createElement('div');
    card.className = `moment-card ${idx === 0 ? 'selected' : ''}`;
    card.dataset.idx = idx;

    const startSec = Number(m.start || 0);
    const endSec = Number(m.end || startSec + 30);
    const durSec = Math.max(1, Math.round(endSec - startSec));

    card.innerHTML = `
      <div class="moment-header">
        <span class="moment-score">🔥 ${m.score || 85}/100</span>
        <span class="moment-time-badge">⏱ ${formatTime(startSec)} - ${formatTime(endSec)} (${durSec}s)</span>
      </div>
      <div class="moment-title">${escapeHtml(m.title || `Viral Climax #${idx + 1}`)}</div>
      ${m.hook ? `<div class="moment-hook">"${escapeHtml(m.hook)}"</div>` : ''}
      <div class="moment-reason">${escapeHtml(m.reason || 'High transcript energy and audio spike.')}</div>
      <button type="button" class="btn-secondary btn-xs moment-select-btn">👉 Select This Moment</button>
    `;

    card.onclick = () => selectMoment(m, card);
    card.querySelector('.moment-select-btn').onclick = (e) => {
      e.stopPropagation();
      selectMoment(m, card);
    };

    container.appendChild(card);
  });
}

function selectMoment(moment, cardEl) {
  appState.selectedMoment = moment;

  // Clear any previously fetched slice & captions because a new moment is selected!
  appState.fetchedSliceId = null;
  appState.fetchedSlicePath = null;
  appState.sliceWords = [];
  appState.sliceWordsSliceId = null;
  if ($('captions-status-msg')) {
    $('captions-status-msg').hidden = true;
    $('captions-status-msg').innerHTML = '';
  }
  if ($('slice-status-msg')) {
    $('slice-status-msg').hidden = true;
    $('slice-status-msg').innerHTML = '';
  }

  // Update time inputs
  $('time-start').value = Math.round(moment.start * 10) / 10;
  $('time-end').value = Math.round(moment.end * 10) / 10;
  if (moment.hook) {
    $('hook-input').value = moment.hook;
  }

  // Update card styles
  document.querySelectorAll('.moment-card').forEach(c => c.classList.remove('selected'));
  if (cardEl) {
    cardEl.classList.add('selected');
  }

  // Update status badge
  const startSec = Number(moment.start || 0);
  const endSec = Number(moment.end || startSec + 30);
  if ($('selected-moment-badge')) {
    $('selected-moment-badge').textContent = `Selected: ${formatTime(startSec)} - ${formatTime(endSec)}`;
  }

  // Fetch frame from video at this exact moment timestamp
  const midSec = (startSec + endSec) / 2;
  updatePreviewFrame(midSec);
}

async function updatePreviewFrame(sec) {
  const url = $('video-url')?.value.trim() || appState.sourceUrl;
  const id = appState.sourceId || '';
  const sliceId = appState.fetchedSliceId || '';
  const start = Number($('time-start')?.value || 0);
  const end = Number($('time-end')?.value || start + 30);
  
  // If slice has been downloaded, use relative time inside slice
  let targetSec = Math.max(0, Number(sec) || 0);
  if (sliceId) {
    if (targetSec >= start && targetSec <= end) {
      targetSec = targetSec - start;
    } else if (targetSec > (end - start)) {
      targetSec = (end - start) / 2;
    }
  }

  const frameUrl = `/api/preview/frame?id=${encodeURIComponent(id)}&url=${encodeURIComponent(url)}&sec=${targetSec.toFixed(2)}&slice_id=${encodeURIComponent(sliceId)}&t=${Date.now()}`;

  const img = new Image();
  img.crossOrigin = "anonymous";
  img.src = frameUrl;
  img.onload = () => {
    setImageSource(img);
  };
}

async function fetchSlice() {
  const url = $('video-url')?.value.trim() || appState.sourceUrl;
  const id = appState.sourceId || '';
  const start = Number($('time-start')?.value || 0);
  const end = Number($('time-end')?.value || start + 30);
  const quality = $('video-quality')?.value || '720';

  if (!url && !id) {
    return alert('Please enter a video URL or upload a file first.');
  }
  if (end <= start) {
    return alert('End time must be greater than start time.');
  }

  const btn = $('fetch-slice-btn');
  const origHtml = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = '<span class="spin">⟳</span> Fetching Slice (' + (end - start).toFixed(0) + 's)...';

  const statusEl = $('slice-status-msg');
  if (statusEl) {
    statusEl.hidden = false;
    statusEl.className = 'status-message active-loading';
    statusEl.innerHTML = `<span class="spin">⟳</span> Downloading ONLY the selected ${formatTime(start)} - ${formatTime(end)} (${(end - start).toFixed(0)}s) range at ${quality}p...`;
  }

  try {
    const res = await api('/api/slice/fetch', {
      method: 'POST',
      body: JSON.stringify({
        id: id || undefined,
        url: url || undefined,
        start,
        end,
        quality
      })
    });

    if (!res || !res.slice_id) {
      throw new Error(res?.detail || 'Failed to fetch slice');
    }

    appState.fetchedSliceId = res.slice_id;
    appState.fetchedSlicePath = res.file;

    // Invalidate old captions when a new slice is fetched!
    appState.sliceWords = [];
    appState.sliceWordsSliceId = null;
    if ($('captions-status-msg')) {
      $('captions-status-msg').hidden = true;
      $('captions-status-msg').innerHTML = '';
    }

    if (statusEl) {
      statusEl.className = 'status-message active-success';
      statusEl.innerHTML = `✅ <strong>Slice Ready!</strong> Fetched ${(res.duration || end - start).toFixed(1)}s slice (ID: <code>${res.slice_id}</code>). You can now customize Hook &amp; Captions below.`;
    }

    if ($('studio-workflow-badge')) {
      $('studio-workflow-badge').textContent = 'Step 3: Slice Fetched · Add Captions';
    }

    if ($('selected-moment-badge')) {
      $('selected-moment-badge').innerHTML = `🎬 Extracted Slice: <strong>${formatTime(start)} - ${formatTime(end)}</strong> (${(end - start).toFixed(0)}s)`;
    }

    // Refresh canvas frame directly from the newly downloaded slice preview
    if (res.preview) {
      const img = new Image();
      img.crossOrigin = "anonymous";
      img.src = `${res.preview}?t=${Date.now()}`;
      img.onload = () => {
        setImageSource(img);
      };
    } else {
      updatePreviewFrame(0);
    }

  } catch (e) {
    if (statusEl) {
      statusEl.className = 'status-message active-error';
      statusEl.innerHTML = `❌ Failed to fetch slice: ${escapeHtml(e.message)}`;
    }
    alert('Slice fetch error: ' + e.message);
  } finally {
    btn.disabled = false;
    btn.innerHTML = origHtml;
  }
}

async function generateCaptionsAndHook() {
  if (!appState.fetchedSliceId) {
    return alert('Please click "📥 Get Clip (Fetch Slice Only)" first before generating captions.');
  }

  const btn = $('generate-captions-btn');
  const origHtml = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = '<span class="spin">⟳</span> Transcribing Slice Audio...';

  const statusEl = $('captions-status-msg');
  if (statusEl) {
    statusEl.hidden = false;
    statusEl.className = 'status-message active-loading';
    statusEl.innerHTML = '<span class="spin">⟳</span> Running local Faster-Whisper to extract exact word timings...';
  }

  try {
    const res = await api('/api/slice/captions', {
      method: 'POST',
      body: JSON.stringify({
        slice_id: appState.fetchedSliceId,
        hook: $('hook-input')?.value.trim() || undefined,
        lang: $('caption-lang')?.value || undefined
      })
    });

    if (!res || !res.words) {
      throw new Error(res?.detail || 'Transcription failed');
    }

    appState.sliceWords = res.words;
    appState.sliceWordsSliceId = appState.fetchedSliceId;
    appState.sliceWordsSourceId = appState.sourceId;
    appState.sliceWordsUrl = $('video-url')?.value.trim() || appState.sourceUrl;
    if (res.hook && !$('hook-input').value) {
      $('hook-input').value = res.hook;
    }

    if (statusEl) {
      statusEl.className = 'status-message active-success';
      statusEl.innerHTML = `✅ <strong>Captions Generated!</strong> Transcribed ${res.words.length} words. Check the 9:16 phone simulator for live preview, then click <strong>🚀 Generate Clip</strong> below.`;
    }

    if ($('studio-workflow-badge')) {
      $('studio-workflow-badge').textContent = 'Step 4: Ready to Render & Download';
    }

  } catch (e) {
    if (statusEl) {
      statusEl.className = 'status-message active-error';
      statusEl.innerHTML = `❌ Captions Error: ${escapeHtml(e.message)}`;
    }
    alert('Transcription error: ' + e.message);
  } finally {
    btn.disabled = false;
    btn.innerHTML = origHtml;
  }
}

async function generateFinalClip() {
  const url = $('video-url')?.value.trim() || appState.sourceUrl;
  const id = appState.sourceId;
  const sliceId = appState.fetchedSliceId;

  if (!url && !id && !sliceId) {
    return alert('Please fetch or upload a video and select a slice first.');
  }

  // Verify words strictly belong to THIS exact slice or video source!
  let wordsToSend = [];
  if (appState.sliceWords && appState.sliceWords.length > 0) {
    if (sliceId && appState.sliceWordsSliceId === sliceId) {
      wordsToSend = appState.sliceWords;
    } else if (!sliceId && ((id && appState.sliceWordsSourceId === id) || (url && appState.sliceWordsUrl === url))) {
      wordsToSend = appState.sliceWords;
    }
  }

  const payload = {
    id: id || undefined,
    url: url || undefined,
    slice_id: sliceId || undefined,
    start: Number($('time-start')?.value || 0),
    end: Number($('time-end')?.value || 30),
    layout: appState.layout,
    top: appState.topH,
    caption_style: appState.captionStyle,
    hook_style: $('hook-style-select')?.value || 'banner',
    caption_y: Number($('caption-y-slider')?.value || 1450),
    hook_y: Number($('hook-y-slider')?.value || 260),
    hook: $('hook-input')?.value.trim() || '',
    words: wordsToSend,
    cam: appState.rect.cam,
    game: appState.rect.game
  };

  $('execution-panel').hidden = false;
  $('job-stage').textContent = 'Rendering 1080x1920 MP4...';
  $('job-progress-bar').style.width = '20%';

  const btn = $('generate-final-clip-btn');
  btn.disabled = true;

  try {
    const res = await api('/export', { method: 'POST', body: JSON.stringify(payload) });
    pollFinalJob(res.job_id);
  } catch (e) {
    alert('Render failed: ' + e.message);
    btn.disabled = false;
  }
}

function pollFinalJob(jobId) {
  if (appState.pollTimer) clearInterval(appState.pollTimer);

  appState.pollTimer = setInterval(async () => {
    try {
      const data = await api(`/jobs/${jobId}`);
      $('job-stage').textContent = data.stage || data.status;
      $('job-progress-bar').style.width = Math.max(10, (data.progress || 0) * 100) + '%';

      if (data.status === 'done') {
        clearInterval(appState.pollTimer);
        appState.pollTimer = null;
        $('generate-final-clip-btn').disabled = false;
        $('job-stage').textContent = 'Done! Clip saved to ./Downloads';
        $('job-progress-bar').style.width = '100%';

        if ($('studio-workflow-badge')) {
          $('studio-workflow-badge').textContent = '✅ Rendered & Downloaded to ./Downloads';
        }

        // Trigger automatic browser download into Downloads folder
        const downloadUrl = data.download_url || `/api/download/${data.clip_id}.mp4`;
        const a = document.createElement('a');
        a.href = downloadUrl;
        a.download = `clipiest-${data.clip_id}.mp4`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);

        // Reset slice and words so next clip starts completely fresh
        appState.fetchedSliceId = null;
        appState.fetchedSlicePath = null;
        appState.sliceWords = [];
        appState.sliceWordsSliceId = null;

        // Render card into results grid
        renderClipCards([{
          id: data.clip_id,
          file: data.file,
          title: $('hook-input')?.value || 'Clipiest Final Clip',
          start: Number($('time-start')?.value || 0),
          end: Number($('time-end')?.value || 30),
          score: 95,
          hook: $('hook-input')?.value || ''
        }], $('results-grid'));

        loadLibrary();
      } else if (data.status === 'error') {
        clearInterval(appState.pollTimer);
        appState.pollTimer = null;
        $('generate-final-clip-btn').disabled = false;
        alert('Render failed: ' + data.error);
      }
    } catch (_) { }
  }, 1200);
}

// -------------------------------------------------------------
// Step 5: Data & Storage Manager
// -------------------------------------------------------------
function setupStorageManager() {
  // Sub-tabs in Settings
  const subTabLlm = $('subtab-btn-llm');
  const subTabStorage = $('subtab-btn-storage');
  const paneLlm = $('subpane-settings-llm');
  const paneStorage = $('subpane-settings-storage');

  if (subTabLlm && subTabStorage) {
    subTabLlm.onclick = () => {
      subTabLlm.classList.add('active');
      subTabStorage.classList.remove('active');
      if (paneLlm) paneLlm.hidden = false;
      if (paneStorage) paneStorage.hidden = true;
      loadCookieStatus();
    };

    subTabStorage.onclick = () => {
      subTabStorage.classList.add('active');
      subTabLlm.classList.remove('active');
      if (paneLlm) paneLlm.hidden = true;
      if (paneStorage) paneStorage.hidden = false;
      loadStorageFiles();
    };
  }

  // Sidebar storage button
  const sidebarStorageBtn = $('sidebar-storage-btn');
  if (sidebarStorageBtn) {
    sidebarStorageBtn.onclick = () => {
      switchTab('settings');
      if (subTabStorage) subTabStorage.click();
    };
  }

  // Storage buttons
  if ($('storage-refresh-btn')) $('storage-refresh-btn').onclick = loadStorageFiles;
  if ($('storage-clean-tmp-btn')) $('storage-clean-tmp-btn').onclick = cleanTmpFiles;

  // Search input
  if ($('storage-search-input')) {
    $('storage-search-input').oninput = (e) => {
      appState.storageSearchQuery = e.target.value.toLowerCase().trim();
      renderStorageTable();
    };
  }

  // Category filter chips
  document.querySelectorAll('[data-storage-cat]').forEach(chip => {
    chip.onclick = () => {
      document.querySelectorAll('[data-storage-cat]').forEach(c => c.classList.remove('active'));
      chip.classList.add('active');
      appState.storageCategoryFilter = chip.dataset.storageCat;
      renderStorageTable();
    };
  });

  // Media preview modal close
  if ($('media-preview-close')) $('media-preview-close').onclick = closeMediaModal;
  if ($('media-preview-close-btn')) $('media-preview-close-btn').onclick = closeMediaModal;
}

async function loadStorageFiles() {
  const tbody = $('storage-table-body');
  if (tbody) tbody.innerHTML = '<tr><td colspan="6" class="table-empty"><span class="spin">⟳</span> Scanning data directory...</td></tr>';

  try {
    const data = await api('/api/storage/files');
    appState.storageFiles = data.files || [];

    // Calculate metrics
    let totalBytes = 0;
    let videoCount = 0;
    let subsCount = 0;

    appState.storageFiles.forEach(f => {
      totalBytes += f.size_bytes || 0;
      if (f.category === 'video') videoCount++;
      if (f.category === 'subtitles' || f.category === 'metadata') subsCount++;
    });

    const totalMb = (totalBytes / (1024 * 1024)).toFixed(1);
    const totalGb = (totalBytes / (1024 * 1024 * 1024)).toFixed(2);
    const totalFormatted = totalBytes >= 1024 * 1024 * 1024 ? `${totalGb} GB` : `${totalMb} MB`;

    if ($('storage-total-count')) $('storage-total-count').textContent = appState.storageFiles.length;
    if ($('storage-total-size')) $('storage-total-size').textContent = `${totalFormatted} disk used`;
    if ($('storage-video-count')) $('storage-video-count').textContent = videoCount;
    if ($('storage-subs-count')) $('storage-subs-count').textContent = subsCount;

    renderStorageTable();
  } catch (e) {
    if (tbody) tbody.innerHTML = `<tr><td colspan="6" class="table-empty error">Failed to load files: ${escapeHtml(e.message)}</td></tr>`;
  }
}

function renderStorageTable() {
  const tbody = $('storage-table-body');
  if (!tbody) return;

  const catFilter = appState.storageCategoryFilter || 'all';
  const query = appState.storageSearchQuery || '';

  const filtered = appState.storageFiles.filter(f => {
    if (catFilter !== 'all' && f.category !== catFilter) return false;
    if (query && !f.name.toLowerCase().includes(query) && !f.rel_path.toLowerCase().includes(query)) return false;
    return true;
  });

  if (!filtered.length) {
    tbody.innerHTML = '<tr><td colspan="6" class="table-empty">No matching files found in data folder.</td></tr>';
    return;
  }

  tbody.innerHTML = '';
  filtered.forEach(f => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td class="file-name-cell" title="${escapeHtml(f.name)}">
        ${escapeHtml(f.name)}
      </td>
      <td>
        <span class="cat-badge cat-${f.category}">${f.category}</span>
      </td>
      <td class="file-size-cell">${f.size_formatted}</td>
      <td class="file-date-cell">${f.modified}</td>
      <td class="file-path-cell" title="${escapeHtml(f.rel_path)}">${escapeHtml(f.rel_path)}</td>
      <td style="text-align:right;white-space:nowrap;">
        <button type="button" class="btn-secondary btn-xs file-preview-btn">▶ Preview</button>
        <button type="button" class="btn-ghost btn-xs btn-danger file-delete-btn">🗑️ Delete</button>
      </td>
    `;

    tr.querySelector('.file-preview-btn').onclick = () => previewStorageFile(f);
    tr.querySelector('.file-delete-btn').onclick = () => deleteStorageFile(f.rel_path, f.name);

    tbody.appendChild(tr);
  });
}

async function deleteStorageFile(relPath, name) {
  if (!confirm(`Are you sure you want to permanently delete '${name}'? This cannot be undone.`)) return;

  try {
    await api('/api/storage/delete', { method: 'POST', body: JSON.stringify({ path: relPath }) });
    loadStorageFiles();
  } catch (e) {
    alert('Delete error: ' + e.message);
  }
}

async function cleanTmpFiles() {
  if (!confirm('Clean all temporary files in data/tmp?')) return;
  try {
    const res = await api('/api/storage/clean-tmp', { method: 'POST' });
    alert(`Cleaned ${res.cleaned} temporary files/folders.`);
    loadStorageFiles();
  } catch (e) {
    alert('Clean temp error: ' + e.message);
  }
}

function previewStorageFile(file) {
  const modal = $('media-preview-modal');
  const title = $('media-preview-title');
  const body = $('media-preview-body');
  const dlBtn = $('media-preview-download-btn');
  if (!modal || !body) return;

  title.textContent = `Preview: ${file.name}`;
  dlBtn.href = file.url;
  dlBtn.download = file.name;

  if (file.category === 'video') {
    body.innerHTML = `<video src="${file.url}" controls autoplay style="max-width:100%;max-height:60vh;border-radius:8px;"></video>`;
  } else if (file.category === 'audio') {
    body.innerHTML = `<div style="padding:40px;text-align:center;"><div style="font-size:48px;margin-bottom:12px;">🎵</div><audio src="${file.url}" controls autoplay style="width:100%;"></audio></div>`;
  } else if (file.category === 'image') {
    body.innerHTML = `<img src="${file.url}" style="max-width:100%;max-height:60vh;border-radius:8px;object-fit:contain;">`;
  } else {
    body.innerHTML = '<div style="padding:20px;text-align:center;"><span class="spin">⟳</span> Loading file text...</div>';
    fetch(file.url)
      .then(r => r.text())
      .then(text => {
        body.innerHTML = `<pre style="max-height:55vh;overflow:auto;background:#06080f;padding:16px;border-radius:6px;font-family:var(--font-mono);font-size:12px;color:#cbd5e1;white-space:pre-wrap;word-break:break-all;">${escapeHtml(text.slice(0, 50000))}</pre>`;
      })
      .catch(err => {
        body.innerHTML = `<p class="error">Could not display file: ${escapeHtml(err.message)}</p>`;
      });
  }

  modal.hidden = false;
}

function closeMediaModal() {
  const modal = $('media-preview-modal');
  const body = $('media-preview-body');
  if (modal) modal.hidden = true;
  if (body) body.innerHTML = '';
}

// -------------------------------------------------------------
// YouTube Cookies Management
// -------------------------------------------------------------
async function loadCookieStatus() {
  const badge = $('cookies-status-badge');
  const infoText = $('cookies-info-text');
  const deleteBtn = $('delete-cookies-btn');
  if (!badge) return;

  try {
    const res = await api('/api/cookies/status');
    if (res && res.configured) {
      const sizeKb = (res.size_bytes / 1024).toFixed(1);
      badge.className = 'badge badge-success';
      badge.textContent = `🟢 Cookies Active (${sizeKb} KB)`;
      if (infoText) infoText.textContent = `Active: ${res.filename} (${sizeKb} KB)`;
      if (deleteBtn) deleteBtn.style.display = 'inline-block';
    } else {
      badge.className = 'badge';
      badge.textContent = '⚪ No Cookies Configured';
      if (infoText) infoText.textContent = 'No cookies loaded (required only for age-restricted videos)';
      if (deleteBtn) deleteBtn.style.display = 'none';
    }
  } catch (e) {
    badge.className = 'badge badge-warning';
    badge.textContent = 'Status Unavailable';
  }
}

function setupCookiesManager() {
  const uploadBtn = $('upload-cookies-btn');
  const fileInput = $('cookies-file-input');
  const deleteBtn = $('delete-cookies-btn');

  if (uploadBtn && fileInput) {
    uploadBtn.onclick = () => fileInput.click();
    fileInput.onchange = async () => {
      const file = fileInput.files[0];
      if (!file) return;
      if (!file.name.toLowerCase().endsWith('.txt')) {
        return alert('Please select a valid .txt cookies file (Netscape format).');
      }
      const formData = new FormData();
      formData.append('file', file);

      uploadBtn.disabled = true;
      uploadBtn.textContent = 'Uploading...';
      try {
        const resp = await fetch('/api/cookies/upload', {
          method: 'POST',
          body: formData
        });
        const data = await resp.json();
        if (!resp.ok) throw new Error(data.detail || data.message || 'Upload failed');
        alert('✅ YouTube cookies uploaded successfully! Clipiest can now process age-restricted and private videos.');
        loadCookieStatus();
      } catch (e) {
        alert('❌ Error uploading cookies: ' + e.message);
      } finally {
        uploadBtn.disabled = false;
        uploadBtn.textContent = '📁 Upload cookies.txt';
        fileInput.value = '';
      }
    };
  }

  if (deleteBtn) {
    deleteBtn.onclick = async () => {
      if (!confirm('Remove YouTube cookies? Age-restricted videos will no longer download until you upload cookies again.')) return;
      try {
        await api('/api/cookies', { method: 'DELETE' });
        alert('Cookies removed.');
        loadCookieStatus();
      } catch (e) {
        alert('Error removing cookies: ' + e.message);
      }
    };
  }

  loadCookieStatus();
}

// -------------------------------------------------------------
// Legacy Make & Manual Export Triggers (Fallback)
// -------------------------------------------------------------
async function triggerMakeClips() {
  const url = $('video-url').value.trim();
  if (!url && !appState.sourceId) {
    return alert('Please paste a video URL or upload a file first.');
  }

  const payload = {
    url: url || undefined,
    id: appState.sourceId || undefined,
    count: Number($('clip-count')?.value || 4),
    min_len: Number($('min-len')?.value || 30),
    max_len: Number($('max-len')?.value || 60),
    mode: $('mode-select')?.value || 'fast',
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
  const url = $('video-url').value.trim();
  if (!appState.sourceId && !url) {
    return alert('Enter a video URL or upload a file first to export a custom slice.');
  }

  const payload = {
    id: appState.sourceId || undefined,
    url: url || undefined,
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
    } catch (_) { }
  }, 1200);
}

function renderClipCards(clips, container) {
  container.innerHTML = '';
  clips.forEach(clip => {
    const card = document.createElement('div');
    card.className = 'clip-card';
    const videoSrc = clip.file?.startsWith('/') ? clip.file : `/media/${clip.file}`;
    const startSec = Number(clip.start || 0);
    const endSec = Number(clip.end || (startSec + 30));
    const durSec = Math.max(1, Math.round(endSec - startSec));

    card.innerHTML = `
      <div class="clip-video-wrap">
        <video src="${videoSrc}" controls preload="metadata"></video>
      </div>
      <div class="clip-info">
        <div class="clip-title-row">
          <h4>${escapeHtml(clip.title || 'Clip')}</h4>
          <span class="viral-badge">Score: ${clip.score || 75}</span>
        </div>
        <div class="clip-time-row" style="margin: 4px 0 8px;">
          <span class="clip-time-badge">⏱ ${formatTime(startSec)} - ${formatTime(endSec)} (${durSec}s)</span>
        </div>
        ${clip.hook ? `<div class="clip-hook">"${escapeHtml(clip.hook)}"</div>` : ''}
        <div class="clip-actions">
          <a href="${videoSrc}" download="clipiest-${clip.id}.mp4" class="btn-secondary btn-sm">↓ MP4</a>
          <a href="/text/${clip.id}/srt" class="btn-secondary btn-sm">↓ SRT</a>
          <button type="button" class="btn-secondary btn-sm select-clip-btn">🎯 Select Slice</button>
        </div>
        <div class="stars-rating" data-id="${clip.id}">
          <span style="font-size:11px;color:var(--text-muted);margin-right:6px;">Tune AI:</span>
          ${[1, 2, 3, 4, 5].map(n => `<button class="star-btn" data-star="${n}">★</button>`).join('')}
        </div>
      </div>
    `;

    const selectSlice = () => {
      $('time-start').value = Math.round(startSec * 10) / 10;
      $('time-end').value = Math.round(endSec * 10) / 10;
      if (clip.hook) $('hook-input').value = clip.hook;
      if ($('source-status-badge')) {
        $('source-status-badge').textContent = `Slice: ${formatTime(startSec)} - ${formatTime(endSec)}`;
      }
      document.querySelectorAll('.clip-card').forEach(c => c.style.borderColor = 'var(--border)');
      card.style.borderColor = 'var(--cyan)';
    };

    card.querySelector('.select-clip-btn').onclick = (e) => {
      e.stopPropagation();
      selectSlice();
    };

    // Star rating
    card.querySelectorAll('.star-btn').forEach(star => {
      star.onclick = async (e) => {
        e.stopPropagation();
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
    } catch (_) { }
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
            <h4>${escapeHtml(clip.title)}</h4>
            <span class="viral-badge">${clip.layout}</span>
          </div>
          <div style="display:flex;align-items:center;gap:8px;margin: 4px 0 6px;">
            <span class="clip-time-badge">⏱ ${formatTime(clip.start || 0)} - ${formatTime(clip.end || 30)}</span>
            <small style="color:var(--text-muted);font-size:11px;">${new Date(clip.created * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</small>
          </div>
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
  } catch (_) { }
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

    if ($('source-status-badge')) {
      $('source-status-badge').textContent = `Re-editing: ${clipId}`;
    }
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
        if ($('source-status-badge')) {
          $('source-status-badge').textContent = `Creator Video: ${v.name}`;
        }
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
