let totalEnergyChartInstance = null;
let powerChartInstance = null;
let loadChartInstance = null;

// Round robin (baseline) stays a neutral mid-gray; energy-aware (the
// contribution) gets the single electric-blue accent — keeps the page's
// one-accent-color discipline instead of a two-hue comparison palette.
const CHART_PALETTE = {
  roundRobin: { dark: '#474747', light: '#707070' },
  energyAware: { dark: '#0060c2', light: '#0071e3' },
};

const CHART_GRID_COLOR = 'rgba(29, 29, 31, 0.08)';
const CHART_TEXT_COLOR = '#707070';

// Chart.js renders text/gridlines in black by default — make it match the
// Apple-style theme globally so every chart (current + future) picks this up.
if (typeof Chart !== 'undefined') {
  Chart.defaults.color = CHART_TEXT_COLOR;
  Chart.defaults.borderColor = CHART_GRID_COLOR;
  Chart.defaults.font.family = "'Inter', -apple-system, BlinkMacSystemFont, sans-serif";
  // No shadows anywhere in this system — flat bars only.
}

// Builds (and caches) a top-to-bottom gradient per canvas+color pair so
// bars read as lit from above instead of flat fills. Chart.js calls this
// on every render, including before the chart has a layout (chartArea is
// null on the very first pass) — fall back to the solid dark shade then.
const gradientCache = new Map();

function getBarGradient(chart, colorKey) {
  const { ctx, chartArea } = chart;
  if (!chartArea) return CHART_PALETTE[colorKey].dark;

  const cacheKey = `${chart.canvas.id}-${colorKey}`;
  const cached = gradientCache.get(cacheKey);
  if (cached && cached.top === chartArea.top && cached.bottom === chartArea.bottom) {
    return cached.gradient;
  }

  const gradient = ctx.createLinearGradient(0, chartArea.top, 0, chartArea.bottom);
  gradient.addColorStop(0, CHART_PALETTE[colorKey].light);
  gradient.addColorStop(1, CHART_PALETTE[colorKey].dark);
  gradientCache.set(cacheKey, { gradient, top: chartArea.top, bottom: chartArea.bottom });
  return gradient;
}

// Custom glass-style tooltip, replacing Chart.js's plain default box.
// Chart.js calls this with everything needed to build our own markup and
// position it relative to the canvas — we just render a styled div.
function glassTooltipHandler(context) {
  const { chart, tooltip } = context;
  const wrap = chart.canvas.parentElement;

  let tooltipEl = wrap.querySelector('.chart-tooltip');
  if (!tooltipEl) {
    tooltipEl = document.createElement('div');
    tooltipEl.className = 'chart-tooltip';
    wrap.appendChild(tooltipEl);
  }

  if (tooltip.opacity === 0) {
    tooltipEl.style.opacity = '0';
    return;
  }

  if (tooltip.body) {
    const titleLines = tooltip.title || [];
    let html = titleLines.length
      ? `<div class="chart-tooltip-title">${titleLines.join(' ')}</div>`
      : '';

    tooltip.body.forEach((bodyItem, i) => {
      const color = tooltip.labelColors[i];
      bodyItem.lines.forEach(line => {
        html += `<div class="chart-tooltip-row">
          <span class="chart-tooltip-dot" style="background:${color.backgroundColor}"></span>${line}
        </div>`;
      });
    });

    tooltipEl.innerHTML = html;
  }

  tooltipEl.style.opacity = '1';
  tooltipEl.style.left = `${tooltip.caretX}px`;
  tooltipEl.style.top = `${tooltip.caretY}px`;
}

const runBtn = document.getElementById('run-comparison-btn');
const summaryEl = document.getElementById('savings-summary');

function setRunning(isRunning) {
  runBtn.disabled = isRunning;
  runBtn.classList.toggle('is-loading', isRunning);
}

let latestComparisonData = null;
let chartsRenderedOnce = false;

async function loadComparison(customConfig = null) {
  setRunning(true);
  if (customConfig) {
    summaryEl.classList.add('is-updating');
  }

  try {
    const options = customConfig
      ? {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(customConfig),
        }
      : {};

    const res = await fetch('/api/compare', options);
    if (!res.ok) {
      const errBody = await res.json().catch(() => ({}));
      summaryEl.textContent = errBody.error
        ? `Couldn't run comparison: ${errBody.error}`
        : 'Failed to load data. Please try again.';
      summaryEl.classList.add('is-error');
      return;
    }

    const data = await res.json();
    summaryEl.classList.remove('is-error');
    latestComparisonData = data;
    renderSummary(data);

    // First page load: don't draw the charts yet — let the scroll observer
    // trigger it the moment the user actually scrolls to them, so the
    // draw-in animation is something they see rather than something that
    // already finished off-screen. Re-runs from the button always redraw
    // immediately since the user is already looking at that section.
    if (chartsRenderedOnce) {
      renderAllCharts(data);
    }

    if (!customConfig) {
      buildGpuControls(data.round_robin.gpus);
    } else {
      // Only POST requests (an explicit "Run Comparison" click) persist to
      // the database — refresh the history table to reflect the new row.
      loadHistory();
    }
  } catch (err) {
    summaryEl.textContent = 'Network error — is the server running?';
    summaryEl.classList.add('is-error');
  } finally {
    setRunning(false);
    summaryEl.classList.remove('is-updating');
  }
}

function renderSummary(data) {
  const direction = data.energy_savings_pct >= 0 ? 'saves' : 'costs';
  const magnitude = Math.abs(data.energy_savings_pct);
  summaryEl.textContent =
    `Energy-aware scheduling ${direction} ${magnitude}% total energy ` +
    `(${data.round_robin.total_energy_wh}Wh → ${data.energy_aware.total_energy_wh}Wh) ` +
    `to finish the same workload.`;

  const bigStatLabel = document.getElementById('big-stat-label');
  bigStatLabel.textContent = data.energy_savings_pct >= 0 ? 'energy saved' : 'energy cost increase';
  animateCountUp(document.getElementById('big-stat-number'), magnitude);

  updateHeroPreview(data);
  renderSecondaryStats(data);
  renderLatencyPanel(data);
}

// Makespan = time until the slowest GPU in this strategy finishes, i.e. the
// real wall-clock latency of the batch — not the same thing as total energy.
// Uses completion_time_sec, which /api/compare already returns per GPU, so
// this needs no backend changes.
function computeMakespanSeconds(gpuSummary) {
  if (!gpuSummary || !gpuSummary.length) return 0;
  return Math.max(...gpuSummary.map(g => g.completion_time_sec));
}

function renderLatencyPanel(data) {
  const rrEl = document.getElementById('latency-rr');
  const llEl = document.getElementById('latency-ll');
  const eaEl = document.getElementById('latency-ea');
  const verdictEl = document.getElementById('latency-verdict');
  if (!rrEl || !llEl || !eaEl) return;

  const rrMakespan = computeMakespanSeconds(data.round_robin.gpus);
  const llMakespan = computeMakespanSeconds(data.least_loaded.gpus);
  const eaMakespan = computeMakespanSeconds(data.energy_aware.gpus);

  rrEl.textContent = `${rrMakespan.toFixed(1)}s`;
  llEl.textContent = `${llMakespan.toFixed(1)}s`;
  eaEl.textContent = `${eaMakespan.toFixed(1)}s`;

  if (verdictEl) {
    const deltaVsRR = eaMakespan - rrMakespan;
    const deltaVsLL = eaMakespan - llMakespan;
    const worse = deltaVsRR > 0 || deltaVsLL > 0;
    const magnitude = Math.max(Math.abs(deltaVsRR), Math.abs(deltaVsLL));

    verdictEl.textContent = worse
      ? `Energy-aware scheduling is ${magnitude.toFixed(1)}s slower at worst here — a real ` +
        `latency trade-off worth knowing about, not something the energy number alone shows.`
      : `Energy-aware scheduling doesn't cost latency here — it matches or beats both ` +
        `baselines' makespan while also using less energy.`;
  }
}

// Renders the three supporting stats under the headline number: savings
// against the *stronger* Least-Loaded baseline (not just naive Round-Robin),
// and an explicitly-labeled at-scale cost/carbon projection so the raw Wh
// figure means something to a reader without a power-engineering background.
function renderSecondaryStats(data) {
  const vsLeastLoadedEl = document.getElementById('stat-vs-least-loaded');
  const usdEl = document.getElementById('stat-usd');
  const co2El = document.getElementById('stat-co2');
  const disclaimerEl = document.getElementById('scale-disclaimer');
  if (!vsLeastLoadedEl || !usdEl || !co2El) return;

  if (typeof data.energy_savings_vs_least_loaded_pct === 'number') {
    vsLeastLoadedEl.textContent = `${data.energy_savings_vs_least_loaded_pct.toFixed(2)}%`;
  }

  const scale = data.at_scale_projection;
  if (scale) {
    usdEl.textContent = `$${scale.usd_saved.toLocaleString()}`;
    co2El.textContent = `${scale.kg_co2_saved.toLocaleString()} kg`;
    if (disclaimerEl) {
      disclaimerEl.textContent =
        `Illustrative: assumes a fleet ${scale.multiplier.toLocaleString()}x the size of this demo trace, ` +
        `US-average grid pricing ($0.12/kWh) and carbon intensity (0.417 kg CO₂e/kWh). Not a measurement of ` +
        `any real deployment.`;
    }
  }
}

let sensitivityChartInstance = null;

async function loadSensitivity() {
  const canvas = document.getElementById('sensitivityChart');
  if (!canvas) return;

  try {
    const res = await fetch('/api/sensitivity');
    if (!res.ok) return;
    const data = await res.json();
    renderSensitivityChart(data.sweep);
    updateHeroScaleNote(data.sweep);
  } catch (err) {
    // Non-critical enhancement — fail silently and leave the section title
    // + explanation visible without the chart rather than breaking the page.
  }
}

// Surfaces the strongest point of the heterogeneity sweep (highest savings
// vs. Round-Robin, which the sweep guarantees is the last/most-heterogeneous
// point) right next to the flat headline %, so a visitor isn't left with
// just "3%" as the whole story. Runs independently of updateHeroPreview —
// whichever of the two API calls (/api/compare, /api/sensitivity) resolves
// second is the one that actually reveals the note, and each guards its own
// element so there's no ordering dependency between them.
function updateHeroScaleNote(sweep) {
  const noteEl = document.getElementById('hero-result-scale-note');
  if (!noteEl || !sweep || !sweep.length) return;

  const peak = sweep.reduce((max, pt) =>
    pt.savings_vs_round_robin_pct > max.savings_vs_round_robin_pct ? pt : max
  );

  if (peak.savings_vs_round_robin_pct <= 0) return;

  noteEl.textContent =
    `Scales up to ${peak.savings_vs_round_robin_pct.toFixed(1)}% as fleet heterogeneity grows`;
  noteEl.hidden = false;
}

function renderSensitivityChart(sweep) {
  const canvas = document.getElementById('sensitivityChart');
  if (!canvas || !sweep || !sweep.length) return;

  if (sensitivityChartInstance) sensitivityChartInstance.destroy();

  const labels = sweep.map(pt => `${Math.round(pt.heterogeneity * 100)}%`);

  sensitivityChartInstance = new Chart(canvas, {
    type: 'line',
    data: {
      labels,
      datasets: [
        {
          label: 'Savings vs. Round-Robin',
          data: sweep.map(pt => pt.savings_vs_round_robin_pct),
          borderColor: CHART_PALETTE.roundRobin.light,
          backgroundColor: 'transparent',
          tension: 0.3,
          pointRadius: 3,
        },
        {
          label: 'Savings vs. Least-Loaded',
          data: sweep.map(pt => pt.savings_vs_least_loaded_pct),
          borderColor: CHART_PALETTE.energyAware.light,
          backgroundColor: 'transparent',
          tension: 0.3,
          pointRadius: 3,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: {
          title: { display: true, text: 'Fleet heterogeneity (100% = your configured fleet)' },
          grid: { color: CHART_GRID_COLOR },
        },
        y: {
          title: { display: true, text: 'Energy savings (%)' },
          grid: { color: CHART_GRID_COLOR },
        },
      },
      plugins: {
        legend: { position: 'bottom' },
      },
    },
  });
}

// Mirrors the same real comparison result into the hero's result preview
// card. Deliberately reads from the same `data` object as the rest of the
// dashboard — never hardcoded — and stays hidden until a real result exists.
function updateHeroPreview(data) {
  const preview = document.getElementById('hero-result-preview');
  const pctEl = document.getElementById('hero-result-pct');
  const labelEl = document.getElementById('hero-result-preview-label');
  const detailEl = document.getElementById('hero-result-detail');
  if (!preview || !pctEl || !labelEl || !detailEl) return;

  const magnitude = Math.abs(data.energy_savings_pct);
  labelEl.textContent = data.energy_savings_pct >= 0 ? 'Energy Saved' : 'Energy Cost Increase';
  pctEl.textContent = `${magnitude.toFixed(2)}%`;
  detailEl.textContent = `${data.round_robin.total_energy_wh} Wh → ${data.energy_aware.total_energy_wh} Wh`;
  preview.hidden = false;
}

const COUNT_UP_DURATION_MS = 900;

function animateCountUp(el, targetValue) {
  const startValue = 0;
  const startTime = performance.now();

  function easeOutQuart(t) {
    return 1 - Math.pow(1 - t, 4);
  }

  function step(now) {
    const elapsed = now - startTime;
    const progress = Math.min(elapsed / COUNT_UP_DURATION_MS, 1);
    const eased = easeOutQuart(progress);
    const current = startValue + (targetValue - startValue) * eased;
    el.textContent = current.toFixed(2);

    if (progress < 1) {
      requestAnimationFrame(step);
    } else {
      el.textContent = targetValue.toFixed(2);
    }
  }

  requestAnimationFrame(step);
}

function gpuLabels(gpus) {
  return gpus.map(g => `GPU ${g.gpu_id} (${g.efficiency_factor}x eff, ${g.compute_capability}x speed)`);
}

function baseChartOptions(titleText) {
  return {
    responsive: true,
    maintainAspectRatio: false,
    // Slimmer, more evenly spaced bars read as deliberate data-viz rather
    // than default-width filler blocks.
    datasets: {
      bar: {
        categoryPercentage: 0.55,
        barPercentage: 0.85,
        maxBarThickness: 40,
        borderSkipped: false,
      },
    },
    animation: {
      duration: 800,
      easing: 'easeOutQuart',
      delay: (context) => {
        if (context.type === 'data' && context.mode === 'default') {
          return context.dataIndex * 90 + context.datasetIndex * 120;
        }
        return 0;
      },
    },
    plugins: {
      title: { display: true, text: titleText, font: { size: 14, weight: '600' } },
      legend: { position: 'top', labels: { usePointStyle: true, boxWidth: 8 } },
      tooltip: {
        enabled: false,
        mode: 'index',
        intersect: false,
        external: glassTooltipHandler,
      },
    },
    scales: {
      y: {
        beginAtZero: true,
        grid: { color: CHART_GRID_COLOR, drawTicks: false },
        border: { display: false },
        ticks: { color: CHART_TEXT_COLOR, padding: 10 },
      },
      x: {
        grid: { display: false },
        border: { display: false },
        ticks: { color: CHART_TEXT_COLOR, padding: 8 },
      },
    },
  };
}

function renderTotalEnergyChart(data) {
  if (totalEnergyChartInstance) totalEnergyChartInstance.destroy();
  totalEnergyChartInstance = new Chart(document.getElementById('totalEnergyChart'), {
    type: 'bar',
    data: {
      labels: gpuLabels(data.round_robin.gpus),
      datasets: [
        {
          label: 'Round-Robin (Wh)',
          data: data.round_robin.gpus.map(g => g.total_energy_wh),
          backgroundColor: (ctx) => getBarGradient(ctx.chart, 'roundRobin'),
          hoverBackgroundColor: CHART_PALETTE.roundRobin.light,
          borderRadius: 10,
        },
        {
          label: 'Energy-Aware (Wh)',
          data: data.energy_aware.gpus.map(g => g.total_energy_wh),
          backgroundColor: (ctx) => getBarGradient(ctx.chart, 'energyAware'),
          hoverBackgroundColor: CHART_PALETTE.energyAware.light,
          borderRadius: 10,
        },
      ],
    },
    options: baseChartOptions('Per-GPU Total Energy to Finish Workload'),
  });
}

function renderPowerChart(data) {
  if (powerChartInstance) powerChartInstance.destroy();
  powerChartInstance = new Chart(document.getElementById('energyChart'), {
    type: 'bar',
    data: {
      labels: gpuLabels(data.round_robin.gpus),
      datasets: [
        {
          label: 'Round-Robin (W)',
          data: data.round_robin.gpus.map(g => g.energy_watts),
          backgroundColor: (ctx) => getBarGradient(ctx.chart, 'roundRobin'),
          hoverBackgroundColor: CHART_PALETTE.roundRobin.light,
          borderRadius: 10,
        },
        {
          label: 'Energy-Aware (W)',
          data: data.energy_aware.gpus.map(g => g.energy_watts),
          backgroundColor: (ctx) => getBarGradient(ctx.chart, 'energyAware'),
          hoverBackgroundColor: CHART_PALETTE.energyAware.light,
          borderRadius: 10,
        },
      ],
    },
    options: baseChartOptions('Per-GPU Instantaneous Power Draw'),
  });
}

function renderLoadChart(data) {
  if (loadChartInstance) loadChartInstance.destroy();
  loadChartInstance = new Chart(document.getElementById('loadChart'), {
    type: 'bar',
    data: {
      labels: gpuLabels(data.round_robin.gpus),
      datasets: [
        {
          label: 'Round-Robin (tokens)',
          data: data.round_robin.gpus.map(g => g.load),
          backgroundColor: (ctx) => getBarGradient(ctx.chart, 'roundRobin'),
          hoverBackgroundColor: CHART_PALETTE.roundRobin.light,
          borderRadius: 10,
        },
        {
          label: 'Energy-Aware (tokens)',
          data: data.energy_aware.gpus.map(g => g.load),
          backgroundColor: (ctx) => getBarGradient(ctx.chart, 'energyAware'),
          hoverBackgroundColor: CHART_PALETTE.energyAware.light,
          borderRadius: 10,
        },
      ],
    },
    options: baseChartOptions('Per-GPU Load Distribution'),
  });
}

const historyTableEl = document.getElementById('history-table');
const historyTableBodyEl = document.getElementById('history-table-body');
const historyEmptyEl = document.getElementById('history-empty');

async function loadHistory() {
  try {
    const res = await fetch('/api/history');
    if (!res.ok) return;

    const runs = await res.json();
    renderHistoryTable(runs);
  } catch (err) {
    // History is a nice-to-have — a failed fetch here shouldn't break the
    // rest of the dashboard, so we just leave the empty-state message up.
  }
}

function formatHistoryTimestamp(isoString) {
  const date = new Date(isoString);
  if (Number.isNaN(date.getTime())) return isoString;

  return date.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function renderHistoryTable(runs) {
  if (!runs.length) {
    historyTableEl.hidden = true;
    historyEmptyEl.hidden = false;
    return;
  }

  historyTableEl.hidden = false;
  historyEmptyEl.hidden = true;
  historyTableBodyEl.innerHTML = '';

  runs.forEach((run, index) => {
    const row = document.createElement('tr');
    const savingsClass = run.energy_savings_pct >= 0 ? 'savings-positive' : 'savings-negative';

    row.innerHTML = `
      <td>${runs.length - index}</td>
      <td>${formatHistoryTimestamp(run.created_at)}</td>
      <td class="${savingsClass}">${run.energy_savings_pct}%</td>
      <td>${run.round_robin_total_wh}</td>
      <td>${run.energy_aware_total_wh}</td>
    `;
    historyTableBodyEl.appendChild(row);
  });
}

function buildGpuControls(gpus) {
  const container = document.getElementById('gpu-controls');
  container.innerHTML = '';

  gpus.forEach(gpu => {
    const card = document.createElement('div');
    card.className = 'gpu-control-card';
    card.innerHTML = `
      <h3>GPU ${gpu.gpu_id}</h3>
      <label class="slider-label">
        <span class="slider-name">Efficiency</span>
        <span class="val" id="eff-val-${gpu.gpu_id}">${gpu.efficiency_factor}x</span>
      </label>
      <input type="range" id="eff-${gpu.gpu_id}" min="0.1" max="3.0" step="0.1" value="${gpu.efficiency_factor}" class="slider slider-eff">

      <label class="slider-label">
        <span class="slider-name">Speed</span>
        <span class="val" id="speed-val-${gpu.gpu_id}">${gpu.compute_capability}x</span>
      </label>
      <input type="range" id="speed-${gpu.gpu_id}" min="0.1" max="4.0" step="0.1" value="${gpu.compute_capability}" class="slider slider-speed">
    `;
    container.appendChild(card);
  });

  gpus.forEach(gpu => {
    const effInput = document.getElementById(`eff-${gpu.gpu_id}`);
    const speedInput = document.getElementById(`speed-${gpu.gpu_id}`);
    effInput.addEventListener('input', () => {
      document.getElementById(`eff-val-${gpu.gpu_id}`).textContent = `${effInput.value}x`;
    });
    speedInput.addEventListener('input', () => {
      document.getElementById(`speed-val-${gpu.gpu_id}`).textContent = `${speedInput.value}x`;
    });
  });
}

function renderAllCharts(data) {
  chartsRenderedOnce = true;
  renderTotalEnergyChart(data);
  renderPowerChart(data);
  renderLoadChart(data);
}

// Fire the (currently unrendered) charts the first time their section
// scrolls into view, so the draw-in/stagger animation actually plays in
// front of the user instead of finishing off-screen during page load.
const firstChartCard = document.getElementById('totalEnergyChart') &&
  document.getElementById('totalEnergyChart').closest('.chart-card');

if (firstChartCard) {
  const chartRevealObserver = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (entry.isIntersecting && latestComparisonData && !chartsRenderedOnce) {
          renderAllCharts(latestComparisonData);
          chartRevealObserver.disconnect();
        }
      }
    },
    { threshold: 0.2 }
  );
  chartRevealObserver.observe(firstChartCard);
}

function collectGpuConfig() {
  const efficiency_factors = [];
  const compute_capabilities = [];

  let i = 0;
  while (document.getElementById(`eff-${i}`)) {
    efficiency_factors.push(parseFloat(document.getElementById(`eff-${i}`).value));
    compute_capabilities.push(parseFloat(document.getElementById(`speed-${i}`).value));
    i++;
  }

  return { efficiency_factors, compute_capabilities };
}

runBtn.addEventListener('click', () => {
  loadComparison(collectGpuConfig());
});

loadComparison();
loadHistory();
loadSensitivity();