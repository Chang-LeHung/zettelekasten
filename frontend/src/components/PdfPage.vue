<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { TextLayer, type PDFDocumentProxy, type PDFPageProxy, type RenderTask } from 'pdfjs-dist'

const props = defineProps<{
  document: PDFDocumentProxy
  pageNumber: number
  scale: number
  baseWidth: number
  baseHeight: number
}>()

const root = ref<HTMLElement | null>(null)
const canvas = ref<HTMLCanvasElement | null>(null)
const textLayer = ref<HTMLElement | null>(null)
const active = ref(false)
const failed = ref(false)
const intrinsicWidth = ref<number | null>(null)
const intrinsicHeight = ref<number | null>(null)
const pageStyle = computed(() => ({
  width: `${Math.ceil((intrinsicWidth.value ?? props.baseWidth) * props.scale)}px`,
  height: `${Math.ceil((intrinsicHeight.value ?? props.baseHeight) * props.scale)}px`,
  '--total-scale-factor': String(props.scale),
}))
let observer: IntersectionObserver | null = null
let renderTask: RenderTask | null = null
let textLayerTask: TextLayer | null = null
let loadedPage: PDFPageProxy | null = null
let loadedPageNumber: number | null = null
let renderVersion = 0
let scaleRenderTimer: number | null = null

async function render(): Promise<void> {
  if (!active.value) return
  const version = ++renderVersion
  const pageNumber = props.pageNumber
  const scale = props.scale
  renderTask?.cancel()
  renderTask = null
  failed.value = false
  try {
    const page = loadedPageNumber === pageNumber && loadedPage
      ? loadedPage
      : await props.document.getPage(pageNumber)
    if (version !== renderVersion) return
    loadedPage = page
    loadedPageNumber = pageNumber
    const intrinsicViewport = page.getViewport({ scale: 1 })
    await nextTick()
    if (version !== renderVersion || !canvas.value || !textLayer.value) return
    const pixelRatio = Math.max(1, window.devicePixelRatio || 1)
    const displayViewport = page.getViewport({ scale })
    const renderViewport = page.getViewport({ scale: scale * pixelRatio })
    // Keep the visible bitmap intact while PDF.js renders asynchronously.
    // Resizing the visible canvas first clears it and exposes blank page regions.
    const buffer = document.createElement('canvas')
    buffer.width = Math.ceil(renderViewport.width)
    buffer.height = Math.ceil(renderViewport.height)
    const currentTask = page.render({ canvas: buffer, viewport: renderViewport })
    renderTask = currentTask
    let textRender: Promise<unknown> = Promise.resolve()
    if (textLayerTask) {
      textLayerTask.update({ viewport: displayViewport })
    } else {
      textLayer.value.replaceChildren()
      textLayerTask = new TextLayer({
        textContentSource: page.streamTextContent(),
        container: textLayer.value,
        viewport: displayViewport,
      })
      textRender = textLayerTask.render()
    }
    try {
      await Promise.all([currentTask.promise, textRender])
      if (version !== renderVersion || !canvas.value) return
      const context = canvas.value.getContext('2d')
      if (!context) return
      intrinsicWidth.value = intrinsicViewport.width
      intrinsicHeight.value = intrinsicViewport.height
      canvas.value.width = buffer.width
      canvas.value.height = buffer.height
      context.drawImage(buffer, 0, 0)
    } finally {
      if (renderTask === currentTask) renderTask = null
    }
  } catch (error) {
    if (version !== renderVersion) return
    if (!(error instanceof Error) || error.name !== 'RenderingCancelledException') failed.value = true
  }
}

function renderPageChange(): void {
  renderVersion += 1
  renderTask?.cancel()
  renderTask = null
  loadedPage = null
  loadedPageNumber = null
  textLayerTask?.cancel()
  textLayerTask = null
  textLayer.value?.replaceChildren()
  void render()
}

function scheduleScaleRender(): void {
  renderVersion += 1
  renderTask?.cancel()
  renderTask = null
  if (loadedPage && textLayerTask) {
    textLayerTask.update({ viewport: loadedPage.getViewport({ scale: props.scale }) })
  }
  if (scaleRenderTimer !== null) window.clearTimeout(scaleRenderTimer)
  scaleRenderTimer = window.setTimeout(() => {
    scaleRenderTimer = null
    void render()
  }, 120)
}

onMounted(() => {
  observer = new IntersectionObserver(
    (entries) => {
      if (!entries.some((entry) => entry.isIntersecting)) return
      active.value = true
      observer?.disconnect()
      observer = null
      void render()
    },
    { rootMargin: '800px 0px' },
  )
  if (root.value) observer.observe(root.value)
})

watch(() => props.scale, scheduleScaleRender)
watch(() => props.pageNumber, renderPageChange)
onBeforeUnmount(() => {
  renderVersion += 1
  observer?.disconnect()
  if (scaleRenderTimer !== null) window.clearTimeout(scaleRenderTimer)
  renderTask?.cancel()
  textLayerTask?.cancel()
})
</script>

<template>
  <article ref="root" class="pdf-page" :data-pdf-page="pageNumber" :style="pageStyle" :aria-label="`Page ${pageNumber}`">
    <canvas v-show="active && !failed" ref="canvas" />
    <div v-show="active && !failed" ref="textLayer" class="text-layer" />
    <span v-if="!active" class="page-placeholder">{{ pageNumber }}</span>
    <span v-else-if="failed" class="page-placeholder error">Page {{ pageNumber }} could not be rendered.</span>
  </article>
</template>

<style scoped>
.pdf-page { position: relative; flex: 0 0 auto; overflow: hidden; background: #fff; box-shadow: 0 8px 30px rgba(28,37,31,.16); }
canvas { display: block; width: 100%; height: 100%; max-width: none; background: #fff; }
.text-layer { position: absolute; inset: 0; z-index: 1; overflow: clip; color: transparent; line-height: 1; text-align: initial; transform-origin: 0 0; user-select: text; -webkit-text-size-adjust: none; text-size-adjust: none; forced-color-adjust: none; --min-font-size: 1; --text-scale-factor: calc(var(--total-scale-factor) * var(--min-font-size)); }
/* PDF.js inserts these nodes itself, so they do not carry Vue's scope attribute. */
.text-layer :deep(:is(span, br)) { position: absolute; color: transparent; white-space: pre; cursor: text; transform-origin: 0 0; }
.text-layer :deep(> :not(.markedContent)), .text-layer :deep(.markedContent span:not(.markedContent)) { z-index: 1; font-size: calc(var(--text-scale-factor) * var(--font-height)); transform: rotate(var(--rotate)) scaleX(var(--scale-x)) scale(var(--min-font-size-inv)); --font-height: 0; --scale-x: 1; --rotate: 0deg; --min-font-size-inv: calc(1 / var(--min-font-size)); }
.text-layer :deep(.markedContent) { display: contents; }
.text-layer :deep(::selection) { color: transparent; background: rgba(83, 128, 101, .3); }
.text-layer :deep(br::selection) { background: transparent; }
.text-layer :deep(.endOfContent) { position: absolute; inset: 100% 0 0; display: block; cursor: default; user-select: none; }
.page-placeholder { position: absolute; inset: 0; display: grid; place-items: center; color: #a0a7a2; font-size: .7rem; background: #f8f9f8; }
.page-placeholder.error { padding: 2rem; color: #9b5959; text-align: center; }
</style>
