<script setup lang="ts">
import { useI18n } from '../i18n'

export type InlineFormat = 'bold' | 'italic' | 'strike' | 'code' | 'link' | 'math'

defineProps<{ top: number; left: number; active: readonly InlineFormat[] }>()
const emit = defineEmits<{ format: [format: InlineFormat] }>()
const { t } = useI18n()

const BUTTONS: Array<{ format: InlineFormat; label: string; glyph: string; shortcut: string }> = [
  { format: 'bold', label: 'editor.fmt.bold', glyph: 'B', shortcut: '⌘B' },
  { format: 'italic', label: 'editor.fmt.italic', glyph: 'I', shortcut: '⌘I' },
  { format: 'strike', label: 'editor.fmt.strike', glyph: 'S', shortcut: '⇧⌘X' },
  { format: 'code', label: 'editor.fmt.code', glyph: '</>', shortcut: '⌘E' },
  { format: 'math', label: 'editor.fmt.math', glyph: 'Σ', shortcut: '' },
  { format: 'link', label: 'editor.fmt.link', glyph: '↗', shortcut: '⌘K' },
]
</script>

<template>
  <Teleport to="body">
    <!-- mousedown is held back so pressing a button never moves focus out of the textarea and loses the selection. -->
    <div class="block-popup selection-bar" role="toolbar" :aria-label="t('editor.fmt.bold')" :style="{ top: `${top}px`, left: `${left}px` }" @mousedown.prevent>
      <button
        v-for="button in BUTTONS"
        :key="button.format"
        class="selection-button"
        :class="[`fmt-${button.format}`, { active: active.includes(button.format) }]"
        type="button"
        :aria-pressed="active.includes(button.format)"
        :aria-label="t(button.label)"
        :title="button.shortcut ? `${t(button.label)} (${button.shortcut})` : t(button.label)"
        @click="emit('format', button.format)"
      >{{ button.glyph }}</button>
    </div>
  </Teleport>
</template>

<style>
.selection-bar { display: flex; align-items: center; gap: .1rem; padding: .22rem; border: 1px solid rgba(29,29,31,.1); border-radius: .65rem; background: rgba(255,255,255,.98); box-shadow: 0 8px 28px rgba(24,28,26,.16), 0 1px 4px rgba(24,28,26,.06); backdrop-filter: blur(16px); animation: block-popup-in 100ms ease-out; }
.selection-button { display: grid; place-items: center; min-width: 1.9rem; height: 1.9rem; padding: 0 .35rem; border: 0; border-radius: .42rem; color: #3c433f; background: transparent; cursor: pointer; font-size: .78rem; font-weight: 650; }
.selection-button:hover { background: #eef1ef; }
.selection-button.active { color: #2f5541; background: #e1ede5; }
.selection-button.fmt-italic { font-family: Georgia, serif; font-style: italic; }
.selection-button.fmt-strike { text-decoration: line-through; }
.selection-button.fmt-code { font-family: "SFMono-Regular", Consolas, monospace; font-size: .68rem; }
@media (prefers-reduced-motion: reduce) { .selection-bar { animation: none; } }
</style>
