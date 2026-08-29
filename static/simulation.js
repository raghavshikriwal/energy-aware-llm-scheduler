// Self-contained, visual-only mini simulation. Uses fixed illustrative
// GPU profiles (not the real backend) purely to demonstrate the *idea*
// of round-robin vs. energy-aware routing in an animated, at-a-glance way.

const SIM_GPUS = [
  { id: 0, label: 'GPU 0', costPerJob: 5, color: '#e74c3c' },  // least efficient
  { id: 1, label: 'GPU 1', costPerJob: 3.5, color: '#e67e22' },
  { id: 2, label: 'GPU 2', costPerJob: 2, color: '#2ecc71' },
  { id: 3, label: 'GPU 3', costPerJob: 1, color: '#27ae60' },  // most efficient
];

const SIM_JOB_COUNT = 16;
const SIM_JOB_INTERVAL_MS = 380;

let simRunning = false;

function buildGpuBoxes(containerId) {
  const container = document.getElementById(containerId);
  container.innerHTML = '';
  SIM_GPUS.forEach(gpu => {
    const box = document.createElement('div');
    box.className = 'sim-gpu-box';
    box.id = `${containerId}-box-${gpu.id}`;
    box.style.setProperty('--gpu-color', gpu.color);
    box.innerHTML = `
      <span class="sim-gpu-label">${gpu.label}</span>
      <span class="sim-gpu-load" id="${containerId}-load-${gpu.id}">0</span>
      <span class="sim-gpu-pulse"></span>
    `;
    container.appendChild(box);
  });
}

function spawnJob(trackId, targetGpuId, containerPrefix) {
  const track = document.getElementById(trackId);
  const targetBox = document.getElementById(`${containerPrefix}-box-${targetGpuId}`);
  if (!track || !targetBox) return;

  const gpu = SIM_GPUS.find(g => g.id === targetGpuId);
  const dot = document.createElement('div');
  dot.className = 'sim-job-dot';
  dot.style.background = gpu.color;
  track.appendChild(dot);

  const trackRect = track.getBoundingClientRect();
  const targetRect = targetBox.getBoundingClientRect();
  const deltaX = targetRect.left - trackRect.left + targetRect.width / 2 - 6;

  requestAnimationFrame(() => {
    dot.style.transform = `translateX(${deltaX}px)`;
    dot.style.opacity = '0';
  });

  setTimeout(() => {
    dot.remove();
    targetBox.classList.add('sim-gpu-hit');
    setTimeout(() => targetBox.classList.remove('sim-gpu-hit'), 300);
  }, 650);
}

function runLane({ trackId, containerPrefix, totalElId, strategy }) {
  return new Promise(resolve => {
    const loads = SIM_GPUS.map(() => 0);
    let total = 0;
    let rrIndex = 0;

    let jobsDone = 0;
    const interval = setInterval(() => {
      if (jobsDone >= SIM_JOB_COUNT) {
        clearInterval(interval);
        resolve(total);
        return;
      }

      let targetId;
      if (strategy === 'round-robin') {
        targetId = rrIndex % SIM_GPUS.length;
        rrIndex++;
      } else {
        // energy-aware: always pick lowest current marginal-ish cost
        // (illustrative: cost grows slightly as load accumulates, so it
        // isn't a flat "always pick GPU 3" outcome)
        let bestIdx = 0;
        let bestCost = Infinity;
        SIM_GPUS.forEach((gpu, idx) => {
          const projectedCost = gpu.costPerJob * (1 + loads[idx] * 0.06);
          if (projectedCost < bestCost) {
            bestCost = projectedCost;
            bestIdx = idx;
          }
        });
        targetId = bestIdx;
      }

      const gpu = SIM_GPUS[targetId];
      const cost = gpu.costPerJob * (1 + loads[targetId] * 0.06);
      loads[targetId] += 1;
      total += cost;

      spawnJob(trackId, targetId, containerPrefix);

      const loadEl = document.getElementById(`${containerPrefix}-load-${targetId}`);
      if (loadEl) loadEl.textContent = loads[targetId];

      document.getElementById(totalElId).textContent = Math.round(total);

      jobsDone++;
    }, SIM_JOB_INTERVAL_MS);
  });
}

async function runSimulation() {
  if (simRunning) return;
  simRunning = true;

  const btn = document.getElementById('sim-run-btn');
  btn.disabled = true;
  btn.classList.add('is-loading');

  document.getElementById('sim-verdict').hidden = true;
  buildGpuBoxes('sim-gpus-rr');
  buildGpuBoxes('sim-gpus-ea');
  document.getElementById('sim-total-rr').textContent = '0';
  document.getElementById('sim-total-ea').textContent = '0';

  const [rrTotal, eaTotal] = await Promise.all([
    runLane({
      trackId: 'sim-track-rr',
      containerPrefix: 'sim-gpus-rr',
      totalElId: 'sim-total-rr',
      strategy: 'round-robin',
    }),
    runLane({
      trackId: 'sim-track-ea',
      containerPrefix: 'sim-gpus-ea',
      totalElId: 'sim-total-ea',
      strategy: 'energy-aware',
    }),
  ]);

  const savings = ((rrTotal - eaTotal) / rrTotal * 100).toFixed(1);
  const verdict = document.getElementById('sim-verdict');
  verdict.hidden = false;
  verdict.textContent = `Energy-aware routing used ${savings}% less energy on this run.`;

  btn.disabled = false;
  btn.classList.remove('is-loading');
  simRunning = false;
}

document.addEventListener('DOMContentLoaded', () => {
  buildGpuBoxes('sim-gpus-rr');
  buildGpuBoxes('sim-gpus-ea');

  const btn = document.getElementById('sim-run-btn');
  if (btn) btn.addEventListener('click', runSimulation);
});