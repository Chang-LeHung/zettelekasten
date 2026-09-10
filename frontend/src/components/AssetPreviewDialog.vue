<script setup lang="ts">
import { computed, defineAsyncComponent, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { SessionAsset } from '../api/types'
import { assetOpenAction } from '../utils/assetOpen'

const MarkdownContent = defineAsyncComponent(() => import('./MarkdownContent.vue'))

const props = defineProps<{
  asset: SessionAsset | null
}>()

const emit = defineEmits<{
  close: []
}>()

const closeButton = ref<HTMLButtonElement | null>(null)
const action = computed(() => {
  if (!props.asset) return null
  return assetOpenAction(props.asset)
})
const imageUrl = computed(() => action.value?.kind === 'preview' && action.value.preview === 'image'
  ? action.value.url
  : null)
const previewsText = computed(() => action.value?.kind === 'preview' && action.value.preview === 'text')
const assetKindLabel = computed(() => props.asset?.mime_type || (previewsText.value ? 'Markdown text' : 'Image'))
let previousFocus: HTMLElement | null = null
let previousOverflow = ''
let pageLocked = false

function close(): void {
  emit('close')
}

function handleKeydown(event: KeyboardEvent): void {
  if (event.key !== 'Escape' || !props.asset) return
  event.preventDefault()
  close()
}

watch(
  () => props.asset,
  (asset) => {
    if (asset && !pageLocked) {
      previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null
      previousOverflow = document.body.style.overflow
      document.body.style.overflow = 'hidden'
      pageLocked = true
      void nextTick(() => closeButton.value?.focus())
      return
    }
    if (!asset && pageLocked) {
      document.body.style.overflow = previousOverflow
      pageLocked = false
      previousFocus?.focus()
      previousFocus = null
    }
  },
)

onMounted(() => window.addEventListener('keydown', handleKeydown))
onBeforeUnmount(() => {
  window.removeEventListener('keydown', handleKeydown)
  if (pageLocked) document.body.style.overflow = previousOverflow
  previousFocus?.focus()
})
</script>

<template>
  <Teleport to="body">
    <Transition name="image-preview">
      <div v-if="asset && action?.kind === 'preview'" class="image-preview-backdrop" @click.self="close">
        <section class="image-preview-panel" role="dialog" aria-modal="true" :aria-label="`Preview ${asset.name}`">
          <header>
            <div>
              <strong>{{ asset.name }}</strong>
              <small>{{ assetKindLabel }}</small>
            </div>
            <button ref="closeButton" type="button" aria-label="Close asset preview" title="Close" @click="close">
              <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18" /></svg>
            </button>
          </header>
          <div class="image-preview-stage" :class="{ 'text-preview-stage': previewsText }">
            <img v-if="imageUrl" :src="imageUrl" :alt="asset.name" />
            <MarkdownContent v-else-if="previewsText" class="asset-markdown" :content="asset.text_content || ''" />
          </div>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.image-preview-backdrop { position: fixed; inset: 0; z-index: 1100; display: grid; place-items: center; padding: clamp(.8rem, 2.5vw, 2rem); background: rgba(31, 38, 34, .3); backdrop-filter: blur(14px) saturate(115%); }
.image-preview-panel { display: grid; grid-template-rows: auto minmax(0, 1fr); width: min(94vw, 90rem); height: min(92vh, 64rem); overflow: hidden; border: 1px solid rgba(55, 70, 61, .14); border-radius: 1.15rem; background: rgba(250, 251, 250, .98); box-shadow: 0 34px 110px rgba(25, 36, 29, .25), 0 3px 12px rgba(25, 36, 29, .08); }
header { display: flex; align-items: center; justify-content: space-between; gap: 1rem; min-height: 4rem; padding: .72rem .8rem .72rem 1.15rem; border-bottom: 1px solid rgba(50, 65, 56, .1); background: rgba(255, 255, 255, .88); }
header div { min-width: 0; }
header strong, header small { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
header strong { color: #252b27; font-size: .86rem; font-weight: 670; }
header small { margin-top: .16rem; color: #858d88; font-size: .67rem; }
button { display: grid; place-items: center; width: 2.35rem; height: 2.35rem; flex: 0 0 auto; border: 0; border-radius: .72rem; color: #68716b; background: transparent; cursor: pointer; }
button:hover { color: #30483a; background: #edf2ef; }
button:focus-visible { outline: 3px solid rgba(71, 105, 87, .2); outline-offset: 2px; }
button svg { width: 1.15rem; height: 1.15rem; fill: none; stroke: currentColor; stroke-width: 1.8; stroke-linecap: round; }
.image-preview-stage { display: grid; place-items: center; min-height: 0; overflow: auto; padding: clamp(1rem, 3vw, 2.5rem); background-color: #f1f3f1; background-image: linear-gradient(45deg, rgba(77, 96, 85, .035) 25%, transparent 25%), linear-gradient(-45deg, rgba(77, 96, 85, .035) 25%, transparent 25%), linear-gradient(45deg, transparent 75%, rgba(77, 96, 85, .035) 75%), linear-gradient(-45deg, transparent 75%, rgba(77, 96, 85, .035) 75%); background-position: 0 0, 0 8px, 8px -8px, -8px 0; background-size: 16px 16px; }
.image-preview-stage img { display: block; max-width: 100%; max-height: 100%; object-fit: contain; border-radius: .3rem; box-shadow: 0 12px 38px rgba(33, 42, 36, .12); }
.text-preview-stage { display: block; padding: clamp(1.25rem, 3vw, 3rem); background: #fafbfa; }
.asset-markdown { width: min(100%, 72rem); min-height: 100%; margin: 0 auto; color: #29312c; font-size: clamp(.82rem, .76rem + .18vw, .98rem); }
.image-preview-enter-active, .image-preview-leave-active { transition: opacity 170ms ease; }
.image-preview-enter-active .image-preview-panel, .image-preview-leave-active .image-preview-panel { transition: transform 220ms cubic-bezier(.2, .8, .2, 1), opacity 170ms ease; }
.image-preview-enter-from, .image-preview-leave-to { opacity: 0; }
.image-preview-enter-from .image-preview-panel, .image-preview-leave-to .image-preview-panel { opacity: 0; transform: translateY(.5rem) scale(.985); }
@media (max-width: 640px) {
  .image-preview-backdrop { padding: .5rem; }
  .image-preview-panel { width: 100%; height: 96vh; border-radius: .9rem; }
}
@media (prefers-reduced-motion: reduce) {
  .image-preview-enter-active, .image-preview-leave-active, .image-preview-enter-active .image-preview-panel, .image-preview-leave-active .image-preview-panel { transition-duration: 1ms; }
}
</style>
