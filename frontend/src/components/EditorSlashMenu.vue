<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { useI18n } from '../i18n'
import type { BlockCommand, CommandGroup } from '../utils/blockCommands'

const props = defineProps<{
  items: readonly BlockCommand[]
  active: number
  /** Viewport position of the menu's left edge, and of the edge it hangs from. */
  left: number
  anchor: { top: number } | { bottom: number }
}>()
const emit = defineEmits<{ pick: [command: BlockCommand]; hover: [index: number] }>()
const { t } = useI18n()

const list = ref<HTMLElement | null>(null)

interface Section { group: CommandGroup; entries: Array<{ command: BlockCommand; index: number }> }
const sections = computed<Section[]>(() => {
  const result: Section[] = []
  props.items.forEach((command, index) => {
    let section = result.find((candidate) => candidate.group === command.group)
    if (!section) result.push(section = { group: command.group, entries: [] })
    section.entries.push({ command, index })
  })
  return result
})

// Keep the highlighted row on screen as the arrow keys walk a long list.
watch(() => props.active, () => {
  void nextTick(() => list.value?.querySelector('[aria-selected="true"]')?.scrollIntoView({ block: 'nearest' }))
})
</script>

<template>
  <Teleport to="body">
    <div class="block-popup slash-menu" role="listbox" :aria-label="t('editor.group.basic')" :style="{ ...('top' in anchor ? { top: `${anchor.top}px` } : { bottom: `${anchor.bottom}px` }), left: `${left}px` }" @mousedown.prevent>
      <div ref="list" class="slash-scroll">
        <p v-if="!items.length" class="slash-empty">{{ t('editor.noResults') }}</p>
        <section v-for="section in sections" :key="section.group">
          <h3>{{ t(`editor.group.${section.group}`) }}</h3>
          <button
            v-for="{ command, index } in section.entries"
            :key="command.id"
            class="slash-item"
            :class="{ active: index === active }"
            type="button"
            role="option"
            :aria-selected="index === active"
            @mousemove="emit('hover', index)"
            @click="emit('pick', command)"
          >
            <span class="slash-glyph" aria-hidden="true">{{ command.glyph }}</span>
            <span class="slash-copy"><strong>{{ t(`editor.cmd.${command.id}`) }}</strong><small>{{ t(`editor.cmd.${command.id}.hint`) }}</small></span>
          </button>
        </section>
      </div>
    </div>
  </Teleport>
</template>

<style>
.block-popup { position: fixed; z-index: 1500; color: #2b312d; font-size: .8rem; }
.slash-menu { width: 19rem; max-height: min(22rem, 60vh); display: flex; flex-direction: column; overflow: hidden; border: 1px solid rgba(29,29,31,.09); border-radius: .8rem; background: rgba(255,255,255,.98); box-shadow: 0 16px 48px rgba(24,28,26,.16), 0 2px 8px rgba(24,28,26,.06); backdrop-filter: blur(18px); animation: block-popup-in 120ms ease-out; }
.slash-scroll { min-height: 0; overflow-y: auto; padding: .35rem; overscroll-behavior: contain; scrollbar-width: thin; }
.slash-menu h3 { margin: .45rem .5rem .2rem; color: #8a918c; font-size: .66rem; font-weight: 650; letter-spacing: .02em; }
.slash-menu section:first-child h3 { margin-top: .2rem; }
.slash-item { display: flex; align-items: center; gap: .65rem; width: 100%; min-height: 2.7rem; padding: .3rem .5rem; border: 0; border-radius: .5rem; color: inherit; background: transparent; cursor: pointer; text-align: left; }
.slash-item.active { background: #eef1ef; }
.slash-glyph { display: grid; place-items: center; width: 2.1rem; height: 2.1rem; flex: 0 0 auto; border: 1px solid #e3e6e4; border-radius: .45rem; color: #4a524d; background: #fff; font-size: .78rem; font-weight: 650; }
.slash-copy { min-width: 0; display: grid; gap: .08rem; }
.slash-copy strong { font-size: .8rem; font-weight: 600; }
.slash-copy small { overflow: hidden; color: #858c87; font-size: .68rem; text-overflow: ellipsis; white-space: nowrap; }
.slash-empty { margin: 0; padding: .9rem .6rem; color: #858c87; text-align: center; }
@keyframes block-popup-in { from { opacity: 0; transform: translateY(-3px) scale(.985); } }
@media (prefers-reduced-motion: reduce) { .slash-menu { animation: none; } }
</style>
