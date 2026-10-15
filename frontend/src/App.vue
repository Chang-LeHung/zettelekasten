<script setup lang="ts">
import { defineAsyncComponent } from 'vue'
import { closeLibraryEditor, saveLibraryEditor } from './app/artifacts/editor'
import { importedStaticAssetIds, previewAsset, staticAssetImportOpen, staticAssetImportingId, staticAssets, staticAssetsLoading } from './app/assets'
import { importStaticAsset } from './app/assetsUpload'
import { deleteTag, filterByTag } from './app/library/actions'
import { collectionTags, libraryEditorArtifactId, libraryEditorItem, libraryEditorSaving, selectedTag, selectedTagName, tagManagerBusy, tagManagerFeedback, tagManagerFeedbackKind, tagManagerOpen } from './app/library/state'
import { createTag, endStaticAssetDrag, startStaticAssetDrag } from './app/library/tags'
import { view } from './app/nav'
import { confirmation, settleConfirmation } from './app/notice'
import { openScheduledSession } from './app/workspace'
import AssetPreviewDialog from './components/AssetPreviewDialog.vue'
import ConfirmDialog from './components/ConfirmDialog.vue'
import TagManagerDialog from './components/TagManagerDialog.vue'
import AppSidebar from './views/AppSidebar.vue'
import AppToast from './views/AppToast.vue'
import LibraryDetailSheet from './views/LibraryDetailSheet.vue'
import LibraryPdfLaunch from './views/LibraryPdfLaunch.vue'
import LibrarySlidesFullscreen from './views/LibrarySlidesFullscreen.vue'
import LibraryView from './views/LibraryView.vue'
import SettingsDialog from './views/SettingsDialog.vue'
import WorkspaceView from './views/WorkspaceView.vue'
import { useAppLifecycle } from './app/lifecycle'

const ChannelsView = defineAsyncComponent(() => import('./components/ChannelsView.vue'))
const LibraryEditor = defineAsyncComponent(() => import('./components/LibraryEditor.vue'))
const ScheduledTasksView = defineAsyncComponent(() => import('./components/ScheduledTasksView.vue'))
const StaticAssetImportDialog = defineAsyncComponent(() => import('./components/StaticAssetImportDialog.vue'))
const StaticAssetsView = defineAsyncComponent(() => import('./components/StaticAssetsView.vue'))

useAppLifecycle()
</script>

<template>
  <div class="app-shell">
    <svg class="icon-library" aria-hidden="true">
      <symbol id="icon-cards" viewBox="0 0 24 24"><rect x="4" y="4" width="16" height="16" rx="3"/><path d="M8 9h8M8 13h5"/></symbol>
      <symbol id="icon-search" viewBox="0 0 24 24"><circle cx="11" cy="11" r="6.5"/><path d="m16 16 4 4"/></symbol>
      <symbol id="icon-add" viewBox="0 0 24 24"><path d="M12 5v14M5 12h14"/></symbol>
      <symbol id="icon-settings" viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path d="M19 13.5v-3l-2.1-.5a7 7 0 0 0-.7-1.7l1.1-1.8-2.1-2.1-1.8 1.1a7 7 0 0 0-1.7-.7L11.2 3h-3l-.5 2.1a7 7 0 0 0-1.7.7L4.2 4.7 2.1 6.8l1.1 1.8a7 7 0 0 0-.7 1.7L.5 10.8v3l2.1.5a7 7 0 0 0 .7 1.7l-1.1 1.8 2.1 2.1 1.8-1.1a7 7 0 0 0 1.7.7l.5 2.1h3l.5-2.1a7 7 0 0 0 1.7-.7l1.8 1.1 2.1-2.1-1.1-1.8a7 7 0 0 0 .7-1.7z" transform="translate(1.5 -0.25) scale(.88)"/></symbol>
      <symbol id="icon-schedule" viewBox="0 0 24 24"><circle cx="12" cy="13" r="8"/><path d="M12 9v4l3 2M8 3h8M5 6l-2 2m16-2 2 2"/></symbol>
      <symbol id="icon-channels" viewBox="0 0 24 24"><circle cx="12" cy="12" r="1.5"/><path d="M5.6 5.6a9 9 0 0 0 0 12.8M18.4 5.6a9 9 0 0 1 0 12.8M8.5 8.5a5 5 0 0 0 0 7M15.5 8.5a5 5 0 0 1 0 7"/></symbol>
      <symbol id="icon-spark" viewBox="0 0 24 24"><path d="m12 2 1.3 5.1L18 9l-4.7 1.9L12 16l-1.3-5.1L6 9l4.7-1.9zM19 15l.7 2.3L22 18l-2.3.7L19 21l-.7-2.3L16 18l2.3-.7z"/></symbol>
      <symbol id="icon-arrow" viewBox="0 0 24 24"><path d="M5 12h14m-5-5 5 5-5 5"/></symbol>
      <symbol id="icon-stop" viewBox="0 0 24 24"><rect x="7" y="7" width="10" height="10" rx="1.5"/></symbol>
      <symbol id="icon-check" viewBox="0 0 24 24"><path d="m5 12 4 4L19 6"/></symbol>
      <symbol id="icon-user" viewBox="0 0 24 24"><circle cx="12" cy="8" r="3.5"/><path d="M5.5 20c.6-4 2.8-6 6.5-6s5.9 2 6.5 6"/></symbol>
      <symbol id="icon-attachment" viewBox="0 0 24 24"><path d="m8.5 12.5 6.2-6.2a3 3 0 0 1 4.2 4.2l-8.1 8.1a5 5 0 0 1-7.1-7.1l8-8"/></symbol>
      <symbol id="icon-link" viewBox="0 0 24 24"><path d="M10 13a5 5 0 0 0 7.5.5l2-2a5 5 0 0 0-7-7l-1.1 1.1M14 11a5 5 0 0 0-7.5-.5l-2 2a5 5 0 0 0 7 7l1.1-1.1"/></symbol>
      <symbol id="icon-text" viewBox="0 0 24 24"><path d="M5 6h14M12 6v13M8 19h8"/></symbol>
      <symbol id="icon-library-import" viewBox="0 0 24 24"><path d="M4 4h5v16H4zM11 4h5v16h-5zM18.5 8v8M22.5 12h-8"/></symbol>
      <symbol id="icon-trash" viewBox="0 0 24 24"><path d="M4 7h16M9 7V4h6v3m3 0-1 13H7L6 7m4 4v5m4-5v5"/></symbol>
      <symbol id="icon-edit" viewBox="0 0 24 24"><path d="m4 20 4.2-1 10.7-10.7a2.1 2.1 0 0 0-3-3L5.2 16zM14.7 6.5l3 3"/></symbol>
      <symbol id="icon-copy" viewBox="0 0 24 24"><rect x="8" y="8" width="11" height="11" rx="2"/><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/></symbol>
      <symbol id="icon-conversation" viewBox="0 0 24 24"><path d="M5 5.5h14a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H10l-5 3v-3H5a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2Z"/><path d="M8 10h8M8 13h5"/></symbol>
      <symbol id="icon-eye" viewBox="0 0 24 24"><path d="M2.5 12s3.5-6 9.5-6 9.5 6 9.5 6-3.5 6-9.5 6-9.5-6-9.5-6Z"/><circle cx="12" cy="12" r="2.5"/></symbol>
      <symbol id="icon-eye-off" viewBox="0 0 24 24"><path d="M3 3l18 18M10.6 6.1A9.8 9.8 0 0 1 12 6c6 0 9.5 6 9.5 6a16.4 16.4 0 0 1-2.1 3M6.2 6.2C3.8 7.8 2.5 12 2.5 12s3.5 6 9.5 6c1.2 0 2.3-.3 3.3-.7M10.2 10.2a2.5 2.5 0 0 0 3.6 3.6"/></symbol>
      <symbol id="icon-refresh" viewBox="0 0 24 24"><path d="M20 12a8 8 0 1 1-2.3-5.7M20 4v5h-5"/></symbol>
      <symbol id="icon-download" viewBox="0 0 24 24"><path d="M12 4v9m0 0 3.5-3.5M12 13 8.5 9.5M5 19h14"/></symbol>
    </svg>

    <AppSidebar />

    <main class="workspace">
      <AppToast />

      <ConfirmDialog :open="confirmation.open" :title="confirmation.title" :message="confirmation.message" :confirm-label="confirmation.confirmLabel" @cancel="settleConfirmation(false)" @confirm="settleConfirmation(true)" />
      <TagManagerDialog v-if="tagManagerOpen" :tags="collectionTags" :busy="tagManagerBusy" :feedback="tagManagerFeedback" :feedback-kind="tagManagerFeedbackKind" @close="tagManagerOpen = false" @create="createTag" @delete="deleteTag" />
      <AssetPreviewDialog :asset="previewAsset" @close="previewAsset = null" />
      <StaticAssetImportDialog
        v-if="staticAssetImportOpen"
        :assets="staticAssets"
        :loading="staticAssetsLoading"
        :importing-id="staticAssetImportingId"
        :imported-ids="importedStaticAssetIds"
        @close="staticAssetImportOpen = false"
        @import="importStaticAsset"
      />
      <LibraryEditor
        v-if="libraryEditorItem"
        :item="libraryEditorItem"
        :saving="libraryEditorSaving"
        :save-label="libraryEditorArtifactId !== null ? $t('Save draft') : $t('Save')"
        @close="closeLibraryEditor"
        @save="saveLibraryEditor"
      />

      <LibraryView v-if="view === 'library' || view === 'search'" />

      <WorkspaceView v-else-if="view === 'new'" />

      <template v-else-if="view === 'assets'">
        <StaticAssetsView
          ref="staticAssetsView"
          :tag-id="selectedTag"
          :tag-path="selectedTagName ?? null"
          @drag-start="startStaticAssetDrag"
          @drag-end="endStaticAssetDrag"
          @clear-tag="filterByTag(null)"
        />
      </template>

      <template v-else-if="view === 'scheduledTasks'">
        <ScheduledTasksView @open-session="openScheduledSession" />
      </template>

      <template v-else-if="view === 'channels'">
        <ChannelsView />
      </template>

      <SettingsDialog />

      <LibrarySlidesFullscreen />
      <LibraryPdfLaunch />
      <LibraryDetailSheet />
    </main>
  </div>
</template>
<style src="./styles/app/index.css"></style>
