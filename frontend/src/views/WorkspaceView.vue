<script setup lang="ts">
import { defineAsyncComponent, ref } from 'vue'
import { assetsPaneHidden, openImagePreview, toggleAssetsPane } from '../app/assets'
import { pasteAssets } from '../app/assetsUpload'
import { loadInteractionTrace, selectedTraceTurnId, setWorkspaceView, traceError, traceLoading, traceMessages, updateTraceTurn, workspaceView } from '../app/conversation/trace'
import { sessionScope, switchingSessionId } from '../app/sessions'
import { chatShare, endWorkspaceResize, keyWorkspaceResize, moveWorkspaceResize, resetChatShare, resizingWorkspace, setWorkspaceMode, startWorkspaceResize, workspaceGridVars, workspaceMode } from '../app/workspaceLayout'
import { MAX_CHAT_SHARE, MIN_CHAT_SHARE, type WorkspaceMode } from '../utils/workspaceLayout'
import AgentChat from './workspace/AgentChat.vue'
import ArtifactPane from './workspace/ArtifactPane.vue'
import AssetsPane from './workspace/AssetsPane.vue'

const InteractionTrace = defineAsyncComponent(() => import('../components/InteractionTrace.vue'))
const workspace = ref<HTMLElement | null>(null)
const chatColumn = ref<HTMLElement | null>(null)
const MODE_LABELS: Array<{ mode: WorkspaceMode; label: string }> = [
  { mode: 'chat', label: 'Conversation' },
  { mode: 'split', label: 'Split' },
  { mode: 'artifact', label: 'Artifact' },
]
</script>

<template>
  <header class="topbar compact chat-topbar">
    <div class="chat-topbar-title"><span class="status-dot online" /><span>{{ sessionScope === 'scheduled' ? $t('nav.scheduledConversation') : sessionScope === 'channel' ? $t('nav.channelConversation') : $t('nav.workspace') }}</span></div>
    <div v-if="workspaceView === 'workspace'" class="layout-controls">
      <div class="layout-switch" role="group" :aria-label="$t('Workspace layout')">
        <button v-for="entry in MODE_LABELS" :key="entry.mode" type="button" :class="{ active: workspaceMode === entry.mode }" :aria-pressed="workspaceMode === entry.mode" @click="setWorkspaceMode(entry.mode)">{{ $t(entry.label) }}</button>
      </div>
      <button class="layout-assets" type="button" :class="{ active: !assetsPaneHidden }" :aria-pressed="!assetsPaneHidden" :title="assetsPaneHidden ? $t('Show assets') : $t('Hide assets')" @click="toggleAssetsPane(!assetsPaneHidden)">
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 5h6v14H4zM13 5h7M13 10h7M13 15h7" /></svg>{{ $t('Assets') }}
      </button>
    </div>
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
    <div v-else ref="workspace" class="agent-workspace layout" :class="[`layout-${workspaceMode}`, { 'session-switching': switchingSessionId !== null, 'assets-hidden': assetsPaneHidden, resizing: resizingWorkspace }]" :style="workspaceGridVars" @paste="pasteAssets">
      <AssetsPane v-if="!assetsPaneHidden" />

      <div ref="chatColumn" class="chat-column"><AgentChat /></div>

      <div
        class="workspace-divider"
        role="separator"
        tabindex="0"
        aria-orientation="vertical"
        :aria-label="$t('Resize conversation and artifact')"
        :aria-valuemin="Math.round(MIN_CHAT_SHARE * 100)"
        :aria-valuemax="Math.round(MAX_CHAT_SHARE * 100)"
        :aria-valuenow="Math.round(chatShare * 100)"
        :aria-valuetext="$t('Conversation {percent}%', { percent: Math.round(chatShare * 100) })"
        @pointerdown="$event.button === 0 && startWorkspaceResize($event, workspace, chatColumn)"
        @pointermove="moveWorkspaceResize"
        @pointerup="endWorkspaceResize"
        @pointercancel="endWorkspaceResize"
        @lostpointercapture="endWorkspaceResize"
        @dblclick="resetChatShare"
        @keydown="keyWorkspaceResize"
      ><span /></div>

      <ArtifactPane />
    </div>
  </section>
</template>
