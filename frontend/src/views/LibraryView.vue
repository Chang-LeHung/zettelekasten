<script setup lang="ts">
import { defineAsyncComponent } from 'vue'
import { libraryClient } from '../api/client'
import { openLibraryEditor } from '../app/artifacts/editor'
import { cardFloatDelay, formatDate, libraryExcerpt, stopCardKey } from '../app/format'
import { clearLibrarySelection, copyLibraryItemId, deleteLibraryItem, deleteSelectedLibraryItems, filterByArtifactType, filterByTag, onLibraryCardActivate, openLibraryPdf, openSlidesFullscreen, search, selectAllLibraryItems, setCardStatuses, setLibraryCardStatus, startLibraryMarquee, toggleLibrarySelection } from '../app/library/actions'
import { bulkDeleting, cardStatusUpdatingIds, deletingLibraryItemId, draggingLibraryItem, libraryGridKey, libraryHasMore, libraryItems, libraryLoading, libraryLoadingMore, libraryMarquee, libraryTypeFilters, pageDescription, pageTitle, query, selectedCardStatuses, selectedLibraryIds, selectedLibraryType, selectedTag, selectingLibrary } from '../app/library/state'
import { endLibraryItemDrag, startLibraryItemDrag } from '../app/library/tags'
import { view } from '../app/nav'
import { navigate, openArtifactSession } from '../app/workspace'
import CardStatusMark from '../components/CardStatusMark.vue'
import CardStatusMenu from '../components/CardStatusMenu.vue'
import LibraryStatusFilter from '../components/LibraryStatusFilter.vue'
import { statusTone } from '../utils/cardStatus'
import { presentationSections } from '../utils/slides'

const PdfThumbnail = defineAsyncComponent(() => import('../components/PdfThumbnail.vue'))
</script>

<template>
  <header class="topbar library-topbar">
    <form class="search-field" role="search" @submit.prevent="search">
      <svg><use href="#icon-search" /></svg>
      <input ref="searchInput" v-model="query" :aria-label="$t('search.placeholder')" :placeholder="$t('search.placeholder')" />
      <button v-if="query" type="button" :aria-label="$t('search.clear')" @click="query = ''; search()">×</button>
      <kbd v-else>⌘ K</kbd>
    </form>
    <button class="primary-action" type="button" @click="navigate('new')"><svg><use href="#icon-add" /></svg>{{ $t('search.newCard') }}</button>
  </header>

  <section class="content library-view" :class="{ selecting: selectingLibrary }" @pointerdown="startLibraryMarquee">
    <div class="page-heading">
      <div><p class="eyebrow">{{ $t('Your knowledge') }}</p><h1>{{ pageTitle }}</h1><p>{{ pageDescription }}</p></div>
      <button v-if="selectedTag !== null" class="text-button" type="button" @click="filterByTag(null)">Clear filter</button>
    </div>

    <div class="library-filter-bar">
      <div class="library-type-filters" aria-label="Artifact type filters">
        <span>{{ $t('Type') }}</span>
        <button
          v-for="filter in libraryTypeFilters"
          :key="filter.label"
          :class="{ active: selectedLibraryType === filter.value }"
          type="button"
          @click="filterByArtifactType(filter.value)"
        >{{ $t(filter.label) }}</button>
      </div>
      <LibraryStatusFilter
        v-if="selectedLibraryType === null || selectedLibraryType === 'card'"
        :model-value="selectedCardStatuses"
        @update:model-value="setCardStatuses"
      />
    </div>

    <!--
      Skeleton cards only stand in for a library that has nothing to show yet.
      Replacing an already loaded grid with placeholders made every filter
      click flash: with two results the other four shimmering slots appeared
      and vanished, which reads as the grid itself flickering.
    -->
    <div v-if="libraryLoading && !libraryItems.length" class="card-grid" aria-label="Loading artifacts">
      <div v-for="index in 6" :key="index" class="card skeleton" />
    </div>
    <div v-else-if="libraryItems.length" :key="libraryGridKey" class="card-grid" :aria-busy="libraryLoading">
      <article
        v-for="(item, index) in libraryItems"
        :key="`${item.item_type}-${item.id}`"
        class="card"
        :class="[`library-${item.item_type}`, item.card_status ? statusTone(item.card_status) : '', { dragging: draggingLibraryItem?.id === item.id, picked: selectedLibraryIds.has(item.id), picking: selectingLibrary }]"
        :style="{ animationDelay: cardFloatDelay(index) }"
        :data-library-id="item.id"
        role="button"
        tabindex="0"
        draggable="true"
        :aria-label="`Open ${item.title}`"
        :aria-selected="selectingLibrary ? selectedLibraryIds.has(item.id) : undefined"
        @click="onLibraryCardActivate(item, $event)"
        @keydown.enter="onLibraryCardActivate(item, $event)"
        @keydown.space.prevent="onLibraryCardActivate(item, $event)"
        @dragstart="startLibraryItemDrag(item, $event)"
        @dragend="endLibraryItemDrag"
      >
        <div class="card-topline">
          <button
            class="card-select"
            type="button"
            role="checkbox"
            :aria-checked="selectedLibraryIds.has(item.id)"
            :aria-label="`Select ${item.title}`"
            @click.stop="toggleLibrarySelection(item)"
            @keydown="stopCardKey"
          >
            <svg viewBox="0 0 20 20" aria-hidden="true"><path d="m5 10.5 3.2 3.2L15 7" /></svg>
          </button>
          <span class="card-type">{{ item.item_type === 'card' ? $t(item.card_type || 'card') : $t(item.item_type) }}</span>
          <div class="card-topline-actions">
            <button class="card-action-button" type="button" :aria-label="`Open conversation for ${item.title}`" title="Open source conversation" @click.stop="openArtifactSession(item)" @keydown="stopCardKey">
              <svg><use href="#icon-conversation" /></svg>
            </button>
            <button v-if="item.item_type === 'slides'" class="card-action-button" type="button" :aria-label="`Preview ${item.title} fullscreen`" title="Fullscreen preview" @click.stop="openSlidesFullscreen(item)" @keydown="stopCardKey">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M9 3H3v6m12-6h6v6M3 15v6h6m12-6v6h-6" /></svg>
            </button>
            <button v-if="item.item_type === 'latex_pdf'" class="card-action-button" type="button" :aria-label="`Preview ${item.title}`" title="Preview PDF" @click.stop="openLibraryPdf(item, 'expanded')" @keydown="stopCardKey">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M9 3H3v6m12-6h6v6M3 15v6h6m12-6v6h-6" /></svg>
            </button>
            <button v-if="item.item_type === 'latex_pdf'" class="card-action-button" type="button" :aria-label="`Present ${item.title}`" title="Present PDF" @click.stop="openLibraryPdf(item, 'presentation')" @keydown="stopCardKey">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="13" rx="2" /><path d="M12 17v4m-4 0h8M10 8l5 2.5-5 2.5Z" /></svg>
            </button>
            <button v-if="item.item_type !== 'latex_pdf'" class="card-action-button" type="button" :aria-label="`Edit ${item.title}`" title="Edit and preview" @click.stop="openLibraryEditor(item)" @keydown="stopCardKey">
              <svg><use href="#icon-edit" /></svg>
            </button>
            <button class="card-action-button card-copy-action" type="button" :aria-label="`Copy ID for ${item.title}`" title="Copy artifact ID" @click.stop="copyLibraryItemId(item)" @keydown="stopCardKey">
              <svg><use href="#icon-copy" /></svg>
            </button>
            <button class="card-action-button danger" :disabled="deletingLibraryItemId !== null || bulkDeleting" type="button" :aria-label="`Delete ${item.title}`" :title="deletingLibraryItemId === item.id ? 'Deleting…' : `Delete ${item.item_type}`" @click.stop="deleteLibraryItem(item)" @keydown="stopCardKey">
              <svg><use href="#icon-trash" /></svg>
            </button>
          </div>
        </div>
        <div v-if="item.card_status" class="card-title-row">
          <CardStatusMark :status="item.card_status" :busy="cardStatusUpdatingIds.has(item.id)" @select="setLibraryCardStatus(item, $event)" />
          <h2 :title="item.title">{{ item.title }}</h2>
        </div>
        <h2 v-else :title="item.title">{{ item.title }}</h2>
        <div v-if="item.item_type === 'latex_pdf'" class="library-pdf-thumbnail">
          <PdfThumbnail :asset="libraryClient.documentReference(item.id)" artifact fit="contain" />
        </div>
        <div v-if="item.item_type === 'slides'" class="library-deck-summary">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="4" width="18" height="13" rx="2" /><path d="M12 17v4m-4 0h8M8 9h8m-8 4h5" /></svg>
          <span>{{ $t('Presentation · {count} slides', { count: presentationSections(item.content).flat().length }) }}</span>
        </div>
        <p v-if="item.item_type !== 'latex_pdf'" class="card-excerpt">{{ libraryExcerpt(item) }}</p>
        <div class="card-footer">
          <div class="card-footer-info">
            <CardStatusMenu v-if="item.card_status" :status="item.card_status" :busy="cardStatusUpdatingIds.has(item.id)" @select="setLibraryCardStatus(item, $event)" />
            <div v-if="item.tags.length" class="card-tags"><span v-for="path in item.tags.slice(0, 2)" :key="path" :title="path">{{ path }}</span></div>
            <time>{{ formatDate(item.updated_at) }}</time>
          </div>
          <svg><use href="#icon-arrow" /></svg>
        </div>
      </article>
    </div>
    <div v-else class="empty-state">
      <span class="empty-icon"><svg><use :href="view === 'search' ? '#icon-search' : '#icon-cards'" /></svg></span>
      <h2>{{ view === 'search' ? $t('Nothing found') : $t('Your library is ready') }}</h2>
      <p>{{ view === 'search' ? $t('Try a different phrase or browse your collections.') : $t('Capture a thought and let AI shape it into a useful card, article, or slide deck.') }}</p>
      <button class="primary-action" type="button" @click="view === 'search' ? navigate('library') : navigate('new')">
        {{ view === 'search' ? $t('Browse library') : $t('Create your first card') }}
      </button>
    </div>
    <!--
      Observer anchor for the grid's next page. It stays outside the
      v-if/v-else chain above so the empty state keeps its place in it.
    -->
    <div v-if="libraryItems.length && libraryHasMore" ref="librarySentinel" class="library-more" role="status" aria-live="polite">
      <span v-if="libraryLoadingMore">{{ $t('Loading more…') }}</span>
    </div>

    <div v-if="libraryMarquee" class="library-marquee" aria-hidden="true" :style="{ left: `${libraryMarquee.left}px`, top: `${libraryMarquee.top}px`, width: `${libraryMarquee.right - libraryMarquee.left}px`, height: `${libraryMarquee.bottom - libraryMarquee.top}px` }" />

    <Transition name="bulk-bar">
      <div v-if="selectingLibrary" class="library-bulk-bar" role="toolbar" :aria-label="$t('Selected artifacts')">
        <strong class="bulk-count" aria-live="polite">{{ $t('{count} selected', { count: selectedLibraryIds.size }) }}</strong>
        <button type="button" class="bulk-secondary" :disabled="bulkDeleting || selectedLibraryIds.size === libraryItems.length" @click="selectAllLibraryItems">
          {{ libraryHasMore ? $t('Select all loaded') : $t('Select all') }}
        </button>
        <button type="button" class="bulk-secondary" :disabled="bulkDeleting" @click="clearLibrarySelection">{{ $t('Clear') }}</button>
        <button type="button" class="bulk-delete" :disabled="bulkDeleting" :aria-busy="bulkDeleting" @click="deleteSelectedLibraryItems">
          <span v-if="bulkDeleting" class="button-spinner" aria-hidden="true" />
          <svg v-else aria-hidden="true"><use href="#icon-trash" /></svg>
          {{ bulkDeleting ? $t('Deleting…') : $t('Delete') }}
        </button>
      </div>
    </Transition>
  </section>
</template>
