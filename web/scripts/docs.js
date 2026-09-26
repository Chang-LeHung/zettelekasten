/**
 * Documentation behaviour: the mobile section drawer, and scroll position
 * highlighting for "On this page".
 */

const navDrawer = document.querySelector('[data-docs-nav]');
const navToggle = document.querySelector('[data-docs-nav-toggle]');

navToggle?.addEventListener('click', () => {
  const open = navDrawer?.classList.toggle('is-open');
  navToggle.setAttribute('aria-expanded', String(Boolean(open)));
});

for (const link of navDrawer?.querySelectorAll('a') || []) {
  link.addEventListener('click', () => {
    navDrawer?.classList.remove('is-open');
    navToggle?.setAttribute('aria-expanded', 'false');
  });
}

const tocLinks = [...document.querySelectorAll('.docs-toc__link')];
if (tocLinks.length) {
  const headings = tocLinks
    .map((link) => document.querySelector(decodeURIComponent(link.hash)))
    .filter(Boolean);

  const highlight = () => {
    // The last heading above the reading line is the section being read.
    let current = headings[0];
    for (const heading of headings) {
      if (heading.getBoundingClientRect().top <= 120) current = heading;
    }
    for (const link of tocLinks) {
      link.classList.toggle('is-active', Boolean(current) && link.hash === `#${current.id}`);
    }
  };

  highlight();
  window.addEventListener('scroll', highlight, { passive: true });
  window.addEventListener('resize', highlight);
}
