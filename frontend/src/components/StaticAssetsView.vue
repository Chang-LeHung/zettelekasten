<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { assetClient } from '../api/client'
import type { StaticAsset } from '../api/types'
import { useI18n } from '../i18n'
import PdfThumbnail from './PdfThumbnail.vue'

const { t } = useI18n()
/**
 * The collection the sidebar selected. The tree belongs to this library, so the
 * grid filters by it: the parent owns the selection, this view owns the files.
 */
const props = defineProps<{ tagId?: string | null; tagPath?: string | null }>()
const emit = defineEmits<{ 'drag-start': [asset: StaticAsset]; 'drag-end': []; 'clear-tag': [] }>()
const assets = ref<StaticAsset[]>([])
const loading = ref(false)
const uploading = ref(false)
const dragging = ref(false)
const query = ref('')
const error = ref('')
const preview = ref<StaticAsset | null>(null)
const previewClose = ref<HTMLButtonElement | null>(null)
let previewTrigger: HTMLElement | null = null
const fileInput = ref<HTMLInputElement | null>(null)

const visibleAssets = computed(() => {
  const needle = query.value.trim().toLowerCase()
  return needle ? assets.value.filter((asset) => asset.name.toLowerCase().includes(needle)) : assets.value
})

function message(errorValue: unknown): string {
  return errorValue instanceof Error ? errorValue.message : t('Asset request failed')
}

async function loadAssets(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    assets.value = await assetClient.list('', 500, 0, props.tagId ?? null)
  } catch (errorValue) {
    error.value = message(errorValue)
  } finally {
    loading.value = false
  }
}

async function uploadFiles(files: File[]): Promise<void> {
  if (!files.length || uploading.value) return
  uploading.value = true
  error.value = ''
  try {
    for (const file of files) assets.value.unshift(await assetClient.upload(file))
  } catch (errorValue) {
    error.value = message(errorValue)
  } finally {
    uploading.value = false
  }
}

async function uploadInput(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  await uploadFiles(Array.from(input.files || []))
  input.value = ''
}

async function dropFiles(event: DragEvent): Promise<void> {
  dragging.value = false
  await uploadFiles(Array.from(event.dataTransfer?.files || []))
}

function pasteFiles(event: ClipboardEvent): void {
  const files = Array.from(event.clipboardData?.items || [])
    .filter((item) => item.kind === 'file')
    .map((item) => item.getAsFile())
    .filter((file): file is File => file !== null)
  if (!files.length) return
  event.preventDefault()
  void uploadFiles(files)
}

async function deleteAsset(asset: StaticAsset): Promise<void> {
  if (!window.confirm(t('Delete {name}?', { name: asset.name }))) return
  try {
    await assetClient.delete(asset.id)
    assets.value = assets.value.filter((item) => item.id !== asset.id)
    if (preview.value?.id === asset.id) preview.value = null
  } catch (errorValue) {
    error.value = message(errorValue)
  }
}

function openAsset(asset: StaticAsset): void {
  if (isImage(asset)) {
    previewTrigger = document.activeElement instanceof HTMLElement ? document.activeElement : null
    preview.value = asset
    void nextTick(() => previewClose.value?.focus())
    return
  }
  window.open(asset.content_url, '_blank', 'noopener,noreferrer')
}

function closePreview(): void {
  const trigger = previewTrigger
  preview.value = null
  previewTrigger = null
  void nextTick(() => trigger?.focus())
}

function handlePreviewKeydown(event: KeyboardEvent): void {
  if (preview.value && event.key === 'Escape') {
    event.preventDefault()
    closePreview()
  }
}

function downloadAsset(asset: StaticAsset): void {
  window.open(asset.content_url, '_blank', 'noopener,noreferrer')
}

function isImage(asset: StaticAsset): boolean {
  return Boolean(asset.mime_type?.startsWith('image/'))
}

function isPdf(asset: StaticAsset): boolean {
  return asset.mime_type === 'application/pdf' || asset.name.toLowerCase().endsWith('.pdf')
}

function extension(asset: StaticAsset): string {
  const suffix = asset.name.split('.').pop()
  if (suffix && suffix !== asset.name && suffix.length <= 5) return suffix.toUpperCase()
  return isImage(asset) ? 'IMG' : 'FILE'
}

function formatBytes(value: number): string {
  if (value < 1024) return `${value} B`
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`
  return `${(value / (1024 * 1024)).toFixed(1)} MB`
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat('en-US', { year: 'numeric', month: 'short', day: 'numeric' }).format(new Date(value))
}

/**
 * Hand the card to the sidebar's tag rows.
 *
 * The payload also travels in the drag data so a drop target outside this
 * component can see the id, and the event tells the parent which asset is in
 * flight: a `dragover` handler may inspect the drag's data types but never its
 * data, so the id alone is not enough while the pointer is still moving.
 */
function startCardDrag(asset: StaticAsset, event: DragEvent): void {
  if (event.dataTransfer) {
    event.dataTransfer.effectAllowed = 'copy'
    event.dataTransfer.setData('application/x-zett-asset-id', asset.id)
    event.dataTransfer.setData('text/plain', asset.id)
  }
  emit('drag-start', asset)
}

function endCardDrag(): void {
  emit('drag-end')
}

/** Highlight the drop area for files only: an internal card is not an upload. */
function handleDragEnter(event: DragEvent): void {
  if (event.dataTransfer?.types.includes('Files')) dragging.value = true
}

onMounted(() => {
  window.addEventListener('paste', pasteFiles)
  window.addEventListener('keydown', handlePreviewKeydown)
  void loadAssets()
})

// The sidebar owns the selection, so a change there reloads the filtered grid.
watch(() => props.tagId, () => void loadAssets())

onBeforeUnmount(() => {
  window.removeEventListener('paste', pasteFiles)
  window.removeEventListener('keydown', handlePreviewKeydown)
})

defineExpose({ reload: loadAssets })
</script>

<template>
  <header class="topbar compact">
    <div><p class="eyebrow">{{ t('Global library') }}</p><h1>{{ t('Static Assets') }}</h1></div>
    <button class="primary-action" type="button" :disabled="uploading" @click="fileInput?.click()">
      <span v-if="uploading" class="button-spinner" aria-hidden="true" />
      <svg v-else viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v14M5 12h14" /></svg>
      {{ uploading ? t('Uploading…') : t('Upload files') }}
    </button>
    <input ref="fileInput" type="file" multiple hidden @change="uploadInput" />
  </header>

  <section
    class="content static-assets-view"
    :class="{ dragging }"
    @dragenter.prevent="handleDragEnter"
    @dragover.prevent="handleDragEnter"
    @dragleave.prevent="dragging = false"
    @drop.prevent="dropFiles"
  >
    <div class="assets-toolbar">
      <label class="asset-search">
        <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="6.5" /><path d="m16 16 4 4" /></svg>
        <input v-model="query" type="search" :placeholder="t('Search files')" />
      </label>
      <button v-if="tagPath" class="asset-collection-filter" type="button" @click="emit('clear-tag')">
        <span>{{ t('Collection: {path}', { path: tagPath }) }}</span>
        <small>{{ t('Clear') }}</small>
      </button>
      <span>{{ visibleAssets.length === 1 ? t('{count} file', { count: visibleAssets.length }) : t('{count} files', { count: visibleAssets.length }) }}</span>
    </div>

    <p v-if="error" class="asset-error" role="alert">{{ error }}</p>

    <div v-if="loading" class="static-asset-grid" :aria-label="t('Loading assets')">
      <div v-for="index in 8" :key="index" class="static-asset-card skeleton" />
    </div>
    <div v-else-if="visibleAssets.length" class="static-asset-grid">
      <article
        v-for="asset in visibleAssets"
        :key="asset.id"
        class="static-asset-card"
        draggable="true"
        :title="t('Drag onto a tag to classify this file')"
        @dragstart="startCardDrag(asset, $event)"
        @dragend="endCardDrag"
      >
        <button class="static-asset-preview" type="button" :aria-label="t('Open {name}', { name: asset.name })" @click="openAsset(asset)">
          <img v-if="isImage(asset)" :src="asset.content_url" :alt="asset.name" />
          <PdfThumbnail v-else-if="isPdf(asset)" :asset="asset" />
          <span v-else class="static-asset-file-icon">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 3h8l4 4v14H6zM14 3v5h5" /></svg>
            <small>{{ extension(asset) }}</small>
          </span>
        </button>
        <div class="static-asset-copy">
          <strong :title="asset.name">{{ asset.name }}</strong>
          <span>{{ formatBytes(asset.size_bytes) }} · {{ formatDate(asset.created_at) }}</span>
          <div v-if="asset.tags.length" class="static-asset-tags">
            <span v-for="tag in asset.tags.slice(0, 2)" :key="tag.id" :title="tag.path">{{ tag.path }}</span>
          </div>
        </div>
        <div class="static-asset-actions">
          <button type="button" :aria-label="t('Download')" :title="t('Download')" @click="downloadAsset(asset)">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 4v11m-4-4 4 4 4-4M5 19h14" /></svg>
          </button>
          <button class="danger" type="button" :aria-label="t('Delete')" :title="t('Delete')" @click="deleteAsset(asset)">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16M9 7V4h6v3m3 0-1 13H7L6 7m4 4v5m4-5v5" /></svg>
          </button>
        </div>
      </article>
    </div>
    <div v-else class="static-asset-empty">
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m8.5 12.5 6.2-6.2a3 3 0 1 1 4.2 4.2l-8.1 8.1a5 5 0 0 1-7.1-7.1l8-8" /></svg>
      <strong>{{ tagPath ? t('No files in this collection') : t('No assets yet') }}</strong>
      <button v-if="tagPath" class="secondary-action" type="button" @click="emit('clear-tag')">{{ t('Clear filter') }}</button>
      <button v-else class="primary-action" type="button" @click="fileInput?.click()">{{ t('Upload files') }}</button>
    </div>
  </section>

  <Teleport to="body">
    <Transition name="zett-preview">
    <div v-if="preview" class="zett-preview-backdrop" @click.self="closePreview">
      <section class="zett-preview-dialog" role="dialog" aria-modal="true" :aria-label="t('Preview {name}', { name: preview.name })">
        <header class="zett-preview-header">
          <div class="zett-preview-title"><strong>{{ preview.name }}</strong><small>{{ extension(preview) }} · {{ formatBytes(preview.size_bytes) }}</small></div>
          <button ref="previewClose" class="zett-preview-close" type="button" :aria-label="t('Close')" @click="closePreview">×</button>
        </header>
        <div class="zett-preview-stage"><img :src="preview.content_url" :alt="preview.name" /></div>
      </section>
    </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.static-assets-view { position: relative; max-width: 74rem; }
.static-assets-view.dragging { border-radius: 1rem; outline: 2px dashed #74917f; outline-offset: -.75rem; background: #f3f7f4; }
.assets-toolbar { display: flex; align-items: center; justify-content: space-between; gap: 1rem; margin: .35rem 0 1.15rem; }
.assets-toolbar > span { color: var(--tertiary); font-size: .72rem; }
.asset-collection-filter { display: inline-flex; align-items: center; gap: .4rem; min-height: 2rem; padding: 0 .6rem; border: 1px solid rgba(78,111,91,.16); border-radius: .55rem; color: #3f604c; background: #edf3ef; cursor: pointer; font-size: .68rem; font-weight: 600; }
.asset-collection-filter small { color: #6c7f74; font-size: .6rem; }
.asset-collection-filter:hover { background: #e3ece7; }
.asset-search { width: min(100%, 25rem); height: 2.6rem; display: flex; align-items: center; gap: .5rem; padding: 0 .72rem; border: 1px solid rgba(29,29,31,.11); border-radius: .65rem; background: #fff; }
.asset-search:focus-within { border-color: rgba(71,105,87,.45); box-shadow: 0 0 0 3px rgba(71,105,87,.08); }
.asset-search svg { width: .9rem; height: .9rem; flex: 0 0 auto; fill: none; stroke: #87908a; stroke-width: 1.7; stroke-linecap: round; }
.asset-search input { width: 100%; border: 0; outline: 0; color: #303632; background: transparent; font-size: .72rem; }
.asset-error { margin: 0 0 1rem; padding: .7rem .85rem; border-radius: .65rem; color: #8b3f3f; background: #f9eded; font-size: .7rem; }
.static-asset-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 13rem), 1fr)); gap: .85rem; }
.static-asset-card { min-width: 0; overflow: hidden; border: 1px solid rgba(29,29,31,.08); border-radius: .8rem; background: #fff; box-shadow: 0 1px 3px rgba(25,34,29,.035); }
.static-asset-preview { width: 100%; aspect-ratio: 4 / 3; display: grid; place-items: center; padding: 0; overflow: hidden; border: 0; color: #56645b; background: #eef2ef; cursor: zoom-in; }
.static-asset-preview img { width: 100%; height: 100%; display: block; object-fit: cover; }
.static-asset-file-icon { display: grid; place-items: center; gap: .35rem; }
.static-asset-file-icon svg { width: 2.1rem; height: 2.1rem; fill: none; stroke: currentColor; stroke-width: 1.45; stroke-linecap: round; stroke-linejoin: round; }
.static-asset-file-icon small { font-size: .58rem; font-weight: 720; letter-spacing: .06em; }
.static-asset-copy { min-width: 0; display: grid; gap: .18rem; padding: .7rem .75rem .55rem; }
.static-asset-copy strong { overflow: hidden; color: #303632; font-size: .74rem; text-overflow: ellipsis; white-space: nowrap; }
.static-asset-copy span { color: #87908a; font-size: .62rem; }
.static-asset-card[draggable="true"] { cursor: grab; }
.static-asset-card[draggable="true"]:active { cursor: grabbing; }
.static-asset-copy .static-asset-tags { display: flex; flex-wrap: wrap; gap: .22rem; margin-top: .1rem; }
.static-asset-copy .static-asset-tags span { max-width: 100%; overflow: hidden; padding: .14rem .4rem; border-radius: .35rem; color: #3f604c; background: #e7f0ea; font-size: .58rem; text-overflow: ellipsis; white-space: nowrap; }
.static-asset-actions { display: flex; justify-content: flex-end; gap: .2rem; padding: 0 .55rem .55rem; }
.static-asset-actions button { display: grid; width: 1.8rem; height: 1.8rem; place-items: center; padding: 0; border: 0; border-radius: .45rem; color: #748078; background: transparent; cursor: pointer; }
.static-asset-actions button:hover { color: #315541; background: #e8efea; }
.static-asset-actions button.danger:hover { color: #9b3f3f; background: #f8eded; }
.static-asset-actions svg { width: .85rem; height: .85rem; fill: none; stroke: currentColor; stroke-width: 1.7; stroke-linecap: round; stroke-linejoin: round; }
.static-asset-empty { min-height: 22rem; display: grid; place-items: center; align-content: center; gap: .7rem; border: 1px dashed #d9e1dc; border-radius: .9rem; color: #8a948e; background: rgba(249,251,249,.72); }
.static-asset-empty > svg { width: 2rem; height: 2rem; fill: none; stroke: currentColor; stroke-width: 1.5; stroke-linecap: round; stroke-linejoin: round; }
.static-asset-empty strong { color: #606b64; font-size: .8rem; }
@media (max-width: 700px) {
  .assets-toolbar { align-items: stretch; flex-direction: column; }
  .asset-search { width: 100%; }
}
</style>
