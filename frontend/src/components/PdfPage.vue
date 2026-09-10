<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { PDFDocumentProxy, RenderTask } from 'pdfjs-dist'

const props = defineProps<{
  document: PDFDocumentProxy
  pageNumber: number
  scale: number
  baseWidth: number
  baseHeight: number
}>()

const root = ref<HTMLElement | null>(null)
const canvas = ref<HTMLCanvasElement | null>(null)
const active = ref(false)
const failed = ref(false)
const intrinsicWidth = ref<number | null>(null)
const intrinsicHeight = ref<number | null>(null)
const pageStyle = computed(() => ({
  width: `${Math.ceil((intrinsicWidth.value ?? props.baseWidth) * props.scale)}px`,
  height: `${Math.ceil((intrinsicHeight.value ?? props.baseHeight) * props.scale)}px`,
}))
let observer: IntersectionObserver | null = null
let renderTask: RenderTask | null = null
let renderVersion = 0

async function render(): Promise<void> {
  if (!active.value) return
  const version = ++renderVersion
  renderTask?.cancel()
  renderTask = null
  failed.value = false
  try {
    const page = await props.document.getPage(props.pageNumber)
    const intrinsicViewport = page.getViewport({ scale: 1 })
    intrinsicWidth.value = intrinsicViewport.width
    intrinsicHeight.value = intrinsicViewport.height
    await nextTick()
    if (version !== renderVersion || !canvas.value) return
    const pixelRatio = Math.max(1, window.devicePixelRatio || 1)
    const displayViewport = page.getViewport({ scale: props.scale })
    const renderViewport = page.getViewport({ scale: props.scale * pixelRatio })
    canvas.value.width = Math.ceil(renderViewport.width)
    canvas.value.height = Math.ceil(renderViewport.height)
    canvas.value.style.width = `${Math.ceil(displayViewport.width)}px`
    canvas.value.style.height = `${Math.ceil(displayViewport.height)}px`
    const currentTask = page.render({ canvas: canvas.value, viewport: renderViewport })
    renderTask = currentTask
    try {
      await currentTask.promise
    } finally {
      if (renderTask === currentTask) renderTask = null
    }
  } catch (error) {
    if (version !== renderVersion) return
    if (!(error instanceof Error) || error.name !== 'RenderingCancelledException') failed.value = true
  }
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

watch(() => props.scale, () => void render())
onBeforeUnmount(() => {
  renderVersion += 1
  observer?.disconnect()
  renderTask?.cancel()
})
</script>

<template>
  <article ref="root" class="pdf-page" :data-pdf-page="pageNumber" :style="pageStyle" :aria-label="`Page ${pageNumber}`">
    <canvas v-show="active && !failed" ref="canvas" />
    <span v-if="!active" class="page-placeholder">{{ pageNumber }}</span>
    <span v-else-if="failed" class="page-placeholder error">Page {{ pageNumber }} could not be rendered.</span>
  </article>
</template>

<style scoped>
.pdf-page { position: relative; flex: 0 0 auto; overflow: hidden; background: #fff; box-shadow: 0 8px 30px rgba(28,37,31,.16); transition: width 120ms ease, height 120ms ease; }
canvas { display: block; max-width: none; background: #fff; }
.page-placeholder { position: absolute; inset: 0; display: grid; place-items: center; color: #a0a7a2; font-size: .7rem; background: #f8f9f8; }
.page-placeholder.error { padding: 2rem; color: #9b5959; text-align: center; }
@media (prefers-reduced-motion: reduce) { .pdf-page { transition-duration: 1ms; } }
</style>
