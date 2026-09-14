<script setup lang="ts">
import { computed, markRaw, nextTick, onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'
import {
  GlobalWorkerOptions,
  getDocument,
  type PDFDocumentLoadingTask,
  type PDFDocumentProxy,
} from 'pdfjs-dist'
import pdfWorkerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url'
import { aiClient } from '../api/client'
import type { SessionAsset } from '../api/types'
import PdfPage from './PdfPage.vue'
import { pdfDocumentOptions } from '../utils/pdfDocument'

GlobalWorkerOptions.workerSrc = pdfWorkerUrl

interface OutlineItem {
  title: string
  dest: string | unknown[] | null
  items: OutlineItem[]
}

interface OutlineEntry {
  id: string
  title: string
  destination: string | unknown[] | null
  depth: number
}

const props = defineProps<{ asset: Pick<SessionAsset, 'id' | 'session_id'> & { version?: number }; artifact?: boolean }>()
const stage = ref<HTMLElement | null>(null)
const documentProxy = shallowRef<PDFDocumentProxy | null>(null)
const loading = ref(true)
const awaitingCompilation = ref(false)
const errorMessage = ref('')
const currentPage = ref(1)
const pageCount = ref(0)
const inlineScale = ref(1)
const expandedScale = ref(1)
const basePageWidth = ref(612)
const basePageHeight = ref(792)
const outline = ref<OutlineEntry[]>([])
const expanded = ref(false)
const presenting = ref(false)
const presentationRoot = ref<HTMLElement | null>(null)
const presentationPage = ref(1)
const viewportWidth = ref(window.innerWidth)
const viewportHeight = ref(window.innerHeight)
const presentationScale = computed(() => Math.max(.1, Math.min(
  (viewportWidth.value - 64) / basePageWidth.value,
  (viewportHeight.value - 64) / basePageHeight.value,
)))
let presentationPreviousFocus: HTMLElement | null = null
let presentationPreviousOverflow = ''
let presentationWheelTimer: number | null = null
const scale = computed({
  get: () => expanded.value ? expandedScale.value : inlineScale.value,
  set: (value: number) => {
    if (expanded.value) expandedScale.value = value
    else inlineScale.value = value
  },
})
const inlineOutlineOpen = ref(false)
const expandedOutlineOpen = ref(false)
const outlineOpen = computed({
  get: () => expanded.value ? expandedOutlineOpen.value : inlineOutlineOpen.value,
  set: (open: boolean) => {
    if (expanded.value) expandedOutlineOpen.value = open
    else inlineOutlineOpen.value = open
  },
})
let previousFocus: HTMLElement | null = null
let previousOverflow = ''

async function toggleExpanded(): Promise<void> {
  if (expanded.value) {
    closeExpanded()
    return
  }
  previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null
  cancelPendingZoom()
  previousOverflow = document.body.style.overflow
  document.body.style.overflow = 'hidden'
  expanded.value = true
  await nextTick()
  previewRoot.value?.focus()
}

function closeExpanded(): void {
  if (!expanded.value) return
  cancelPendingZoom()
  expanded.value = false
  document.body.style.overflow = previousOverflow
  void nextTick(() => previousFocus?.focus())
}

async function startPresentation(): Promise<void> {
  if (!documentProxy.value || presenting.value) return
  presentationPreviousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null
  presentationPreviousOverflow = document.body.style.overflow
  presentationPage.value = currentPage.value
  document.body.style.overflow = 'hidden'
  presenting.value = true
  await nextTick()
  updatePresentationViewport()
  presentationRoot.value?.focus()
  try {
    await presentationRoot.value?.requestFullscreen?.()
  } catch {
    // The fixed in-page stage remains fully usable when browser fullscreen is denied.
  }
}

function stopPresentation(exitNativeFullscreen = true): void {
  if (!presenting.value) return
  presenting.value = false
  if (presentationWheelTimer !== null) window.clearTimeout(presentationWheelTimer)
  presentationWheelTimer = null
  if (exitNativeFullscreen && document.fullscreenElement === presentationRoot.value) {
    void document.exitFullscreen().catch(() => undefined)
  }
  document.body.style.overflow = expanded.value ? 'hidden' : presentationPreviousOverflow
  void nextTick(() => presentationPreviousFocus?.focus())
}

function changePresentationPage(offset: number): void {
  presentationPage.value = Math.min(pageCount.value, Math.max(1, presentationPage.value + offset))
}

function handlePresentationKey(event: KeyboardEvent): void {
  if (!presenting.value) return
  if (['ArrowRight', 'ArrowDown', 'PageDown', ' '].includes(event.key)) changePresentationPage(1)
  else if (['ArrowLeft', 'ArrowUp', 'PageUp'].includes(event.key)) changePresentationPage(-1)
  else if (event.key === 'Home') presentationPage.value = 1
  else if (event.key === 'End') presentationPage.value = pageCount.value
  else if (event.key === 'Escape') stopPresentation()
  else return
  event.preventDefault()
  event.stopPropagation()
}

function handlePresentationWheel(event: WheelEvent): void {
  event.preventDefault()
  if (presentationWheelTimer !== null || Math.abs(event.deltaY) < 8) return
  changePresentationPage(event.deltaY > 0 ? 1 : -1)
  presentationWheelTimer = window.setTimeout(() => { presentationWheelTimer = null }, 320)
}

function updatePresentationViewport(): void {
  viewportWidth.value = presentationRoot.value?.clientWidth || window.innerWidth
  viewportHeight.value = presentationRoot.value?.clientHeight || window.innerHeight
}

function handleFullscreenChange(): void {
  if (!presenting.value) return
  if (!document.fullscreenElement) stopPresentation(false)
  else updatePresentationViewport()
}

function handleExpandedKey(event: KeyboardEvent): void {
  if (!expanded.value) return
  if (event.key === 'Escape') {
    event.preventDefault()
    event.stopPropagation()
    closeExpanded()
  } else if (event.key === 'Tab') {
    const controls = [...(previewRoot.value?.querySelectorAll<HTMLElement>('button:not(:disabled), [tabindex="0"]') || [])]
    const first = controls[0]
    const last = controls.at(-1)
    if (event.shiftKey && (document.activeElement === first || document.activeElement === previewRoot.value)) {
      event.preventDefault()
      last?.focus()
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault()
      first?.focus()
    }
  }
}
const previewRoot = ref<HTMLElement | null>(null)
const outlineWidth = ref(240)
const resizingOutline = ref(false)
let resizePointer: number | null = null
let resizeStartX = 0
let resizeStartWidth = 240

function setOutlineWidth(width: number): void {
  const available = previewRoot.value?.getBoundingClientRect().width || 800
  outlineWidth.value = Math.max(Math.min(120, available * 0.45), Math.min(width, 480, available * 0.6))
}

function startOutlineResize(event: PointerEvent): void {
  if (event.button !== 0) return
  resizePointer = event.pointerId
  resizeStartX = event.clientX
  resizeStartWidth = previewRoot.value?.querySelector('.pdf-outline')?.getBoundingClientRect().width || outlineWidth.value
  resizingOutline.value = true
  ;(event.currentTarget as HTMLElement).setPointerCapture(event.pointerId)
  event.preventDefault()
}

function resizeOutline(event: PointerEvent): void {
  if (resizePointer !== event.pointerId) return
  setOutlineWidth(resizeStartWidth + event.clientX - resizeStartX)
}

function stopOutlineResize(): void {
  resizePointer = null
  resizingOutline.value = false
}

function resizeOutlineWithKeyboard(event: KeyboardEvent): void {
  if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return
  event.preventDefault()
  setOutlineWidth(event.key === 'Home' ? 120 : event.key === 'End' ? 480 : outlineWidth.value + (event.key === 'ArrowLeft' ? -20 : 20))
}
let loadingTask: PDFDocumentLoadingTask | null = null
let abortController: AbortController | null = null
let loadVersion = 0
let scrollFrame: number | null = null
let zoomFrame: number | null = null
let pendingZoomDelta = 0
function cancelPendingZoom(): void {
  // A queued pinch belongs to its current view, never the view entered next.
  if (zoomFrame !== null) window.cancelAnimationFrame(zoomFrame)
  zoomFrame = null
  pendingZoomDelta = 0
}
let zoomPointer = { x: 0, y: 0 }

function flattenOutline(items: OutlineItem[], depth = 0, path = 'root'): OutlineEntry[] {
  return items.flatMap((item, index) => {
    const id = `${path}-${index}`
    return [
      { id, title: item.title, destination: item.dest, depth },
      ...flattenOutline(item.items || [], depth + 1, id),
    ]
  })
}

async function disposeDocument(): Promise<void> {
  abortController?.abort()
  abortController = null
  if (loadingTask) await loadingTask.destroy()
  loadingTask = null
  documentProxy.value = null
}

async function loadDocument(): Promise<void> {
  const version = ++loadVersion
  loading.value = true
  awaitingCompilation.value = false
  errorMessage.value = ''
  currentPage.value = 1
  pageCount.value = 0
  outline.value = []
  try {
    await disposeDocument()
    abortController = new AbortController()
    const readContent = props.artifact ? aiClient.getArtifactPdfContent : aiClient.getSessionAssetContent
    const bytes = await readContent(
      props.asset.session_id,
      props.asset.id,
      abortController.signal,
    )
    if (version !== loadVersion) return
    if (bytes === null) {
      awaitingCompilation.value = true
      return
    }
    const currentLoadingTask = getDocument(pdfDocumentOptions(bytes))
    loadingTask = currentLoadingTask
    const loadedDocument = await currentLoadingTask.promise
    if (version !== loadVersion) {
      await currentLoadingTask.destroy()
      if (loadingTask === currentLoadingTask) loadingTask = null
      return
    }

    documentProxy.value = markRaw(loadedDocument)
    pageCount.value = loadedDocument.numPages
    const [firstPage, documentOutline] = await Promise.all([
      loadedDocument.getPage(1),
      loadedDocument.getOutline(),
    ])
    if (version !== loadVersion) return
    const viewport = firstPage.getViewport({ scale: 1 })
    basePageWidth.value = viewport.width
    basePageHeight.value = viewport.height
    outline.value = flattenOutline((documentOutline || []) as OutlineItem[])
    await nextTick()
    updateCurrentPage()
  } catch (error) {
    if (version !== loadVersion || (error instanceof DOMException && error.name === 'AbortError')) return
    errorMessage.value = error instanceof Error ? error.message : 'Unable to preview this PDF.'
  } finally {
    if (version === loadVersion) loading.value = false
  }
}

function updateCurrentPage(): void {
  const container = stage.value
  if (!container) return
  const containerTop = container.getBoundingClientRect().top
  let nearestPage = currentPage.value
  let nearestDistance = Number.POSITIVE_INFINITY
  for (const element of container.querySelectorAll<HTMLElement>('[data-pdf-page]')) {
    const distance = Math.abs(element.getBoundingClientRect().top - containerTop - 16)
    if (distance < nearestDistance) {
      nearestDistance = distance
      nearestPage = Number(element.dataset.pdfPage)
    }
  }
  if (Number.isFinite(nearestPage)) currentPage.value = nearestPage
}

function handleScroll(): void {
  if (scrollFrame !== null) return
  scrollFrame = window.requestAnimationFrame(() => {
    scrollFrame = null
    updateCurrentPage()
  })
}

function handleWheel(event: WheelEvent): void {
  // Browsers expose trackpad pinch gestures as ctrl-modified wheel events.
  // Consume only that gesture so ordinary wheel scrolling remains native.
  if (!event.ctrlKey) return
  event.preventDefault()
  pendingZoomDelta += event.deltaY
  zoomPointer = { x: event.clientX, y: event.clientY }
  if (zoomFrame !== null) return
  zoomFrame = window.requestAnimationFrame(applyWheelZoom)
}

function applyWheelZoom(): void {
  zoomFrame = null
  const container = stage.value
  if (!container) return
  const previousScale = scale.value
  const normalizedDelta = Math.min(160, Math.max(-160, pendingZoomDelta))
  pendingZoomDelta = 0
  const nextScale = Math.min(2.5, Math.max(0.5, previousScale * Math.exp(-normalizedDelta * 0.002)))
  if (Math.abs(nextScale - previousScale) < 0.005) return

  const bounds = container.getBoundingClientRect()
  const pointerX = zoomPointer.x - bounds.left
  const pointerY = zoomPointer.y - bounds.top
  const contentX = container.scrollLeft + pointerX
  const contentY = container.scrollTop + pointerY
  const ratio = nextScale / previousScale
  scale.value = Number(nextScale.toFixed(2))
  void nextTick(() => {
    container.scrollTo({
      left: contentX * ratio - pointerX,
      top: contentY * ratio - pointerY,
      behavior: 'auto',
    })
    updateCurrentPage()
  })
}

function scrollToPage(page: number, behavior: ScrollBehavior = 'smooth'): void {
  const container = stage.value
  const target = container?.querySelector<HTMLElement>(`[data-pdf-page="${page}"]`)
  if (!container || !target) return
  currentPage.value = page
  container.scrollTo({ top: target.offsetTop - 16, behavior })
}

async function resolveOutlineDestination(entry: OutlineEntry): Promise<void> {
  const document = documentProxy.value
  if (!document || !entry.destination) return
  const destination = typeof entry.destination === 'string'
    ? await document.getDestination(entry.destination)
    : entry.destination
  const reference = destination?.[0]
  if (reference === undefined || reference === null) return
  const pageIndex = typeof reference === 'number' ? reference : await document.getPageIndex(reference)
  scrollToPage(pageIndex + 1, 'auto')
}

function changePage(offset: number): void {
  scrollToPage(Math.min(pageCount.value, Math.max(1, currentPage.value + offset)))
}

function changeScale(offset: number): void {
  const anchoredPage = currentPage.value
  scale.value = Math.min(2.5, Math.max(0.5, Number((scale.value + offset).toFixed(2))))
  void nextTick(() => scrollToPage(anchoredPage, 'auto'))
}

function resetScale(): void {
  const anchoredPage = currentPage.value
  scale.value = 1
  void nextTick(() => scrollToPage(anchoredPage, 'auto'))
}

watch(() => [props.asset.session_id, props.asset.id, props.asset.version, props.artifact], () => void loadDocument(), { immediate: true })
onMounted(() => {
  window.addEventListener('resize', updatePresentationViewport)
  window.addEventListener('keydown', handlePresentationKey, true)
  document.addEventListener('fullscreenchange', handleFullscreenChange)
})
onBeforeUnmount(() => {
  stopPresentation()
  window.removeEventListener('resize', updatePresentationViewport)
  window.removeEventListener('keydown', handlePresentationKey, true)
  document.removeEventListener('fullscreenchange', handleFullscreenChange)
  if (expanded.value) document.body.style.overflow = previousOverflow
  loadVersion += 1
  if (scrollFrame !== null) window.cancelAnimationFrame(scrollFrame)
  if (zoomFrame !== null) window.cancelAnimationFrame(zoomFrame)
  void disposeDocument().catch(() => undefined)
})
</script>

<template>
  <Teleport to="body" :disabled="!expanded">
  <div :class="expanded ? 'pdf-expanded-backdrop' : 'pdf-inline-host'" @click.self="closeExpanded">
  <div ref="previewRoot" class="pdf-preview" tabindex="-1" :role="expanded ? 'dialog' : undefined" :aria-modal="expanded ? true : undefined" :aria-label="expanded ? 'Expanded PDF preview' : undefined" :class="{ 'outline-open': outlineOpen, 'artifact-pdf': artifact, 'resizing-outline': resizingOutline, 'pdf-expanded': expanded }" :style="{ '--outline-width': `${outlineWidth}px` }" @keydown="handleExpandedKey">
    <div class="pdf-toolbar" aria-label="PDF controls">
      <button class="outline-toggle" type="button" :aria-expanded="outlineOpen" aria-label="Toggle document outline" @click="outlineOpen = !outlineOpen">☰</button>
      <button class="expand-toggle" type="button" :aria-label="expanded ? 'Close expanded PDF preview' : 'Expand PDF preview'" :title="expanded ? 'Close (Esc)' : 'Expand preview'" @click="toggleExpanded">
        <svg v-if="expanded" viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18" /></svg>
        <svg v-else viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path d="M9 3H3v6m12-6h6v6M3 15v6h6m12-6v6h-6" /></svg>
      </button>
      <button class="presentation-toggle" type="button" :disabled="!documentProxy || loading" aria-label="Start PDF presentation" title="Present PDF" @click="startPresentation">
        <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="4" width="18" height="13" rx="2" /><path d="M12 17v4m-4 0h8M10 8l5 2.5-5 2.5Z" /></svg>
      </button>
      <div>
        <button type="button" :disabled="currentPage <= 1 || loading" aria-label="Previous page" @click="changePage(-1)">‹</button>
        <span>{{ currentPage }} / {{ pageCount || '—' }}</span>
        <button type="button" :disabled="currentPage >= pageCount || loading" aria-label="Next page" @click="changePage(1)">›</button>
      </div>
      <div>
        <button type="button" :disabled="scale <= 0.5 || loading" aria-label="Zoom out" @click="changeScale(-0.25)">−</button>
        <button class="scale-value" type="button" :disabled="loading" aria-label="Reset zoom" @click="resetScale">{{ Math.round(scale * 100) }}%</button>
        <button type="button" :disabled="scale >= 2.5 || loading" aria-label="Zoom in" @click="changeScale(0.25)">+</button>
      </div>
    </div>

    <aside v-if="outlineOpen" class="pdf-outline" aria-label="Document outline">
      <header><div><strong>Contents</strong><small>{{ outline.length ? `${outline.length} sections` : 'No outline' }}</small></div><button type="button" aria-label="Collapse document outline" title="Collapse outline" @click="outlineOpen = false">‹</button></header>
      <nav v-if="outline.length">
        <button
          v-for="entry in outline"
          :key="entry.id"
          type="button"
          :style="{ '--outline-depth': entry.depth }"
          @click="resolveOutlineDestination(entry)"
        >{{ entry.title }}</button>
      </nav>
      <p v-else>This PDF does not include a document outline.</p>
    </aside>

    <div v-if="outlineOpen" class="pdf-outline-resizer" role="separator" tabindex="0" aria-label="Resize document outline" aria-orientation="vertical" :aria-valuenow="Math.round(outlineWidth)" @pointerdown="startOutlineResize" @pointermove="resizeOutline" @pointerup="stopOutlineResize" @pointercancel="stopOutlineResize" @lostpointercapture="stopOutlineResize" @keydown="resizeOutlineWithKeyboard" />

    <div ref="stage" class="pdf-pages" @scroll.passive="handleScroll" @wheel="handleWheel">
      <div v-if="documentProxy && !errorMessage" class="pdf-page-stack">
        <PdfPage
          v-for="page in pageCount"
          :key="page"
          :document="documentProxy"
          :page-number="page"
          :scale="scale"
          :base-width="basePageWidth"
          :base-height="basePageHeight"
        />
      </div>
      <div v-if="loading" class="pdf-state"><span class="spinner" />Loading PDF…</div>
      <div v-else-if="awaitingCompilation" class="pdf-state" role="status">
        <strong>PDF not generated yet</strong>
        <span>The project is ready. Its PDF will be available after compilation.</span>
        <button type="button" @click="loadDocument">Refresh preview</button>
      </div>
      <div v-else-if="errorMessage" class="pdf-state error" role="alert">
        <strong>Preview unavailable</strong>
        <span>{{ errorMessage }}</span>
        <button type="button" @click="loadDocument">Try again</button>
      </div>
    </div>
  </div>
  </div>
  </Teleport>

  <Teleport to="body">
    <div v-if="presenting && documentProxy" ref="presentationRoot" class="pdf-presentation" role="dialog" aria-modal="true" aria-label="PDF presentation" tabindex="-1" @wheel="handlePresentationWheel">
      <div class="presentation-page">
        <PdfPage :key="presentationPage" :document="documentProxy" :page-number="presentationPage" :scale="presentationScale" :base-width="basePageWidth" :base-height="basePageHeight" />
      </div>
      <button class="presentation-close" type="button" aria-label="Exit PDF presentation" title="Exit presentation (Esc)" @click="stopPresentation()">×</button>
      <button class="presentation-previous" type="button" :disabled="presentationPage <= 1" aria-label="Previous presentation page" @click="changePresentationPage(-1)">‹</button>
      <button class="presentation-next" type="button" :disabled="presentationPage >= pageCount" aria-label="Next presentation page" @click="changePresentationPage(1)">›</button>
      <span class="presentation-progress">{{ presentationPage }} / {{ pageCount }}</span>
    </div>
  </Teleport>
</template>

<style scoped>
.pdf-preview { display: grid; grid-template: auto minmax(0, 1fr) / minmax(0, 1fr); width: 100%; height: 100%; min-height: 0; color: #3e4741; }
.pdf-preview.outline-open { grid-template-columns: min(var(--outline-width), 60%) 6px minmax(0, 1fr); }
.pdf-outline-resizer { cursor: col-resize; touch-action: none; background: #eef1ef; }
.pdf-outline-resizer:hover, .pdf-outline-resizer:focus-visible, .resizing-outline .pdf-outline-resizer { background: #9cb3a4; outline: none; }
.pdf-preview.resizing-outline { user-select: none; cursor: col-resize; }
.pdf-preview.artifact-pdf { height: 65vh; min-height: 24rem; }
.pdf-inline-host { display: contents; }
.pdf-expanded-backdrop { position: fixed; inset: 0; z-index: 1600; display: grid; place-items: center; padding: 2vh 2vw; background: rgba(31,38,34,.4); }
.pdf-preview.pdf-expanded { width: 96vw; height: 96vh; height: 96dvh; min-height: 0; overflow: hidden; border-radius: .9rem; background: #fafbfa; box-shadow: 0 24px 90px rgba(25,36,29,.25); outline: none; }
.pdf-toolbar .expand-toggle { position: absolute; right: .65rem; top: 50%; transform: translateY(-50%); width: 2.5rem; height: 2.5rem; border-radius: .65rem; }
.pdf-toolbar .presentation-toggle { position: absolute; right: 3.45rem; top: 50%; transform: translateY(-50%); }
.pdf-expanded .expand-toggle { background: #e8eeea; color: #3d5145; }
.pdf-toolbar { position: relative; z-index: 2; grid-column: 1 / -1; display: flex; align-items: center; justify-content: center; gap: 1.5rem; min-height: 2.85rem; padding: .4rem .75rem; border-bottom: 1px solid rgba(55,70,61,.12); background: rgba(250,251,250,.96); box-shadow: 0 2px 10px rgba(33,42,36,.04); }
.pdf-toolbar > div { display: flex; align-items: center; gap: .34rem; }
.pdf-toolbar span { min-width: 3.8rem; color: #747d77; font-size: .7rem; font-variant-numeric: tabular-nums; text-align: center; }
.pdf-toolbar button, .pdf-state button, .pdf-outline button { border: 0; color: #4d5a52; background: transparent; cursor: pointer; }
.pdf-toolbar button { display: grid; place-items: center; width: 1.9rem; height: 1.9rem; border-radius: .55rem; font-size: 1.1rem; }
.pdf-toolbar button:hover:not(:disabled) { color: #294d3b; background: #e8efeb; }
.pdf-toolbar button:disabled { opacity: .3; cursor: default; }
.pdf-toolbar .outline-toggle { position: absolute; left: .75rem; font-size: .9rem; }
.pdf-toolbar .scale-value { width: 3.8rem; color: #747d77; font-size: .7rem; font-variant-numeric: tabular-nums; }
.pdf-outline { min-width: 0; min-height: 0; overflow: auto; background: #f6f8f7; }
.pdf-outline header { display: flex; align-items: center; justify-content: space-between; min-height: auto; padding: 1rem .9rem .75rem; border-bottom: 1px solid rgba(55,70,61,.08); background: transparent; }
.pdf-outline header button { padding: .25rem .5rem; border-radius: .4rem; font-size: 1.25rem; }
.pdf-outline header button:hover { background: #e7eee9; }
.pdf-outline header strong, .pdf-outline header small { display: block; }
.pdf-outline header strong { color: #3d4941; font-size: .74rem; }
.pdf-outline header small { margin-top: .18rem; color: #8a928d; font-size: .6rem; }
.pdf-outline nav { display: grid; padding: .45rem; }
.pdf-outline nav button { width: 100%; padding: .48rem .55rem .48rem calc(.55rem + var(--outline-depth) * .72rem); border-radius: .45rem; overflow: hidden; color: #5f6963; font-size: .66rem; line-height: 1.35; text-align: left; text-overflow: ellipsis; white-space: nowrap; }
.pdf-outline nav button:hover { color: #2f513e; background: #e7eee9; }
.pdf-outline p { margin: 1rem; color: #8a928d; font-size: .65rem; line-height: 1.5; }
.pdf-pages { position: relative; min-width: 0; min-height: 0; overflow: auto; overflow-anchor: none; scrollbar-gutter: stable; padding: 1.5rem; background: #e7eae8; }
.pdf-page-stack { display: grid; justify-items: center; gap: 1rem; width: max-content; min-width: 100%; }
.pdf-presentation { position: fixed; inset: 0; z-index: 1900; display: grid; place-items: center; overflow: hidden; color: #eef3ef; background: #1c211e; outline: none; }
.presentation-page { display: grid; place-items: center; width: 100%; height: 100%; }
.presentation-page :deep(.pdf-page) { box-shadow: 0 20px 80px rgba(0,0,0,.36); }
.pdf-presentation > button { position: absolute; display: grid; place-items: center; border: 0; color: rgba(245,248,246,.84); background: rgba(20,26,22,.5); backdrop-filter: blur(12px); cursor: pointer; }
.pdf-presentation > button:hover:not(:disabled) { color: #fff; background: rgba(70,91,78,.78); }
.pdf-presentation > button:disabled { opacity: .22; cursor: default; }
.presentation-close { top: 1rem; right: 1rem; width: 3rem; height: 3rem; border-radius: .8rem; font-size: 1.7rem; }
.presentation-previous, .presentation-next { top: 50%; width: 3.25rem; height: 4.5rem; transform: translateY(-50%); border-radius: .85rem; font-size: 2.25rem; }
.presentation-previous { left: 1rem; }
.presentation-next { right: 1rem; }
.presentation-progress { position: absolute; right: 1rem; bottom: 1rem; min-width: 4.4rem; padding: .48rem .7rem; border-radius: .6rem; color: rgba(245,248,246,.86); background: rgba(20,26,22,.55); font-size: .75rem; font-variant-numeric: tabular-nums; text-align: center; backdrop-filter: blur(12px); }
.pdf-state { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; gap: .55rem; color: #737c76; font-size: .78rem; }
.pdf-state.error { flex-direction: column; padding: 2rem; }
.pdf-state.error strong { color: #3d4941; font-size: .9rem; }
.pdf-state.error button { margin-top: .4rem; padding: .5rem .8rem; border-radius: .55rem; color: #fff; background: #476957; }
.spinner { width: .9rem; height: .9rem; border: 2px solid #cbd5cf; border-top-color: #527460; border-radius: 50%; animation: spin .75s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
@media (max-width: 760px) {
  .pdf-toolbar { justify-content: center; gap: .35rem; padding-inline: 2.75rem; }
  .pdf-pages { padding: .75rem; }
}
@media (prefers-reduced-motion: reduce) { .spinner { animation-duration: 1.5s; } }
</style>
