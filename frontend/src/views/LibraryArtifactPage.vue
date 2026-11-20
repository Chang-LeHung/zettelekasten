<script setup lang="ts">
import { defineAsyncComponent, nextTick, onMounted, ref } from 'vue'
import { libraryClient } from '../api/client'
import { openLibraryEditor } from '../app/artifacts/editor'
import { formatDateTime } from '../app/format'
import { copyLibraryItemId, deleteSelectedLibraryItem, setLibraryCardStatus } from '../app/library/actions'
import { cardStatusUpdatingIds, deletingLibraryItemId, selectedLibraryItem } from '../app/library/state'
import { openArtifactSession } from '../app/workspace'
import CardStatusMenu from '../components/CardStatusMenu.vue'
import { isStruck, statusTone } from '../utils/cardStatus'

const back = ref<HTMLButtonElement | null>(null)
onMounted(() => { void nextTick(() => back.value?.focus()) })

const MarkdownContent = defineAsyncComponent(() => import('../components/MarkdownContent.vue'))
const PdfPreview = defineAsyncComponent(() => import('../components/PdfPreview.vue'))
const SlidesPreview = defineAsyncComponent(() => import('../components/SlidesPreview.vue'))
</script>

<template>
  <section v-if="selectedLibraryItem" class="artifact-page" :class="`is-${selectedLibraryItem.item_type}`" :aria-label="selectedLibraryItem.title">
    <header class="artifact-page-bar">
      <button ref="back" class="artifact-page-back" type="button" @keydown.esc="selectedLibraryItem = null" @click="selectedLibraryItem = null">← {{ $t('Artifacts') }}</button>
      <span class="card-type">{{ selectedLibraryItem.item_type === 'card' ? selectedLibraryItem.card_type : selectedLibraryItem.item_type }}</span>
      <CardStatusMenu v-if="selectedLibraryItem.card_status" :status="selectedLibraryItem.card_status" :busy="cardStatusUpdatingIds.has(selectedLibraryItem.id)" @select="setLibraryCardStatus(selectedLibraryItem, $event)" />
      <div class="artifact-page-actions">
        <button class="detail-header-button" type="button" @click="openArtifactSession(selectedLibraryItem)"><svg><use href="#icon-conversation" /></svg>{{ $t('Conversation') }}</button>
        <button v-if="selectedLibraryItem.item_type !== 'latex_pdf'" class="detail-header-button" type="button" @click="openLibraryEditor(selectedLibraryItem)"><svg><use href="#icon-edit" /></svg>{{ $t('Edit') }}</button>
        <button class="detail-header-button" type="button" @click="copyLibraryItemId(selectedLibraryItem)"><svg><use href="#icon-copy" /></svg>{{ $t('Copy ID') }}</button>
        <button class="detail-delete-button" :disabled="deletingLibraryItemId !== null" type="button" @click="deleteSelectedLibraryItem"><svg><use href="#icon-trash" /></svg>{{ $t('Delete') }}</button>
      </div>
    </header>

    <div class="artifact-page-body">
      <h1 :class="selectedLibraryItem.card_status ? [statusTone(selectedLibraryItem.card_status), { 'status-struck': isStruck(selectedLibraryItem.card_status) }] : undefined">{{ selectedLibraryItem.title }}</h1>
      <p v-if="selectedLibraryItem.item_type !== 'card' && selectedLibraryItem.subtitle" class="detail-subtitle">{{ selectedLibraryItem.subtitle }}</p>
      <MarkdownContent v-if="selectedLibraryItem.summary" class="detail-summary" :content="selectedLibraryItem.summary" />
      <div v-if="selectedLibraryItem.tags.length" class="detail-tags"><span v-for="path in selectedLibraryItem.tags" :key="path">{{ path }}</span></div>

      <div class="artifact-stage">
        <PdfPreview v-if="selectedLibraryItem.item_type === 'latex_pdf'" :key="selectedLibraryItem.id" :asset="libraryClient.documentReference(selectedLibraryItem.id)" artifact />
        <SlidesPreview v-else-if="selectedLibraryItem.item_type === 'slides'" :title="selectedLibraryItem.title" :content="selectedLibraryItem.content" />
        <MarkdownContent v-else class="detail-body" :content="selectedLibraryItem.content" />
      </div>

      <details v-if="selectedLibraryItem.raw_content" class="artifact-more"><summary>{{ $t('Original input') }}</summary><div class="detail-body">{{ selectedLibraryItem.raw_content }}</div></details>
      <details class="artifact-more">
        <summary>{{ $t('Details') }}</summary>
        <dl class="detail-metadata">
          <div><dt>{{ $t('Type') }}</dt><dd>{{ selectedLibraryItem.item_type }}</dd></div>
          <div><dt>{{ $t('Status') }}</dt><dd>{{ selectedLibraryItem.status }}</dd></div>
          <div><dt>{{ $t('Created') }}</dt><dd>{{ formatDateTime(selectedLibraryItem.created_at) }}</dd></div>
          <div><dt>{{ $t('Updated') }}</dt><dd>{{ formatDateTime(selectedLibraryItem.updated_at) }}</dd></div>
          <div><dt>{{ $t('Artifact ID') }}</dt><dd>{{ selectedLibraryItem.id }}</dd></div>
        </dl>
      </details>
    </div>
  </section>
</template>

<style scoped>
.artifact-page { display: flex; flex-direction: column; min-height: 100%; }
.artifact-page-bar { position: sticky; top: 0; z-index: 3; display: flex; align-items: center; gap: .65rem; min-height: 3.6rem; padding: 0 clamp(.8rem, 2vw, 1.6rem); border-bottom: 1px solid #e7ebe8; background: rgba(250, 251, 250, .9); backdrop-filter: saturate(1.4) blur(14px); }
.artifact-page-back { padding: .38rem .8rem; border: 0; border-radius: .6rem; color: #3d5145; background: #e8eeea; font-size: .74rem; font-weight: 640; cursor: pointer; }
.artifact-page-back:hover { background: #dce6df; }
.artifact-page-actions { display: flex; align-items: center; gap: .3rem; margin-left: auto; }
.artifact-page-body { width: min(100%, 60rem); margin: 0 auto; padding: 1.6rem clamp(.9rem, 2.4vw, 2rem) 4rem; }
.artifact-page.is-latex_pdf .artifact-page-body { width: min(100%, 84rem); }
.artifact-page-body > h1 { margin: .2rem 0 .7rem; font-size: clamp(1.7rem, 3vw, 2.3rem); line-height: 1.12; letter-spacing: -.035em; }
.artifact-stage { margin-top: 1.3rem; }
.artifact-page.is-latex_pdf .artifact-stage { height: min(78vh, 60rem); min-height: 26rem; border: 1px solid #e4e9e5; border-radius: .9rem; overflow: hidden; }
.artifact-more { margin-top: 1.4rem; padding-top: .9rem; border-top: 1px solid #e7ebe8; color: #6d7570; font-size: .78rem; }
.artifact-more summary { cursor: pointer; font-weight: 640; }
</style>
