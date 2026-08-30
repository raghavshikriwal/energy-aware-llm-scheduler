// Live GPU Lab frontend.
//
// Everything shown here comes from /api/live/* responses, which are
// themselves either a real GPU worker's measurements or an honest
// "offline" state. This file never invents numbers to fill a gap; a
// missing value renders as "—" rather than 0 or a placeholder.

const STATUS_POLL_MS = 5000;

const statusDot = document.getElementById('status-dot');
const statusText = document.getElementById('status-text');
const gpuGrid = document.getElementById('gpu-card-grid');
const gpuEmptyState = document.getElementById('gpu-empty-state');
const runBtn = document.getElementById('run-inference-btn');
const runBtnHint = document.getElementById('run-btn-hint');
const form = document.getElementById('inference-form');
const resultPanel = document.getElementById('result-panel');
const resultGrid = document.getElementById('result-grid');
const resultText = document.getElementById('result-text');
const resultRequestId = document.getElementById('result-request-id');
const resultStrategyTag = document.getElementById('result-strategy-tag');

let isOnline = false;
let requestCounter = 0;

function fmt(value, unit = '') {
  if (value === null || value === undefined) {
    return { text: '—', unknown: true };
  }
  if (typeof value === 'number') {
    return { text: `${value.toLocaleString(undefined, { maximumFractionDigits: 2 })}${unit}`, unknown: false };
  }
  return { text: `${value}${unit}`, unknown: false };
}

function setOnline(online, reason) {
  isOnline = online;
  statusDot.classList.toggle('is-online', online);
  statusDot.classList.toggle('is-offline', !online);

  if (online) {
    statusText.textContent = 'GPU SERVER ONLINE';
    runBtn.disabled = false;
    runBtnHint.textContent = '';
    runBtnHint.classList.remove('is-error');
  } else {
    statusText.textContent = `GPU SERVER OFFLINE${reason ? ' — ' + reason : ''}`;
    runBtn.disabled = true;
    runBtnHint.textContent = 'GPU server offline — start the worker to enable real inference.';
    gpuGrid.innerHTML = '';
    gpuGrid.appendChild(gpuEmptyState);
    gpuEmptyState.textContent = 'GPU server offline.';
  }
}

async function pollStatus() {
  try {
    const res = await fetch('/api/live/status');
    const data = await res.json();
    setOnline(Boolean(data.online), data.reason || null);
    if (data.online) {
      loadGpus();
    }
  } catch (err) {
    setOnline(false, 'could not reach the app server');
  }
}

function renderGpuCard(gpu) {
  const card = document.createElement('div');
  card.className = 'gpu-card';

  const stat = (label, value, unit = '') => {
    const { text, unknown } = fmt(value, unit);
    return `<div class="gpu-stat-row">
      <span class="gpu-stat-label">${label}</span>
      <span class="gpu-stat-value${unknown ? ' is-unknown' : ''}">${text}</span>
    </div>`;
  };

  card.innerHTML = `
    <div class="gpu-card-title-row">
      <span class="gpu-card-index">GPU ${gpu.index}</span>
      <span class="gpu-card-badge">ONLINE</span>
    </div>
    <p class="gpu-card-name">${gpu.name}</p>
    ${stat('Utilization', gpu.utilization_pct, '%')}
    ${stat('VRAM used', gpu.memory_used_mb ? Math.round(gpu.memory_used_mb) : null, ' MB')}
    ${stat('VRAM total', gpu.memory_total_mb ? Math.round(gpu.memory_total_mb) : null, ' MB')}
    ${stat('Temperature', gpu.temperature_c, '°C')}
    ${stat('Power draw', gpu.power_draw_w, ' W')}
    ${stat('Power limit', gpu.power_limit_w, ' W')}
    ${stat('SM clock', gpu.sm_clock_mhz, ' MHz')}
    ${stat('Mem clock', gpu.mem_clock_mhz, ' MHz')}
  `;
  return card;
}

async function loadGpus() {
  try {
    const res = await fetch('/api/live/gpus');
    const data = await res.json();
    const gpus = data.gpus || [];

    gpuGrid.innerHTML = '';
    if (gpus.length === 0) {
      gpuEmptyState.textContent = 'GPU server online, but no GPU is currently visible to it.';
      gpuGrid.appendChild(gpuEmptyState);
      return;
    }
    gpus.forEach((gpu) => gpuGrid.appendChild(renderGpuCard(gpu)));
  } catch (err) {
    // Status poll will catch and reflect the offline state on its own cycle.
  }
}

function renderResult(data, strategyLabel) {
  requestCounter += 1;
  resultRequestId.textContent = `#${String(requestCounter).padStart(4, '0')}`;
  resultStrategyTag.textContent = strategyLabel;

  const m = data.measurement || {};
  const gpuName = data.selected_gpu ? `${data.selected_gpu.name} (GPU ${data.selected_gpu.index})` : null;

  const stats = [
    ['Input tokens', data.input_tokens],
    ['Output tokens', data.output_tokens],
    ['Selected GPU', gpuName],
    ['Inference time', m.elapsed_sec, ' s'],
    ['Average power', m.avg_power_w, ' W'],
    ['Energy consumed', m.energy_wh, ' Wh'],
    ['Throughput', data.throughput_tokens_per_sec, ' tok/s'],
    ['Energy / token', data.energy_per_token_wh, ' Wh'],
  ];

  resultGrid.innerHTML = stats.map(([label, value, unit]) => {
    const { text, unknown } = fmt(value, unit || '');
    return `<div class="result-stat">
      <p class="result-stat-label">${label}</p>
      <p class="result-stat-value${unknown ? ' is-unknown' : ''}">${text}</p>
    </div>`;
  }).join('');

  resultText.textContent = data.text || '';
  resultPanel.hidden = false;
  resultPanel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  if (!isOnline) return;

  const prompt = document.getElementById('prompt-input').value;
  const maxNewTokens = parseInt(document.getElementById('max-tokens-input').value, 10);
  const strategySelect = document.getElementById('strategy-select');
  const strategy = strategySelect.value;
  const strategyLabel = strategySelect.options[strategySelect.selectedIndex].text;

  runBtn.disabled = true;
  runBtn.textContent = 'Running on real GPU…';
  runBtnHint.textContent = '';
  runBtnHint.classList.remove('is-error');

  try {
    const res = await fetch('/api/live/inference', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt, max_new_tokens: maxNewTokens, strategy }),
    });
    const data = await res.json();

    if (!res.ok) {
      runBtnHint.textContent = data.error || 'The GPU worker returned an error.';
      runBtnHint.classList.add('is-error');
    } else {
      renderResult(data, strategyLabel);
    }
  } catch (err) {
    runBtnHint.textContent = 'Request failed — GPU server may have gone offline.';
    runBtnHint.classList.add('is-error');
  } finally {
    runBtn.disabled = !isOnline;
    runBtn.textContent = 'Run Real Inference';
  }
});

pollStatus();
setInterval(pollStatus, STATUS_POLL_MS);