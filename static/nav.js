// Sticky navbar behaviour: mobile menu toggle + active-section highlighting.
// Kept separate from landing.js (hero/choice-card effects) and dashboard.js
// (simulator logic) so each file has one clear job.

document.addEventListener('DOMContentLoaded', () => {
  const toggle = document.getElementById('site-nav-toggle');
  const links = document.getElementById('site-nav-links');

  if (toggle && links) {
    const closeMenu = () => {
      links.classList.remove('is-open');
      toggle.setAttribute('aria-expanded', 'false');
      toggle.setAttribute('aria-label', 'Open menu');
    };

    const openMenu = () => {
      links.classList.add('is-open');
      toggle.setAttribute('aria-expanded', 'true');
      toggle.setAttribute('aria-label', 'Close menu');
    };

    toggle.addEventListener('click', () => {
      const isOpen = links.classList.contains('is-open');
      if (isOpen) {
        closeMenu();
      } else {
        openMenu();
      }
    });

    // Tapping any nav link closes the mobile menu so the destination
    // section is actually visible right away.
    links.querySelectorAll('a').forEach((link) => {
      link.addEventListener('click', closeMenu);
    });

    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && links.classList.contains('is-open')) {
        closeMenu();
        toggle.focus();
      }
    });

    // If the viewport grows back to desktop width while the mobile menu
    // is open, drop the mobile-only "is-open" state so it doesn't stick.
    window.addEventListener('resize', () => {
      if (window.innerWidth > 760 && links.classList.contains('is-open')) {
        closeMenu();
      }
    });
  }

  // ---- Active-section highlighting (scroll-spy) ----
  const navLinkByTarget = new Map();
  document.querySelectorAll('.site-nav-link[data-nav-target]').forEach((link) => {
    navLinkByTarget.set(link.dataset.navTarget, link);
  });

  const observedSections = [...navLinkByTarget.keys()]
    .map((id) => document.getElementById(id))
    .filter(Boolean);

  if (observedSections.length && 'IntersectionObserver' in window) {
    const setActive = (id) => {
      navLinkByTarget.forEach((link, key) => {
        link.classList.toggle('is-active', key === id);
      });
    };

    const sectionObserver = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            setActive(entry.target.id);
          }
        });
      },
      { rootMargin: '-45% 0px -50% 0px', threshold: 0 }
    );

    observedSections.forEach((section) => sectionObserver.observe(section));
  }
});