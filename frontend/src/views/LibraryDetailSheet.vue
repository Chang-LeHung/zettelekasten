<script setup lang="ts">
import { defineAsyncComponent } from 'vue'
import { libraryClient } from '../api/client'
import { openLibraryEditor } from '../app/artifacts/editor'
import { formatDateTime } from '../app/format'
import { copyLibraryItemId, deleteSelectedLibraryItem, setLibraryCardStatus } from '../app/library/actions'
import { cardStatusUpdatingIds, deletingLibraryItemId, selectedLibraryItem } from '../app/library/state'
import { openArtifactSession } from '../app/workspace'
import CardStatusMenu from '../components/CardStatusMenu.vue'
import { isStruck, statusTone } from '../utils/cardStatus'

const MarkdownContent = defineAsyncComponent(() => import('../components/MarkdownContent.vue'))
const PdfPreview = defineAsyncComponent(() => import('../components/PdfPreview.vue'))
const SlidesPreview = defineAsyncComponent(() => import('../components/SlidesPreview.vue'))
</script>

<template>
  <Transition name="sheet">
    <div v-if="selectedLibraryItem" class="detail-backdrop" @click.self="selectedLibraryItem = null">
      <aside class="detail-sheet" role="dialog" aria-modal="true" :aria-label="selectedLibraryItem.title">
        <header class="detail-header">
          <div><span class="card-type">{{ selectedLibraryItem.item_type === 'card' ? selectedLibraryItem.card_type : selectedLibraryItem.item_type }}</span><CardStatusMenu v-if="selectedLibraryItem.card_status" :status="selectedLibraryItem.card_status" :busy="cardStatusUpdatingIds.has(selectedLibraryItem.id)" @select="setLibraryCardStatus(selectedLibraryItem, $event)" /></div>
          <div class="detail-header-actions">
            <button class="detail-header-button" type="button" @click="openArtifactSession(selectedLibraryItem)"><svg><use href="#icon-conversation" /></svg>Conversation</button>
            <button class="detail-header-button" type="button" @click="copyLibraryItemId(selectedLibraryItem)"><svg><use href="#icon-copy" /></svg>Copy ID</button>
            <button v-if="selectedLibraryItem.item_type !== 'latex_pdf'" class="detail-header-button" type="button" @click="openLibraryEditor(selectedLibraryItem)"><svg><use href="#icon-edit" /></svg>Edit</button>
            <button class="detail-delete-button" :disabled="deletingLibraryItemId !== null" type="button" @click="deleteSelectedLibraryItem"><svg><use href="#icon-trash" /></svg>Delete</button>
            <button class="close-button" type="button" aria-label="Close resource details" @click="selectedLibraryItem = null">×</button>
          </div>
        </header>
        <div class="detail-content">
          <h1 :class="selectedLibraryItem.card_status ? [statusTone(selectedLibraryItem.card_status), { 'status-struck': isStruck(selectedLibraryItem.card_status) }] : undefined">{{ selectedLibraryItem.title }}</h1>
          <p v-if="selectedLibraryItem.item_type !== 'card' && selectedLibraryItem.subtitle" class="detail-subtitle">{{ selectedLibraryItem.subtitle }}</p>
          <MarkdownContent v-if="selectedLibraryItem.summary" class="detail-summary" :content="selectedLibraryItem.summary" />
          <div v-if="selectedLibraryItem.tags.length" class="detail-tags"><span v-for="path in selectedLibraryItem.tags" :key="path">{{ path }}</span></div>

          <section class="detail-section"><h2>{{ selectedLibraryItem.item_type === 'article' ? 'Article' : selectedLibraryItem.item_type === 'slides' ? 'Slide deck' : 'Content' }}</h2><PdfPreview v-if="selectedLibraryItem.item_type === 'latex_pdf'" :asset="libraryClient.documentReference(selectedLibraryItem.id)" artifact /><SlidesPreview v-else-if="selectedLibraryItem.item_type === 'slides'" :title="selectedLibraryItem.title" :content="selectedLibraryItem.content" /><MarkdownContent v-else class="detail-body" :content="selectedLibraryItem.content" /></section>
          <section v-if="selectedLibraryItem.raw_content" class="detail-section raw-section"><h2>Original input</h2><div class="detail-body">{{ selectedLibraryItem.raw_content }}</div></section>

          <dl class="detail-metadata">
            <div><dt>Type</dt><dd>{{ selectedLibraryItem.item_type }}</dd></div>
            <div><dt>Status</dt><dd>{{ selectedLibraryItem.status }}</dd></div>
            <div><dt>Created</dt><dd>{{ formatDateTime(selectedLibraryItem.created_at) }}</dd></div>
            <div><dt>Updated</dt><dd>{{ formatDateTime(selectedLibraryItem.updated_at) }}</dd></div>
            <div><dt>Artifact ID</dt><dd>{{ selectedLibraryItem.id }}</dd></div>
          </dl>
        </div>
      </aside>
    </div>
  </Transition>
</template>
