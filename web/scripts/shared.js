/**
 * Behaviour shared by the landing page and the documentation: the light/dark
 * theme, the search dialog, and copy buttons on code blocks.
 */

/* ------------------------------------------------------------------ theme */

const THEME_KEY = 'zett.theme';
const root = document.documentElement;

function applyTheme(theme, { persist = true } = {}) {
  if (theme === 'dark') root.dataset.theme = 'dark';
  else delete root.dataset.theme;
  if (persist) {
    try {
      localStorage.setItem(THEME_KEY, theme);
    } catch {
      // A blocked localStorage must not break the toggle.
    }
  }
  for (const button of document.querySelectorAll('[data-theme-toggle]')) {
    button.setAttribute('aria-pressed', String(theme === 'dark'));
    button.setAttribute('aria-label', theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode');
  }
}

function initialTheme() {
  try {
    const stored = localStorage.getItem(THEME_KEY);
    if (stored === 'dark' || stored === 'light') return stored;
  } catch {
    // fall through to the system preference
  }
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

applyTheme(initialTheme(), { persist: false });

for (const button of document.querySelectorAll('[data-theme-toggle]')) {
  button.addEventListener('click', () => {
    applyTheme(root.dataset.theme === 'dark' ? 'light' : 'dark');
  });
}

/* ----------------------------------------------------------------- search */

const dialog = document.querySelector('[data-search-dialog]');
const input = dialog?.querySelector('input');
const results = dialog?.querySelector('[data-search-results]');
const empty = dialog?.querySelector('[data-search-empty]');
let indexPromise = null;
let items = [];
let cursor = -1;

/** The site base, so a GitHub Pages project site under a sub-path still works. */
const siteBase = document.querySelector('meta[name="zett-base"]')?.content ?? '/';

function loadIndex() {
  if (!indexPromise) {
    indexPromise = fetch(`${siteBase}docs/search.json`)
      .then((response) => (response.ok ? response.json() : []))
      .catch(() => []);
  }
  return indexPromise;
}

function openSearch() {
  if (!dialog) return;
  dialog.classList.add('is-open');
  input.value = '';
  render([]);
  input.focus();
  loadIndex().then(() => render([]));
}

function closeSearch() {
  dialog?.classList.remove('is-open');
}

function score(item, query) {
  const haystack = `${item.title} ${item.text} ${(item.headings || []).join(' ')}`.toLowerCase();
  const title = item.title.toLowerCase();
  if (title.includes(query)) return 3;
  if ((item.headings || []).some((heading) => heading.toLowerCase().includes(query))) return 2;
  return haystack.includes(query) ? 1 : 0;
}

function render(matches) {
  if (!results) return;
  results.replaceChildren();
  empty.hidden = matches.length > 0;
  cursor = -1;
  for (const item of matches) {
    const li = document.createElement('li');
    const link = document.createElement('a');
    link.href = item.url;
    const title = document.createElement('strong');
    title.textContent = item.title;
    const context = document.createElement('span');
    context.textContent = item.section ? `${item.section} · ${item.text}` : item.text;
    link.append(title, context);
    li.append(link);
    results.append(li);
  }
}

function search(query) {
  const normalized = query.trim().toLowerCase();
  if (!normalized) {
    render([]);
    return;
  }
  const matches = items
    .map((item) => ({ item, rank: score(item, normalized) }))
    .filter((entry) => entry.rank > 0)
    .sort((a, b) => b.rank - a.rank)
    .slice(0, 12)
    .map((entry) => entry.item);
  render(matches);
}

function moveCursor(delta) {
  const links = [...(results?.querySelectorAll('a') || [])];
  if (!links.length) return;
  links[cursor]?.classList.remove('is-active');
  cursor = (cursor + delta + links.length) % links.length;
  links[cursor].classList.add('is-active');
  links[cursor].scrollIntoView({ block: 'nearest' });
}

for (const trigger of document.querySelectorAll('[data-search-open]')) {
  trigger.addEventListener('click', openSearch);
}

input?.addEventListener('input', () => {
  loadIndex().then((data) => {
    items = data;
    search(input.value);
  });
});

input?.addEventListener('keydown', (event) => {
  if (event.key === 'ArrowDown') {
    event.preventDefault();
    moveCursor(1);
  } else if (event.key === 'ArrowUp') {
    event.preventDefault();
    moveCursor(-1);
  } else if (event.key === 'Enter') {
    const active = results?.querySelector('a.is-active') || results?.querySelector('a');
    if (active) {
      event.preventDefault();
      window.location.href = active.href;
    }
  }
});

dialog?.addEventListener('click', (event) => {
  if (event.target === dialog) closeSearch();
});

window.addEventListener('keydown', (event) => {
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
    event.preventDefault();
    openSearch();
  } else if (event.key === 'Escape') {
    closeSearch();
  }
});

loadIndex().then((data) => {
  items = data;
});

/* --------------------------------------------------------- copy buttons */

for (const block of document.querySelectorAll('.docs-content .highlight')) {
  const button = document.createElement('button');
  button.className = 'copy-button';
  button.type = 'button';
  button.textContent = 'Copy';
  button.addEventListener('click', async () => {
    const code = block.querySelector('code')?.textContent ?? '';
    try {
      await navigator.clipboard.writeText(code);
      button.textContent = 'Copied';
      setTimeout(() => {
        button.textContent = 'Copy';
      }, 1600);
    } catch {
      button.textContent = 'Copy failed';
    }
  });
  block.append(button);
}

/* ------------------------------------------------------------- nav hairline */

const nav = document.querySelector('.nav');
if (nav && !nav.classList.contains('nav--solid')) {
  const onScroll = () => nav.classList.toggle('is-scrolled', window.scrollY > 8);
  onScroll();
  window.addEventListener('scroll', onScroll, { passive: true });
}
