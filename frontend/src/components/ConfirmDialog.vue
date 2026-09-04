<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, watch } from 'vue'

const props = withDefaults(defineProps<{
  open: boolean
  title: string
  message: string
  confirmLabel?: string
}>(), {
  confirmLabel: 'Delete',
})

const emit = defineEmits<{
  cancel: []
  confirm: []
}>()

const cancelButton = ref<HTMLButtonElement | null>(null)
let previousFocus: HTMLElement | null = null

watch(
  () => props.open,
  (open) => {
    if (open) {
      previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null
      void nextTick(() => cancelButton.value?.focus())
      return
    }
    previousFocus?.focus()
    previousFocus = null
  },
)

onBeforeUnmount(() => previousFocus?.focus())
</script>

<template>
  <Teleport to="body">
    <Transition name="confirm-dialog">
      <div v-if="open" class="confirm-backdrop" @click.self="emit('cancel')" @keydown.esc.stop.prevent="emit('cancel')">
        <section class="confirm-panel" role="alertdialog" aria-modal="true" aria-labelledby="confirm-title" aria-describedby="confirm-message">
          <div class="confirm-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24"><path d="M4 7h16M9 7V4h6v3m3 0-1 13H7L6 7m4 4v5m4-5v5" /></svg>
          </div>
          <div class="confirm-copy">
            <span>Permanent action</span>
            <h2 id="confirm-title">{{ title }}</h2>
            <p id="confirm-message">{{ message }}</p>
          </div>
          <footer>
            <button ref="cancelButton" class="cancel-button" type="button" @click="emit('cancel')">Cancel</button>
            <button class="confirm-button" type="button" @click="emit('confirm')">
              <svg viewBox="0 0 24 24"><path d="M4 7h16M9 7V4h6v3m3 0-1 13H7L6 7m4 4v5m4-5v5" /></svg>
              {{ confirmLabel }}
            </button>
          </footer>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.confirm-backdrop { position: fixed; inset: 0; z-index: 1000; display: grid; place-items: center; padding: 1.25rem; background: rgba(35, 42, 38, .22); backdrop-filter: blur(12px) saturate(115%); }
.confirm-panel { width: min(100%, 27rem); overflow: hidden; border: 1px solid rgba(60, 72, 65, .12); border-radius: 1.25rem; background: rgba(255, 255, 255, .97); box-shadow: 0 28px 80px rgba(31, 42, 35, .2), 0 2px 8px rgba(31, 42, 35, .08); }
.confirm-icon { display: grid; place-items: center; width: 2.8rem; height: 2.8rem; margin: 1.35rem 1.35rem .8rem; border-radius: .88rem; color: #a64949; background: #f9eceb; box-shadow: inset 0 0 0 1px rgba(166, 73, 73, .08); }
.confirm-icon svg, .confirm-button svg { width: 1.15rem; height: 1.15rem; fill: none; stroke: currentColor; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; }
.confirm-copy { padding: 0 1.35rem 1.3rem; }
.confirm-copy > span { color: #a35757; font-size: .62rem; font-weight: 720; letter-spacing: .075em; text-transform: uppercase; }
.confirm-copy h2 { margin: .38rem 0 .55rem; color: #262b28; font-size: 1.2rem; line-height: 1.28; letter-spacing: -.02em; }
.confirm-copy p { margin: 0; color: #717873; font-size: .8rem; line-height: 1.6; overflow-wrap: anywhere; }
.confirm-panel footer { display: flex; justify-content: flex-end; gap: .55rem; padding: .85rem 1rem; border-top: 1px solid #e7eae8; background: #f7f8f7; }
.confirm-panel button { min-height: 2.35rem; padding: 0 .9rem; border-radius: .68rem; cursor: pointer; font-size: .72rem; font-weight: 660; }
.cancel-button { border: 1px solid #dfe3e0; color: #59615c; background: #fff; }
.cancel-button:hover { color: #344239; border-color: #cbd3ce; background: #fafbfa; }
.confirm-button { display: inline-flex; align-items: center; gap: .42rem; border: 1px solid #9d4545; color: #fff; background: #a94d4d; box-shadow: 0 4px 12px rgba(153, 61, 61, .18); }
.confirm-button:hover { background: #963f3f; }
.confirm-panel button:focus-visible { outline: 3px solid rgba(71, 105, 87, .2); outline-offset: 2px; }
.confirm-dialog-enter-active, .confirm-dialog-leave-active { transition: opacity 170ms ease; }
.confirm-dialog-enter-active .confirm-panel, .confirm-dialog-leave-active .confirm-panel { transition: transform 220ms cubic-bezier(.2, .8, .2, 1), opacity 170ms ease; }
.confirm-dialog-enter-from, .confirm-dialog-leave-to { opacity: 0; }
.confirm-dialog-enter-from .confirm-panel, .confirm-dialog-leave-to .confirm-panel { opacity: 0; transform: translateY(.55rem) scale(.975); }
@media (max-width: 520px) {
  .confirm-backdrop { align-items: end; padding: .75rem; }
  .confirm-panel { border-radius: 1.15rem; }
  .confirm-panel footer { display: grid; grid-template-columns: 1fr 1fr; }
  .confirm-panel button { justify-content: center; }
}
@media (prefers-reduced-motion: reduce) {
  .confirm-dialog-enter-active, .confirm-dialog-leave-active, .confirm-dialog-enter-active .confirm-panel, .confirm-dialog-leave-active .confirm-panel { transition-duration: 1ms; }
}
</style>
