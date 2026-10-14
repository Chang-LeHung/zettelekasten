<script setup lang="ts">
import { formatDateTime } from '../app/format'
import { deleteTag, filterByTag } from '../app/library/actions'
import { collapsedTagIds, flatTags, hoveredTagId, libraryItems, libraryTotal, selectedTag, tagAssignmentBusy, tagDropTargetId, tagManagerBusy } from '../app/library/state'
import { dropResourceOnTag, handleTagDragLeave, handleTagDragOver, openTagManager, toggleTag } from '../app/library/tags'
import { view } from '../app/nav'
import { providers } from '../app/providers'
import { activeSessionsLoading, activeSessionsPending, cancelSessionTitleEdit, conversationId, editingSessionId, handleSessionListScroll, handleSessionTitleFocusOut, saveSessionTitle, sessionScope, sessionTitleDraft, startSessionTitleEdit, switchingSessionId, visibleSessions } from '../app/sessions'
import { settingsOpen } from '../app/settings'
import { installAvailableUpdate, restartZett, updateInstalling, updateRestarting, updateStatus } from '../app/updates'
import { deleteSession, navigate, openSession, prefetchSession, resetWorkspace } from '../app/workspace'
</script>

<template>
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
</template>
