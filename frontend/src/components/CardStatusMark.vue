<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from '../i18n'
import type { CardStatus } from '../api/types'
import { cardStatusLabel, isActive, quickTarget, statusGlyph, statusTone } from '../utils/cardStatus'
import '../styles/cardStatusTone.css'

const props = defineProps<{ status: CardStatus; busy?: boolean }>()
const emit = defineEmits<{ select: [status: CardStatus] }>()
const { t } = useI18n()

const target = computed(() => quickTarget(props.status))
const glyph = computed(() => statusGlyph(props.status))
const label = computed(() => t(cardStatusLabel(props.status)))
const action = computed(() => (target.value ? `${label.value} · ${t(cardStatusLabel(target.value))}` : label.value))
// A mark that finishes something reports itself as a checkbox: unfinished work is
// "mixed" while it is under way, so a screen reader hears what the circle shows.
const checked = computed(() => (glyph.value === 'check' ? 'true' : glyph.value === 'half' ? 'mixed' : 'false'))
</script>

<template>
  <component
    :is="target ? 'button' : 'span'"
    class="status-mark"
    :class="[statusTone(status), { active: isActive(status), quick: target }]"
    v-bind="target
      ? { type: 'button', role: 'checkbox', 'aria-checked': checked, 'aria-label': action, title: action, disabled: busy }
      : { role: 'img', 'aria-label': label, title: label }"
    @click.stop="target && emit('select', target)"
    @keydown.stop
    @pointerdown.stop
  >
    <svg viewBox="0 0 20 20" aria-hidden="true">
      <circle class="ring" cx="10" cy="10" r="8" />
      <path v-if="glyph === 'half'" class="glyph fill" d="M10 5.2a4.8 4.8 0 0 1 0 9.6Z" />
      <path v-else-if="glyph === 'pause'" class="glyph" d="M8 7v6M12 7v6" />
      <path v-else-if="glyph === 'check'" class="glyph tick" d="m6.2 10.4 2.5 2.5 5.1-5.6" />
      <path v-else-if="glyph === 'cross'" class="glyph" d="m7.2 7.2 5.6 5.6m0-5.6-5.6 5.6" />
      <circle v-else-if="glyph === 'dot'" class="glyph fill" cx="10" cy="10" r="2.2" />
      <path v-else-if="glyph === 'spark'" class="glyph" d="M10 6.2v7.6M6.2 10h7.6" />
    </svg>
  </component>
</template>

<style scoped>
.status-mark { flex: 0 0 auto; display: inline-grid; place-items: center; width: 1.45rem; height: 1.45rem; padding: 0; border: 0; border-radius: 50%; color: var(--status-ink); background: transparent; transition: transform 140ms ease, background 140ms ease; }
.status-mark.quick { cursor: pointer; }
.status-mark.quick:hover:not(:disabled) { background: var(--status-soft); transform: scale(1.08); }
.status-mark:focus-visible { outline: 2px solid var(--status-ink); outline-offset: 1px; }
.status-mark:disabled { cursor: progress; opacity: .55; }
svg { width: 1.2rem; height: 1.2rem; overflow: visible; fill: none; stroke: currentColor; stroke-width: 1.6; stroke-linecap: round; stroke-linejoin: round; }
.ring { fill: transparent; transition: fill 160ms ease; }
.status-done .ring, .status-adopted .ring, .status-read .ring { fill: var(--status-soft); }
.active .ring { stroke-dasharray: 3 2.2; animation: status-spin 7s linear infinite; transform-origin: 10px 10px; }
.status-on-hold .ring { stroke-dasharray: 2 2.4; }
.status-cancelled .ring, .status-dropped .ring { opacity: .75; }
.status-unread .ring { fill: var(--status-soft); stroke-width: 2.1; }
.glyph.fill { fill: currentColor; stroke: none; }
.glyph.tick { stroke-width: 2; stroke-dasharray: 16; stroke-dashoffset: 0; animation: status-draw 220ms ease-out; }
@keyframes status-spin { to { transform: rotate(360deg); } }
@keyframes status-draw { from { stroke-dashoffset: 16; } }
@media (prefers-reduced-motion: reduce) {
  .active .ring, .glyph.tick { animation: none; }
  .status-mark { transition: none; }
}
</style>
