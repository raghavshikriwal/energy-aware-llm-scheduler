// Lightweight keyword-overlap FAQ matcher — no backend/API required.

const FAQ_ENTRIES = [
  {
    keywords: ['what', 'project', 'do', 'about', 'purpose'],
    question: "What does this project do?",
    answer: "It simulates a fleet of heterogeneous cloud GPUs and compares two ways of routing LLM inference requests to them: a naive round-robin baseline, and an energy-aware scheduler that routes each request to whichever GPU currently has the lowest marginal energy cost."
  },
  {
    keywords: ['marginal', 'cost', 'energy', 'mean', 'why'],
    question: "What is marginal energy cost?",
    answer: "It's the extra energy a GPU would burn to handle just one more request, given its current load — not its total energy for the whole workload. Comparing totals instead of marginals was actually a real bug we found and fixed in this project's history."
  },
  {
    keywords: ['real', 'gpu', 'hardware', 'actual', 'live', 'cluster'],
    question: "Is this using real GPUs?",
    answer: "No — this is a synthetic simulation. Each GPU is modeled with two traits, an efficiency factor and a compute capability, and power/energy are computed from a simple physical model rather than measured from real hardware."
  },
  {
    keywords: ['who', 'built', 'author', 'made', 'created'],
    question: "Who built this?",
    answer: "Raghav Shikriwal, a BTech IT student at NSUT, as a Cloud Computing course project."
  },
  {
    keywords: ['savings', 'percent', 'how much', 'better'],
    question: "How much energy does the energy-aware scheduler actually save?",
    answer: "It depends on the GPU fleet you configure — try the sliders above. On the default fleet it typically saves a few percent versus round-robin; the more spread out the GPUs' efficiency and speed are, the more there is to gain."
  },
  {
    keywords: ['slider', 'try', 'custom', 'configure', 'change'],
    question: "Can I try my own GPU configuration?",
    answer: "Yes — scroll up to \"Try Your Own GPU Fleet,\" adjust each GPU's efficiency and speed sliders, and hit Run Comparison to see live results."
  },
  {
    keywords: ['source', 'code', 'github', 'open'],
    question: "Is the source code available?",
    answer: "Yes, it's open on GitHub — see the link in the Author section above."
  },
];

function scoreMatch(input, entry) {
  const words = input.toLowerCase().split(/\W+/).filter(Boolean);
  let score = 0;
  entry.keywords.forEach(kw => {
    if (words.some(w => w.includes(kw) || kw.includes(w))) score += 1;
  });
  return score;
}

function findBestAnswer(input) {
  if (!input.trim()) return null;
  let best = null;
  let bestScore = 0;
  FAQ_ENTRIES.forEach(entry => {
    const s = scoreMatch(input, entry);
    if (s > bestScore) {
      bestScore = s;
      best = entry;
    }
  });
  return bestScore > 0 ? best : null;
}

function showAnswer(entry, rawInput) {
  const box = document.getElementById('faq-answer');
  if (!box) return;
  box.hidden = false;
  if (entry) {
    box.classList.remove('faq-answer-empty');
    box.innerHTML = `<strong>${entry.question}</strong><p>${entry.answer}</p>`;
  } else {
    box.classList.add('faq-answer-empty');
    box.innerHTML = `<p>I don't have an answer for "${rawInput}" yet — try one of the suggestions below, or check the How It Works section.</p>`;
  }
}

document.addEventListener('DOMContentLoaded', () => {
  const input = document.getElementById('faq-input');
  const askBtn = document.getElementById('faq-ask-btn');
  if (!input || !askBtn) return;

  const runQuery = () => {
    const val = input.value;
    const match = findBestAnswer(val);
    showAnswer(match, val);
  };

  askBtn.addEventListener('click', runQuery);
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') runQuery();
  });

  document.querySelectorAll('.faq-chip').forEach(chip => {
    chip.addEventListener('click', () => {
      input.value = chip.dataset.q;
      runQuery();
    });
  });
});