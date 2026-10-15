<script setup lang="ts">
import { defineAsyncComponent } from 'vue'
import { assetsPaneHidden, openImagePreview } from '../app/assets'
import { pasteAssets } from '../app/assetsUpload'
import { loadInteractionTrace, selectedTraceTurnId, setWorkspaceView, traceError, traceLoading, traceMessages, updateTraceTurn, workspaceView } from '../app/conversation/trace'
import { sessionScope, switchingSessionId } from '../app/sessions'
import AgentChat from './workspace/AgentChat.vue'
import ArtifactPane from './workspace/ArtifactPane.vue'
import AssetsPane from './workspace/AssetsPane.vue'

const InteractionTrace = defineAsyncComponent(() => import('../components/InteractionTrace.vue'))
</script>

<template>
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
      <AssetsPane v-if="!assetsPaneHidden" />

      <AgentChat />

      <ArtifactPane />
    </div>
  </section>
</template>
