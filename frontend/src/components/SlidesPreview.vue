<script setup lang="ts">
import Reveal, { type RevealApi } from 'reveal.js'
import 'reveal.js/reveal.css'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { slideDensity, splitSlides } from '../utils/slides'
import MarkdownContent from './MarkdownContent.vue'

const props = withDefaults(defineProps<{
  content: string
  title?: string
  compact?: boolean
}>(), {
  title: '',
  compact: false,
})

const stage = ref<HTMLElement | null>(null)
const revealRoot = ref<HTMLElement | null>(null)
const slides = computed(() => splitSlides(props.content))
const currentSlide = ref(0)
let deck: RevealApi | null = null
let resizeObserver: ResizeObserver | null = null

function updateCurrentSlide(): void {
  currentSlide.value = deck?.getIndices().h ?? 0
}

function previous(): void {
  deck?.prev()
  updateCurrentSlide()
}

function next(): void {
  deck?.next()
  updateCurrentSlide()
}

async function syncDeck(): Promise<void> {
  await nextTick()
  if (!deck) return
  deck.sync()
  deck.slide(Math.min(currentSlide.value, slides.value.length - 1))
  deck.layout()
  updateCurrentSlide()
}

onMounted(async () => {
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
    transition: 'fade',
    transitionSpeed: 'fast',
    keyboardCondition: 'focused',
    width: 960,
    height: 540,
    margin: 0,
    minScale: 0.1,
    maxScale: 2,
  })
  await deck.initialize()
  deck.on('slidechanged', updateCurrentSlide)
  resizeObserver = new ResizeObserver(() => deck?.layout())
  if (stage.value) resizeObserver.observe(stage.value)
})

watch(() => props.content, syncDeck)

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  deck?.destroy()
  deck = null
})
</script>

<template>
  <section ref="stage" class="slides-stage" :class="{ compact }" :aria-label="title || 'Slide deck preview'">
    <div ref="revealRoot" class="reveal zett-deck" tabindex="0">
      <div class="slides">
        <section
          v-for="(slide, index) in slides"
          :key="`${index}-${slide.slice(0, 40)}`"
          class="zett-slide"
          :class="`density-${slideDensity(slide)}`"
        >
          <div class="slide-accent" />
          <MarkdownContent class="slide-body" :content="slide || '*Empty slide*'" />
          <footer><span>Zett</span><small>{{ String(index + 1).padStart(2, '0') }}</small></footer>
        </section>
      </div>
    </div>
    <nav v-if="slides.length > 1" class="deck-navigation" aria-label="Slide navigation">
      <button type="button" aria-label="Previous slide" :disabled="currentSlide === 0" @click="previous">‹</button>
      <span>{{ currentSlide + 1 }} / {{ slides.length }}</span>
      <button type="button" aria-label="Next slide" :disabled="currentSlide === slides.length - 1" @click="next">›</button>
    </nav>
  </section>
</template>

<style scoped>
.slides-stage { position: relative; width: 100%; aspect-ratio: 16 / 9; min-height: 12rem; overflow: hidden; border: 1px solid #dfe6e1; border-radius: 1rem; background: #f4f7f5; box-shadow: 0 16px 42px rgba(35, 57, 44, .1); }
.slides-stage.compact { min-height: 9rem; border-radius: .78rem; }
.zett-deck { width: 100%; height: 100%; color: #243029; font-family: Inter, -apple-system, BlinkMacSystemFont, "SF Pro Text", sans-serif; }
.zett-deck:focus-visible { outline: 3px solid rgba(73, 118, 92, .24); outline-offset: -3px; }
.zett-slide { box-sizing: border-box; height: 100%; padding: 3.5rem 4.25rem 3rem; overflow: hidden; color: #243029; background: linear-gradient(145deg, #fff 0%, #fbfcfb 72%, #f0f5f1 100%); text-align: left; }
.slide-accent { position: absolute; top: 0; left: 0; width: 100%; height: .48rem; background: linear-gradient(90deg, #385e49, #7fa28d 68%, #cadbd0); }
.slide-body { height: calc(100% - 1.5rem); overflow: auto; overflow-wrap: anywhere; overscroll-behavior: contain; scrollbar-color: #bdc9c1 transparent; scrollbar-width: thin; }
.density-normal .slide-body { font-size: 1.4rem; line-height: 1.48; }
.density-compact .slide-body { font-size: 1.08rem; line-height: 1.4; }
.density-dense .slide-body { font-size: .88rem; line-height: 1.34; }
.slide-body :deep(h1), .slide-body :deep(h2), .slide-body :deep(h3) { color: #1f2b24; letter-spacing: -.035em; }
.slide-body :deep(h1) { margin: 0 0 1.35rem; font-size: 2.7em; line-height: 1.04; }
.slide-body :deep(h2) { margin: 0 0 1.1rem; font-size: 2em; line-height: 1.08; }
.slide-body :deep(h3) { margin: .8rem 0 .55rem; font-size: 1.35em; }
.slide-body :deep(p), .slide-body :deep(ul), .slide-body :deep(ol), .slide-body :deep(pre), .slide-body :deep(blockquote) { margin-top: .55rem; margin-bottom: .55rem; }
.slide-body :deep(img) { display: block; max-width: 100%; max-height: 18em; margin: .65rem auto; object-fit: contain; }
.slide-body :deep(pre), .slide-body :deep(table) { max-width: 100%; overflow: auto; font-size: .68em; }
.slide-body :deep(.mermaid-shell) { max-height: 19em; overflow: auto; }
.zett-slide footer { position: absolute; right: 2rem; bottom: 1.35rem; left: 2rem; display: flex; align-items: center; justify-content: space-between; color: #789083; font-size: .72rem; font-weight: 690; letter-spacing: .08em; text-transform: uppercase; }
.zett-slide footer small { font: inherit; font-variant-numeric: tabular-nums; }
.deck-navigation { position: absolute; right: .8rem; bottom: .72rem; z-index: 20; display: flex; align-items: center; gap: .35rem; padding: .25rem; border: 1px solid rgba(54, 88, 69, .12); border-radius: 2rem; background: rgba(255, 255, 255, .86); box-shadow: 0 5px 16px rgba(32, 52, 40, .09); backdrop-filter: blur(10px); }
.deck-navigation button { width: 1.75rem; height: 1.75rem; padding: 0; border: 0; border-radius: 50%; color: #365845; background: transparent; cursor: pointer; font-size: 1.3rem; line-height: 1; }
.deck-navigation button:hover:not(:disabled) { background: #e7efea; }
.deck-navigation button:disabled { opacity: .28; cursor: default; }
.deck-navigation span { min-width: 2.7rem; color: #69766e; font-size: .65rem; font-variant-numeric: tabular-nums; text-align: center; }
.compact .deck-navigation { right: .45rem; bottom: .42rem; transform: scale(.88); transform-origin: right bottom; }

@media (max-width: 700px) {
  .zett-slide { padding: 2.5rem 2.7rem 2.2rem; }
}
</style>
