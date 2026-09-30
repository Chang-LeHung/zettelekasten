<script setup lang="ts">
import { computed, defineAsyncComponent, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { SessionAsset } from '../api/types'
import { assetOpenAction } from '../utils/assetOpen'

const MarkdownContent = defineAsyncComponent(() => import('./MarkdownContent.vue'))
const PdfPreview = defineAsyncComponent(() => import('./PdfPreview.vue'))

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
const pdfUrl = computed(() => action.value?.kind === 'preview' && action.value.preview === 'pdf'
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
    <Transition name="zett-preview">
      <div v-if="asset && action?.kind === 'preview'" class="zett-preview-backdrop" @click.self="close">
        <section class="zett-preview-dialog" role="dialog" aria-modal="true" :aria-label="`Preview ${asset.name}`">
          <header class="zett-preview-header">
            <div class="zett-preview-title">
              <strong>{{ asset.name }}</strong>
              <small>{{ assetKindLabel }}</small>
            </div>
            <button ref="closeButton" class="zett-preview-close" type="button" aria-label="Close asset preview" title="Close" @click="close">
              <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18" /></svg>
            </button>
          </header>
          <div class="zett-preview-stage" :class="{ 'text-preview-stage': previewsText, 'pdf-preview-stage': pdfUrl }">
            <img v-if="imageUrl" :src="imageUrl" :alt="asset.name" />
            <PdfPreview v-else-if="pdfUrl" :asset="asset" />
            <MarkdownContent v-else-if="previewsText" class="asset-markdown" :content="asset.text_content || ''" />
          </div>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
button svg { width: 1.15rem; height: 1.15rem; fill: none; stroke: currentColor; stroke-width: 1.8; stroke-linecap: round; }
.pdf-preview-stage { padding: 0; background: #e9ece7; }
.text-preview-stage { display: block; padding: clamp(1.25rem, 3vw, 3rem); background: #fafbfa; }
.asset-markdown { width: min(100%, 72rem); min-height: 100%; margin: 0 auto; color: #29312c; font-size: clamp(.82rem, .76rem + .18vw, .98rem); }
</style>
