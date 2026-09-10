<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, watch } from 'vue'
import {
  GlobalWorkerOptions,
  getDocument,
  type PDFDocumentLoadingTask,
  type RenderTask,
} from 'pdfjs-dist'
import pdfWorkerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url'
import { aiClient } from '../api/client'
import type { SessionAsset } from '../api/types'

GlobalWorkerOptions.workerSrc = pdfWorkerUrl

const props = defineProps<{
  asset: SessionAsset
}>()

const root = ref<HTMLElement | null>(null)
const canvas = ref<HTMLCanvasElement | null>(null)
const failed = ref(false)
let loadingTask: PDFDocumentLoadingTask | null = null
let renderTask: RenderTask | null = null
let abortController: AbortController | null = null
let loadVersion = 0

async function dispose(): Promise<void> {
  renderTask?.cancel()
  renderTask = null
  abortController?.abort()
  abortController = null
  if (loadingTask) await loadingTask.destroy()
  loadingTask = null
}

async function renderFirstPage(): Promise<void> {
  const version = ++loadVersion
  failed.value = false
  try {
    await dispose()
    abortController = new AbortController()
    const bytes = await aiClient.getSessionAssetContent(
      props.asset.session_id,
      props.asset.id,
      abortController.signal,
    )
    if (version !== loadVersion) return
    const currentLoadingTask = getDocument({ data: new Uint8Array(bytes) })
    loadingTask = currentLoadingTask
    const document = await currentLoadingTask.promise
    const page = await document.getPage(1)
    await nextTick()
    if (version !== loadVersion || !root.value || !canvas.value) return

    const baseViewport = page.getViewport({ scale: 1 })
    const displayWidth = root.value.clientWidth || 58
    const displayScale = displayWidth / baseViewport.width
    const pixelRatio = Math.max(1, window.devicePixelRatio || 1)
    const viewport = page.getViewport({ scale: displayScale * pixelRatio })
    canvas.value.width = Math.ceil(viewport.width)
    canvas.value.height = Math.ceil(viewport.height)
    canvas.value.style.width = `${displayWidth}px`
    canvas.value.style.height = `${Math.ceil((baseViewport.height * displayWidth) / baseViewport.width)}px`
    const currentRenderTask = page.render({ canvas: canvas.value, viewport })
    renderTask = currentRenderTask
    await currentRenderTask.promise
    if (renderTask === currentRenderTask) renderTask = null
  } catch (error) {
    if (version !== loadVersion || (error instanceof DOMException && error.name === 'AbortError')) return
    if (!(error instanceof Error) || error.name !== 'RenderingCancelledException') failed.value = true
  }
}

watch(() => [props.asset.session_id, props.asset.id], () => void renderFirstPage(), { immediate: true })
onBeforeUnmount(() => {
  loadVersion += 1
  void dispose().catch(() => undefined)
})
</script>

<template>
  <span ref="root" class="pdf-thumbnail" :class="{ failed }" aria-hidden="true">
    <canvas v-show="!failed" ref="canvas" />
    <strong v-if="failed">PDF</strong>
  </span>
</template>

<style scoped>
.pdf-thumbnail { display: grid; place-items: center; width: 100%; height: 100%; overflow: hidden; background: #dfe4e1; }
canvas { display: block; min-width: 100%; min-height: 100%; object-fit: cover; object-position: top center; background: #fff; }
.failed { color: #fff; background: linear-gradient(145deg, #b95b55, #93423f); }
strong { font-size: .58rem; letter-spacing: .04em; }
</style>
