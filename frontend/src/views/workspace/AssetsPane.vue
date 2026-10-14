<script setup lang="ts">
import { defineAsyncComponent } from 'vue'
import { assetDragging, assetEditorMode, assetFileInput, assetFilter, assetFilters, assetName, assetQuery, assetUploading, assetValue, assets, filteredAssets, openAsset, openStaticAssetImport, removeAsset, renameAsset, showAssetEditor, toggleAssetsPane } from '../../app/assets'
import { addInlineAsset, dropAssets, uploadAssets } from '../../app/assetsUpload'
import { assetExtension, assetSourceLabel, assetTypeLabel, classifyAsset, formatAssetDate, formatBytes } from '../../app/format'
import AssetRename from '../../components/AssetRename.vue'
import { isPdfAsset } from '../../utils/assetOpen'

const PdfThumbnail = defineAsyncComponent(() => import('../../components/PdfThumbnail.vue'))
</script>

<template>
  <aside class="assets-pane" aria-label="Session assets" tabindex="0">
    <header class="assets-header">
      <div><strong>{{ $t('Assets') }}</strong><small>{{ $t('Session resources') }}</small></div>
      <div class="assets-header-actions">
        <button type="button" :title="$t('Add text note')" :aria-label="$t('Add text note')" @click="showAssetEditor('text')"><svg><use href="#icon-text" /></svg></button>
        <button type="button" :title="$t('Add link')" :aria-label="$t('Add link')" @click="showAssetEditor('link')"><svg><use href="#icon-link" /></svg></button>
        <button type="button" :title="$t('Upload files')" :aria-label="$t('Upload files')" @click="assetFileInput?.click()"><svg><use href="#icon-attachment" /></svg></button>
        <button class="asset-import-action" type="button" :title="$t('Import static asset')" :aria-label="$t('Import static asset')" @click="openStaticAssetImport">
          <svg><use href="#icon-library-import" /></svg>
          <span>{{ $t('Import') }}</span>
        </button>
        <button class="asset-hide-action" type="button" :title="$t('Hide assets')" :aria-label="$t('Hide assets')" @click="toggleAssetsPane(true)">
          <svg><use href="#icon-eye-off" /></svg>
        </button>
      </div>
    </header>

    <div class="assets-search">
      <svg><use href="#icon-search" /></svg>
      <input v-model="assetQuery" type="search" :placeholder="$t('Search assets')" :aria-label="$t('Search assets')" />
    </div>

    <div class="asset-filter-list" :aria-label="$t('Asset type')">
      <button v-for="filter in assetFilters" :key="filter.value" :class="{ active: assetFilter === filter.value }" type="button" @click="assetFilter = filter.value">{{ $t(filter.label) }}</button>
    </div>

    <div class="asset-list-heading">
      <span>{{ filteredAssets.length === 1 ? $t('{count} asset', { count: filteredAssets.length }) : $t('{count} assets', { count: filteredAssets.length }) }}</span>
      <small>{{ $t('Newest') }}</small>
    </div>

    <form v-if="assetEditorMode !== 'closed'" class="asset-editor" @submit.prevent="addInlineAsset">
      <strong>{{ assetEditorMode === 'link' ? $t('Add a link') : $t('Add a note') }}</strong>
      <input v-model="assetName" :placeholder="assetEditorMode === 'link' ? $t('Link name') : $t('Note name')" />
      <textarea v-model="assetValue" :placeholder="assetEditorMode === 'link' ? 'https://…' : $t('Text content')" rows="3" />
      <div><button :disabled="assetUploading || !assetName.trim() || !assetValue.trim()" type="submit">{{ $t('Add asset') }}</button><button type="button" @click="assetEditorMode = 'closed'">{{ $t('Cancel') }}</button></div>
    </form>

    <div class="asset-browser">
      <div class="asset-browser-list">
        <article v-for="asset in filteredAssets" :key="asset.id" class="asset-row">
          <button class="asset-row-main" type="button" @click="openAsset(asset)">
            <span class="asset-thumbnail" :class="classifyAsset(asset)">
              <img v-if="asset.mime_type?.startsWith('image/') && (asset.source_url || asset.content_url)" :src="asset.source_url || asset.content_url || ''" alt="" />
              <PdfThumbnail v-else-if="isPdfAsset(asset)" :asset="asset" />
              <svg v-else><use :href="asset.asset_type === 'link' ? '#icon-link' : asset.asset_type === 'text' ? '#icon-text' : '#icon-attachment'" /></svg>
              <small>{{ assetExtension(asset) }}</small>
            </span>
            <span class="asset-row-copy">
              <strong>{{ asset.name }}</strong>
              <small>{{ assetTypeLabel(asset) }} · {{ assetSourceLabel(asset) || formatBytes(asset.size_bytes) }}</small>
              <time>{{ formatAssetDate(asset.created_at) }}</time>
            </span>
          </button>
          <button class="asset-delete" type="button" :aria-label="`Delete ${asset.name}`" @click="removeAsset(asset)"><svg><use href="#icon-trash" /></svg></button>
          <AssetRename :name="asset.name" :save="name => renameAsset(asset, name)" />
        </article>
        <div v-if="!filteredAssets.length" class="asset-empty">
          <svg><use :href="assets.length ? '#icon-search' : '#icon-attachment'" /></svg>
          <strong>{{ assets.length ? $t('No matching assets') : $t('No assets yet') }}</strong>
          <small>{{ assets.length ? $t('Try another search or filter.') : $t('Add reference material for this conversation.') }}</small>
        </div>
      </div>

      <button class="asset-drop-zone" :class="{ dragging: assetDragging }" type="button" @click="assetFileInput?.click()" @dragenter.prevent="assetDragging = true" @dragover.prevent="assetDragging = true" @dragleave.prevent="assetDragging = false" @drop.prevent="dropAssets">
        <svg><use href="#icon-attachment" /></svg>
        <strong>{{ assetUploading ? 'Uploading…' : $t('Drop or paste assets here') }}</strong>
        <small>{{ $t('Click this area, then press Ctrl/⌘ + V') }}</small>
      </button>
    </div>
    <input ref="assetFileInput" type="file" multiple hidden @change="uploadAssets" />
  </aside>
</template>
