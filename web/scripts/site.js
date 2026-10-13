/**
 * Landing page behaviour: a small reveal as blocks scroll into view, the data
 * folder listing, a copy button on the install commands, and a nav hairline.
 * The hero entrance is pure CSS. Hidden start states live under `.js`, so the
 * page is complete without script and with reduced motion.
 */

const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
document.documentElement.classList.add('js');

const targets = [...document.querySelectorAll('[data-reveal], [data-tree]')];

if (reduceMotion.matches || !('IntersectionObserver' in window)) {
  targets.forEach((element) => element.classList.add('is-visible'));
} else {
  const observer = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        entry.target.classList.add('is-visible');
        observer.unobserve(entry.target);
      }
    },
    { rootMargin: '0px 0px -8% 0px', threshold: 0.1 },
  );
  targets.forEach((element) => observer.observe(element));
}

const copyButton = document.querySelector('[data-copy]');

if (copyButton) {
  copyButton.addEventListener('click', async () => {
    const source = document.querySelector('[data-copy-source]');
    const commands = [...source.querySelectorAll('.line:not(.out)')]
      .map((line) => line.textContent.replace(/^\$\s*/, '').trim())
      .join('\n');
    try {
      await navigator.clipboard.writeText(commands);
      copyButton.textContent = 'Copied';
    } catch {
      copyButton.textContent = 'Press ⌘C';
    }
    setTimeout(() => {
      copyButton.textContent = 'Copy';
    }, 1600);
  });
}

const nav = document.querySelector('.nav');
const onScroll = () => nav?.classList.toggle('is-scrolled', window.scrollY > 8);
onScroll();
window.addEventListener('scroll', onScroll, { passive: true });
