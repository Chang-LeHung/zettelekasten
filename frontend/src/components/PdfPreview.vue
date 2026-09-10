<script setup lang="ts">
import { markRaw, nextTick, onBeforeUnmount, ref, shallowRef, watch } from 'vue'
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

const props = defineProps<{ asset: SessionAsset }>()
const stage = ref<HTMLElement | null>(null)
const documentProxy = shallowRef<PDFDocumentProxy | null>(null)
const loading = ref(true)
const errorMessage = ref('')
const currentPage = ref(1)
const pageCount = ref(0)
const scale = ref(1)
const basePageWidth = ref(612)
const basePageHeight = ref(792)
const outline = ref<OutlineEntry[]>([])
const outlineOpen = ref(true)
let loadingTask: PDFDocumentLoadingTask | null = null
let abortController: AbortController | null = null
let loadVersion = 0
let scrollFrame: number | null = null

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
  errorMessage.value = ''
  currentPage.value = 1
  pageCount.value = 0
  outline.value = []
  try {
    await disposeDocument()
    abortController = new AbortController()
    const bytes = await aiClient.getSessionAssetContent(
      props.asset.session_id,
      props.asset.id,
      abortController.signal,
    )
    if (version !== loadVersion) return
    const currentLoadingTask = getDocument({ data: new Uint8Array(bytes) })
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
  const container = stage.value
  if (!container) return

  const previousScale = scale.value
  const normalizedDelta = Math.min(100, Math.max(-100, event.deltaY))
  const nextScale = Math.min(2.5, Math.max(0.5, previousScale * Math.exp(-normalizedDelta * 0.002)))
  if (Math.abs(nextScale - previousScale) < 0.005) return

  const bounds = container.getBoundingClientRect()
  const pointerX = event.clientX - bounds.left
  const pointerY = event.clientY - bounds.top
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

watch(() => [props.asset.session_id, props.asset.id], () => void loadDocument(), { immediate: true })
onBeforeUnmount(() => {
  loadVersion += 1
  if (scrollFrame !== null) window.cancelAnimationFrame(scrollFrame)
  void disposeDocument().catch(() => undefined)
})
</script>

<template>
  <div class="pdf-preview" :class="{ 'outline-open': outlineOpen }">
    <div class="pdf-toolbar" aria-label="PDF controls">
      <button class="outline-toggle" type="button" :aria-expanded="outlineOpen" aria-label="Toggle document outline" @click="outlineOpen = !outlineOpen">☰</button>
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
      <header><strong>Contents</strong><small>{{ outline.length ? `${outline.length} sections` : 'No outline' }}</small></header>
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
      <div v-else-if="errorMessage" class="pdf-state error" role="alert">
        <strong>Preview unavailable</strong>
        <span>{{ errorMessage }}</span>
        <button type="button" @click="loadDocument">Try again</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.pdf-preview { display: grid; grid-template: auto minmax(0, 1fr) / minmax(0, 1fr); width: 100%; height: 100%; min-height: 0; color: #3e4741; }
.pdf-preview.outline-open { grid-template-columns: 15rem minmax(0, 1fr); }
.pdf-toolbar { position: relative; z-index: 2; grid-column: 1 / -1; display: flex; align-items: center; justify-content: center; gap: 1.5rem; min-height: 2.85rem; padding: .4rem .75rem; border-bottom: 1px solid rgba(55,70,61,.12); background: rgba(250,251,250,.96); box-shadow: 0 2px 10px rgba(33,42,36,.04); }
.pdf-toolbar > div { display: flex; align-items: center; gap: .34rem; }
.pdf-toolbar span { min-width: 3.8rem; color: #747d77; font-size: .7rem; font-variant-numeric: tabular-nums; text-align: center; }
.pdf-toolbar button, .pdf-state button, .pdf-outline button { border: 0; color: #4d5a52; background: transparent; cursor: pointer; }
.pdf-toolbar button { display: grid; place-items: center; width: 1.9rem; height: 1.9rem; border-radius: .55rem; font-size: 1.1rem; }
.pdf-toolbar button:hover:not(:disabled) { color: #294d3b; background: #e8efeb; }
.pdf-toolbar button:disabled { opacity: .3; cursor: default; }
.pdf-toolbar .outline-toggle { position: absolute; left: .75rem; font-size: .9rem; }
.pdf-toolbar .scale-value { width: 3.8rem; color: #747d77; font-size: .7rem; font-variant-numeric: tabular-nums; }
.pdf-outline { min-height: 0; overflow: auto; border-right: 1px solid rgba(55,70,61,.1); background: #f6f8f7; }
.pdf-outline header { display: block; min-height: auto; padding: 1rem .9rem .75rem; border-bottom: 1px solid rgba(55,70,61,.08); background: transparent; }
.pdf-outline header strong, .pdf-outline header small { display: block; }
.pdf-outline header strong { color: #3d4941; font-size: .74rem; }
.pdf-outline header small { margin-top: .18rem; color: #8a928d; font-size: .6rem; }
.pdf-outline nav { display: grid; padding: .45rem; }
.pdf-outline nav button { width: 100%; padding: .48rem .55rem .48rem calc(.55rem + var(--outline-depth) * .72rem); border-radius: .45rem; overflow: hidden; color: #5f6963; font-size: .66rem; line-height: 1.35; text-align: left; text-overflow: ellipsis; white-space: nowrap; }
.pdf-outline nav button:hover { color: #2f513e; background: #e7eee9; }
.pdf-outline p { margin: 1rem; color: #8a928d; font-size: .65rem; line-height: 1.5; }
.pdf-pages { position: relative; min-width: 0; min-height: 0; overflow: auto; padding: 1.5rem; background: #e7eae8; }
.pdf-page-stack { display: grid; justify-items: center; gap: 1rem; width: max-content; min-width: 100%; }
.pdf-state { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; gap: .55rem; color: #737c76; font-size: .78rem; }
.pdf-state.error { flex-direction: column; padding: 2rem; }
.pdf-state.error strong { color: #3d4941; font-size: .9rem; }
.pdf-state.error button { margin-top: .4rem; padding: .5rem .8rem; border-radius: .55rem; color: #fff; background: #476957; }
.spinner { width: .9rem; height: .9rem; border: 2px solid #cbd5cf; border-top-color: #527460; border-radius: 50%; animation: spin .75s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
@media (max-width: 760px) {
  .pdf-preview.outline-open { grid-template-columns: min(45%, 13rem) minmax(0, 1fr); }
  .pdf-toolbar { justify-content: flex-end; gap: .35rem; }
  .pdf-pages { padding: .75rem; }
}
@media (prefers-reduced-motion: reduce) { .spinner { animation-duration: 1.5s; } }
</style>
