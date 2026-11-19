<script setup lang="ts">
import { computed, defineAsyncComponent, nextTick, ref, watch } from 'vue'
import { diffMarkdown, markWords, renderedWords, wordMask } from '../utils/markdownDiff'

const MarkdownContent = defineAsyncComponent(() => import('./MarkdownContent.vue'))

const props = defineProps<{ before: string; after: string }>()

type View = 'changes' | 'before' | 'after'
const view = ref<View>('changes')
const changedOnly = ref(false)
const current = ref(0)
const root = ref<HTMLElement | null>(null)
const VIEWS: Array<{ id: View; label: string }> = [
  { id: 'changes', label: 'Changes' },
  { id: 'before', label: 'Before' },
  { id: 'after', label: 'After' },
]

const diff = computed(() => diffMarkdown(props.before, props.after))

type Item = { type: 'block'; block: (typeof diff.value.blocks)[number]; index: number } | { type: 'gap'; count: number; key: string }
/** With "changed only", an unchanged stretch collapses to one row, keeping a block of context on each side. */
const items = computed<Item[]>(() => {
  const blocks = diff.value.blocks
  if (!changedOnly.value) return blocks.map((block, index) => ({ type: 'block', block, index }))
  const keep = new Set<number>()
  blocks.forEach((block, index) => {
    if (block.kind === 'same') return
    for (let near = index - 1; near <= index + 1; near += 1) keep.add(near)
  })
  const result: Item[] = []
  let skipped = 0
  blocks.forEach((block, index) => {
    if (keep.has(index)) {
      if (skipped) result.push({ type: 'gap', count: skipped, key: `g${index}` })
      skipped = 0
      result.push({ type: 'block', block, index })
    } else skipped += 1
  })
  if (skipped) result.push({ type: 'gap', count: skipped, key: 'gend' })
  return result
})
const changeKeys = computed(() => diff.value.blocks.filter((block) => block.kind === 'added' || (block.kind === 'removed' && block.pair === null)).map((block) => block.key))

/** Word-level emphasis inside a rewritten block, applied once its Markdown has rendered. */
async function emphasize(): Promise<void> {
  await nextTick()
  requestAnimationFrame(() => {
    const host = root.value
    if (!host || view.value !== 'changes') return
    const pairs = new Map<string, { removed?: HTMLElement; added?: HTMLElement }>()
    host.querySelectorAll<HTMLElement>('[data-pair]').forEach((element) => {
      const id = element.dataset.pair ?? ''
      pairs.set(id, { ...pairs.get(id), [element.dataset.kind === 'removed' ? 'removed' : 'added']: element })
    })
    for (const { removed, added } of pairs.values()) {
      if (!removed || !added || removed.dataset.marked) continue
      const mask = wordMask(renderedWords(removed), renderedWords(added))
      markWords(removed, mask.removed, 'w-del')
      markWords(added, mask.added, 'w-add')
      removed.dataset.marked = '1'
      added.dataset.marked = '1'
    }
  })
}

function goTo(index: number): void {
  if (!changeKeys.value.length) return
  const wrapped = (index + changeKeys.value.length) % changeKeys.value.length
  current.value = wrapped
  root.value?.querySelector<HTMLElement>(`[data-key="${changeKeys.value[wrapped]}"]`)?.scrollIntoView({ block: 'center', behavior: 'smooth' })
}

function onKey(event: KeyboardEvent): void {
  if (event.target instanceof HTMLElement && /input|textarea|select/i.test(event.target.tagName)) return
  if (event.key === 'j') goTo(current.value + 1)
  else if (event.key === 'k') goTo(current.value - 1)
  else return
  event.preventDefault()
}

watch([() => props.before, () => props.after, view, changedOnly], () => { current.value = 0; void emphasize() }, { immediate: true })
</script>

<template>
  <section class="mdd" tabindex="-1" aria-label="Changes" @keydown="onKey">
    <header class="mdd-bar">
      <div class="mdd-summary">
        <span v-if="!diff.changed" class="mdd-chip same">{{ $t('No visible changes') }}</span>
        <template v-else>
          <span class="mdd-chip add">+{{ diff.added }}</span>
          <span class="mdd-chip del">−{{ diff.removed }}</span>
        </template>
      </div>
      <div class="mdd-tools">
        <div class="mdd-seg" role="group" :aria-label="$t('Comparison mode')">
          <button v-for="item in VIEWS" :key="item.id" type="button" :class="{ on: view === item.id }" @click="view = item.id">{{ $t(item.label) }}</button>
        </div>
        <label v-if="view === 'changes'" class="mdd-toggle"><input v-model="changedOnly" type="checkbox" /><span>{{ $t('Changed only') }}</span></label>
        <div v-if="view === 'changes'" class="mdd-nav" role="group" aria-label="Changes">
          <button type="button" :disabled="!changeKeys.length" :title="$t('Previous change (k)')" @click="goTo(current - 1)">‹</button>
          <em>{{ changeKeys.length ? `${current + 1} / ${changeKeys.length}` : '–' }}</em>
          <button type="button" :disabled="!changeKeys.length" :title="$t('Next change (j)')" @click="goTo(current + 1)">›</button>
        </div>
      </div>
    </header>
    <div ref="root" class="mdd-scroll">
      <article class="mdd-page">
        <MarkdownContent v-if="view === 'before'" :content="before" />
        <MarkdownContent v-else-if="view === 'after'" :content="after" />
        <template v-else>
          <template v-for="item in items" :key="item.type === 'gap' ? item.key : item.block.key">
            <p v-if="item.type === 'gap'" class="mdd-gap">{{ $t('{count} unchanged blocks', { count: item.count }) }}</p>
            <div v-else class="mdd-block" :class="`is-${item.block.kind}`" :data-key="item.block.key" :data-kind="item.block.kind" :data-pair="item.block.pair ?? undefined">
              <MarkdownContent :content="item.block.text" />
            </div>
          </template>
        </template>
      </article>
    </div>
  </section>
</template>

<style scoped>
.mdd { display: grid; grid-template-rows: auto minmax(0, 1fr); width: 100%; height: 100%; min-height: 0; background: #f4f6f4; outline: none; }
.mdd-bar { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: .5rem .8rem; padding: .5rem .8rem; border-bottom: 1px solid #e4e9e5; background: rgba(255,255,255,.86); backdrop-filter: saturate(1.4) blur(12px); }
.mdd-summary, .mdd-tools { display: flex; flex-wrap: wrap; align-items: center; gap: .45rem; }
.mdd-chip { display: inline-flex; align-items: center; height: 1.5rem; padding: 0 .6rem; border-radius: 999px; font-size: .7rem; font-weight: 650; font-variant-numeric: tabular-nums; }
.mdd-chip.add { color: #1c6a41; background: #e1f4e8; }
.mdd-chip.del { color: #a23232; background: #fbe6e4; }
.mdd-chip.same { color: #3d6650; background: #e6f1ea; }
.mdd-seg { display: inline-flex; padding: .15rem; border-radius: .7rem; background: #e9eeea; }
.mdd-seg button { border: 0; padding: .28rem .75rem; border-radius: .55rem; color: #5b675f; background: transparent; font-size: .7rem; font-weight: 600; cursor: pointer; transition: background .16s, color .16s, box-shadow .16s; }
.mdd-seg button.on { color: #20382b; background: #fff; box-shadow: 0 1px 3px rgba(26,40,31,.14); }
.mdd-toggle { display: inline-flex; align-items: center; gap: .35rem; color: #5b675f; font-size: .7rem; cursor: pointer; }
.mdd-toggle input { accent-color: #3f7a58; }
.mdd-nav { display: inline-flex; align-items: center; gap: .1rem; padding: .15rem; border-radius: .7rem; background: #e9eeea; }
.mdd-nav em { min-width: 2.8rem; color: #5b675f; font-size: .68rem; font-style: normal; text-align: center; font-variant-numeric: tabular-nums; }
.mdd-nav button { display: grid; place-items: center; min-width: 1.6rem; height: 1.6rem; border: 0; border-radius: .5rem; color: #43524a; background: transparent; font-size: 1rem; cursor: pointer; }
.mdd-nav button:hover:not(:disabled) { background: #fff; }
.mdd-nav button:disabled { opacity: .35; cursor: default; }
.mdd-scroll { min-height: 0; padding: 1.1rem 1rem 2.5rem; overflow: auto; scrollbar-gutter: stable; }
.mdd-page { max-width: 46rem; margin: 0 auto; padding: 1.6rem 1.9rem; border-radius: .35rem; background: #fff; box-shadow: 0 8px 30px rgba(28,37,31,.12); }
.mdd-block { margin: .15rem -.6rem; padding: .05rem .6rem; border-radius: .5rem; }
.mdd-block.is-added { background: rgba(52, 181, 106, .12); }
.mdd-block.is-removed { background: rgba(232, 84, 76, .1); }
.mdd-gap { margin: .6rem 0; padding: .3rem 0; color: #8a938d; font-size: .68rem; text-align: center; border-block: 1px dashed #dde4df; }
.mdd-block :deep(mark) { color: inherit; text-decoration: none; border-radius: .2rem; }
.mdd-block :deep(mark.w-add) { background: rgba(52, 181, 106, .3); }
.mdd-block :deep(mark.w-del) { background: rgba(232, 84, 76, .26); }
</style>
