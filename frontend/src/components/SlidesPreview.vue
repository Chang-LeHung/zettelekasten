<script setup lang="ts">
import Reveal, { type RevealApi } from 'reveal.js'
import 'reveal.js/reveal.css'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { isHtmlSlide, isSlideCover, presentationSections, slideDensity, slideWithTitle } from '../utils/slides'
import SlidesMarkdownContent from './SlidesMarkdownContent.vue'

const props = withDefaults(defineProps<{
  content: string
  title?: string
  compact?: boolean
  showFullscreenButton?: boolean
  autoFocus?: boolean
}>(), {
  title: '',
  compact: false,
  showFullscreenButton: true,
  autoFocus: false,
})

const stage = ref<HTMLElement | null>(null)
const revealRoot = ref<HTMLElement | null>(null)
const fullscreen = ref(false)
const fullscreenError = ref('')
const sections = computed(() => presentationSections(props.content))
const currentSection = ref(0)
const currentSlide = ref(0)
const activeSection = computed(() => sections.value[currentSection.value] ?? [])
const totalSlides = computed(() => sections.value.reduce((total, section) => total + section.length, 0))
let deck: RevealApi | null = null
let resizeObserver: ResizeObserver | null = null

function syncFullscreen(): void {
  fullscreen.value = document.fullscreenElement === stage.value
  deck?.layout()
  if (document.fullscreenElement?.contains(stage.value)) revealRoot.value?.focus({ preventScroll: true })
}

async function toggleFullscreen(): Promise<void> {
  fullscreenError.value = ''
  try {
    if (document.fullscreenElement === stage.value) {
      await document.exitFullscreen()
    } else {
      await stage.value?.requestFullscreen()
    }
  } catch {
    fullscreenError.value = 'Fullscreen is unavailable in this browser.'
  }
}

function updateCurrentSlide(): void {
  const indices = deck?.getIndices()
  currentSection.value = indices?.h ?? 0
  currentSlide.value = indices?.v ?? 0
}

function previousSection(): void {
  deck?.slide(Math.max(0, currentSection.value - 1), 0)
  updateCurrentSlide()
}

function nextSection(): void {
  deck?.slide(Math.min(sections.value.length - 1, currentSection.value + 1), 0)
  updateCurrentSlide()
}

function previousSlide(): void {
  deck?.up()
  updateCurrentSlide()
}

function nextSlide(): void {
  deck?.down()
  updateCurrentSlide()
}

function pageNumber(sectionIndex: number, slideIndex: number): number {
  return sections.value
    .slice(0, sectionIndex)
    .reduce((total, section) => total + section.length, slideIndex + 1)
}

async function syncDeck(): Promise<void> {
  await nextTick()
  if (!deck) return
  deck.sync()
  const horizontal = Math.min(currentSection.value, sections.value.length - 1)
  const vertical = Math.min(currentSlide.value, (sections.value[horizontal]?.length ?? 1) - 1)
  deck.slide(horizontal, vertical)
  deck.layout()
  updateCurrentSlide()
}

onMounted(async () => {
  document.addEventListener('fullscreenchange', syncFullscreen)
  if (!revealRoot.value) return
  deck = new Reveal(revealRoot.value, {
    embedded: true,
    controls: false,
    progress: false,
    center: false,
    hash: false,
    history: false,
    overview: false,
    touch: true,
    transition: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'none' : 'slide',
    transitionSpeed: 'fast',
    // Reveal's embedded focus is set by pointerdown, not DOM focus(). Use
    // actual focus/fullscreen ownership so opening a deck needs no extra click.
    keyboardCondition: () => {
      const root = stage.value
      if (!root) return false
      if (document.fullscreenElement) return document.fullscreenElement.contains(root)
      return root.contains(document.activeElement)
    },
    keyboard: {
      37: previousSection,
      39: nextSection,
    },
    width: 960,
    height: 540,
    margin: 0.04,
    minScale: 0.1,
    maxScale: 2,
  })
  await deck.initialize()
  if (props.autoFocus || document.fullscreenElement?.contains(stage.value)) {
    revealRoot.value?.focus({ preventScroll: true })
  }
  deck.on('slidechanged', updateCurrentSlide)
  resizeObserver = new ResizeObserver(() => deck?.layout())
  if (stage.value) resizeObserver.observe(stage.value)
})

watch(() => props.content, syncDeck)

onBeforeUnmount(() => {
  document.removeEventListener('fullscreenchange', syncFullscreen)
  resizeObserver?.disconnect()
  deck?.destroy()
  deck = null
})
</script>

<template>
  <section ref="stage" class="slides-stage" :class="{ compact }" :aria-label="title || 'Slide deck preview'">
    <button
      type="button"
      class="deck-fullscreen"
      v-if="showFullscreenButton"
      :aria-label="fullscreen ? 'Exit fullscreen' : 'Preview slides fullscreen'"
      :title="fullscreen ? 'Exit fullscreen (Esc)' : 'Fullscreen'"
      @click="toggleFullscreen"
    >
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
        <path v-if="fullscreen" d="M9 3v6H3m12-6v6h6M3 15h6v6m12-6h-6v6" />
        <path v-else d="M9 3H3v6m12-6h6v6M3 15v6h6m12-6v6h-6" />
      </svg>
    </button>
    <span v-if="fullscreenError" class="fullscreen-error" role="status">{{ fullscreenError }}</span>
    <div ref="revealRoot" class="reveal zett-deck" tabindex="0">
      <div class="slides">
        <template v-for="(section, sectionIndex) in sections" :key="`${sectionIndex}-${section[0]?.slice(0, 40)}`">
          <section v-if="section.length > 1" class="zett-section">
            <section
              v-for="(slide, slideIndex) in section"
              :key="`${slideIndex}-${slide.slice(0, 40)}`"
              class="zett-slide"
              :class="[`density-${slideDensity(slide)}`, { 'section-title-slide': slideIndex === 0 && !isHtmlSlide(slide), 'cover-slide': isSlideCover(slide) }]"
            >
              <div class="slide-body">
                <SlidesMarkdownContent :content="slideWithTitle(slide, pageNumber(sectionIndex, slideIndex))" />
              </div>
              <footer><span>Zett</span><small>{{ String(pageNumber(sectionIndex, slideIndex)).padStart(2, '0') }}</small></footer>
            </section>
          </section>
          <section v-else class="zett-slide" :class="[`density-${slideDensity(section[0] ?? '')}`, { 'section-title-slide': !isHtmlSlide(section[0] ?? ''), 'cover-slide': isSlideCover(section[0] ?? '') }]">
            <div class="slide-body">
              <SlidesMarkdownContent :content="slideWithTitle(section[0] ?? '', pageNumber(sectionIndex, 0))" />
            </div>
            <footer><span>Zett</span><small>{{ String(pageNumber(sectionIndex, 0)).padStart(2, '0') }}</small></footer>
          </section>
        </template>
      </div>
    </div>
    <nav v-if="sections.length > 1 || activeSection.length > 1" class="deck-navigation" aria-label="Slide navigation">
      <button class="nav-left" type="button" aria-label="Previous section" title="Previous section" :disabled="currentSection === 0" @click="previousSection"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m15 4-8 8 8 8" /></svg></button>
      <button class="nav-up" type="button" aria-label="Previous slide in section" title="Previous slide in section" :disabled="currentSlide === 0" @click="previousSlide"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m4 15 8-8 8 8" /></svg></button>
      <button class="nav-down" type="button" aria-label="Next slide in section" title="Next slide in section" :disabled="currentSlide >= activeSection.length - 1" @click="nextSlide"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m4 9 8 8 8-8" /></svg></button>
      <button class="nav-right" type="button" aria-label="Next section" title="Next section" :disabled="currentSection >= sections.length - 1" @click="nextSection"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m9 4 8 8-8 8" /></svg></button>
      <span class="deck-page-number" aria-live="polite" :aria-label="`Slide ${pageNumber(currentSection, currentSlide)} of ${totalSlides}`">{{ pageNumber(currentSection, currentSlide) }} / {{ totalSlides }}</span>
    </nav>
  </section>
</template>

<style scoped>
.slides-stage {
  --slide-ink: #242624;
  --slide-muted: #656a67;
  --slide-accent: #617d70;
  --slide-line: #dedfdf;
  position: relative;
  width: 100%;
  aspect-ratio: 16 / 9;
  min-height: 12rem;
  overflow: hidden;
  border: 0;
  border-radius: 0;
  background: #fff;
}
.slides-stage.compact { min-height: 9rem; }
.slides-stage:fullscreen { width: 100vw; height: 100dvh; max-width: none; aspect-ratio: auto; border: 0; border-radius: 0; }
.deck-fullscreen { position: absolute; top: .6rem; right: .6rem; z-index: 21; display: grid; place-items: center; width: 2rem; height: 2rem; padding: .4rem; border: 1px solid #d9e2dc; border-radius: .55rem; color: #426b53; background: rgba(255,255,255,.92); cursor: pointer; }
.deck-fullscreen svg { width: 100%; height: 100%; }
.deck-fullscreen:hover { background: #e8f0eb; }
.deck-fullscreen:focus-visible { outline: 2px solid #426b53; outline-offset: 2px; }
.fullscreen-error { position: absolute; top: 3rem; right: .6rem; z-index: 21; padding: .5rem; background: white; color: #774541; font-size: .75rem; }
.slides-stage:fullscreen .deck-navigation { transform: none; right: 1rem; bottom: 1rem; }
.zett-deck { width: 100%; height: 100%; color: var(--slide-ink); font-family: inherit; }
.zett-deck:focus, .zett-deck:focus-visible { outline: none; }
.zett-slide {
  box-sizing: border-box;
  height: 100%;
  padding: 1.5rem 2rem 3rem;
  overflow: hidden;
  color: var(--slide-ink);
  background: #fff;
  text-align: left;
  border: 1px solid #dedfdf;
  border-radius: .35rem;
}
.section-title-slide .slide-body { display: grid; place-items: center; height: 100%; text-align: center; }
.section-title-slide .slide-body :deep(.markdown-body > h1:first-child) { margin: 0; padding: 0; border: 0; font-size: 3em; font-weight: 600; line-height: 1.25; }
.section-title-slide footer { display: none; }
.cover-slide .slide-body :deep(.markdown-body) { width: 100%; text-align: center; }
.cover-slide .slide-body :deep(h2) { margin: .7em 0 1.3em; color: var(--slide-muted); font-size: 1.15em; font-weight: 400; }
.cover-slide .slide-body :deep(p) { margin: 1em 0; }
.cover-slide .slide-body :deep(.markdown-figure) { display: inline-flex; flex-direction: column-reverse; vertical-align: top; width: 28%; margin: .7em 2%; }
.cover-slide .slide-body :deep(.markdown-figure img), .cover-slide .slide-body :deep(p > img) { width: 100%; height: 4em; object-fit: contain; }
.cover-slide .slide-body :deep(p:has(> img)) { display: flex; justify-content: center; flex-wrap: wrap; gap: 1em; }
.cover-slide .slide-body :deep(p > img) { width: 28%; }
.slide-body {
  height: calc(100% - 1.45rem);
  padding: 0;
  overflow: auto;
  overflow-wrap: anywhere;
  overscroll-behavior: contain;
  scrollbar-color: #bdc9c1 transparent;
  scrollbar-width: thin;
}
.density-normal .slide-body { font-size: 1.34rem; line-height: 1.48; }
.density-compact .slide-body { font-size: 1.04rem; line-height: 1.4; }
.density-dense .slide-body { font-size: .84rem; line-height: 1.34; }

/* A slide title is also its visual anchor: the rule keeps every page aligned. */
.slide-body :deep(.markdown-body > :is(h1, h2, h3, h4, h5, h6):first-child) {
  margin: 0 0 1.12rem;
  padding-bottom: .58rem;
  border-bottom: 1px solid var(--slide-accent);
  color: var(--slide-ink);
  font-size: 2em;
  line-height: 1.15;
  font-weight: 450;
  letter-spacing: -.015em;
  text-transform: none;
}
.slide-body :deep(h1), .slide-body :deep(h2), .slide-body :deep(h3), .slide-body :deep(h4) { color: var(--slide-ink); font-weight: 500; letter-spacing: 0; }
.slide-body :deep(h1), .slide-body :deep(h2) {
  margin: 1.1em 0 .5em;
  padding: 0;
  border: 0;
  line-height: 1.25;
}
.slide-body :deep(h1), .slide-body :deep(h2) { font-size: 1.25em; }
.slide-body :deep(h3), .slide-body :deep(h4) { margin: 1em 0 .45em; font-size: 1.1em; line-height: 1.25; }
.slide-body :deep(p), .slide-body :deep(ul), .slide-body :deep(ol), .slide-body :deep(blockquote), .slide-body :deep(table) { margin-top: .5rem; margin-bottom: .5rem; }
.slide-body :deep(strong) { color: inherit; font-weight: 700; }
.slide-body :deep(a) { color: #27684a; text-decoration: none; }
.slide-body :deep(a:hover) { color: #17472f; text-decoration: none; }
.slide-body :deep(ul), .slide-body :deep(ol) { padding-left: 1.35em; }
.slide-body :deep(li) { padding-left: .14em; }
.slide-body :deep(li + li) { margin-top: .28em; }
.slide-body :deep(li::marker) { color: inherit; }
.slide-body :deep(li ul), .slide-body :deep(li ol) { margin-top: .22em; margin-bottom: .22em; font-size: 1em; }
.slide-body :deep(blockquote) {
  /* Keep the shared Markdown callout style, with compact slide spacing. */
  padding: .75em 1em;
}
.slide-body :deep(blockquote > :first-child) { margin-top: 0; }
.slide-body :deep(blockquote > :last-child) { margin-bottom: 0; }

/* Inline code stays quiet; fenced code becomes a readable presentation panel. */
.slide-body :deep(code) { padding: 0 .12em; border-radius: 0; color: inherit; background: transparent; font-family: "SFMono-Regular", "SF Mono", Consolas, monospace; font-size: .86em; }
.slide-body :deep(.code-block) { margin: .62rem .4rem; border-radius: .85rem; font-size: .68em; }
.slide-body :deep(.code-block-toolbar) { min-height: 2.15rem; padding: .35rem .55rem .2rem .78rem; font-size: .9em; }
.slide-body :deep(.code-copy-button) { min-width: 1.7rem; width: 1.7rem; height: 1.7rem; padding: .25rem; }
.slide-body :deep(.code-block pre) { max-height: 16em; padding: .25rem .85rem .8rem; overflow: auto; }
.slide-body :deep(.code-block code) { padding: 0; color: #26312b; background: transparent; font-size: 1em; line-height: 1.48; }

/* Display math reads as a first-class statement rather than inline prose. */
.slide-body :deep(.katex-display) { max-width: 100%; margin: .65rem 0; padding: .35rem 0; overflow-x: auto; overflow-y: hidden; border: 0; color: #263d30; background: transparent; font-size: 1.02em; text-align: center; }
.slide-body :deep(.katex-display > .katex) { white-space: nowrap; }

.slide-body :deep(table) { display: table; width: 100%; max-width: 100%; table-layout: fixed; overflow: hidden; border: 1px solid #d5dfd9; border-radius: .5rem; border-collapse: separate; border-spacing: 0; font-size: .72em; }
.slide-body :deep(th), .slide-body :deep(td) { padding: .42em .62em; overflow-wrap: anywhere; border: 0; border-right: 1px solid #dce4df; border-bottom: 1px solid #dce4df; text-align: left; }
.slide-body :deep(th) { color: #31523f; background: #eaf1ed; font-weight: 720; }
.slide-body :deep(tr:last-child td) { border-bottom: 0; }
.slide-body :deep(th:last-child), .slide-body :deep(td:last-child) { border-right: 0; }
.slide-body :deep(hr) { margin: .85rem 0; border: 0; border-top: 1px solid var(--slide-line); }
.slide-body :deep(img) { display: block; max-width: 100%; max-height: 17em; margin: .62rem auto; border: 0; border-radius: 0; object-fit: contain; box-shadow: none; }
.slide-body :deep(.markdown-figure) { margin: .7em 0; }
.slide-body :deep(.markdown-figure img) { max-height: 13em; margin: 0 auto; }
.slide-body :deep(figcaption) { margin-top: .45em; font-size: .7em; }
.slide-body :deep(.mermaid-block) { margin: .6rem 0; border-color: #dedfdf; border-radius: .2rem; background: #fff; }
.slide-body :deep(.mermaid-toolbar) { min-height: 1.75rem; padding: .2rem .35rem .2rem .7rem; background: #edf2ef; font-size: .55em; }
.slide-body :deep(.mermaid-canvas) { min-height: 4rem; max-height: 15em; padding: .7rem; overflow: auto; }

.zett-slide footer { position: absolute; right: 2rem; bottom: 1.25rem; left: 2rem; display: flex; align-items: center; justify-content: space-between; color: #789083; font-size: .68rem; font-weight: 690; letter-spacing: .08em; text-transform: uppercase; }
.zett-slide footer small { font: inherit; font-variant-numeric: tabular-nums; }
.deck-navigation { position: absolute; right: .65rem; bottom: .6rem; z-index: 20; display: grid; grid-template-columns: repeat(3, 1.65rem); grid-template-rows: repeat(3, 1.4rem) auto; justify-items: center; align-items: center; }
.deck-navigation button { display: grid; place-items: center; width: 1.85rem; height: 1.85rem; padding: .15rem; border: 0; border-radius: .3rem; color: #365f47; background: transparent; cursor: pointer; }
.deck-navigation button svg { width: 100%; height: 100%; fill: none; stroke: currentColor; stroke-width: 3; stroke-linecap: round; stroke-linejoin: round; }
.deck-navigation button:hover:not(:disabled) { color: #193f29; background: rgba(225, 237, 229, .8); }
.deck-navigation button:focus-visible { outline: 2px solid #426b53; outline-offset: 1px; }
.deck-navigation button:disabled { opacity: .24; cursor: default; }
.nav-up { grid-column: 2; grid-row: 1; }
.nav-left { grid-column: 1; grid-row: 2; }
.nav-right { grid-column: 3; grid-row: 2; }
.nav-down { grid-column: 2; grid-row: 3; }
.deck-page-number { grid-column: 1 / -1; grid-row: 4; justify-self: end; margin-top: .22rem; padding: .18rem .45rem; border-radius: .3rem; color: #fff; background: rgba(71, 82, 75, .58); font-size: .85rem; font-weight: 650; line-height: 1.25; font-variant-numeric: tabular-nums; white-space: nowrap; }
.compact .deck-navigation { right: .45rem; bottom: .42rem; transform: scale(.88); transform-origin: right bottom; }

</style>
