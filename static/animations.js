// animations.js — hero particle background + scroll-reveal for dashboard cards

const PARTICLE_COUNT = 42;
const CONNECT_DISTANCE = 130;
const PARTICLE_COLOR = "rgba(188, 113, 85, 0.45)";
const LINE_COLOR = "rgba(0, 13, 16, 0.08)";
const PARTICLE_SPEED = 0.3;

class Particle {
  constructor(width, height) {
    this.x = Math.random() * width;
    this.y = Math.random() * height;
    this.vx = (Math.random() - 0.5) * PARTICLE_SPEED;
    this.vy = (Math.random() - 0.5) * PARTICLE_SPEED;
    this.radius = 1.6;
  }

  step(width, height) {
    this.x += this.vx;
    this.y += this.vy;
    if (this.x < 0 || this.x > width) this.vx *= -1;
    if (this.y < 0 || this.y > height) this.vy *= -1;
  }
}

function initHeroCanvas() {
  const canvas = document.getElementById("heroCanvas");
  if (!canvas) return;

  const ctx = canvas.getContext("2d");
  let width, height, particles;

  function resize() {
    width = canvas.width = canvas.offsetWidth;
    height = canvas.height = canvas.offsetHeight;
  }

  function createParticles() {
    particles = Array.from({ length: PARTICLE_COUNT }, () => new Particle(width, height));
  }

  function drawFrame() {
    ctx.clearRect(0, 0, width, height);

    for (const p of particles) {
      p.step(width, height);
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.radius, 0, Math.PI * 2);
      ctx.fillStyle = PARTICLE_COLOR;
      ctx.fill();
    }

    for (let i = 0; i < particles.length; i++) {
      for (let j = i + 1; j < particles.length; j++) {
        const dx = particles[i].x - particles[j].x;
        const dy = particles[i].y - particles[j].y;
        const dist = Math.sqrt(dx * dx + dy * dy);

        if (dist < CONNECT_DISTANCE) {
          ctx.beginPath();
          ctx.moveTo(particles[i].x, particles[i].y);
          ctx.lineTo(particles[j].x, particles[j].y);
          ctx.strokeStyle = LINE_COLOR;
          ctx.lineWidth = 1;
          ctx.stroke();
        }
      }
    }

    requestAnimationFrame(drawFrame);
  }

  resize();
  createParticles();
  drawFrame();

  window.addEventListener("resize", () => {
    resize();
    createParticles();
  });
}

function initScrollReveal() {
  const DIRECTIONS = ['reveal-left', 'reveal-zoom', 'reveal-right'];
  const STAGGER_STEP_MS = 70;
  const MAX_DELAY_MS = 420;

  // Grid children cascade in with alternating left/zoom/right entrances —
  // gives each row visual variety instead of every card arriving the same
  // way. Applied in JS so the HTML markup doesn't need per-card classes.
  const staggerGroups = [
    '.choice-grid > .choice-card',
    '.info-grid > .info-block',
    '.secondary-stats > .secondary-stat',
    '.latency-stats > .latency-stat',
    '.gpu-controls > .gpu-control-card',
  ];

  staggerGroups.forEach((selector) => {
    document.querySelectorAll(selector).forEach((el, i) => {
      el.classList.add('reveal', DIRECTIONS[i % DIRECTIONS.length]);
      el.style.setProperty('--reveal-delay', `${Math.min(i * STAGGER_STEP_MS, MAX_DELAY_MS)}ms`);
    });
  });

  // Full-width stacked panels (sensitivity, latency, controls, the three
  // charts, history) alternate left/right as you scroll down the
  // dashboard, for a gentle zig-zag rather than a flat stack of fades.
  const panelSelector = [
    '#sensitivity-panel',
    '#latency-panel',
    '#controls-panel',
    '#history-panel',
  ].join(', ');
  const namedPanels = document.querySelectorAll(panelSelector);
  namedPanels.forEach((el, i) => {
    el.classList.add(i % 2 === 0 ? 'reveal-left' : 'reveal-right');
  });

  // The three unlabeled chart-card sections (total energy / power / load)
  // don't have ids, so pick them up as "any .chart-card.reveal not already
  // tagged with a direction" and continue the same left/right alternation.
  const untaggedCharts = document.querySelectorAll(
    '.chart-card.reveal:not(.reveal-left):not(.reveal-right):not(.reveal-zoom)'
  );
  untaggedCharts.forEach((el, i) => {
    el.classList.add(i % 2 === 0 ? 'reveal-right' : 'reveal-left');
  });

  // The headline number gets a confident zoom-in rather than a slide.
  const bigStat = document.getElementById('big-stat');
  if (bigStat) bigStat.classList.add('reveal-zoom');

  const revealEls = document.querySelectorAll('.reveal');
  if (!revealEls.length) return;

  const observer = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (entry.isIntersecting) {
          entry.target.classList.add('is-visible');
          observer.unobserve(entry.target);
        }
      }
    },
    { threshold: 0.12, rootMargin: '0px 0px -8% 0px' }
  );

  revealEls.forEach((el) => observer.observe(el));
}

document.addEventListener("DOMContentLoaded", () => {
  initHeroCanvas();
  initScrollReveal();
});