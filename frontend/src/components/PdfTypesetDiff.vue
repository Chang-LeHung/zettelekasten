<script setup lang="ts">
import { computed, markRaw, nextTick, onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'
import { GlobalWorkerOptions, getDocument, type PDFDocumentProxy } from 'pdfjs-dist'
import pdfWorkerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url'
import { assetClient, libraryClient } from '../api/client'
import type { PdfDiffSources } from '../api/types'
import { pdfDocumentOptions } from '../utils/pdfDocument'
import { changedPageNumbers, typesetChanges, type DiffRect, type PageChanges, type TextBox, type TypesetChanges } from '../utils/pdfTypesetDiff'
import { visualChanges } from '../utils/pdfVisualDiff'
import PdfPage from './PdfPage.vue'

GlobalWorkerOptions.workerSrc = pdfWorkerUrl

const props = defineProps<{ artifactId: string; nonce?: number; sessionId?: string }>()
const emit = defineEmits<{ restored: [] }>()

/** changes: the current page with edits marked; before / after: one version. */
type View = 'changes' | 'before' | 'after'
type Phase = 'loading' | 'ready' | 'no-base' | 'no-target' | 'error'

const phase = ref<Phase>('loading')
const errorMessage = ref('')
const sources = ref<PdfDiffSources | null>(null)
const baseDoc = shallowRef<PDFDocumentProxy | null>(null)
const targetDoc = shallowRef<PDFDocumentProxy | null>(null)
const changes = ref<TypesetChanges | null>(null)
const visual = ref<Record<number, DiffRect[]>>({})
const visualBusy = ref(false)
const figuresCapped = ref(false)
const pageSize = ref({ width: 612, height: 792 })
const view = ref<View>('changes')
const scale = ref(1)
const changedOnly = ref(false)
const current = ref(0)
const root = ref<HTMLElement | null>(null)
const stage = ref<HTMLElement | null>(null)
const confirmRestore = ref(false)
const restoring = ref(false)
const restoreError = ref('')
let loadVersion = 0
let firstLoad = true
let controller: AbortController | null = null
let resizeObserver: ResizeObserver | null = null
const MIN_SCALE = 0.4
const MAX_SCALE = 2.2
/** Pages compared pixel by pixel; later pages still get the text diff. */
const MAX_VISUAL_PAGES = 80
const VISUAL_SCALE = 0.75

const activeDoc = computed(() => view.value === 'before' ? baseDoc.value : targetDoc.value)
const pageCount = computed(() => activeDoc.value?.numPages ?? 0)
const visualPages = computed(() => Object.keys(visual.value).map(Number))
const textPages = computed(() => view.value === 'before'
  ? (changes.value?.base.map((item) => item.page) ?? [])
  : (changes.value ? changedPageNumbers(changes.value, targetDoc.value?.numPages ?? 0) : []))
/** Pages worth visiting: any with changed words, or with a changed figure. */
const navPages = computed(() => [...new Set([...textPages.value, ...visualPages.value])].sort((p, q) => p - q))
const pages = computed(() => {
  const all = Array.from({ length: pageCount.value }, (_, index) => index + 1)
  if (!changedOnly.value) return all
  const keep = new Set(navPages.value)
  return all.filter((page) => keep.has(page))
})
const figureCount = computed(() => Object.values(visual.value).reduce((sum, list) => sum + list.length, 0))
const identical = computed(() => !!changes.value && !changes.value.addedWords && !changes.value.removedWords
  && figureCount.value === 0 && !visualBusy.value && baseDoc.value?.numPages === targetDoc.value?.numPages)
const savedAt = computed(() => {
  const value = sources.value?.base_saved_at
  return value ? new Date(value).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : ''
})
const removedPages = computed(() => changes.value?.base ?? [])

function entry(list: PageChanges[] | undefined, page: number): PageChanges | undefined {
  return list?.find((item) => item.page === page)
}

function rectStyle(rect: DiffRect): Record<string, string> {
  const pad = 1.5 * scale.value
  return {
    left: `${rect.x * scale.value - pad}px`,
    top: `${rect.y * scale.value - pad}px`,
    width: `${rect.width * scale.value + pad * 2}px`,
    height: `${rect.height * scale.value + pad * 2}px`,
  }
}

/** The marks drawn on one page of the current view. After is shown clean. */
function marks(page: number): Array<{ rect: DiffRect; kind: 'add' | 'del' | 'vis' }> {
  if (view.value === 'after') return []
  const text = view.value === 'before'
    ? (entry(changes.value?.base, page)?.rects ?? []).map((rect) => ({ rect, kind: 'del' as const }))
    : (entry(changes.value?.target, page)?.rects ?? []).map((rect) => ({ rect, kind: 'add' as const }))
  return [...text, ...(visual.value[page] ?? []).map((rect) => ({ rect, kind: 'vis' as const }))]
}

async function textBoxes(doc: PDFDocumentProxy): Promise<TextBox[][]> {
  const result: TextBox[][] = []
  for (let number = 1; number <= doc.numPages; number += 1) {
    const page = await doc.getPage(number)
    const viewport = page.getViewport({ scale: 1 })
    const content = await page.getTextContent()
    const boxes: TextBox[] = []
    for (const item of content.items) {
      if (!('str' in item) || !item.str.trim()) continue
      const [x, y] = viewport.convertToViewportPoint(item.transform[4], item.transform[5])
      boxes.push({ str: item.str, x, y: y - item.height, width: item.width, height: item.height })
    }
    result.push(boxes)
  }
  return result
}

async function pixels(doc: PDFDocumentProxy, number: number): Promise<{ data: Uint8ClampedArray; width: number; height: number } | null> {
  const page = await doc.getPage(number)
  const viewport = page.getViewport({ scale: VISUAL_SCALE })
  const canvas = document.createElement('canvas')
  canvas.width = Math.ceil(viewport.width)
  canvas.height = Math.ceil(viewport.height)
  const context = canvas.getContext('2d', { willReadFrequently: true })
  if (!context) return null
  await page.render({ canvas, viewport }).promise
  const image = context.getImageData(0, 0, canvas.width, canvas.height)
  return { data: image.data, width: image.width, height: image.height }
}

/** Compare rendered pages for figure-level changes, one page at a time so the view stays usable. */
async function findVisualChanges(version: number, base: PDFDocumentProxy, target: PDFDocumentProxy, basePages: TextBox[][], targetPages: TextBox[][]): Promise<void> {
  visualBusy.value = true
  try {
    const last = Math.min(base.numPages, target.numPages, MAX_VISUAL_PAGES)
    for (let number = 1; number <= last; number += 1) {
      if (version !== loadVersion) return
      try {
        const [before, after] = await Promise.all([pixels(base, number), pixels(target, number)])
        if (version !== loadVersion) return
        if (!before || !after) continue
        const rects = visualChanges(before, after, VISUAL_SCALE, [...(basePages[number - 1] ?? []), ...(targetPages[number - 1] ?? [])])
        if (rects.length) visual.value = { ...visual.value, [number]: rects }
      } catch {
        // One page that cannot be rendered only loses its own figure marks.
      }
      await new Promise((resolve) => setTimeout(resolve, 0))
    }
    if (Math.min(base.numPages, target.numPages) > MAX_VISUAL_PAGES) figuresCapped.value = true
  } finally {
    if (version === loadVersion) visualBusy.value = false
  }
}

async function open(url: string, signal: AbortSignal): Promise<PDFDocumentProxy> {
  const bytes = await assetClient.getUrlContent(url, signal)
  return markRaw(await getDocument(pdfDocumentOptions(bytes)).promise)
}

async function dispose(): Promise<void> {
  const documents = [baseDoc.value, targetDoc.value]
  baseDoc.value = null
  targetDoc.value = null
  await Promise.all(documents.map((doc) => doc?.destroy()))
}

async function load(): Promise<void> {
  const version = ++loadVersion
  controller?.abort()
  controller = new AbortController()
  const signal = controller.signal
  phase.value = 'loading'
  errorMessage.value = ''
  changes.value = null
  visual.value = {}
  visualBusy.value = false
  figuresCapped.value = false
  confirmRestore.value = false
  try {
    await dispose()
    const found = await libraryClient.getPdfDiff(props.artifactId, signal)
    if (version !== loadVersion) return
    sources.value = found
    if (!found.target_url) { phase.value = 'no-target'; return }
    if (!found.base_url) { phase.value = 'no-base'; return }
    const [base, target] = await Promise.all([open(found.base_url, signal), open(found.target_url, signal)])
    if (version !== loadVersion) { await Promise.all([base.destroy(), target.destroy()]); return }
    baseDoc.value = base
    targetDoc.value = target
    const viewport = (await target.getPage(1)).getViewport({ scale: 1 })
    pageSize.value = { width: viewport.width, height: viewport.height }
    const [basePages, targetPages] = await Promise.all([textBoxes(base), textBoxes(target)])
    if (version !== loadVersion) return
    changes.value = typesetChanges(basePages, targetPages)
    phase.value = 'ready'
    current.value = 0
    await nextTick()
    fit()
    if (firstLoad) root.value?.focus({ preventScroll: true })
    firstLoad = false
    void findVisualChanges(version, base, target, basePages, targetPages)
  } catch (error) {
    if (version !== loadVersion || (error instanceof DOMException && error.name === 'AbortError')) return
    errorMessage.value = error instanceof Error ? error.message : String(error)
    phase.value = 'error'
  }
}

function fit(): void {
  const width = stage.value?.clientWidth ?? 0
  if (!width) return
  scale.value = Math.max(MIN_SCALE, Math.min(MAX_SCALE, (width - 64) / pageSize.value.width))
}

function zoom(delta: number): void {
  scale.value = Math.max(MIN_SCALE, Math.min(MAX_SCALE, Math.round((scale.value + delta) * 100) / 100))
}

function goTo(index: number): void {
  const list = navPages.value
  if (!list.length) return
  const wrapped = (index + list.length) % list.length
  current.value = wrapped
  stage.value?.querySelector<HTMLElement>(`[data-row="${list[wrapped]}"]`)?.scrollIntoView({ block: 'start', behavior: 'smooth' })
}

function onKey(event: KeyboardEvent): void {
  if (event.target instanceof HTMLElement && /input|textarea|select/i.test(event.target.tagName)) return
  if (event.key === 'j') goTo(current.value + 1)
  else if (event.key === 'k') goTo(current.value - 1)
  else return
  event.preventDefault()
}

async function restore(): Promise<void> {
  if (restoring.value) return
  if (!props.sessionId) { restoreError.value = 'Restore is only available inside the conversation that owns this paper'; return }
  restoring.value = true
  restoreError.value = ''
  try {
    await libraryClient.restorePdfProject(props.sessionId, props.artifactId)
    confirmRestore.value = false
    await load()
    emit('restored')
  } catch (error) {
    restoreError.value = error instanceof Error ? error.message : String(error)
  } finally {
    restoring.value = false
  }
}

const total = computed(() => navPages.value.length)
const VIEWS: Array<{ id: View; label: string }> = [
  { id: 'changes', label: 'Changes' },
  { id: 'before', label: 'Before' },
  { id: 'after', label: 'After' },
]

watch(() => [props.artifactId, props.nonce], () => void load())
watch(view, () => { current.value = 0 })
onMounted(() => {
  void load()
  if (stage.value) {
    resizeObserver = new ResizeObserver(() => { if (phase.value === 'ready') fit() })
    resizeObserver.observe(stage.value)
  }
})
onBeforeUnmount(() => {
  loadVersion += 1
  controller?.abort()
  resizeObserver?.disconnect()
  void dispose()
})
</script>

<template>
  <section ref="root" class="tsd" tabindex="-1" :aria-label="$t('Typeset changes')" @keydown="onKey">
    <header class="tsd-bar">
      <div class="tsd-summary">
        <template v-if="phase === 'ready' && changes">
          <span v-if="identical" class="tsd-chip same">{{ $t('No visible changes') }}</span>
          <template v-else>
            <span class="tsd-chip add">+{{ changes.addedWords }}</span>
            <span class="tsd-chip del">−{{ changes.removedWords }}</span>
            <span v-if="figureCount" class="tsd-chip vis" :title="$t('Figures or graphics changed')">▣ {{ figureCount }}</span>
            <span v-else-if="visualBusy" class="tsd-chip busy">{{ $t('Checking figures…') }}</span>
            <span v-if="figuresCapped" class="tsd-chip busy" :title="$t('Figures were checked on the first pages only')">{{ $t('Figures: first {count} pages', { count: MAX_VISUAL_PAGES }) }}</span>
          </template>
          <small v-if="savedAt" class="tsd-when">{{ $t('vs. saved') }} {{ savedAt }}</small>
        </template>
      </div>
      <div class="tsd-tools">
        <div class="tsd-seg" role="group" :aria-label="$t('Comparison mode')">
          <button v-for="item in VIEWS" :key="item.id" type="button" :class="{ on: view === item.id }" :aria-pressed="view === item.id" @click="view = item.id">{{ $t(item.label) }}</button>
        </div>
        <label class="tsd-toggle"><input v-model="changedOnly" type="checkbox" /><span>{{ $t('Changed pages only') }}</span></label>
        <div class="tsd-nav" role="group" :aria-label="$t('Changes')">
          <button type="button" :disabled="!total" :title="$t('Previous change (k)')" :aria-label="$t('Previous change (k)')" @click="goTo(current - 1)">‹</button>
          <em>{{ total ? `${current + 1} / ${total}` : '–' }}</em>
          <button type="button" :disabled="!total" :title="$t('Next change (j)')" :aria-label="$t('Next change (j)')" @click="goTo(current + 1)">›</button>
        </div>
        <div class="tsd-zoom" role="group" :aria-label="$t('Zoom')">
          <button type="button" :aria-label="$t('Zoom out')" @click="zoom(-0.1)">−</button>
          <button type="button" class="pct" :title="$t('Fit to width')" @click="fit">{{ Math.round(scale * 100) }}%</button>
          <button type="button" :aria-label="$t('Zoom in')" @click="zoom(0.1)">+</button>
        </div>
      </div>
    </header>

    <p v-if="sources?.stale && phase === 'ready'" class="tsd-note warn" role="status">{{ $t('Sources changed after the PDF was compiled, so this PDF may not show the latest edit. Ask the assistant to recompile, then refresh.') }}</p>
    <p v-if="changes?.coarse && phase === 'ready'" class="tsd-note" role="status">{{ $t('This is a large rewrite; highlights are approximate.') }}</p>

    <div v-if="phase === 'ready' && sources?.can_restore && sessionId" class="tsd-restore">
      <template v-if="!confirmRestore">
        <span>{{ $t('{count} commits since you saved', { count: sources.commits_since ?? 0 }) }}</span>
        <button type="button" @click="confirmRestore = true">{{ $t('Restore saved version') }}</button>
      </template>
      <template v-else>
        <span>{{ $t('Undo everything since the saved version? History is kept: a revert commit is added.') }}</span>
        <button type="button" class="danger" :disabled="restoring" @click="restore">{{ restoring ? $t('Restoring…') : $t('Restore') }}</button>
        <button type="button" class="quiet" :disabled="restoring" @click="confirmRestore = false">{{ $t('Cancel') }}</button>
      </template>
      <p v-if="restoreError" class="tsd-restore-error" role="alert">{{ restoreError }}</p>
    </div>

    <details v-if="phase === 'ready' && view === 'changes' && removedPages.length" class="tsd-removed-list">
      <summary>{{ $t('Removed text') }} · {{ changes?.removedWords }}</summary>
      <p v-for="item in removedPages" :key="item.page"><b>{{ $t('Saved page {page}', { page: item.page }) }}</b> {{ item.text }}</p>
    </details>

    <div ref="stage" class="tsd-stage" :class="{ ready: phase === 'ready' }">
      <div v-if="phase === 'loading'" class="tsd-state"><i class="tsd-spin" /><strong>{{ $t('Comparing typeset pages…') }}</strong></div>
      <div v-else-if="phase === 'no-target'" class="tsd-state"><strong>{{ $t('PDF has not been generated yet') }}</strong><span>{{ $t('Compile the LaTeX project, then refresh.') }}</span><button type="button" @click="load">{{ $t('Refresh') }}</button></div>
      <div v-else-if="phase === 'no-base'" class="tsd-state"><strong>{{ $t('No saved version to compare with') }}</strong><span>{{ $t('Save this artifact once. Later edits will show here as typeset before-and-after.') }}</span></div>
      <div v-else-if="phase === 'error'" class="tsd-state err" role="alert"><strong>{{ $t('Comparison unavailable') }}</strong><span>{{ errorMessage }}</span><button type="button" @click="load">{{ $t('Retry') }}</button></div>

      <div v-else class="tsd-scroll">
        <div v-for="page in pages" :key="`${view}-${page}`" class="tsd-row" :data-row="page">
          <PdfPage v-if="activeDoc" :document="activeDoc" :page-number="page" :scale="scale" :base-width="pageSize.width" :base-height="pageSize.height">
            <i v-for="(mark, index) in marks(page)" :key="index" class="hl" :class="mark.kind" :style="rectStyle(mark.rect)" />
          </PdfPage>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.tsd { display: flex; flex-direction: column; width: 100%; height: 100%; min-height: 0; color: #2f3833; background: #f4f6f4; outline: none; }
.tsd-bar { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: .5rem .8rem; padding: .5rem .8rem; border-bottom: 1px solid #e4e9e5; background: rgba(255,255,255,.86); backdrop-filter: saturate(1.4) blur(12px); }
.tsd-summary, .tsd-tools { display: flex; flex-wrap: wrap; align-items: center; gap: .45rem; min-width: 0; }
.tsd-chip { display: inline-flex; align-items: center; height: 1.5rem; padding: 0 .6rem; border-radius: 999px; font-size: .7rem; font-weight: 650; font-variant-numeric: tabular-nums; }
.tsd-chip.add { color: #1c6a41; background: #e1f4e8; }
.tsd-chip.del { color: #a23232; background: #fbe6e4; }
.tsd-chip.vis { color: #7a5413; background: #fbefd2; }
.tsd-chip.busy { color: #6d7570; background: #eaefeb; font-weight: 500; }
.tsd-chip.same { color: #3d6650; background: #e6f1ea; }
.tsd-when { color: #8a938d; font-size: .66rem; }
.tsd-seg { display: inline-flex; padding: .15rem; border-radius: .7rem; background: #e9eeea; }
.tsd-seg button { border: 0; padding: .28rem .75rem; border-radius: .55rem; color: #5b675f; background: transparent; font-size: .7rem; font-weight: 600; cursor: pointer; transition: background .16s, color .16s, box-shadow .16s; }
.tsd-seg button.on { color: #20382b; background: #fff; box-shadow: 0 1px 3px rgba(26,40,31,.14); }
.tsd-toggle { display: inline-flex; align-items: center; gap: .35rem; color: #5b675f; font-size: .7rem; cursor: pointer; }
.tsd-toggle input { accent-color: #3f7a58; }
.tsd-nav, .tsd-zoom { display: inline-flex; align-items: center; gap: .1rem; padding: .15rem; border-radius: .7rem; background: #e9eeea; }
.tsd-nav em { min-width: 2.8rem; color: #5b675f; font-size: .68rem; font-style: normal; text-align: center; font-variant-numeric: tabular-nums; }
.tsd-nav button, .tsd-zoom button { display: grid; place-items: center; min-width: 1.6rem; height: 1.6rem; border: 0; border-radius: .5rem; color: #43524a; background: transparent; font-size: 1rem; cursor: pointer; }
.tsd-zoom .pct { padding: 0 .35rem; font-size: .68rem; font-variant-numeric: tabular-nums; }
.tsd-nav button:hover:not(:disabled), .tsd-zoom button:hover { background: #fff; }
.tsd-nav button:disabled { opacity: .35; cursor: default; }
.tsd-note { margin: 0; padding: .4rem .9rem; color: #66706a; background: #f0f3f1; font-size: .72rem; border-bottom: 1px solid #e4e9e5; }
.tsd-note.warn { color: #7a5b17; background: #fbf3dc; border-color: #efe2b8; }
.tsd-restore { display: flex; flex-wrap: wrap; align-items: center; gap: .5rem .7rem; padding: .45rem .9rem; color: #5b675f; background: #fff; border-bottom: 1px solid #e4e9e5; font-size: .72rem; }
.tsd-restore button { padding: .28rem .75rem; border: 1px solid #cfe0d5; border-radius: .6rem; color: #2f5a41; background: #f1f8f4; font-size: .7rem; font-weight: 640; cursor: pointer; }
.tsd-restore button.danger { color: #fff; border-color: #a23232; background: #b6403d; }
.tsd-restore button.quiet { color: #5b675f; border-color: transparent; background: transparent; }
.tsd-restore button:disabled { opacity: .55; cursor: default; }
.tsd-restore-error { flex-basis: 100%; margin: 0; color: #a23232; }
.tsd-removed-list { padding: .35rem .9rem; border-bottom: 1px solid #e4e9e5; background: #fdf5f4; color: #8c2f2f; font-size: .7rem; }
.tsd-removed-list summary { cursor: pointer; font-weight: 640; }
.tsd-removed-list p { margin: .3rem 0 0; line-height: 1.5; }
.tsd-removed-list b { margin-right: .35rem; font-size: .64rem; }
.tsd-stage { position: relative; display: flex; flex: 1 1 auto; flex-direction: column; min-height: 0; overflow: hidden; }
.tsd-stage:not(.ready) { align-items: center; justify-content: center; }
.tsd-state { display: grid; justify-items: center; gap: .5rem; max-width: 26rem; padding: 2rem; text-align: center; color: #66706a; font-size: .8rem; }
.tsd-state strong { color: #2f3833; font-size: .95rem; }
.tsd-state button { margin-top: .3rem; padding: .45rem .95rem; border: 0; border-radius: .65rem; color: #fff; background: #3f7a58; font-weight: 600; cursor: pointer; }
.tsd-state.err strong { color: #9a3b3b; }
.tsd-spin { width: 1.4rem; height: 1.4rem; border: 2px solid #d6dfd9; border-top-color: #3f7a58; border-radius: 50%; animation: tsd-rot .8s linear infinite; }
@keyframes tsd-rot { to { transform: rotate(360deg); } }
.tsd-scroll { display: flex; flex: 1 1 auto; flex-direction: column; align-items: center; gap: 1.3rem; min-height: 0; padding: 1.1rem 1rem 2.5rem; overflow: auto; scrollbar-gutter: stable; }
.tsd-row { flex: none; scroll-margin-top: .75rem; }
.hl { position: absolute; z-index: 2; border-radius: .25rem; pointer-events: none; mix-blend-mode: multiply; animation: tsd-in .32s ease-out both; }
.hl.add { background: rgba(52, 181, 106, .26); }
.hl.del { background: rgba(232, 84, 76, .24); }
.hl.vis { background: rgba(242, 171, 40, .26); }
@keyframes tsd-in { from { opacity: 0; transform: scaleY(.6); } }
@media (prefers-reduced-motion: reduce) { .hl { animation: none; } .tsd-spin { animation-duration: 2s; } }
</style>
