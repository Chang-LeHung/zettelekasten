<script setup lang="ts">
import { defineAsyncComponent, nextTick, onBeforeUnmount, ref, watch } from 'vue'

const PdfTypesetDiff = defineAsyncComponent(() => import('./PdfTypesetDiff.vue'))
const props = defineProps<{ open: boolean; artifactId: string; title: string; nonce?: number }>()
const emit = defineEmits<{ close: [] }>()
const root = ref<HTMLElement | null>(null)
let previousOverflow = ''
let previousFocus: HTMLElement | null = null

watch(() => props.open, async (open) => {
  if (open) {
    previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null
    previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    await nextTick()
    root.value?.querySelector<HTMLElement>('.tsd')?.focus()
    return
  }
  document.body.style.overflow = previousOverflow
  previousFocus?.focus()
})
onBeforeUnmount(() => { if (props.open) document.body.style.overflow = previousOverflow })
</script>

<template>
  <Teleport to="body">
    <Transition name="compare">
      <div v-if="open" ref="root" class="compare-backdrop" role="dialog" aria-modal="true" :aria-label="$t('Compare with saved version')" @mousedown.self="emit('close')">
        <div class="compare-dialog">
          <header>
            <div><small>{{ $t('Typeset changes') }}</small><strong>{{ title }}</strong></div>
            <button type="button" :aria-label="$t('Close')" @click="emit('close')">×</button>
          </header>
          <PdfTypesetDiff :artifact-id="artifactId" :nonce="nonce" @close="emit('close')" />
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.compare-backdrop { position: fixed; inset: 0; z-index: 1700; display: grid; place-items: center; padding: clamp(.5rem, 2vw, 1.75rem); background: rgba(20, 28, 23, .5); backdrop-filter: blur(12px) saturate(1.2); }
.compare-dialog { display: grid; grid-template-rows: auto minmax(0, 1fr); width: min(98vw, 108rem); height: min(94dvh, 70rem); overflow: hidden; border: 1px solid rgba(255,255,255,.7); border-radius: 1.1rem; background: #f4f6f4; box-shadow: 0 32px 100px rgba(14, 24, 18, .32), 0 3px 12px rgba(14, 24, 18, .1); }
header { display: flex; align-items: center; justify-content: space-between; gap: 1rem; padding: .7rem .8rem .7rem 1.2rem; background: #fff; border-bottom: 1px solid #e4e9e5; }
header div { display: grid; min-width: 0; }
header small { color: #3f7a58; font-size: .62rem; font-weight: 700; letter-spacing: .09em; text-transform: uppercase; }
header strong { overflow: hidden; color: #26302a; font-size: .95rem; text-overflow: ellipsis; white-space: nowrap; }
header button { width: 2rem; height: 2rem; border: 0; border-radius: .6rem; color: #55625a; background: #edf1ee; font-size: 1.2rem; cursor: pointer; }
header button:hover { background: #e0e7e2; }
.compare-enter-active, .compare-leave-active { transition: opacity .2s ease; }
.compare-enter-active .compare-dialog, .compare-leave-active .compare-dialog { transition: transform .24s cubic-bezier(.2, .8, .2, 1); }
.compare-enter-from, .compare-leave-to { opacity: 0; }
.compare-enter-from .compare-dialog { transform: translateY(14px) scale(.985); }
@media (prefers-reduced-motion: reduce) { .compare-enter-active, .compare-leave-active, .compare-enter-active .compare-dialog { transition: none; } }
</style>
