// hero-3d.js — mouse-tilt on the hero GPU stack, scroll parallax, and magnetic buttons.
// All effects are skipped for reduced-motion users and devices with no real pointer.

(function () {
  const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const hasHoverPointer = window.matchMedia("(hover: hover) and (pointer: fine)").matches;

  function initHeroTilt() {
    const stage = document.getElementById("hero3dStage");
    const scene = document.getElementById("hero3dScene");
    if (!stage || !scene || prefersReducedMotion || !hasHoverPointer) return;

    const BASE_ROTATE_X = 14;
    const BASE_ROTATE_Y = -16;
    const MAX_OFFSET = 10;

    stage.addEventListener("mousemove", (event) => {
      const rect = stage.getBoundingClientRect();
      const relX = (event.clientX - rect.left) / rect.width - 0.5;
      const relY = (event.clientY - rect.top) / rect.height - 0.5;

      const rotateY = BASE_ROTATE_Y + relX * MAX_OFFSET * 2;
      const rotateX = BASE_ROTATE_X - relY * MAX_OFFSET * 2;

      scene.style.transform = `rotateX(${rotateX}deg) rotateY(${rotateY}deg)`;
    });

    stage.addEventListener("mouseleave", () => {
      scene.style.transform = `rotateX(${BASE_ROTATE_X}deg) rotateY(${BASE_ROTATE_Y}deg)`;
    });
  }

  function initHeroParallax() {
    const hero = document.getElementById("top");
    const stage = document.getElementById("hero3dStage");
    const content = hero ? hero.querySelector(".hero-content") : null;
    if (!hero || !stage || prefersReducedMotion) return;

    let ticking = false;

    function update() {
      const rect = hero.getBoundingClientRect();
      const progress = Math.min(Math.max(1 - rect.bottom / (rect.height + window.innerHeight), 0), 1);

      stage.style.transform = `translateY(${progress * -40}px)`;
      stage.style.opacity = String(1 - progress * 0.6);

      if (content) {
        content.style.transform = `translateY(${progress * -18}px)`;
      }

      ticking = false;
    }

    window.addEventListener("scroll", () => {
      if (!ticking) {
        requestAnimationFrame(update);
        ticking = true;
      }
    });

    update();
  }

  function initMagneticButtons() {
    if (prefersReducedMotion || !hasHoverPointer) return;

    const buttons = document.querySelectorAll("[data-magnetic]");
    const STRENGTH = 0.35;
    const MAX_PULL = 10;

    buttons.forEach((btn) => {
      btn.addEventListener("mousemove", (event) => {
        const rect = btn.getBoundingClientRect();
        const relX = event.clientX - (rect.left + rect.width / 2);
        const relY = event.clientY - (rect.top + rect.height / 2);

        const pullX = Math.max(Math.min(relX * STRENGTH, MAX_PULL), -MAX_PULL);
        const pullY = Math.max(Math.min(relY * STRENGTH, MAX_PULL), -MAX_PULL);

        btn.style.transform = `translate(${pullX}px, ${pullY}px)`;
      });

      btn.addEventListener("mouseleave", () => {
        btn.style.transform = "translate(0, 0)";
      });
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    initHeroTilt();
    initHeroParallax();
    initMagneticButtons();
  });
})();