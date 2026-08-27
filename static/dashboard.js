let totalEnergyChartInstance = null;
let powerChartInstance = null;
let loadChartInstance = null;

const CHART_PALETTE = {
  roundRobin: '#e67e22',
  energyAware: '#27ae60',
};

const runBtn = document.getElementById('run-comparison-btn');
const summaryEl = document.getElementById('savings-summary');

function setRunning(isRunning) {
  runBtn.disabled = isRunning;
  runBtn.classList.toggle('is-loading', isRunning);
}

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
    renderSummary(data);
    renderTotalEnergyChart(data);
    renderPowerChart(data);
    renderLoadChart(data);

    if (!customConfig) {
      buildGpuControls(data.round_robin.gpus);
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
}

function gpuLabels(gpus) {
  return gpus.map(g => `GPU ${g.gpu_id} (${g.efficiency_factor}x eff, ${g.compute_capability}x speed)`);
}

function baseChartOptions(titleText) {
  return {
    responsive: true,
    maintainAspectRatio: false,
    animation: { duration: 400, easing: 'easeOutQuart' },
    plugins: {
      title: { display: true, text: titleText, font: { size: 14, weight: '600' } },
      legend: { position: 'top', labels: { usePointStyle: true, boxWidth: 8 } },
      tooltip: { mode: 'index', intersect: false },
    },
    scales: {
      y: { beginAtZero: true, grid: { color: 'rgba(0,0,0,0.06)' } },
      x: { grid: { display: false } },
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
          backgroundColor: CHART_PALETTE.roundRobin,
          borderRadius: 4,
        },
        {
          label: 'Energy-Aware (Wh)',
          data: data.energy_aware.gpus.map(g => g.total_energy_wh),
          backgroundColor: CHART_PALETTE.energyAware,
          borderRadius: 4,
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
          backgroundColor: CHART_PALETTE.roundRobin,
          borderRadius: 4,
        },
        {
          label: 'Energy-Aware (W)',
          data: data.energy_aware.gpus.map(g => g.energy_watts),
          backgroundColor: CHART_PALETTE.energyAware,
          borderRadius: 4,
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
          backgroundColor: CHART_PALETTE.roundRobin,
          borderRadius: 4,
        },
        {
          label: 'Energy-Aware (tokens)',
          data: data.energy_aware.gpus.map(g => g.load),
          backgroundColor: CHART_PALETTE.energyAware,
          borderRadius: 4,
        },
      ],
    },
    options: baseChartOptions('Per-GPU Load Distribution'),
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