<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useI18n } from '../i18n'
import type { TurnTarget } from '../utils/markdownBlocks'

defineProps<{ top: number; left: number; canTurn: boolean; canMoveUp: boolean; canMoveDown: boolean; canDelete: boolean }>()
const emit = defineEmits<{
  turn: [target: TurnTarget]
  duplicate: []
  remove: []
  move: [direction: -1 | 1]
  close: []
}>()
const { t } = useI18n()
const root = ref<HTMLElement | null>(null)

const TURN: Array<{ target: TurnTarget; label: string; glyph: string }> = [
  { target: 'paragraph', label: 'editor.cmd.text', glyph: 'Aa' },
  { target: 'h1', label: 'editor.cmd.h1', glyph: 'H1' },
  { target: 'h2', label: 'editor.cmd.h2', glyph: 'H2' },
  { target: 'h3', label: 'editor.cmd.h3', glyph: 'H3' },
  { target: 'bullet', label: 'editor.cmd.bullet', glyph: '•' },
  { target: 'numbered', label: 'editor.cmd.numbered', glyph: '1.' },
  { target: 'todo', label: 'editor.cmd.todo', glyph: '☐' },
  { target: 'quote', label: 'editor.cmd.quote', glyph: '”' },
  { target: 'code', label: 'editor.cmd.code', glyph: '</>' },
]

function onOutside(event: Event): void {
  if (event.target instanceof Node && root.value?.contains(event.target)) return
  emit('close')
}
function onKey(event: KeyboardEvent): void {
  if (event.key !== 'Escape') return
  event.stopPropagation()
  emit('close')
}
onMounted(() => {
  document.addEventListener('pointerdown', onOutside, true)
  document.addEventListener('keydown', onKey, true)
  root.value?.querySelector<HTMLElement>('button')?.focus()
})
onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', onOutside, true)
  document.removeEventListener('keydown', onKey, true)
})
</script>

<template>
  <Teleport to="body">
    <div ref="root" class="block-popup block-menu" role="menu" :style="{ top: `${top}px`, left: `${left}px` }">
      <template v-if="canTurn">
        <h3>{{ t('editor.menu.turnInto') }}</h3>
        <div class="turn-grid">
          <button v-for="item in TURN" :key="item.target" class="turn-item" type="button" role="menuitem" :title="t(item.label)" :aria-label="t(item.label)" @click="emit('turn', item.target)">{{ item.glyph }}</button>
        </div>
        <hr />
      </template>
      <button class="menu-row" type="button" role="menuitem" :disabled="!canMoveUp" @click="emit('move', -1)"><span aria-hidden="true">↑</span>{{ t('editor.menu.moveUp') }}</button>
      <button class="menu-row" type="button" role="menuitem" :disabled="!canMoveDown" @click="emit('move', 1)"><span aria-hidden="true">↓</span>{{ t('editor.menu.moveDown') }}</button>
      <button class="menu-row" type="button" role="menuitem" @click="emit('duplicate')"><span aria-hidden="true">⧉</span>{{ t('editor.menu.duplicate') }}</button>
      <button class="menu-row danger" type="button" role="menuitem" :disabled="!canDelete" @click="emit('remove')"><span aria-hidden="true">⌫</span>{{ t('editor.menu.delete') }}</button>
    </div>
  </Teleport>
</template>

<style>
.block-menu { width: 13.5rem; padding: .35rem; border: 1px solid rgba(29,29,31,.09); border-radius: .8rem; background: rgba(255,255,255,.98); box-shadow: 0 16px 48px rgba(24,28,26,.16), 0 2px 8px rgba(24,28,26,.06); backdrop-filter: blur(18px); animation: block-popup-in 120ms ease-out; }
.block-menu h3 { margin: .3rem .5rem .35rem; color: #8a918c; font-size: .66rem; font-weight: 650; }
.block-menu hr { margin: .35rem .2rem; border: 0; border-top: 1px solid #edefed; }
.turn-grid { display: grid; grid-template-columns: repeat(5, 1fr); gap: .2rem; padding: 0 .15rem; }
.turn-item { height: 2rem; border: 1px solid #e6e9e7; border-radius: .45rem; color: #4a524d; background: #fff; cursor: pointer; font-size: .74rem; font-weight: 650; }
.turn-item:hover { background: #eef1ef; }
.menu-row { display: flex; align-items: center; gap: .6rem; width: 100%; min-height: 2rem; padding: 0 .5rem; border: 0; border-radius: .45rem; color: #2f3632; background: transparent; cursor: pointer; font-size: .78rem; text-align: left; }
.menu-row span { width: 1rem; color: #7b827d; text-align: center; }
.menu-row:hover:not(:disabled), .menu-row:focus-visible { outline: 0; background: #eef1ef; }
.menu-row:disabled { opacity: .38; cursor: default; }
.menu-row.danger:hover:not(:disabled) { color: #a24747; background: #f9eded; }
.menu-row.danger:hover:not(:disabled) span { color: inherit; }
@media (prefers-reduced-motion: reduce) { .block-menu { animation: none; } }
</style>
