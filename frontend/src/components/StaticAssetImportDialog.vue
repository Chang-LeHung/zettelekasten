<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import type { StaticAsset } from '../api/types'
import { useI18n } from '../i18n'

const props = defineProps<{
  assets: StaticAsset[]
  loading: boolean
  importingId: string | null
  importedIds: string[]
}>()

const emit = defineEmits<{
  close: []
  import: [asset: StaticAsset]
}>()

const { t } = useI18n()
const query = ref('')
const closeButton = ref<HTMLButtonElement | null>(null)
let previousFocus: HTMLElement | null = null
let previousOverflow = ''

const visibleAssets = computed(() => {
  const needle = query.value.trim().toLowerCase()
  return needle
    ? props.assets.filter((asset) => asset.name.toLowerCase().includes(needle))
    : props.assets
})

function close(): void {
  emit('close')
}

function handleKeydown(event: KeyboardEvent): void {
  if (event.key !== 'Escape') return
  event.preventDefault()
  close()
}

function importAsset(asset: StaticAsset): void {
  if (props.importingId !== null || props.importedIds.includes(asset.id)) return
  emit('import', asset)
}

function extension(asset: StaticAsset): string {
  const suffix = asset.name.split('.').pop()
  if (suffix && suffix !== asset.name && suffix.length <= 5) return suffix.toUpperCase()
  return asset.mime_type?.startsWith('image/') ? 'IMG' : 'FILE'
}

function formatBytes(value: number): string {
  if (value < 1024) return `${value} B`
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`
  return `${(value / (1024 * 1024)).toFixed(1)} MB`
}

onMounted(() => {
  previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null
  previousOverflow = document.body.style.overflow
  document.body.style.overflow = 'hidden'
  window.addEventListener('keydown', handleKeydown)
  void nextTick(() => closeButton.value?.focus())
})

onBeforeUnmount(() => {
  document.body.style.overflow = previousOverflow
  window.removeEventListener('keydown', handleKeydown)
  previousFocus?.focus()
})
</script>

<template>
  <Teleport to="body">
    <div class="static-import-backdrop" @click.self="close">
      <section class="static-import-dialog" role="dialog" aria-modal="true" :aria-label="t('Import static asset')">
        <header>
          <div>
            <strong>{{ t('Import static asset') }}</strong>
            <small>{{ t('Files are referenced by URL and are not copied.') }}</small>
          </div>
          <button ref="closeButton" type="button" :aria-label="t('Close')" @click="close">×</button>
        </header>

        <div class="static-import-body">
          <label class="static-import-search">
            <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="6.5" /><path d="m16 16 4 4" /></svg>
            <input v-model="query" type="search" :placeholder="t('Search static assets')" />
          </label>

          <div v-if="loading" class="static-import-list" aria-label="Loading static assets">
            <div v-for="index in 5" :key="index" class="static-import-row skeleton" />
          </div>
          <div v-else-if="visibleAssets.length" class="static-import-list">
            <article v-for="asset in visibleAssets" :key="asset.id" class="static-import-row">
              <span class="static-import-thumb">
                <img v-if="asset.mime_type?.startsWith('image/')" :src="asset.content_url" :alt="asset.name" />
                <svg v-else viewBox="0 0 24 24" aria-hidden="true"><path d="M6 3h8l4 4v14H6zM14 3v5h5" /></svg>
                <small>{{ extension(asset) }}</small>
              </span>
              <span class="static-import-copy">
                <strong :title="asset.name">{{ asset.name }}</strong>
                <small>{{ asset.mime_type || t('File') }} · {{ formatBytes(asset.size_bytes) }}</small>
              </span>
              <button
                class="static-import-action"
                type="button"
                :disabled="importingId !== null || importedIds.includes(asset.id)"
                @click="importAsset(asset)"
              >
                {{ importedIds.includes(asset.id) ? t('Imported') : importingId === asset.id ? t('Importing…') : t('Import') }}
              </button>
            </article>
          </div>
          <div v-else class="static-import-empty">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m8.5 12.5 6.2-6.2a3 3 0 1 1 4.2 4.2l-8.1 8.1a5 5 0 0 1-7.1-7.1l8-8" /></svg>
            <strong>{{ t('No static assets available.') }}</strong>
          </div>
        </div>
      </section>
    </div>
  </Teleport>
</template>

<style scoped>
.static-import-backdrop { position: fixed; z-index: 1220; inset: 0; display: grid; place-items: center; padding: 1rem; background: rgba(29,36,32,.32); backdrop-filter: blur(12px); }
.static-import-dialog { display: grid; grid-template-rows: auto minmax(0,1fr); width: min(94vw, 42rem); max-height: min(86vh, 44rem); overflow: hidden; border: 1px solid rgba(55,70,61,.16); border-radius: .9rem; background: #fbfcfb; box-shadow: 0 1.5rem 4rem rgba(25,36,29,.24); }
header { min-height: 4.4rem; display: flex; align-items: center; justify-content: space-between; gap: 1rem; padding: .78rem .82rem .78rem 1.05rem; border-bottom: 1px solid #e1e6e3; background: #fff; }
header > div { min-width: 0; }
header strong, header small { display: block; }
header strong { color: #29332d; font-size: .86rem; }
header small { margin-top: .16rem; color: #7f8983; font-size: .64rem; }
header button { width: 2.15rem; height: 2.15rem; display: grid; place-items: center; padding: 0; border: 0; border-radius: .55rem; color: #68716b; background: transparent; cursor: pointer; font-size: 1.25rem; }
header button:hover { color: #30483a; background: #edf2ef; }
.static-import-body { min-height: 0; display: grid; grid-template-rows: auto minmax(0,1fr); gap: .72rem; padding: .85rem; }
.static-import-search { height: 2.6rem; display: flex; align-items: center; gap: .5rem; padding: 0 .72rem; border: 1px solid #dfe5e1; border-radius: .62rem; background: #fff; }
.static-import-search:focus-within { border-color: rgba(71,105,87,.45); box-shadow: 0 0 0 3px rgba(71,105,87,.08); }
.static-import-search svg { width: .9rem; height: .9rem; flex: 0 0 auto; fill: none; stroke: #87908a; stroke-width: 1.7; stroke-linecap: round; }
.static-import-search input { width: 100%; min-width: 0; border: 0; outline: 0; color: #303632; background: transparent; font-size: .72rem; }
.static-import-list { min-height: 0; display: grid; align-content: start; gap: .42rem; overflow-y: auto; padding-right: .15rem; scrollbar-width: thin; }
.static-import-row { min-width: 0; min-height: 3.7rem; display: flex; align-items: center; gap: .68rem; padding: .5rem .52rem; border: 1px solid #e1e6e3; border-radius: .68rem; background: #fff; }
.static-import-thumb { position: relative; width: 3.25rem; height: 2.65rem; flex: 0 0 auto; display: grid; place-items: center; overflow: hidden; border-radius: .52rem; color: #607269; background: #eef2ef; }
.static-import-thumb img { width: 100%; height: 100%; display: block; object-fit: cover; }
.static-import-thumb svg { width: 1.15rem; height: 1.15rem; fill: none; stroke: currentColor; stroke-width: 1.55; stroke-linecap: round; stroke-linejoin: round; }
.static-import-thumb small { position: absolute; right: .18rem; bottom: .15rem; padding: .08rem .18rem; border-radius: .22rem; color: #fff; background: #60796b; font-size: .43rem; font-weight: 700; }
.static-import-copy { min-width: 0; flex: 1; }
.static-import-copy strong, .static-import-copy small { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.static-import-copy strong { color: #303632; font-size: .72rem; }
.static-import-copy small { margin-top: .16rem; color: #87908a; font-size: .6rem; }
.static-import-action { min-width: 4.7rem; height: 1.95rem; flex: 0 0 auto; padding: 0 .62rem; border: 0; border-radius: .5rem; color: #fff; background: #547562; cursor: pointer; font-size: .62rem; font-weight: 650; }
.static-import-action:hover:not(:disabled) { background: #41614f; }
.static-import-action:disabled { color: #7f8983; background: #e9eeeb; cursor: default; }
.static-import-empty { min-height: 18rem; display: grid; place-items: center; align-content: center; gap: .6rem; border: 1px dashed #d9e1dc; border-radius: .72rem; color: #8a948e; background: #f7f9f7; }
.static-import-empty svg { width: 1.8rem; height: 1.8rem; fill: none; stroke: currentColor; stroke-width: 1.55; stroke-linecap: round; stroke-linejoin: round; }
.static-import-empty strong { color: #606b64; font-size: .74rem; }
.static-import-row.skeleton { min-height: 3.7rem; border: 0; background: linear-gradient(100deg, #eef1ef 30%, #f7f9f7 45%, #eef1ef 60%); background-size: 220% 100%; animation: import-shimmer 1.4s infinite linear; }
@keyframes import-shimmer { to { background-position-x: -220%; } }
@media (max-width: 640px) {
  .static-import-backdrop { padding: .5rem; }
  .static-import-dialog { width: 100%; max-height: 92vh; }
}
</style>
