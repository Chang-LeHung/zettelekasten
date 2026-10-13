<script setup lang="ts">
/**
 * The home page's hero picture: a miniature of the workspace that loops through
 * one request. Pure CSS — a prompt is typed, then a card, a deck and a paper
 * rise out of it — and it stands still when the reader prefers reduced motion.
 */
</script>

<template>
  <div class="hero-art" role="img" aria-label="A prompt in the Zett workspace becomes a card, a slide deck, and a paper">
    <div class="ha-window">
      <div class="ha-bar">
        <span class="ha-dots"><i /><i /><i /></span>
        <span class="ha-title">AI workspace</span>
        <span class="ha-chip">Your model</span>
      </div>
      <div class="ha-body">
        <p class="ha-prompt"><span class="ha-type">Turn this idea into a card, a deck, and a paper.</span></p>
        <div class="ha-stack">
          <article class="ha-card ha-card--1">
            <span class="ha-kind">Card</span>
            <strong>Local-first beats sync</strong>
            <span class="ha-line" /><span class="ha-line ha-line--short" />
          </article>
          <article class="ha-card ha-card--2">
            <span class="ha-kind">Slides</span>
            <strong>Ten minutes on local notes</strong>
            <span class="ha-slides"><i /><i /><i /></span>
          </article>
          <article class="ha-card ha-card--3">
            <span class="ha-kind">Paper · PDF</span>
            <strong>Note sync without a server</strong>
            <span class="ha-line" /><span class="ha-line ha-line--short" />
          </article>
        </div>
        <p class="ha-saved"><span class="ha-check" />Saved to a folder you own</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.hero-art {
  width: min(100%, 25rem);
  margin: 0 auto;
}

.ha-window {
  overflow: hidden;
  border: 1px solid var(--vp-c-divider);
  border-radius: 16px;
  background: var(--vp-c-bg);
  box-shadow: 0 2px 6px rgba(23, 35, 29, 0.06), 0 28px 60px rgba(23, 35, 29, 0.14);
}

.ha-bar {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  padding: 0.6rem 0.8rem;
  border-bottom: 1px solid var(--vp-c-divider);
  background: var(--vp-c-bg-soft);
  font-size: 0.75rem;
  color: var(--vp-c-text-2);
}

.ha-dots {
  display: inline-flex;
  gap: 5px;
}

.ha-dots i {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: var(--vp-c-divider);
}

.ha-title {
  font-weight: 600;
  color: var(--vp-c-text-1);
}

.ha-chip {
  margin-left: auto;
  padding: 0.1rem 0.55rem;
  border-radius: 999px;
  background: var(--vp-c-brand-soft);
  color: var(--vp-c-brand-1);
  font-weight: 600;
}

.ha-body {
  display: grid;
  gap: 0.75rem;
  padding: 1rem;
}

.ha-prompt {
  margin: 0;
  justify-self: end;
  max-width: 100%;
  padding: 0.5rem 0.8rem;
  border-radius: 14px 14px 4px 14px;
  background: var(--vp-button-brand-bg);
  color: #fff;
  font-size: 0.8rem;
  line-height: 1.4;
}

.ha-type {
  display: block;
}

.ha-stack {
  display: grid;
  gap: 0.55rem;
}

.ha-card {
  display: grid;
  gap: 0.35rem;
  padding: 0.7rem 0.85rem;
  border: 1px solid var(--vp-c-divider);
  border-radius: 12px;
  background: var(--vp-c-bg-alt);
}

.ha-kind {
  font-size: 0.68rem;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--vp-c-brand-1);
}

.ha-card strong {
  font-size: 0.86rem;
  color: var(--vp-c-text-1);
}

.ha-line {
  height: 6px;
  border-radius: 3px;
  background: var(--vp-c-divider);
}

.ha-line--short {
  width: 62%;
}

.ha-slides {
  display: flex;
  gap: 5px;
}

.ha-slides i {
  width: 34px;
  height: 22px;
  border-radius: 4px;
  background: var(--vp-c-brand-soft);
  border: 1px solid var(--vp-c-divider);
}

.ha-saved {
  display: flex;
  align-items: center;
  gap: 0.45rem;
  margin: 0;
  font-size: 0.75rem;
  color: var(--vp-c-text-2);
}

.ha-check {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: var(--vp-c-brand-2);
  box-shadow: inset 0 0 0 4px var(--vp-c-bg);
  outline: 2px solid var(--vp-c-brand-2);
  outline-offset: -2px;
}

@media (prefers-reduced-motion: no-preference) {
  .hero-art {
    animation: ha-float 7s ease-in-out infinite;
  }

  .ha-type {
    animation: ha-type 10s steps(46, end) infinite;
  }

  .ha-card,
  .ha-saved {
    opacity: 0;
    animation: ha-rise 10s cubic-bezier(0.33, 1, 0.68, 1) infinite;
  }

  .ha-card--2 { animation-delay: 0.3s; }
  .ha-card--3 { animation-delay: 0.6s; }
  .ha-saved { animation-delay: 1.2s; }
}

/* One shared 10s loop: type, rise one by one, hold, then fade for the next run. */
@keyframes ha-type {
  0% { clip-path: inset(0 100% 0 0); }
  22%, 88% { clip-path: inset(0 0 0 0); }
  96%, 100% { clip-path: inset(0 100% 0 0); }
}

@keyframes ha-rise {
  0%, 25% { opacity: 0; transform: translate3d(0, 14px, 0); }
  36%, 88% { opacity: 1; transform: none; }
  96%, 100% { opacity: 0; transform: translate3d(0, -4px, 0); }
}

@keyframes ha-float {
  0%, 100% { transform: translate3d(0, 0, 0); }
  50% { transform: translate3d(0, -6px, 0); }
}
</style>
