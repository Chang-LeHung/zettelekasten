<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import type { PDFDocumentProxy } from 'pdfjs-dist'
import type { DiffRect, HunkSide } from '../utils/pdfTypesetDiff'
import PdfCrop from './PdfCrop.vue'

/**
 * One edit, shown the way a reviewer reads it: the old typeset lines on a red band, the new
 * ones on a green band. A figure change shows the same region before and after.
 */
const props = defineProps<{
  index: number
  kind: 'text' | 'figure'
  before: HunkSide | null
  after: HunkSide | null
  /** For a figure: the changed regions of the page, drawn on both sides. */
  figure?: { page: number; rect: DiffRect; marks: DiffRect[] } | null
  baseDoc: PDFDocumentProxy
  targetDoc: PDFDocumentProxy
  /** The horizontal extent shared by the text of the page, in page units. */
  column: { x: number; width: number }
  width: number
}>()

const copied = ref(false)
let copiedTimer: number | null = null

/** Most lines of an edit shown in one band; the page views hold the rest. */
const MAX_LINES = 7

/** A line of the page above and below the edit, and at most MAX_LINES of the edit itself. */
function bandOf(side: HunkSide): { y: number; height: number } {
  const line = side.line
  const top = Math.max(0, side.rect.y - line * 0.9)
  return { y: top, height: Math.min(side.rect.y + side.rect.height + line * 0.9 - top, line * (MAX_LINES + 1.8)) }
}

/** Both bands of a card get the taller height, so Before and After line up. */
function matchHeights<T extends { band: { y: number; height: number } } | null>(first: T, second: T): void {
  const height = Math.max(first?.band.height ?? 0, second?.band.height ?? 0)
  if (first) first.band.height = height
  if (second) second.band.height = height
}

const sides = computed(() => {
  if (props.kind === 'figure' && props.figure) {
    const { page, rect, marks } = props.figure
    const pad = 14
    const band = { y: Math.max(0, rect.y - pad), height: rect.height + pad * 2 }
    return {
      before: { page, band, marks, doc: props.baseDoc },
      after: { page, band, marks, doc: props.targetDoc },
    }
  }
  const before = props.before ? { page: props.before.page, band: bandOf(props.before), marks: props.before.marks, doc: props.baseDoc } : null
  const after = props.after ? { page: props.after.page, band: bandOf(props.after), marks: props.after.marks, doc: props.targetDoc } : null
  if (before && after) matchHeights(before, after)
  return { before, after }
})
const page = computed(() => props.figure?.page ?? props.after?.page ?? props.before?.page ?? 1)
const title = computed(() => (props.kind === 'figure' ? 'Figure' : 'Change'))
const removed = computed(() => props.before?.words ?? 0)
const added = computed(() => props.after?.words ?? 0)

onBeforeUnmount(() => { if (copiedTimer !== null) window.clearTimeout(copiedTimer) })

async function copy(): Promise<void> {
  const text = props.kind === 'figure'
    ? `Figure on page ${page.value} changed`
    : `- ${props.before?.text ?? ''}\n+ ${props.after?.text ?? ''}`
  try {
    await navigator.clipboard.writeText(text)
    copied.value = true
    if (copiedTimer !== null) window.clearTimeout(copiedTimer)
    copiedTimer = window.setTimeout(() => { copied.value = false }, 1400)
  } catch {
    copied.value = false
  }
}
</script>

<template>
  <article class="change-card" :aria-label="`${$t(title)} ${index}`">
    <header class="card-head">
      <strong>{{ $t(title) }} {{ index }}</strong>
      <span class="card-page">{{ $t('Page {page}', { page }) }}</span>
      <span v-if="kind === 'text'" class="card-delta">
        <em v-if="added" class="add">+{{ added }}</em>
        <em v-if="removed" class="del">−{{ removed }}</em>
      </span>
      <button type="button" class="card-copy" :title="$t('Copy the change as text')" :aria-label="$t('Copy the change as text')" @click="copy">{{ copied ? $t('Copied') : $t('Copy') }}</button>
    </header>
    <section class="band before">
      <span class="band-label">{{ $t('Before') }}</span>
      <PdfCrop v-if="sides.before" :document="sides.before.doc" :page="sides.before.page" :band="sides.before.band" :column="column" :marks="sides.before.marks" :kind="kind === 'figure' ? 'fig' : 'del'" :width="width" />
      <p v-else class="band-empty">{{ $t('Nothing here before') }}</p>
    </section>
    <section class="band after">
      <span class="band-label">{{ $t('After') }}</span>
      <PdfCrop v-if="sides.after" :document="sides.after.doc" :page="sides.after.page" :band="sides.after.band" :column="column" :marks="sides.after.marks" :kind="kind === 'figure' ? 'fig' : 'add'" :width="width" />
      <p v-else class="band-empty">{{ $t('Removed') }}</p>
    </section>
  </article>
</template>

<style scoped>
.change-card { overflow: hidden; border: 1px solid var(--diff-border); border-radius: var(--diff-radius); background: #fff; box-shadow: var(--diff-shadow); }
.card-head { display: flex; align-items: center; gap: .6rem; padding: .6rem .9rem; white-space: nowrap; background: var(--diff-head); }
.card-head strong { color: var(--diff-head-ink); font-size: .8rem; font-weight: 650; letter-spacing: -.005em; }
.card-page { color: #6b7a8c; font-size: .68rem; font-variant-numeric: tabular-nums; }
.card-delta { display: inline-flex; gap: .3rem; font-size: .66rem; font-weight: 650; }
.card-delta em { padding: .05rem .45rem; border-radius: 999px; font-style: normal; font-variant-numeric: tabular-nums; }
.card-delta .add { color: var(--diff-add-ink); background: var(--diff-add-tint); }
.card-delta .del { color: var(--diff-del-ink); background: var(--diff-del-tint); }
.card-copy { margin-left: auto; padding: .24rem .7rem; border: 0; border-radius: .6rem; color: #3b5f8f; background: rgba(255, 255, 255, .8); font-size: .68rem; font-weight: 620; cursor: pointer; transition: background .15s; }
.card-copy:hover { background: #fff; }
.band { position: relative; border-left: 3px solid; }
.band.before { border-color: var(--diff-del-line); background: var(--diff-del-tint); }
.band.after { border-color: var(--diff-add-line); background: var(--diff-add-tint); }
.band-label { position: absolute; z-index: 2; top: .4rem; right: .7rem; padding: .05rem .4rem; border-radius: .4rem; font-size: .62rem; font-weight: 650; letter-spacing: .02em; background: rgba(255, 255, 255, .7); }
.band.before .band-label { color: var(--diff-del-ink); }
.band.after .band-label { color: var(--diff-add-ink); }
.band-empty { margin: 0; padding: 1.1rem 1rem; color: #8a96a3; font-size: .74rem; font-style: italic; }
.band :deep(.crop) { background: transparent; }
.band :deep(.crop canvas) { mix-blend-mode: multiply; }
</style>
