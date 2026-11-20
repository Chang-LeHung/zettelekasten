<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { PDFDocumentProxy, RenderTask } from 'pdfjs-dist'
import type { DiffRect } from '../utils/pdfTypesetDiff'

/**
 * A horizontal band of one PDF page, drawn as typeset text with the changed words boxed.
 * Only a band is rendered, so a card for one edited sentence never paints a whole page.
 */
const props = defineProps<{
  document: PDFDocumentProxy
  page: number
  /** The band to show, in page units. */
  band: { y: number; height: number }
  /** Horizontal extent to show, in page units. */
  column: { x: number; width: number }
  marks: readonly DiffRect[]
  kind: 'del' | 'add' | 'fig'
  /** Pixel width the band is drawn at. */
  width: number
}>()

const host = ref<HTMLElement | null>(null)
const canvas = ref<HTMLCanvasElement | null>(null)
const visible = ref(false)
const failed = ref(false)
const scale = computed(() => (props.column.width > 0 ? props.width / props.column.width : 1))
const height = computed(() => Math.max(1, Math.ceil(props.band.height * scale.value)))
let observer: IntersectionObserver | null = null
let task: RenderTask | null = null
let version = 0

async function draw(): Promise<void> {
  if (!visible.value || !canvas.value || props.width <= 0) return
  const mine = ++version
  task?.cancel()
  failed.value = false
  try {
    const page = await props.document.getPage(props.page)
    if (mine !== version || !canvas.value) return
    const ratio = Math.max(1, window.devicePixelRatio || 1)
    const viewport = page.getViewport({ scale: scale.value * ratio })
    const buffer = document.createElement('canvas')
    buffer.width = Math.ceil(props.width * ratio)
    buffer.height = Math.ceil(height.value * ratio)
    const current = page.render({
      canvas: buffer,
      viewport,
      transform: [1, 0, 0, 1, -props.column.x * scale.value * ratio, -props.band.y * scale.value * ratio],
    })
    task = current
    await current.promise
    task = null
    if (mine !== version || !canvas.value) return
    canvas.value.width = buffer.width
    canvas.value.height = buffer.height
    canvas.value.getContext('2d')?.drawImage(buffer, 0, 0)
  } catch (error) {
    if (mine !== version) return
    if (!(error instanceof Error) || error.name !== 'RenderingCancelledException') failed.value = true
  }
}

function markStyle(rect: DiffRect): Record<string, string> {
  const pad = 1.5
  return {
    left: `${(rect.x - props.column.x - pad) * scale.value}px`,
    top: `${(rect.y - props.band.y - pad) * scale.value}px`,
    width: `${(rect.width + pad * 2) * scale.value}px`,
    height: `${(rect.height + pad * 2) * scale.value}px`,
  }
}

onMounted(() => {
  observer = new IntersectionObserver((entries) => {
    if (!entries.some((entry) => entry.isIntersecting)) return
    visible.value = true
    // Drawn once it is near the viewport; nothing more to observe.
    observer?.disconnect()
  }, { rootMargin: '700px 0px' })
  if (host.value) observer.observe(host.value)
})
onBeforeUnmount(() => {
  version += 1
  task?.cancel()
  observer?.disconnect()
})
watch(() => [visible.value, props.document, props.page, props.band.y, props.band.height, props.column.x, props.column.width, props.width], () => { void draw() })
</script>

<template>
  <div ref="host" class="crop" :class="kind" :style="{ width: `${width}px`, height: `${height}px` }">
    <canvas ref="canvas" :style="{ width: `${width}px`, height: `${height}px` }" />
    <i v-for="(mark, index) in marks" :key="index" class="crop-mark" :style="markStyle(mark)" />
    <span v-if="failed" class="crop-failed">!</span>
  </div>
</template>

<style scoped>
.crop { position: relative; overflow: hidden; background: #fff; }
.crop canvas { display: block; }
.crop-mark { position: absolute; border-radius: .2rem; pointer-events: none; mix-blend-mode: multiply; }
.crop.del .crop-mark { background: rgba(232, 84, 76, .26); }
.crop.del .crop-mark::after { content: ''; position: absolute; left: 0; right: 0; top: 52%; height: 1.5px; background: rgba(196, 52, 44, .85); }
.crop.add .crop-mark { background: rgba(52, 181, 106, .3); }
.crop.fig .crop-mark { background: rgba(242, 171, 40, .22); box-shadow: inset 0 0 0 1.5px rgba(214, 140, 20, .75); border-radius: .35rem; }
.crop-failed { position: absolute; right: .4rem; top: .3rem; color: #a23232; font-weight: 700; }
</style>
