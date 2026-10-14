<script setup lang="ts">
import { defineAsyncComponent } from 'vue'
import { libraryClient } from './api/client'
import AgentComposerControls from './components/AgentComposerControls.vue'
import ArtifactDiffView from './components/ArtifactDiffView.vue'
import ComposerCommandMenu from './components/ComposerCommandMenu.vue'
import CacheHitRate from './components/CacheHitRate.vue'
import ConfirmDialog from './components/ConfirmDialog.vue'
import TagManagerDialog from './components/TagManagerDialog.vue'
import AssetPreviewDialog from './components/AssetPreviewDialog.vue'
import AssetRename from './components/AssetRename.vue'
import AskUserPrompt from './components/AskUserPrompt.vue'
import ShellApprovalPrompt from './components/ShellApprovalPrompt.vue'
import BlockEditor from './components/BlockEditor.vue'
import LibraryStatusFilter from './components/LibraryStatusFilter.vue'
import CardStatusMark from './components/CardStatusMark.vue'
import CardStatusMenu from './components/CardStatusMenu.vue'
import AgentExecution from './components/AgentExecution.vue'
import UsageActivityGraph from './components/UsageActivityGraph.vue'
import { artifactEditableContent } from './utils/artifactEditor'
import { artifactLifecycle, lifecycleClass, lifecycleHint, lifecycleLabel } from './utils/artifactLifecycle'
import { cardStatusLabel, cardStatusType, isStruck, statusTone } from './utils/cardStatus'
import { isPdfAsset } from './utils/assetOpen'
import { providerBaseUrlHelp, providerIgnoresTemperature } from './utils/providerDefaults'
import { presentationSections } from './utils/slides'
import { artifactListExcerpt, artifactListImage } from './utils/artifactListPresentation'
import { artifactTone } from './utils/artifactTone'
import { MIN_ARTIFACT_LIST_HEIGHT } from './utils/artifactSplit'
import { bulkDeleting, cardStatusUpdatingIds, cardTypes, collapsedTagIds, collectionTags, deletingLibraryItemId, draggingLibraryItem, flatTags, fullscreenSlidesItem, hoveredTagId, libraryEditorArtifactId, libraryEditorItem, libraryEditorSaving, libraryGridKey, libraryHasMore, libraryItems, libraryLoading, libraryLoadingMore, libraryMarquee, libraryPdfLaunch, librarySentinel, librarySlidesStage, libraryTotal, libraryTypeFilters, pageDescription, pageTitle, query, searchInput, selectedCardStatuses, selectedLibraryIds, selectedLibraryItem, selectedLibraryType, selectedTag, selectedTagName, selectingLibrary, tagAssignmentBusy, tagDropTargetId, tagManagerBusy, tagManagerFeedback, tagManagerFeedbackKind, tagManagerOpen } from './app/library/state'
import { clearLibrarySelection, closeSlidesFullscreen, copyLibraryItemId, deleteLibraryItem, deleteSelectedLibraryItem, deleteSelectedLibraryItems, deleteTag, filterByArtifactType, filterByTag, onLibraryCardActivate, openLibraryPdf, openSlidesFullscreen, search, selectAllLibraryItems, setCardStatuses, setLibraryCardStatus, startLibraryMarquee, toggleLibrarySelection } from './app/library/actions'
import { view } from './app/nav'
import { atCommandsLoaded, atCommandsLoading, atMenu, atMenuActiveIndex, atMenuItems, composerComposing, followUp, followUpComposerHighlight, followUpComposerInput, initialComposerHighlight, initialComposerInput, pendingMessageImages, raw, slashCommands, slashCommandsLoaded, slashCommandsLoading, slashMenu, slashMenuActiveIndex, slashMenuItems } from './app/composer/state'
import { artifactContent, artifactDiff, artifactHeaderRef, artifactListHeight, artifactPaneRef, artifactPreview, artifactPreviewAsset, artifactRefreshing, artifacts, artifactsNeedingSave, saving, savingAllArtifacts, selectedArtifact, selectedArtifactDiff, selectedArtifactDirty, selectedArtifactId, selectedImageUrl, selectedSuggestions, workspaceRestoring } from './app/artifacts/state'
import { activeTodos, agentThread, agentTurnStack, answeringQuestion, askAnswer, askUserImages, canSubmitMessage, contextComposition, conversation, conversationStarted, conversationTurns, conversationUsage, currentContextUsage, draggingQueuedFollowUpId, loading, pendingQuestion, pendingShellApprovals, queuedFollowUps, queuedQuestions, selectedAskOptions, shellApprovalSubmittingIds, steeringQueuedFollowUpId } from './app/conversation/state'
import { loadInteractionTrace, selectedTraceTurnId, setWorkspaceView, traceError, traceLoading, traceMessages, updateTraceTurn, workspaceView } from './app/conversation/trace'
import { activeSessionsLoading, activeSessionsPending, cancelSessionTitleEdit, conversationId, editingSessionId, handleSessionListScroll, handleSessionTitleFocusOut, saveSessionTitle, sessionListRef, sessionScope, sessionTitleDraft, startSessionTitleEdit, switchingSessionId, visibleSessions } from './app/sessions'
import { assetDragging, assetEditorMode, assetFileInput, assetFilter, assetFilters, assetName, assetQuery, assetUploading, assetValue, assets, assetsPaneHidden, filteredAssets, importedStaticAssetIds, openAsset, openImagePreview, openMessageImage, openStaticAssetImport, pdfPreviewRef, previewAsset, removeAsset, renameAsset, showAssetEditor, staticAssetImportOpen, staticAssetImportingId, staticAssets, staticAssetsLoading, staticAssetsView, toggleAssetsPane } from './app/assets'
import { confirmation, notice, noticeKind, settleConfirmation } from './app/notice'
import { ai, apiKeyVisible, editingProviderId, newProvider, providerLoading, providerSaving, providers, reasoningEffort, removeProvider, saveAI, selectProvider, selectProviderKind, selectedProviderId, setResponseMode, shellApprovalMode } from './app/providers'
import { agentPermissionSaving, agentPermissions, changeLocale, closeSettings, maxAssetSizeMb, modelUsageActivity, runtimeSettings, runtimeSettingsSaving, saveRuntimeSettings, selectSettingsSection, setAgentPermission, settingsDialog, settingsOpen, settingsSection, usageActivity, usageActivityLoading } from './app/settings'
import { installAvailableUpdate, restartZett, updateInstalling, updateRestarting, updateStatus } from './app/updates'
import { finishComposerComposition, followUpTokenHighlight, handleComposerSelection, initialTokenHighlight, removeMessageImage, selectAtCommand, selectSlashCommand, syncComposerHighlight, updateComposerText } from './app/composer/actions'
import { artifactTitle, assetExtension, assetSourceLabel, assetTypeLabel, cardFloatDelay, classifyAsset, formatAssetDate, formatBytes, formatDate, formatDateTime, libraryExcerpt, stopCardKey } from './app/format'
import { deleteSelectedArtifact, endArtifactSplit, keyArtifactSplit, moveArtifactSplit, refreshSelectedArtifact, saveAllArtifacts, saveSelectedArtifact, selectArtifact, setConversationCardStatus, startArtifactSplit } from './app/artifacts/actions'
import { handleAgentThreadScroll, handleAgentThreadWheel, isRunningTurn, isSteeredTurn, isTurnDetailsOpen, toggleTurnExecution, turnAnswerTimeline, turnCacheHitRate, turnDuration, turnExecutionTimeline, turnTask } from './app/conversation/stream'
import { answerAgentQuestion, attachAskUserImages, removeAskUserImage, respondToShellApproval, toggleAskOption, updateAskAnswer, updateShellApprovalMode } from './app/conversation/askUser'
import { createTag, dropResourceOnTag, endLibraryItemDrag, endStaticAssetDrag, handleTagDragLeave, handleTagDragOver, openTagManager, startLibraryItemDrag, startStaticAssetDrag, toggleTag } from './app/library/tags'
import { deleteSession, navigate, openArtifactSession, openScheduledSession, openSession, prefetchSession, resetWorkspace } from './app/workspace'
import { closeLibraryEditor, editArtifactFromList, openLibraryEditor, saveLibraryEditor } from './app/artifacts/editor'
import { handleComposerKeydown, refine, stopGeneration, submitConversation } from './app/conversation/turns'
import { dropQueuedFollowUp, endQueuedFollowUpDrag, queuedFollowUpText, removeQueuedFollowUp, startQueuedFollowUpDrag, steerQueuedFollowUp } from './app/conversation/queue'
import { addInlineAsset, dropAssets, importStaticAsset, pasteAssets, uploadAssets } from './app/assetsUpload'
import { t, locale } from './app/i18n'
import { useAppLifecycle } from './app/lifecycle'

const MarkdownContent = defineAsyncComponent(() => import('./components/MarkdownContent.vue'))
const LibraryEditor = defineAsyncComponent(() => import('./components/LibraryEditor.vue'))
const PdfThumbnail = defineAsyncComponent(() => import('./components/PdfThumbnail.vue'))
const SlidesPreview = defineAsyncComponent(() => import('./components/SlidesPreview.vue'))
const PdfPreview = defineAsyncComponent(() => import('./components/PdfPreview.vue'))
const InteractionTrace = defineAsyncComponent(() => import('./components/InteractionTrace.vue'))
const ModelUsageTrend = defineAsyncComponent(() => import('./components/ModelUsageTrend.vue'))
const StaticAssetsView = defineAsyncComponent(() => import('./components/StaticAssetsView.vue'))
const StaticAssetImportDialog = defineAsyncComponent(() => import('./components/StaticAssetImportDialog.vue'))
const ScheduledTasksView = defineAsyncComponent(() => import('./components/ScheduledTasksView.vue'))
const ChannelsView = defineAsyncComponent(() => import('./components/ChannelsView.vue'))

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

    <aside class="sidebar">
      <button class="brand" type="button" aria-label="Open artifacts" @click="navigate('library')">
        <span class="brand-mark"><img src="/logo.png" alt="" /></span>
        <span><strong>Commonplace</strong><small>{{ $t('brand.subtitle') }}</small></span>
      </button>

      <nav class="primary-nav" aria-label="Main navigation">
        <button :class="{ active: view === 'new' && sessionScope === 'normal' }" type="button" @click="navigate('new')">
          <svg><use href="#icon-spark" /></svg><span>{{ $t('nav.workspace') }}</span>
        </button>
        <button :class="{ active: view === 'scheduledTasks' || (view === 'new' && sessionScope === 'scheduled') }" type="button" @click="navigate('scheduledTasks')">
          <svg><use href="#icon-schedule" /></svg><span>{{ $t('nav.scheduledTasks') }}</span>
        </button>
        <button :class="{ active: view === 'search' || (view === 'library' && selectedTag === null) }" type="button" @click="navigate('library')">
          <svg><use href="#icon-cards" /></svg><span>{{ $t('nav.artifacts') }}</span><small>{{ libraryTotal ?? libraryItems.length }}</small>
        </button>
        <button :class="{ active: view === 'assets' }" type="button" @click="navigate('assets')">
          <svg><use href="#icon-attachment" /></svg><span>{{ $t('nav.assets') }}</span>
        </button>
      </nav>

      <div v-if="view === 'new' || view === 'scheduledTasks' || view === 'channels'" class="sidebar-section session-section">
        <div class="sidebar-heading"><span>{{ sessionScope === 'channel' ? $t('nav.channelConversations') : $t('nav.conversations') }}</span><button v-if="sessionScope === 'normal'" type="button" :aria-label="$t('nav.newConversation')" @click="resetWorkspace"><svg><use href="#icon-add" /></svg></button></div>
        <div ref="sessionListRef" class="session-history-list" @scroll.passive="handleSessionListScroll">
          <div
            v-for="session in visibleSessions"
            :key="session.id"
            class="session-history-item"
            :class="{ active: conversationId === session.id || switchingSessionId === session.id, switching: switchingSessionId === session.id }"
            :aria-current="conversationId === session.id ? 'page' : undefined"
          >
            <form v-if="editingSessionId === session.id" class="session-title-editor" @submit.prevent="saveSessionTitle(session.id)" @focusout="handleSessionTitleFocusOut">
              <input v-model="sessionTitleDraft" maxlength="100" aria-label="Conversation title" autofocus @keydown.esc.prevent="cancelSessionTitleEdit" />
              <button type="submit" aria-label="Save title">Save</button>
              <button type="button" aria-label="Cancel title edit" @click="cancelSessionTitleEdit">Cancel</button>
            </form>
            <button v-else class="session-open-button" type="button" @mouseenter="prefetchSession(session.id)" @focus="prefetchSession(session.id)" @click="openSession(session.id)">
              <span><strong title="Click to rename" @click.stop="startSessionTitleEdit(session)">{{ session.title || '新会话' }}</strong><small>{{ formatDateTime(session.created_at) }}</small></span>
              <small>{{ session.message_count }}</small>
            </button>
            <button v-if="editingSessionId !== session.id" class="session-delete-button" type="button" :aria-label="`Delete ${session.title || 'conversation'}`" title="Delete conversation" @click.stop="deleteSession(session)"><svg><use href="#icon-trash" /></svg></button>
          </div>
          <template v-if="!visibleSessions.length && activeSessionsPending">
            <div v-for="index in 3" :key="`session-skeleton-${index}`" class="session-history-skeleton" aria-hidden="true" />
          </template>
          <p v-else-if="!visibleSessions.length" class="sidebar-empty">{{ $t('nav.noConversations') }}</p>
          <div v-if="visibleSessions.length && activeSessionsLoading" class="session-list-loading" role="status" aria-live="polite">
            <span class="session-switch-spinner" aria-hidden="true" />
            <small>{{ $t('nav.loading') }}</small>
          </div>
        </div>
      </div>

      <div v-else class="sidebar-section">
        <div class="sidebar-heading"><span>{{ $t('nav.collections') }}</span><button type="button" :aria-label="$t('nav.manageTags')" @click="openTagManager"><svg><use href="#icon-add" /></svg></button></div>
        <div class="tag-list">
          <div
            v-for="tag in flatTags"
            :key="tag.id"
            class="tag-row"
            :class="{ 'drop-target': tagDropTargetId === tag.id, 'drop-busy': tagAssignmentBusy }"
            :style="{ '--tag-depth': tag.depth }"
            @mouseenter="hoveredTagId = tag.id"
            @mouseleave="hoveredTagId = null"
            @dragenter="handleTagDragOver(tag, $event)"
            @dragover="handleTagDragOver(tag, $event)"
            @dragleave="handleTagDragLeave(tag, $event)"
            @drop="dropResourceOnTag(tag, $event)"
          >
            <button
              v-if="tag.hasChildren"
              class="tag-toggle"
              :class="{ collapsed: collapsedTagIds.has(tag.id) }"
              type="button"
              :aria-label="`${collapsedTagIds.has(tag.id) ? $t('nav.expand') : $t('nav.collapse')} ${tag.name}`"
              @click="toggleTag(tag.id)"
            ><span>⌄</span></button>
            <span v-else class="tag-toggle-placeholder" />
            <button
              class="tag-select"
              :class="{ active: selectedTag === tag.id && view === 'library' }"
              :title="tag.path"
              type="button"
              @click="filterByTag(tag.id)"
            >
              <span class="tag-dot" :style="tag.color ? { background: tag.color } : undefined" />
              <span class="tag-label">{{ tag.name }}</span><small v-if="hoveredTagId !== tag.id">{{ tag.total_count }}</small>
            </button>
            <button
              v-if="hoveredTagId === tag.id"
              class="tag-delete"
              type="button"
              :disabled="tagManagerBusy"
              :aria-label="$t('nav.deleteTag', { path: tag.path })"
              :title="$t('nav.deleteTag', { path: tag.path })"
              @click.stop="deleteTag(tag)"
            ><svg><use href="#icon-trash" /></svg></button>
          </div>
          <p v-if="!flatTags.length" class="sidebar-empty">{{ $t('nav.tagsEmpty') }}</p>
        </div>
      </div>

      <div class="sidebar-footer">
        <button class="channels-nav-button" :class="{ active: view === 'channels' || (view === 'new' && sessionScope === 'channel') }" type="button" @click="navigate('channels')">
          <svg><use href="#icon-channels" /></svg><span>{{ $t('nav.channels') }}</span>
        </button>
        <!--
          The update lives where the reader already looks for the running copy:
          one line above Settings, absent until PyPI has something newer that this copy
          can install (a source checkout never shows it), and a click installs it. Once
          installed, the same spot becomes the button that restarts Zett into it.
        -->
        <button
          v-if="updateStatus?.restart_required"
          class="update-callout restart"
          type="button"
          :disabled="updateRestarting"
          :aria-busy="updateRestarting"
          :title="$t('Installed {version} — restart Zett to use it', { version: updateStatus.installed })"
          @click="restartZett"
        >
          <svg><use href="#icon-refresh" /></svg>
          <span>{{ updateRestarting ? $t('Restarting…') : $t('Restart Zett to use {version}', { version: updateStatus.installed }) }}</span>
          <span v-if="updateRestarting" class="button-spinner" aria-hidden="true" />
        </button>
        <button
          v-else-if="updateStatus?.can_install"
          class="update-callout"
          type="button"
          :disabled="updateInstalling"
          :aria-busy="updateInstalling"
          :title="updateStatus.detail"
          @click="installAvailableUpdate"
        >
          <svg><use href="#icon-download" /></svg>
          <span>{{ updateInstalling ? $t('Installing…') : $t('Update to {version}', { version: updateStatus.latest ?? '' }) }}</span>
          <span v-if="updateInstalling" class="button-spinner" aria-hidden="true" />
        </button>
        <button :class="{ active: settingsOpen }" type="button" @click="navigate('settings')">
          <svg><use href="#icon-settings" /></svg><span>{{ $t('nav.settings') }}</span>
          <span class="status-dot" :class="{ online: providers.some((provider) => provider.enabled) }" />
        </button>
      </div>
    </aside>

    <main class="workspace">
      <Transition name="toast">
        <div v-if="notice" class="toast" :class="noticeKind" role="status">
          <svg v-if="noticeKind === 'success'"><use href="#icon-check" /></svg>
          <span>{{ notice }}</span>
        </div>
      </Transition>

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

      <template v-if="view === 'library' || view === 'search'">
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

      <template v-else-if="view === 'new'">
        <header class="topbar compact chat-topbar">
          <div class="chat-topbar-title"><span class="status-dot online" /><span>{{ sessionScope === 'scheduled' ? $t('nav.scheduledConversation') : sessionScope === 'channel' ? $t('nav.channelConversation') : $t('nav.workspace') }}</span></div>
          <button class="workspace-view-toggle" type="button" :aria-label="workspaceView === 'workspace' ? 'Show trace' : 'Show workspace'" :title="workspaceView === 'workspace' ? 'Show trace' : 'Show workspace'" @click="setWorkspaceView(workspaceView === 'workspace' ? 'trace' : 'workspace')">
            <svg v-if="workspaceView === 'workspace'" viewBox="0 0 24 24" aria-hidden="true"><path d="M4 6h4v4H4zM10 8h10M4 15h4v4H4zM10 17h10" /></svg>
            <svg v-else viewBox="0 0 24 24" aria-hidden="true"><path d="M4 4h7v16H4zM14 4h6v16h-6z" /></svg>
          </button>
        </header>
        <section class="content create-view">
          <div v-if="workspaceView === 'trace'" class="trace-workspace">
            <InteractionTrace
              :messages="traceMessages"
              :loading="traceLoading"
              :error="traceError"
              :selected-turn-id="selectedTraceTurnId"
              @refresh="loadInteractionTrace()"
              @preview-image="openImagePreview"
              @update:selected-turn-id="updateTraceTurn"
            />
          </div>
          <div v-else class="agent-workspace" :class="{ 'session-switching': switchingSessionId !== null, 'assets-hidden': assetsPaneHidden }" @paste="pasteAssets">
            <aside v-if="!assetsPaneHidden" class="assets-pane" aria-label="Session assets" tabindex="0">
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

            <section class="agent-chat" :class="{ 'session-switching': switchingSessionId !== null }" aria-label="Knowledge card conversation" :aria-busy="switchingSessionId !== null">
              <div class="agent-chat-header">
                <div class="agent-identity"><img src="/logo.png" alt="" /><div><strong>{{ $t('Zettelkasten Agent') }}</strong><small>{{ $t('Turn a conversation into knowledge') }}</small></div></div>
                <button v-if="assetsPaneHidden" class="asset-show-action" type="button" :title="$t('Show assets')" :aria-label="$t('Show assets')" @click="toggleAssetsPane(false)">
                  <svg><use href="#icon-eye" /></svg>
                  <span>{{ $t('Assets') }}</span>
                </button>
                <span class="streaming-status"><i />{{ $t('Zettelkasten Agent online') }}</span>
              </div>

              <div ref="agentThread" class="agent-thread" :class="{ empty: !conversationStarted && switchingSessionId === null }" aria-live="polite" @scroll.passive="handleAgentThreadScroll" @wheel.passive="handleAgentThreadWheel">
                <Transition name="session-content" mode="out-in">
                  <div v-if="switchingSessionId || workspaceRestoring" key="switching" class="session-switch-state" aria-live="polite">
                    <span class="session-switch-spinner" aria-hidden="true" />
                    <strong>{{ workspaceRestoring ? 'Restoring conversation' : 'Switching conversation' }}</strong>
                    <small>Loading messages and workspace…</small>
                  </div>
                  <div v-else-if="!conversationStarted" key="welcome" class="agent-welcome">
                    <span class="feature-icon"><svg><use href="#icon-spark" /></svg></span>
                    <h2>{{ $t('What should we remember?') }}</h2>
                    <p>{{ $t('Share a rough thought, excerpt, or question. You can refine the result through conversation before saving it.') }}</p>
                    <div class="prompt-hints"><button type="button" @click="raw = 'I have an idea: '">{{ $t('Capture an idea') }}</button><button type="button" @click="raw = 'Key point from what I just read: '">{{ $t('Summarize a note') }}</button></div>
                  </div>
                  <div v-else ref="agentTurnStack" :key="conversationId || 'conversation'" class="turn-stack">
                  <article
                    v-for="(turn, index) in conversationTurns"
                    :key="turn.id"
                    class="conversation-turn"
                    :class="{ running: isRunningTurn(index) }"
                  >
                    <section class="turn-prompt" aria-label="User message">
                      <div class="turn-prompt-content">
                        <div v-if="turn.prompt.steering_status === 'waiting'" class="turn-steering-status">
                          <i aria-hidden="true" />
                          <span>Will respond immediately after the current tool call or turn finishes.</span>
                        </div>
                        <template v-if="turn.prompt.parts?.length">
                          <template v-for="(part, partIndex) in turn.prompt.parts" :key="`${turn.id}-part-${partIndex}`">
                            <div
                              v-if="part.type === 'text' && part.text"
                              class="message-content"
                            >
                              <MarkdownContent :content="part.text" />
                            </div>
                            <button
                              v-else-if="part.type === 'image'"
                              class="turn-prompt-image-button"
                              type="button"
                              :aria-label="`Preview ${part.name}`"
                              @click="openMessageImage(part)"
                            >
                              <img class="turn-prompt-image" :src="part.content_url" :alt="part.name" />
                            </button>
                          </template>
                        </template>
                        <div v-else-if="turn.prompt.content" class="message-content">
                          <MarkdownContent :content="turn.prompt.content" />
                        </div>
                      </div>
                    </section>

                    <div class="turn-content">
                      <AgentExecution
                        :timeline="turnExecutionTimeline(turn, index)"
                        :running="isRunningTurn(index)"
                        :open="isTurnDetailsOpen(turn, index)"
                        :task="turnTask(index)"
                        :duration="turnDuration(turn, index)"
                        @toggle="toggleTurnExecution(turn, $event)"
                        @preview-image="openImagePreview"
                      >
                        <template #metrics>
                          <CacheHitRate class="turn-execution-cache" label="Cache" :rate="turnCacheHitRate(turn, index)" />
                        </template>
                        <template #tasks>
                          <div v-if="isRunningTurn(index) && activeTodos?.todos.length" class="turn-task-list">
                            <div><strong>Task progress</strong><small>{{ activeTodos.completed ? 'Completed' : `${(activeTodos.processing_index ?? 0) + 1} of ${activeTodos.todos.length}` }}</small></div>
                            <ol>
                              <li v-for="todo in activeTodos.todos" :key="todo.content" :class="todo.status">
                                <i aria-hidden="true">{{ todo.status === 'completed' ? '✓' : todo.status === 'processing' ? '•' : '' }}</i>
                                <span>{{ todo.content }}</span>
                              </li>
                            </ol>
                          </div>
                        </template>
                        <template #markdown="{ content }"><MarkdownContent :content="content" /></template>
                      </AgentExecution>

                      <section class="turn-response" aria-label="Agent response">
                        <div class="agent-response-content">
                          <template v-for="entry in turnAnswerTimeline(turn, index)" :key="entry.id">
                            <MarkdownContent class="final-response" :content="entry.content" />
                          </template>
                          <span v-if="isRunningTurn(index)" class="streaming-dots compact" aria-label="Generating"><i /><i /><i /></span>
                          <p v-else-if="isSteeredTurn(index)" class="turn-steered-note">This turn was steered by a follow-up message.</p>
                          <p v-else-if="!turnAnswerTimeline(turn, index).length && !turn.response?.error" class="turn-empty-response">No response was recorded for this turn.</p>
                          <div v-if="turn.response?.error" class="turn-error" role="alert">
                            <strong>Request failed</strong>
                            <span>{{ turn.response.error }}</span>
                          </div>
                        </div>
                      </section>
                    </div>
                  </article>
                  </div>
                </Transition>
              </div>

              <AskUserPrompt
                v-if="pendingQuestion"
                :question="pendingQuestion.question"
                :options="pendingQuestion.options"
                :allow-multiple="pendingQuestion.allowMultiple"
                :selected-options="selectedAskOptions"
                :answer="askAnswer"
                :images="askUserImages"
                :queued-count="queuedQuestions.length"
                :submitting="answeringQuestion"
                @toggle="toggleAskOption"
                @update:answer="updateAskAnswer"
                @add-images="attachAskUserImages"
                @preview-image="openImagePreview"
                @remove-image="removeAskUserImage"
                @submit="answerAgentQuestion"
              />

              <ShellApprovalPrompt
                v-for="approval in pendingShellApprovals"
                :key="approval.toolCallId"
                :command="approval.command"
                :timeout-seconds="approval.timeoutSeconds"
                :remember-supported="approval.rememberSupported"
                :submitting="shellApprovalSubmittingIds.includes(approval.toolCallId)"
                @execute="remember => respondToShellApproval(approval.toolCallId, 'execute', remember)"
                @abort="respondToShellApproval(approval.toolCallId, 'abort')"
              />

              <div class="agent-composer-stack">
                <div v-if="queuedFollowUps.length" class="queued-followup-list" aria-label="Queued follow-up messages" aria-live="polite">
                  <article
                    v-for="item in queuedFollowUps"
                    :key="item.id"
                    class="queued-followup"
                    :class="{ dragging: draggingQueuedFollowUpId === item.id }"
                    @dragover.prevent
                    @drop.prevent="dropQueuedFollowUp(item, $event)"
                  >
                    <button
                      class="queued-followup-drag"
                      type="button"
                      draggable="true"
                      title="Drag to reorder"
                      aria-label="Drag to reorder"
                      @dragstart.stop="startQueuedFollowUpDrag(item, $event)"
                      @dragend.stop="endQueuedFollowUpDrag"
                    >
                      <svg viewBox="0 0 20 20" aria-hidden="true"><circle cx="7" cy="5" r="1" /><circle cx="13" cy="5" r="1" /><circle cx="7" cy="10" r="1" /><circle cx="13" cy="10" r="1" /><circle cx="7" cy="15" r="1" /><circle cx="13" cy="15" r="1" /></svg>
                    </button>
                    <span class="queued-followup-icon" aria-hidden="true"><svg><use href="#icon-conversation" /></svg></span>
                    <div class="queued-followup-copy">
                      <p>{{ queuedFollowUpText(item) }}</p>
                      <div v-if="item.parts.some((part) => part.type === 'image')" class="queued-followup-images">
                        <template v-for="(part, partIndex) in item.parts" :key="`${item.id}-${partIndex}`">
                          <button
                            v-if="part.type === 'image'"
                            class="queued-followup-image-preview"
                            type="button"
                            :aria-label="`Preview ${part.name}`"
                            @click="openImagePreview({ name: part.name, url: part.content_url })"
                          >
                            <img :src="part.content_url" :alt="part.name" />
                          </button>
                        </template>
                      </div>
                    </div>
                    <button
                      class="queued-followup-steer"
                      type="button"
                      :disabled="steeringQueuedFollowUpId === item.id || item.slashCommandId !== null || item.atCommandId !== null"
                      :aria-label="`Steer with ${queuedFollowUpText(item)}`"
                      title="Apply this follow-up to the active run now"
                      @click="steerQueuedFollowUp(item)"
                    >
                      <svg aria-hidden="true" viewBox="0 0 24 24"><path d="m9 7-5 5 5 5M5 12h8a6 6 0 0 1 6 6" /></svg>
                      <span>{{ steeringQueuedFollowUpId === item.id ? 'Sending…' : 'Steer' }}</span>
                    </button>
                    <button
                      class="queued-followup-remove"
                      type="button"
                      :aria-label="`Remove ${queuedFollowUpText(item)}`"
                      @click="removeQueuedFollowUp(item)"
                    >
                      <svg aria-hidden="true"><use href="#icon-trash" /></svg>
                    </button>
                  </article>
                </div>
                <form class="agent-input" @submit.prevent="submitConversation">
                  <ComposerCommandMenu
                    v-if="slashMenu"
                    :items="slashMenuItems"
                    :active-index="slashMenuActiveIndex"
                    :loading="slashCommandsLoading && !slashCommandsLoaded"
                    :heading="$t('composer.slashCommands')"
                    :hint="$t('composer.selectOneCommand')"
                    :empty-label="$t('composer.noSlashCommands')"
                    @select="selectSlashCommand"
                    @hover="slashMenu = slashMenu ? { ...slashMenu, activeIndex: $event } : null"
                  />
                  <ComposerCommandMenu
                    v-if="atMenu"
                    trigger="@"
                    :items="atMenuItems"
                    :active-index="atMenuActiveIndex"
                    :loading="atCommandsLoading && !atCommandsLoaded"
                    :heading="$t('composer.references')"
                    :hint="$t('composer.selectOneReference')"
                    :empty-label="$t('composer.noReferences')"
                    @select="selectAtCommand"
                    @hover="atMenu = atMenu ? { ...atMenu, activeIndex: $event } : null"
                  />
                  <div v-if="pendingMessageImages.length" class="message-image-drafts" aria-label="Images attached to this message">
                    <figure v-for="image in pendingMessageImages" :key="image.id">
                      <button
                        class="message-image-preview"
                        type="button"
                        :aria-label="`Preview ${image.name}`"
                        @click="openImagePreview({ name: image.name, url: image.content_url })"
                      >
                        <img :src="image.content_url" :alt="image.name" />
                      </button>
                      <button class="message-image-remove" type="button" :aria-label="`Remove ${image.name}`" @click="removeMessageImage(image.id)">×</button>
                    </figure>
                  </div>
                  <div v-if="!conversationStarted" class="composer-textarea-wrap" :class="{ 'token-selected': initialTokenHighlight, composing: composerComposing }">
                    <div ref="initialComposerHighlight" class="composer-input-mirror" aria-hidden="true"><template v-if="initialTokenHighlight"><template v-for="(segment, index) in initialTokenHighlight" :key="index"><mark v-if="segment.kind" :class="segment.kind === 'reference' ? 'reference' : ''">{{ segment.text }}</mark><span v-else>{{ segment.text }}</span></template></template><template v-else>{{ raw }}</template></div>
                    <textarea
                      ref="initialComposerInput"
                      :value="raw"
                      rows="3"
                      autofocus
                      :placeholder="$t('composer.messagePlaceholder')"
                      @input="updateComposerText($event, 'initial')"
                      @scroll.passive="syncComposerHighlight('initial')"
                      @compositionstart="composerComposing = true"
                      @compositionend="finishComposerComposition"
                      @click="handleComposerSelection('initial', $event)"
                      @keydown="handleComposerKeydown($event, 'initial')"
                    />
                  </div>
                  <div v-else class="composer-textarea-wrap" :class="{ 'token-selected': followUpTokenHighlight, composing: composerComposing }">
                    <div ref="followUpComposerHighlight" class="composer-input-mirror" aria-hidden="true"><template v-if="followUpTokenHighlight"><template v-for="(segment, index) in followUpTokenHighlight" :key="index"><mark v-if="segment.kind" :class="segment.kind === 'reference' ? 'reference' : ''">{{ segment.text }}</mark><span v-else>{{ segment.text }}</span></template></template><template v-else>{{ followUp }}</template></div>
                    <textarea
                      ref="followUpComposerInput"
                      :value="followUp"
                      rows="3"
                      :placeholder="$t('composer.continuePlaceholder')"
                      @input="updateComposerText($event, 'follow-up')"
                      @scroll.passive="syncComposerHighlight('follow-up')"
                      @compositionstart="composerComposing = true"
                      @compositionend="finishComposerComposition"
                      @click="handleComposerSelection('follow-up', $event)"
                      @keydown="handleComposerKeydown($event, 'follow-up')"
                    />
                  </div>
                  <div class="agent-input-footer">
                    <div class="composer-leading">
                      <AgentComposerControls
                        :providers="providers"
                        :selected-provider-id="selectedProviderId"
                        :effort="reasoningEffort"
                        :shell-approval="shellApprovalMode"
                        :disabled="loading"
                        :usage="conversationUsage"
                        :current-usage="currentContextUsage"
                        :context-composition="contextComposition"
                        :compaction-max-tokens="runtimeSettings.compaction_max_tokens"
                        @update:selected-provider-id="selectedProviderId = $event"
                        @update:effort="reasoningEffort = $event"
                        @update:shell-approval="updateShellApprovalMode"
                        @add-provider="navigate('settings')"
                      />
                    </div>
                    <div class="composer-submit">
                      <small>{{ loading ? $t('composer.enterToQueue') : $t('composer.enterToSend') }}</small>
                      <button
                        class="send-button"
                        :class="{ stop: loading }"
                        :disabled="!loading && !canSubmitMessage"
                        type="button"
                        :aria-label="loading ? 'Stop generating' : 'Send message'"
                        @click="loading ? stopGeneration() : submitConversation()"
                      >
                        <svg v-if="loading"><use href="#icon-stop" /></svg>
                        <svg v-else><use href="#icon-arrow" /></svg>
                      </button>
                    </div>
                  </div>
                </form>
              </div>
            </section>

            <aside ref="artifactPaneRef" class="artifact-pane artifact-workspace">
              <header ref="artifactHeaderRef" class="artifact-collection-header">
                <div><strong>{{ $t('Artifacts') }}</strong><small>{{ $t('{count} in this conversation', { count: artifacts.length }) }}</small></div>
                <div class="artifact-collection-actions">
                  <span v-if="loading" class="artifact-syncing"><i />{{ $t('Updating') }}</span>
                  <button class="artifact-save-all" type="button" :disabled="savingAllArtifacts || saving || !artifactsNeedingSave.length" @click="saveAllArtifacts">{{ savingAllArtifacts ? 'Saving…' : 'Save all' }}</button>
                  <button class="artifact-refresh" type="button" :title="$t('Refresh artifacts')" :aria-label="$t('Refresh artifacts')" :disabled="artifactRefreshing" @click="refreshSelectedArtifact">
                    <svg :class="{ spinning: artifactRefreshing }"><use href="#icon-refresh" /></svg>
                  </button>
                </div>
              </header>
              <div v-if="artifacts.length" class="artifact-list" :style="artifactListHeight === null ? undefined : { height: `${artifactListHeight}px` }" aria-label="Conversation artifacts">
                <div v-for="artifact in artifacts" :key="artifact.id" class="artifact-list-item" :class="[artifactTone(artifact.artifact_type), lifecycleClass(artifactLifecycle(artifact)), artifact.card_status ? statusTone(artifact.card_status) : '', { active: artifact.id === selectedArtifactId }]" :data-lifecycle="artifactLifecycle(artifact)">
                  <CardStatusMark v-if="artifact.card_status" class="artifact-list-check" :status="artifact.card_status" :busy="cardStatusUpdatingIds.has(artifact.id)" @select="setConversationCardStatus(artifact, $event)" />
                  <button class="artifact-list-select" type="button" :disabled="saving || savingAllArtifacts" @click="selectArtifact(artifact)">
                    <img v-if="artifactListImage(artifact)" class="artifact-list-image" :src="artifactListImage(artifact) || undefined" alt="" />
                    <span v-else-if="artifact.card_status" class="artifact-kind-icon status-slot" aria-hidden="true" />
                    <span v-else class="artifact-kind-icon">{{ artifact.artifact_type === 'card' ? '◇' : artifact.artifact_type === 'article' ? '¶' : artifact.artifact_type === 'slides' ? '▤' : '▧' }}</span>
                    <span class="artifact-list-copy">
                      <small class="artifact-list-meta">
                        <span>{{ artifact.card_status ? $t(cardStatusType(artifact.card_status)) : artifact.artifact_type }}</span>
                        <em class="artifact-life-badge" :title="t(lifecycleHint(artifactLifecycle(artifact)))">{{ t(lifecycleLabel(artifactLifecycle(artifact))) }}</em>
                        <em v-if="artifact.card_status" class="artifact-status-tag">{{ t(cardStatusLabel(artifact.card_status)) }}</em>
                      </small>
                      <strong :class="{ 'status-struck': artifact.card_status && isStruck(artifact.card_status) }">{{ artifactTitle(artifactEditableContent(artifact)) }}</strong>
                      <span class="artifact-list-excerpt">{{ artifactListExcerpt(artifactEditableContent(artifact)) }}</span>
                    </span>
                  </button>
                  <div class="artifact-list-actions">
                    <button class="artifact-list-action" type="button" :disabled="saving || savingAllArtifacts || !artifactTitle(artifactEditableContent(artifact)).trim()" :aria-label="`${artifact.status === 'saved' ? 'Update' : 'Save'} ${artifactTitle(artifactEditableContent(artifact))}`" :title="artifact.status === 'saved' ? 'Update artifact' : 'Save artifact'" @click="saveSelectedArtifact(artifact)"><svg aria-hidden="true"><use href="#icon-check" /></svg></button>
                    <button class="artifact-list-action" type="button" :disabled="savingAllArtifacts" :aria-label="`Edit ${artifactTitle(artifactEditableContent(artifact))}`" title="Edit artifact" @click="editArtifactFromList(artifact)"><svg aria-hidden="true"><use href="#icon-edit" /></svg></button>
                    <button class="artifact-list-action danger" type="button" :disabled="saving || savingAllArtifacts" :aria-label="`Delete ${artifactTitle(artifactEditableContent(artifact))}`" title="Delete artifact" @click="deleteSelectedArtifact(artifact)"><svg aria-hidden="true"><use href="#icon-trash" /></svg></button>
                  </div>
                </div>
              </div>
              <div
                v-if="artifacts.length && artifactContent"
                class="artifact-splitter"
                role="separator"
                aria-label="Resize artifact list and preview"
                aria-orientation="horizontal"
                tabindex="0"
                :aria-valuenow="Math.round(artifactListHeight ?? MIN_ARTIFACT_LIST_HEIGHT)"
                @pointerdown="startArtifactSplit"
                @pointermove="moveArtifactSplit"
                @pointerup="endArtifactSplit"
                @pointercancel="endArtifactSplit"
                @keydown="keyArtifactSplit"
              ><span /></div>
              <div v-if="workspaceRestoring" class="artifact-placeholder">
                <span><svg><use href="#icon-cards" /></svg></span>
                <h2>{{ $t('Restoring conversation') }}</h2>
                <p>{{ $t('Artifacts appear once this conversation has loaded.') }}</p>
              </div>
              <div v-else-if="!artifactContent" class="artifact-placeholder">
                <span><svg><use href="#icon-cards" /></svg></span>
                <h2>{{ $t('No artifacts yet') }}</h2>
                <p>{{ $t('Keep talking with Zett Agent. Cards, articles, slides, and images will appear here when the conversation produces them.') }}</p>
              </div>
              <div v-else :key="selectedArtifactId ?? 'artifact-preview'" class="artifact-panel artifact-editor" :class="[artifactTone(artifactContent.artifact_type), selectedArtifact ? lifecycleClass(artifactLifecycle(selectedArtifact)) : '', { editing: selectedArtifactDirty }]">
                <div class="artifact-editor-accent" />
                <header class="artifact-editor-header">
                  <div class="artifact-state"><i /><span><strong>{{ selectedArtifact?.card_status ? $t(cardStatusType(selectedArtifact.card_status)) : selectedArtifact?.artifact_type }} artifact</strong><small v-if="selectedArtifact" :title="t(lifecycleHint(artifactLifecycle(selectedArtifact)))"><span class="artifact-life-note">{{ t(lifecycleLabel(artifactLifecycle(selectedArtifact))) }}</span> · version {{ selectedArtifact.version }}<em v-if="selectedArtifactDirty" class="artifact-dirty-badge">{{ t('artifact.editing') }}</em></small></span></div>
                  <CardStatusMenu v-if="selectedArtifact?.card_status" :status="selectedArtifact.card_status" :busy="cardStatusUpdatingIds.has(selectedArtifact.id)" @select="setConversationCardStatus(selectedArtifact, $event)" />
                  <div v-if="selectedArtifactDiff?.changed || !artifactPreview" class="artifact-mode-switch" :aria-label="$t('Artifact display mode')"><button v-if="selectedArtifactDiff?.changed" type="button" :class="{ active: artifactDiff }" @click="artifactDiff = true; artifactPreview = false">{{ $t('Diff') }}</button><button v-if="!artifactPreview || artifactDiff" type="button" @click="artifactPreview = true; artifactDiff = false">{{ $t('Preview') }}</button></div>
                </header>
                <div class="artifact-editor-body">
                  <ArtifactDiffView v-if="artifactDiff && selectedArtifactDiff" :diff="selectedArtifactDiff" />
                  <template v-else>
                  <div v-if="artifactContent.artifact_type === 'card' && !artifactPreview" class="card-meta-row">
                    <div class="card-type-control">
                      <span>{{ $t('Card type') }}</span>
                      <div class="card-type-options" role="group" :aria-label="$t('Card type')">
                        <button v-for="cardType in cardTypes" :key="cardType" :class="{ active: artifactContent.card_type === cardType }" type="button" @click="artifactContent.card_type = cardType">{{ $t(cardType) }}</button>
                      </div>
                    </div>
                  </div>
                  <template v-if="artifactContent.artifact_type === 'latex_pdf'">
                    <template v-if="!artifactPreview">
                      <label class="card-summary-control"><span>{{ $t('Project directory') }}</span><textarea v-model="artifactContent.project_path" rows="3" /></label>
                      <label class="card-title-control"><span>{{ $t('PDF filename') }}</span><textarea v-model="artifactContent.pdf_name" rows="1" /></label>
                      <p>{{ $t('Source files stay in the project directory. Compile the PDF before saving this reference.') }}</p>
                    </template>
                    <PdfPreview v-else-if="artifactPreviewAsset" ref="pdfPreviewRef" :asset="artifactPreviewAsset" artifact />
                  </template>
                  <template v-else-if="!artifactPreview">
                    <label class="card-title-control"><span>Title</span><textarea v-model="artifactContent.title" rows="2" /></label>
                    <label v-if="artifactContent.artifact_type === 'article' || artifactContent.artifact_type === 'slides'" class="card-summary-control"><span>Subtitle</span><textarea v-model="artifactContent.subtitle" rows="2" placeholder="Optional subtitle" /></label>
                    <label class="card-summary-control"><span>{{ artifactContent.artifact_type === 'image' ? 'Caption' : 'Summary' }}</span><textarea v-model="artifactContent.summary" rows="3" /></label>
                    <label v-if="artifactContent.artifact_type === 'image'" class="card-content-control"><span>Image prompt</span><textarea v-model="artifactContent.prompt" placeholder="Creative direction or generation prompt" /></label>
                    <label v-if="artifactContent.artifact_type === 'image'" class="card-summary-control"><span>Alt text</span><textarea v-model="artifactContent.alt_text" rows="3" /></label>
                    <template v-if="artifactContent.artifact_type === 'image'">
                      <label class="card-summary-control"><span>Source URL</span><textarea v-model="artifactContent.source_url" rows="2" placeholder="https://…" /></label>
                      <!-- The local key belongs to an uploaded session file, not to this edit: the assistant sets it through upload_asset, so it is shown read-only instead of being typed here. -->
                      <label v-if="artifactContent.asset_path" class="card-summary-control"><span>Local file</span><textarea :value="artifactContent.asset_path" rows="1" readonly /></label>
                    </template>
                    <div v-else class="card-body-editor"><span>{{ artifactContent.artifact_type === 'article' ? 'Article' : artifactContent.artifact_type === 'slides' ? 'Slides' : 'Knowledge' }} · Markdown</span><BlockEditor v-model="artifactContent.content" compact :slides="artifactContent.artifact_type === 'slides'" /></div>
                  </template>
                  <article v-else class="artifact-preview" :class="`artifact-preview-${artifactContent.artifact_type}`">
                    <SlidesPreview v-if="artifactContent.artifact_type === 'slides'" compact :title="artifactContent.title" :content="artifactContent.content" />
                    <template v-else>
                    <span class="artifact-preview-label">{{ artifactContent.artifact_type }}</span>
                    <h1>{{ artifactContent.title }}</h1>
                    <p v-if="artifactContent.artifact_type === 'article' && artifactContent.subtitle" class="article-subtitle">{{ artifactContent.subtitle }}</p>
                    <img v-if="artifactContent.artifact_type === 'image' && selectedImageUrl" :src="selectedImageUrl" :alt="artifactContent.alt_text" />
                    <div v-else-if="artifactContent.artifact_type === 'image'" class="image-brief-placeholder"><span>Image brief</span><p>{{ artifactContent.prompt || 'Waiting for an image source or generation step.' }}</p></div>
                    <MarkdownContent v-if="artifactContent.summary" class="preview-summary" :content="artifactContent.summary" />
                    <div v-if="artifactContent.artifact_type !== 'image'" class="preview-divider" />
                    <MarkdownContent v-if="artifactContent.artifact_type !== 'image'" class="preview-content" :content="artifactContent.content" />
                    </template>
                  </article>
                  <div v-if="artifactContent.artifact_type !== 'latex_pdf' && artifactContent.suggested_tags.length" class="suggestions card-tags-editor"><span>Classification</span><div class="suggestion-list"><label v-for="tag in artifactContent.suggested_tags" :key="tag.path" :class="{ selected: selectedSuggestions.includes(tag.path) }"><input v-model="selectedSuggestions" type="checkbox" :value="tag.path" /><span>{{ tag.path }}</span><small>{{ Math.round(tag.confidence * 100) }}%</small></label></div></div>
                  </template>
                </div>
              </div>
            </aside>
          </div>
        </section>
      </template>

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

      <Teleport to="body">
        <div v-if="settingsOpen" class="settings-backdrop" @click.self="closeSettings">
        <section ref="settingsDialog" class="settings-dialog" role="dialog" aria-modal="true" :aria-label="$t('Settings')" tabindex="-1">
          <header class="settings-dialog-header">
            <h1>{{ $t('Settings') }}</h1>
            <button class="close-button" type="button" :aria-label="$t('Close')" @click="closeSettings">×</button>
          </header>
          <div class="settings-dialog-body">
          <nav class="settings-tabs" role="tablist" aria-label="Settings sections">
            <button :class="{ active: settingsSection === 'general' }" type="button" role="tab" :aria-selected="settingsSection === 'general'" @click="selectSettingsSection('general')">{{ $t('settings.general') }}</button>
            <button :class="{ active: settingsSection === 'usage' }" type="button" role="tab" :aria-selected="settingsSection === 'usage'" @click="selectSettingsSection('usage')">{{ $t('settings.usage') }}</button>
            <button :class="{ active: settingsSection === 'providers' }" type="button" role="tab" :aria-selected="settingsSection === 'providers'" @click="selectSettingsSection('providers')">{{ $t('settings.providers') }}</button>
            <button :class="{ active: settingsSection === 'limits' }" type="button" role="tab" :aria-selected="settingsSection === 'limits'" @click="selectSettingsSection('limits')">{{ $t('settings.limits') }}</button>
          </nav>
          <section class="content settings-view">
          <div v-if="settingsSection === 'general'" class="settings-section">
          <div class="settings-intro">
            <div><h2>{{ $t('Preferences') }}</h2><p>{{ $t('Choose how Zett reads on this computer.') }}</p></div>
          </div>
          <div class="settings-card">
            <div class="form-grid">
              <label class="field">
                <span>{{ $t('settings.language') }}</span>
                <select :value="locale" @change="changeLocale">
                  <option value="en">{{ $t('settings.english') }}</option>
                  <option value="zh">{{ $t('settings.chinese') }}</option>
                </select>
                <small>{{ $t('Applied right away, and remembered in this browser.') }}</small>
              </label>
            </div>
          </div>
          </div>
          <div v-else-if="settingsSection === 'providers'" class="settings-section">
          <div class="settings-intro"><div><h2>{{ $t('AI providers') }}</h2><p>{{ $t('Keep multiple model connections and choose one for each conversation.') }}</p></div></div>
          <div class="provider-toolbar">
            <div v-if="providers.length" class="provider-list">
              <button v-for="provider in providers" :key="provider.id" :class="{ active: editingProviderId === provider.id }" type="button" @click="selectProvider(provider)"><span class="status-dot" :class="{ online: provider.enabled }" /><span><strong>{{ provider.name }}</strong><small>{{ provider.provider }} · {{ provider.model }}</small></span></button>
            </div>
            <button class="secondary-action" type="button" @click="newProvider"><svg><use href="#icon-add" /></svg>{{ $t('New provider') }}</button>
          </div>
          <form class="settings-card" @submit.prevent="saveAI">
            <div class="form-grid">
              <label class="field"><span>{{ $t('Connection name') }}</span><input v-model="ai.name" placeholder="e.g. Fast OpenAI" /><small>Shown in the conversation provider picker.</small></label>
              <label class="field"><span>{{ $t('Provider') }}</span><select v-model="ai.provider" @change="selectProviderKind"><option value="openai_compatible">OpenAI compatible</option><option value="responses_compatible">Responses compatible</option><option value="openai">OpenAI</option><option value="deepseek">DeepSeek</option><option value="anthropic">Anthropic</option><option value="anthropic_compatible">Anthropic compatible</option><option value="google">Google Gemini</option><option value="ollama">Ollama</option></select><small>The API format used for model requests.</small></label>
              <label class="field"><span>{{ $t('Model') }}</span><input v-model="ai.model" placeholder="e.g. gpt-4.1-mini" /><small>Use the exact model identifier from your provider.</small></label>
              <label class="field full"><span>{{ $t('Base URL') }} <em>{{ ['openai_compatible', 'responses_compatible', 'anthropic_compatible'].includes(ai.provider) ? 'Custom' : 'Auto-filled' }}</em></span><input v-model="ai.base_url" :placeholder="ai.provider === 'responses_compatible' ? 'https://api.example.com' : 'https://api.example.com/v1'" /><small>{{ providerBaseUrlHelp(ai.provider) }}</small></label>
              <label class="field full"><span>{{ $t('API key') }} <em>{{ providerLoading ? 'Loading…' : editingProviderId === null ? 'New' : ai.api_key ? 'Loaded' : 'Not set' }}</em></span><div class="secret-input"><input v-model="ai.api_key" :type="apiKeyVisible ? 'text' : 'password'" autocomplete="off" placeholder="Leave blank to keep the saved key" /><button type="button" :aria-label="apiKeyVisible ? 'Hide API key' : 'Show API key'" :title="apiKeyVisible ? 'Hide API key' : 'Show API key'" @click="apiKeyVisible = !apiKeyVisible"><svg aria-hidden="true"><use :href="apiKeyVisible ? '#icon-eye-off' : '#icon-eye'" /></svg></button></div><small>Stored encrypted locally. Saving a blank value keeps the existing key.</small></label>
              <label v-if="!providerIgnoresTemperature(ai.provider)" class="field temperature-field"><span>{{ $t('Temperature') }} <output>{{ ai.temperature.toFixed(1) }}</output></span><input v-model.number="ai.temperature" type="range" min="0" max="2" step="0.1" /></label>
              <div v-if="ai.provider === 'responses_compatible'" class="field"><span>{{ $t('API mode') }}</span><strong>Responses API</strong><small>This compatible connection always uses the Responses protocol.</small></div>
              <div v-else-if="['openai', 'openai_compatible', 'deepseek'].includes(ai.provider)" class="field"><span>{{ $t('API mode') }}</span><div class="mode-options" role="group" :aria-label="$t('API mode')"><button type="button" :class="{ active: !ai.response }" @click="setResponseMode(false)">Chat Completions</button><button type="button" :class="{ active: ai.response }" @click="setResponseMode(true)">Responses API</button></div><small>Responses mode enables provider-hosted tools such as web search.</small></div>
            </div>
            <div class="settings-actions"><button v-if="editingProviderId !== null" class="danger-button" type="button" @click="removeProvider">Delete provider</button><span v-else>Credentials are encrypted in your local database.</span><div><label class="switch"><input v-model="ai.enabled" type="checkbox" /><span /><small>{{ ai.enabled ? 'Enabled' : 'Disabled' }}</small></label><button class="primary-action" :disabled="providerSaving || providerLoading || !ai.name || !ai.model" :aria-busy="providerSaving" type="submit"><span v-if="providerSaving" class="button-spinner" aria-hidden="true" /><span>{{ providerSaving ? 'Testing…' : editingProviderId === null ? 'Add provider' : 'Save provider' }}</span></button></div></div>
          </form>
          </div>
          <div v-else-if="settingsSection === 'limits'" class="settings-section">
          <div class="settings-intro runtime-settings-heading">
            <div><h2>{{ $t('Conversation limits') }}</h2><p>{{ $t('Control local limits applied to new Agent requests.') }}</p></div>
          </div>
          <form class="settings-card" @submit.prevent="saveRuntimeSettings">
            <div class="form-grid">
              <label class="field">
                <span>{{ $t('Images per message') }}</span>
                <input v-model.number="runtimeSettings.max_message_images" type="number" min="1" max="256" step="1" />
                <small>Maximum number of images that can be pasted into one user message.</small>
              </label>
              <label class="field">
                <span>{{ $t('Model steps per turn') }}</span>
                <input v-model.number="runtimeSettings.max_turn_iterations" type="number" min="1" max="512" step="1" />
                <small>Maximum model calls, including tool-loop continuations, allowed in one turn.</small>
              </label>
              <label class="field">
                <span>{{ $t('Max asset file size') }} <em>MB</em></span>
                <input v-model.number="maxAssetSizeMb" type="number" min="1" max="2048" step="1" />
                <small>{{ $t('Maximum size for an uploaded image or file in this conversation.') }}</small>
              </label>
              <label class="field">
                <span>{{ $t('Compact context at') }}</span>
                <input v-model.number="runtimeSettings.compaction_max_tokens" type="number" min="128000" max="800000" step="1000" />
                <small>Estimated active-context tokens that trigger a compact snapshot.</small>
              </label>
              <label class="field">
                <span>{{ $t('Keep recent context') }}</span>
                <input v-model.number="runtimeSettings.compaction_keep_recent_tokens" type="number" min="32000" max="256000" step="1000" />
                <small>Recent estimated tokens retained verbatim after compaction.</small>
              </label>
            </div>
            <div class="settings-actions">
              <span>Stored locally and applied without restarting Zett.</span>
              <div><button class="primary-action" :disabled="runtimeSettingsSaving" type="submit">{{ runtimeSettingsSaving ? 'Saving…' : $t('Save limits') }}</button></div>
            </div>
          </form>
          <div class="settings-intro runtime-settings-heading">
            <div><h2>{{ $t('Agent permissions') }}</h2><p>{{ $t('Things the Agent may do in a conversation only when you allow them.') }}</p></div>
          </div>
          <div class="settings-card permission-card">
            <label v-for="permission in agentPermissions" :key="permission.key" class="permission-row">
              <span class="permission-copy">
                <strong>{{ $t(permission.title) }}</strong>
                <small>{{ $t(permission.description) }}</small>
              </span>
              <span class="switch">
                <input
                  type="checkbox"
                  role="switch"
                  :checked="runtimeSettings[permission.key]"
                  :disabled="agentPermissionSaving !== null"
                  @change="setAgentPermission(permission.key, ($event.target as HTMLInputElement).checked)"
                />
                <span />
              </span>
            </label>
          </div>
          </div>
          <div v-else class="settings-section">
          <div class="settings-intro runtime-settings-heading">
            <div><h2>{{ $t('Model activity') }}</h2><p>{{ $t('Daily token requests recorded from completed LLM calls.') }}</p></div>
          </div>
          <div class="settings-card">
            <div v-if="usageActivityLoading" class="settings-activity-state">Loading activity…</div>
            <UsageActivityGraph v-else :days="usageActivity" />
          </div>

          <div class="settings-intro runtime-settings-heading">
            <div><h2>{{ $t('By model') }}</h2><p>{{ $t('Request volume and token usage for every provider model.') }}</p></div>
          </div>
          <div v-if="usageActivityLoading" class="settings-activity-state">Loading model activity…</div>
          <div v-else-if="!modelUsageActivity.length" class="settings-card settings-activity-state">No model activity recorded yet.</div>
          <div v-else class="model-usage-list">
            <ModelUsageTrend
              v-for="series in modelUsageActivity"
              :key="`${series.provider || 'unknown'}:${series.model || 'unknown'}`"
              :provider="series.provider"
              :model="series.model"
              :days="series.days"
            />
          </div>
          </div>
          </section>
          </div>
        </section>
        </div>
      </Teleport>

      <Teleport to="body">
        <section v-if="fullscreenSlidesItem" ref="librarySlidesStage" class="library-slides-fullscreen" role="dialog" aria-modal="true" :aria-label="fullscreenSlidesItem.title" tabindex="-1">
          <button class="library-slides-close" type="button" aria-label="Close fullscreen preview" @click="closeSlidesFullscreen">×</button>
          <SlidesPreview :title="fullscreenSlidesItem.title" :content="fullscreenSlidesItem.content" :show-fullscreen-button="false" auto-focus />
        </section>
      </Teleport>
      <div v-if="libraryPdfLaunch" class="library-pdf-launch">
        <PdfPreview
          :asset="libraryClient.documentReference(libraryPdfLaunch.item.id)"
          artifact
          :initial-mode="libraryPdfLaunch.mode"
          @close="libraryPdfLaunch = null"
        />
      </div>
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
    </main>
  </div>
</template>
<style src="./styles/app/index.css"></style>
