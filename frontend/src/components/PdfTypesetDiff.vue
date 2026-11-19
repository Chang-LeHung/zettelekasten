<script setup lang="ts">
import { computed, markRaw, nextTick, onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'
import { GlobalWorkerOptions, getDocument, type PDFDocumentProxy } from 'pdfjs-dist'
import pdfWorkerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url'
import { assetClient, libraryClient } from '../api/client'
import type { PdfDiffSources } from '../api/types'
import { pdfDocumentOptions } from '../utils/pdfDocument'
import { changedPageNumbers, typesetChanges, type PageChanges, type TextBox, type TypesetChanges } from '../utils/pdfTypesetDiff'
import PdfPage from './PdfPage.vue'

GlobalWorkerOptions.workerSrc = pdfWorkerUrl

const props = defineProps<{ artifactId: string; nonce?: number }>()
const emit = defineEmits<{ close: [] }>()

type Mode = 'split' | 'swipe'
type Phase = 'loading' | 'ready' | 'no-base' | 'no-target' | 'error'

const phase = ref<Phase>('loading')
const errorMessage = ref('')
const sources = ref<PdfDiffSources | null>(null)
const baseDoc = shallowRef<PDFDocumentProxy | null>(null)
const targetDoc = shallowRef<PDFDocumentProxy | null>(null)
const changes = ref<TypesetChanges | null>(null)
const pageSize = ref({ width: 612, height: 792 })
const mode = ref<Mode>('split')
const swipe = ref(50)
const scale = ref(1)
const fitted = ref(false)
const changedOnly = ref(false)
const current = ref(0)
const stage = ref<HTMLElement | null>(null)
const leftScroll = ref<HTMLElement | null>(null)
const rightScroll = ref<HTMLElement | null>(null)
let loadVersion = 0
let syncing = false
let resizeObserver: ResizeObserver | null = null
const MIN_SCALE = 0.4
const MAX_SCALE = 2.2

const baseCount = computed(() => baseDoc.value?.numPages ?? 0)
const targetCount = computed(() => targetDoc.value?.numPages ?? 0)
const rowCount = computed(() => Math.max(baseCount.value, targetCount.value))
const changedPages = computed(() => changes.value ? changedPageNumbers(changes.value, targetCount.value) : [])
const rows = computed(() => {
  const all = Array.from({ length: rowCount.value }, (_, index) => index + 1)
  if (!changedOnly.value) return all
  const keep = new Set(changedPages.value)
  for (const entry of changes.value?.base ?? []) keep.add(entry.page)
  return all.filter((page) => keep.has(page))
})
const identical = computed(() => !!changes.value && !changes.value.addedWords && !changes.value.removedWords && baseCount.value === targetCount.value)
const savedAt = computed(() => {
  const value = sources.value?.base_saved_at
  if (!value) return ''
  return new Date(value).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
})

function byPage(entries: PageChanges[] | undefined, page: number): PageChanges | undefined {
  return entries?.find((entry) => entry.page === page)
}

function rectStyle(rect: { x: number; y: number; width: number; height: number }): Record<string, string> {
  const pad = 1.5 * scale.value
  return {
    left: `${rect.x * scale.value - pad}px`,
    top: `${rect.y * scale.value - pad}px`,
    width: `${rect.width * scale.value + pad * 2}px`,
    height: `${rect.height * scale.value + pad * 2}px`,
  }
}

async function textBoxes(doc: PDFDocumentProxy): Promise<TextBox[][]> {
  const pages: TextBox[][] = []
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
    pages.push(boxes)
  }
  return pages
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

let controller: AbortController | null = null

async function load(): Promise<void> {
  const version = ++loadVersion
  controller?.abort()
  controller = new AbortController()
  const signal = controller.signal
  phase.value = 'loading'
  errorMessage.value = ''
  changes.value = null
  fitted.value = false
  try {
    await dispose()
    const found = await libraryClient.getPdfDiff(props.artifactId)
    if (version !== loadVersion) return
    sources.value = found
    if (!found.target_url) {
      phase.value = 'no-target'
      return
    }
    if (!found.base_url) {
      phase.value = 'no-base'
      return
    }
    const [base, target] = await Promise.all([open(found.base_url, signal), open(found.target_url, signal)])
    if (version !== loadVersion) {
      await Promise.all([base.destroy(), target.destroy()])
      return
    }
    baseDoc.value = base
    targetDoc.value = target
    const first = await target.getPage(1)
    const viewport = first.getViewport({ scale: 1 })
    pageSize.value = { width: viewport.width, height: viewport.height }
    const [basePages, targetPages] = await Promise.all([textBoxes(base), textBoxes(target)])
    if (version !== loadVersion) return
    changes.value = typesetChanges(basePages, targetPages)
    phase.value = 'ready'
    current.value = 0
    await nextTick()
    fit()
  } catch (error) {
    if (version !== loadVersion || (error instanceof DOMException && error.name === 'AbortError')) return
    errorMessage.value = error instanceof Error ? error.message : String(error)
    phase.value = 'error'
  }
}

function fit(): void {
  const width = stage.value?.clientWidth ?? 0
  if (!width) return
  const columns = mode.value === 'split' ? 2 : 1
  const available = width / columns - (mode.value === 'split' ? 56 : 80)
  scale.value = Math.max(MIN_SCALE, Math.min(MAX_SCALE, available / pageSize.value.width))
  fitted.value = true
}

function zoom(delta: number): void {
  scale.value = Math.max(MIN_SCALE, Math.min(MAX_SCALE, Math.round((scale.value + delta) * 100) / 100))
}

function pageElement(root: HTMLElement | null, page: number): HTMLElement | null {
  return root?.querySelector<HTMLElement>(`[data-row="${page}"]`) ?? null
}

function goTo(index: number): void {
  if (!changedPages.value.length) return
  const wrapped = (index + changedPages.value.length) % changedPages.value.length
  current.value = wrapped
  const page = changedPages.value[wrapped]
  if (changedOnly.value && !rows.value.includes(page)) return
  const root = mode.value === 'split' ? leftScroll.value : stage.value
  pageElement(root, page)?.scrollIntoView({ block: 'start', behavior: 'smooth' })
}

function mirror(from: HTMLElement | null, to: HTMLElement | null): void {
  if (!from || !to || syncing) return
  syncing = true
  to.scrollTop = from.scrollTop
  requestAnimationFrame(() => { syncing = false })
}

function onKey(event: KeyboardEvent): void {
  if (event.target instanceof HTMLElement && /input|textarea|select/i.test(event.target.tagName)) return
  if (event.key === 'j' || event.key === 'ArrowDown' && event.altKey) goTo(current.value + 1)
  else if (event.key === 'k' || event.key === 'ArrowUp' && event.altKey) goTo(current.value - 1)
  else if (event.key === 'Escape') emit('close')
  else return
  event.preventDefault()
}

function rowLabel(page: number): string {
  const added = byPage(changes.value?.target, page)?.words ?? 0
  const removed = byPage(changes.value?.base, page)?.words ?? 0
  if (!added && !removed) return ''
  return [added ? `+${added}` : '', removed ? `−${removed}` : ''].filter(Boolean).join(' ')
}

watch(() => [props.artifactId, props.nonce], () => void load())
watch(mode, async () => { await nextTick(); fit() })
onMounted(() => {
  void load()
  if (stage.value) {
    resizeObserver = new ResizeObserver(() => { if (!fitted.value && phase.value === 'ready') fit() })
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
  <section class="tsd" tabindex="-1" aria-label="Typeset changes" @keydown="onKey">
    <header class="tsd-bar">
      <div class="tsd-summary">
        <template v-if="phase === 'ready' && changes">
          <span v-if="identical" class="tsd-chip same">No visible changes</span>
          <template v-else>
            <span class="tsd-chip add">+{{ changes.addedWords }} words</span>
            <span class="tsd-chip del">−{{ changes.removedWords }} words</span>
            <span class="tsd-chip pages">{{ changedPages.length }} {{ changedPages.length === 1 ? 'page' : 'pages' }} changed</span>
          </template>
          <small v-if="savedAt" class="tsd-when">vs. saved {{ savedAt }}</small>
        </template>
        <span v-else class="tsd-chip pages">{{ $t('Compare with saved version') }}</span>
      </div>
      <div class="tsd-tools">
        <div class="tsd-seg" role="group" :aria-label="$t('Comparison mode')">
          <button type="button" :class="{ on: mode === 'split' }" @click="mode = 'split'">{{ $t('Side by side') }}</button>
          <button type="button" :class="{ on: mode === 'swipe' }" @click="mode = 'swipe'">{{ $t('Swipe') }}</button>
        </div>
        <label class="tsd-toggle"><input v-model="changedOnly" type="checkbox" /><span>{{ $t('Changed pages only') }}</span></label>
        <div class="tsd-nav" role="group" aria-label="Changes">
          <button type="button" :disabled="!changedPages.length" :title="$t('Previous change (k)')" @click="goTo(current - 1)">‹</button>
          <em>{{ changedPages.length ? `${current + 1} / ${changedPages.length}` : '–' }}</em>
          <button type="button" :disabled="!changedPages.length" :title="$t('Next change (j)')" @click="goTo(current + 1)">›</button>
        </div>
        <div class="tsd-zoom" role="group" aria-label="Zoom">
          <button type="button" :aria-label="$t('Zoom out')" @click="zoom(-0.1)">−</button>
          <button type="button" class="pct" :title="$t('Fit to width')" @click="fit">{{ Math.round(scale * 100) }}%</button>
          <button type="button" :aria-label="$t('Zoom in')" @click="zoom(0.1)">+</button>
        </div>
      </div>
    </header>

    <p v-if="sources?.stale && phase === 'ready'" class="tsd-note warn" role="status">
      {{ $t('Sources changed after the PDF was compiled, so this PDF may not show the latest edit. Ask the assistant to recompile, then refresh.') }}
    </p>
    <p v-if="changes?.coarse && phase === 'ready'" class="tsd-note" role="status">
      {{ $t('This is a large rewrite; highlights are approximate.') }}
    </p>

    <div ref="stage" class="tsd-stage" :class="[`mode-${mode}`, { ready: phase === 'ready' }]">
      <div v-if="phase === 'loading'" class="tsd-state"><i class="tsd-spin" /><strong>{{ $t('Comparing typeset pages…') }}</strong></div>
      <div v-else-if="phase === 'no-target'" class="tsd-state"><strong>{{ $t('PDF has not been generated yet') }}</strong><span>{{ $t('Compile the LaTeX project, then refresh.') }}</span><button type="button" @click="load">{{ $t('Refresh') }}</button></div>
      <div v-else-if="phase === 'no-base'" class="tsd-state">
        <strong>{{ $t('No saved version to compare with') }}</strong>
        <span>{{ $t('Save this artifact once. Later edits will show here as typeset before-and-after.') }}</span>
      </div>
      <div v-else-if="phase === 'error'" class="tsd-state err" role="alert"><strong>{{ $t('Comparison unavailable') }}</strong><span>{{ errorMessage }}</span><button type="button" @click="load">{{ $t('Retry') }}</button></div>

      <template v-else>
        <template v-if="mode === 'split'">
          <div class="tsd-col-label"><b>{{ $t('Saved') }}</b><b>{{ $t('Current') }}</b></div>
          <div class="tsd-split">
            <div ref="leftScroll" class="tsd-scroll" @scroll="mirror(leftScroll, rightScroll)">
              <div v-for="page in rows" :key="`b-${page}`" class="tsd-row" :data-row="page">
                <span v-if="rowLabel(page)" class="tsd-tag del">{{ page }} · {{ byPage(changes?.base, page)?.words ? `−${byPage(changes?.base, page)?.words}` : '' }}</span>
                <PdfPage v-if="baseDoc && page <= baseCount" :document="baseDoc" :page-number="page" :scale="scale" :base-width="pageSize.width" :base-height="pageSize.height">
                  <i v-for="(rect, index) in byPage(changes?.base, page)?.rects" :key="index" class="hl del" :style="rectStyle(rect)" />
                </PdfPage>
                <div v-else class="tsd-gap" :style="{ width: `${pageSize.width * scale}px`, height: `${pageSize.height * scale}px` }">{{ $t('No page') }}</div>
              </div>
            </div>
            <div ref="rightScroll" class="tsd-scroll" @scroll="mirror(rightScroll, leftScroll)">
              <div v-for="page in rows" :key="`t-${page}`" class="tsd-row" :data-row="page">
                <span v-if="rowLabel(page)" class="tsd-tag add">{{ page }} · {{ byPage(changes?.target, page)?.words ? `+${byPage(changes?.target, page)?.words}` : '' }}</span>
                <PdfPage v-if="targetDoc && page <= targetCount" :document="targetDoc" :page-number="page" :scale="scale" :base-width="pageSize.width" :base-height="pageSize.height">
                  <i v-for="(rect, index) in byPage(changes?.target, page)?.rects" :key="index" class="hl add" :style="rectStyle(rect)" />
                </PdfPage>
                <div v-else class="tsd-gap" :style="{ width: `${pageSize.width * scale}px`, height: `${pageSize.height * scale}px` }">{{ $t('No page') }}</div>
              </div>
            </div>
          </div>
        </template>

        <div v-else class="tsd-scroll swipe">
          <div v-for="page in rows" :key="`s-${page}`" class="tsd-row" :data-row="page">
            <span v-if="rowLabel(page)" class="tsd-tag mix">{{ page }} · {{ rowLabel(page) }}</span>
            <div class="tsd-swipe" :style="{ width: `${pageSize.width * scale}px`, height: `${pageSize.height * scale}px`, '--cut': `${swipe}%` }">
              <PdfPage v-if="targetDoc && page <= targetCount" :document="targetDoc" :page-number="page" :scale="scale" :base-width="pageSize.width" :base-height="pageSize.height">
                <i v-for="(rect, index) in byPage(changes?.target, page)?.rects" :key="index" class="hl add" :style="rectStyle(rect)" />
              </PdfPage>
              <div v-if="baseDoc && page <= baseCount" class="tsd-over">
                <PdfPage :document="baseDoc" :page-number="page" :scale="scale" :base-width="pageSize.width" :base-height="pageSize.height">
                  <i v-for="(rect, index) in byPage(changes?.base, page)?.rects" :key="index" class="hl del" :style="rectStyle(rect)" />
                </PdfPage>
              </div>
              <span class="tsd-handle" aria-hidden="true"><b>‹ ›</b></span>
              <span class="tsd-end l">{{ $t('Saved') }}</span><span class="tsd-end r">{{ $t('Current') }}</span>
            </div>
          </div>
        </div>
        <label v-if="mode === 'swipe'" class="tsd-slider"><span>{{ $t('Saved') }}</span><input v-model.number="swipe" type="range" min="0" max="100" :aria-label="$t('Swipe position')" /><span>{{ $t('Current') }}</span></label>
      </template>
    </div>
  </section>
</template>

<style scoped>
.tsd { display: grid; grid-template-rows: auto auto auto minmax(0, 1fr); width: 100%; height: 100%; min-height: 0; color: #2f3833; background: #f4f6f4; outline: none; }
.tsd-bar { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: .6rem .9rem; padding: .55rem .85rem; border-bottom: 1px solid #e4e9e5; background: rgba(255,255,255,.86); backdrop-filter: saturate(1.4) blur(12px); }
.tsd-summary, .tsd-tools { display: flex; flex-wrap: wrap; align-items: center; gap: .5rem; min-width: 0; }
.tsd-chip { display: inline-flex; align-items: center; height: 1.55rem; padding: 0 .6rem; border-radius: 999px; font-size: .7rem; font-weight: 650; font-variant-numeric: tabular-nums; letter-spacing: .005em; }
.tsd-chip.add { color: #1c6a41; background: #e1f4e8; }
.tsd-chip.del { color: #a23232; background: #fbe6e4; }
.tsd-chip.pages { color: #4c5a52; background: #eaefeb; }
.tsd-chip.same { color: #3d6650; background: #e6f1ea; }
.tsd-when { color: #8a938d; font-size: .66rem; }
.tsd-seg { display: inline-flex; padding: .15rem; border-radius: .7rem; background: #e9eeea; }
.tsd-seg button { border: 0; padding: .28rem .7rem; border-radius: .55rem; color: #5b675f; background: transparent; font-size: .7rem; font-weight: 600; cursor: pointer; transition: background .16s, color .16s, box-shadow .16s; }
.tsd-seg button.on { color: #20382b; background: #fff; box-shadow: 0 1px 3px rgba(26,40,31,.14); }
.tsd-toggle { display: inline-flex; align-items: center; gap: .35rem; color: #5b675f; font-size: .7rem; cursor: pointer; }
.tsd-toggle input { accent-color: #3f7a58; }
.tsd-nav, .tsd-zoom { display: inline-flex; align-items: center; gap: .15rem; padding: .15rem; border-radius: .7rem; background: #e9eeea; }
.tsd-nav em { min-width: 3rem; color: #5b675f; font-size: .68rem; font-style: normal; text-align: center; font-variant-numeric: tabular-nums; }
.tsd-nav button, .tsd-zoom button { display: grid; place-items: center; min-width: 1.6rem; height: 1.6rem; border: 0; border-radius: .5rem; color: #43524a; background: transparent; font-size: 1rem; cursor: pointer; }
.tsd-zoom .pct { padding: 0 .35rem; font-size: .68rem; font-variant-numeric: tabular-nums; }
.tsd-nav button:hover:not(:disabled), .tsd-zoom button:hover { background: #fff; }
.tsd-nav button:disabled { opacity: .35; cursor: default; }
.tsd-note { margin: 0; padding: .45rem .9rem; color: #66706a; background: #f0f3f1; font-size: .72rem; border-bottom: 1px solid #e4e9e5; }
.tsd-note.warn { color: #7a5b17; background: #fbf3dc; border-color: #efe2b8; }
.tsd-stage { position: relative; display: flex; flex-direction: column; min-height: 0; overflow: hidden; }
.tsd-stage:not(.ready) { align-items: center; justify-content: center; }
.tsd-state { display: grid; justify-items: center; gap: .5rem; max-width: 26rem; padding: 2rem; text-align: center; color: #66706a; font-size: .8rem; }
.tsd-state strong { color: #2f3833; font-size: .95rem; }
.tsd-state button { margin-top: .3rem; padding: .45rem .95rem; border: 0; border-radius: .65rem; color: #fff; background: #3f7a58; font-weight: 600; cursor: pointer; }
.tsd-state.err strong { color: #9a3b3b; }
.tsd-spin { width: 1.4rem; height: 1.4rem; border: 2px solid #d6dfd9; border-top-color: #3f7a58; border-radius: 50%; animation: tsd-rot .8s linear infinite; }
@keyframes tsd-rot { to { transform: rotate(360deg); } }
.tsd-col-label { display: grid; grid-template-columns: 1fr 1fr; flex: none; padding: .4rem 0 .1rem; color: #7b857f; font-size: .64rem; letter-spacing: .08em; text-transform: uppercase; text-align: center; }
.tsd-split { display: grid; grid-template-columns: 1fr 1fr; flex: 1 1 auto; min-height: 0; }
.tsd-split .tsd-scroll:first-child { border-right: 1px solid #e1e7e3; }
.tsd-scroll { display: flex; flex-direction: column; align-items: center; gap: 1.4rem; min-height: 0; padding: 1rem 1.25rem 2.5rem; overflow: auto; scrollbar-gutter: stable; }
.tsd-scroll.swipe { flex: 1 1 auto; }
.tsd-row { position: relative; flex: none; scroll-margin-top: .75rem; }
.tsd-tag { position: absolute; top: .6rem; left: .6rem; z-index: 5; padding: .12rem .45rem; border-radius: .4rem; font-size: .62rem; font-weight: 700; white-space: nowrap; pointer-events: none; box-shadow: 0 1px 3px rgba(26,40,31,.12); }
.tsd-tag.add { color: #1c6a41; background: #e1f4e8; }
.tsd-tag.del { color: #a23232; background: #fbe6e4; }
.tsd-tag.mix { color: #4c5a52; background: #e9eeea; }
.tsd-gap { display: grid; place-items: center; border: 1px dashed #cdd6d0; border-radius: .3rem; color: #9aa39d; font-size: .72rem; background: repeating-linear-gradient(135deg, #f7f9f7, #f7f9f7 8px, #f1f4f2 8px, #f1f4f2 16px); }
.hl { position: absolute; z-index: 2; border-radius: .2rem; pointer-events: none; mix-blend-mode: multiply; animation: tsd-in .32s ease-out both; }
.hl.add { background: rgba(52, 181, 106, .32); box-shadow: inset 0 -2px 0 rgba(31, 138, 78, .75); }
.hl.del { background: rgba(232, 84, 76, .28); box-shadow: inset 0 -2px 0 rgba(196, 52, 46, .7); }
@keyframes tsd-in { from { opacity: 0; transform: scaleY(.6); } }
.tsd-swipe { position: relative; }
.tsd-over { position: absolute; inset: 0; z-index: 3; clip-path: inset(0 calc(100% - var(--cut)) 0 0); }
.tsd-handle { position: absolute; top: 0; bottom: 0; left: var(--cut); z-index: 4; width: 2px; margin-left: -1px; background: #3f7a58; box-shadow: 0 0 0 1px rgba(255,255,255,.8); pointer-events: none; }
.tsd-handle b { position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); padding: .2rem .4rem; border-radius: 999px; color: #fff; background: #3f7a58; font-size: .7rem; letter-spacing: .1em; box-shadow: 0 2px 8px rgba(24,60,40,.3); }
.tsd-end { position: absolute; top: .5rem; z-index: 5; padding: .1rem .4rem; border-radius: .35rem; color: #fff; background: rgba(40,55,47,.62); font-size: .6rem; pointer-events: none; }
.tsd-end.l { left: .5rem; } .tsd-end.r { right: .5rem; }
.tsd-slider { display: flex; flex: none; align-items: center; gap: .7rem; padding: .5rem 1rem; border-top: 1px solid #e4e9e5; color: #66706a; background: #fff; font-size: .7rem; }
.tsd-slider input { flex: 1; accent-color: #3f7a58; }
@media (prefers-reduced-motion: reduce) { .hl { animation: none; } .tsd-spin { animation-duration: 2s; } }
</style>
