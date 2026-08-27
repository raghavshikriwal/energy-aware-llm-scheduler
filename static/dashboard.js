async function loadComparison() {
  const res = await fetch('/api/compare');
  if (!res.ok) {
    document.getElementById('savings-summary').textContent = 'Failed to load data.';
    return;
  }
  const data = await res.json();
  renderSummary(data);
  renderTotalEnergyChart(data);
  renderPowerChart(data);
  renderLoadChart(data);
}

function renderSummary(data) {
  document.getElementById('savings-summary').textContent =
    `Energy-aware scheduling saves ${data.energy_savings_pct}% total energy ` +
    `(${data.round_robin.total_energy_wh}Wh → ${data.energy_aware.total_energy_wh}Wh) ` +
    `to finish the same workload.`;
}

function gpuLabels(gpus) {
  return gpus.map(g => `GPU ${g.gpu_id} (${g.efficiency_factor}x eff, ${g.compute_capability}x speed)`);
}

function renderTotalEnergyChart(data) {
  new Chart(document.getElementById('totalEnergyChart'), {
    type: 'bar',
    data: {
      labels: gpuLabels(data.round_robin.gpus),
      datasets: [
        {
          label: 'Round-Robin (Wh)',
          data: data.round_robin.gpus.map(g => g.total_energy_wh),
          backgroundColor: '#e67e22',
        },
        {
          label: 'Energy-Aware (Wh)',
          data: data.energy_aware.gpus.map(g => g.total_energy_wh),
          backgroundColor: '#27ae60',
        },
      ],
    },
    options: {
      responsive: false,
      plugins: { title: { display: true, text: 'Per-GPU Total Energy to Finish Workload' } },
    },
  });
}

function renderPowerChart(data) {
  new Chart(document.getElementById('energyChart'), {
    type: 'bar',
    data: {
      labels: gpuLabels(data.round_robin.gpus),
      datasets: [
        {
          label: 'Round-Robin (W)',
          data: data.round_robin.gpus.map(g => g.energy_watts),
          backgroundColor: '#e67e22',
        },
        {
          label: 'Energy-Aware (W)',
          data: data.energy_aware.gpus.map(g => g.energy_watts),
          backgroundColor: '#27ae60',
        },
      ],
    },
    options: {
      responsive: false,
      plugins: { title: { display: true, text: 'Per-GPU Instantaneous Power Draw' } },
    },
  });
}

function renderLoadChart(data) {
  new Chart(document.getElementById('loadChart'), {
    type: 'bar',
    data: {
      labels: gpuLabels(data.round_robin.gpus),
      datasets: [
        {
          label: 'Round-Robin (tokens)',
          data: data.round_robin.gpus.map(g => g.load),
          backgroundColor: '#e67e22',
        },
        {
          label: 'Energy-Aware (tokens)',
          data: data.energy_aware.gpus.map(g => g.load),
          backgroundColor: '#27ae60',
        },
      ],
    },
    options: {
      responsive: false,
      plugins: { title: { display: true, text: 'Per-GPU Load Distribution' } },
    },
  });
}

loadComparison();
