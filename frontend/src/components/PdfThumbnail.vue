<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, watch } from 'vue'
import {
  GlobalWorkerOptions,
  getDocument,
  type PDFDocumentLoadingTask,
  type RenderTask,
} from 'pdfjs-dist'
import pdfWorkerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url'
import { aiClient, assetClient } from '../api/client'
import type { SessionAsset, StaticAsset } from '../api/types'
import { pdfDocumentOptions } from '../utils/pdfDocument'

GlobalWorkerOptions.workerSrc = pdfWorkerUrl

const props = withDefaults(defineProps<{
  asset: (Pick<SessionAsset, 'id' | 'session_id'> & Partial<Pick<SessionAsset, 'source_url' | 'content_url'>>) | StaticAsset
  artifact?: boolean
  fit?: 'cover' | 'contain'
}>(), {
  artifact: false,
  fit: 'cover',
})

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
    const referencedUrl = !props.artifact && 'session_id' in props.asset ? props.asset.source_url : null
    const bytes = props.artifact
      ? await aiClient.getArtifactPdfContent(
          'session_id' in props.asset ? props.asset.session_id : '',
          props.asset.id,
          abortController.signal,
        )
      : referencedUrl
        ? await assetClient.getUrlContent(referencedUrl, abortController.signal)
      : 'session_id' in props.asset
        ? await aiClient.getSessionAssetContent(props.asset.session_id, props.asset.id, abortController.signal)
        : await assetClient.getContent(props.asset.id, abortController.signal)
    if (version !== loadVersion) return
    if (bytes === null || bytes.byteLength === 0) {
      failed.value = true
      return
    }
    const currentLoadingTask = getDocument(pdfDocumentOptions(bytes))
    loadingTask = currentLoadingTask
    const document = await currentLoadingTask.promise
    const page = await document.getPage(1)
    await nextTick()
    if (version !== loadVersion || !root.value || !canvas.value) return

    const baseViewport = page.getViewport({ scale: 1 })
    const availableWidth = root.value.clientWidth || 58
    const availableHeight = root.value.clientHeight || 58
    const scaleForWidth = availableWidth / baseViewport.width
    const scaleForHeight = availableHeight / baseViewport.height
    const displayScale = props.fit === 'contain'
      ? Math.min(scaleForWidth, scaleForHeight)
      : Math.max(scaleForWidth, scaleForHeight)
    const displayWidth = Math.max(1, Math.floor(baseViewport.width * displayScale))
    const displayHeight = Math.max(1, Math.floor(baseViewport.height * displayScale))
    const pixelRatio = Math.max(1, window.devicePixelRatio || 1)
    const viewport = page.getViewport({ scale: displayScale * pixelRatio })
    canvas.value.width = Math.ceil(viewport.width)
    canvas.value.height = Math.ceil(viewport.height)
    canvas.value.style.width = `${displayWidth}px`
    canvas.value.style.height = `${displayHeight}px`
    const currentRenderTask = page.render({ canvas: canvas.value, viewport })
    renderTask = currentRenderTask
    await currentRenderTask.promise
    if (renderTask === currentRenderTask) renderTask = null
  } catch (error) {
    if (version !== loadVersion || (error instanceof DOMException && error.name === 'AbortError')) return
    if (!(error instanceof Error) || error.name !== 'RenderingCancelledException') failed.value = true
  }
}

watch(
  [
    () => 'session_id' in props.asset ? props.asset.session_id : null,
    () => props.asset.id,
    () => props.artifact,
    () => props.fit,
  ],
  () => void renderFirstPage(),
  { immediate: true },
)
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
.pdf-thumbnail { display: grid; place-items: center; width: 100%; height: 100%; min-width: 0; min-height: 0; overflow: hidden; background: #dfe4e1; }
canvas { display: block; max-width: 100%; max-height: 100%; background: #fff; }
.failed { color: #fff; background: linear-gradient(145deg, #b95b55, #93423f); }
strong { font-size: .58rem; letter-spacing: .04em; }
</style>
