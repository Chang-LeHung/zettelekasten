<script setup lang="ts">
import { onBeforeUnmount } from 'vue'
import { endArtifactSplit, keyArtifactSplit, moveArtifactSplit, refreshSelectedArtifact, saveAllArtifacts, startArtifactSplit } from '../../app/artifacts/actions'
import { appliedArtifactListWidth, artifactContent, artifactPaneRef, artifactPaneWidth, artifactRefreshing, artifacts, artifactsNeedingSave, saving, savingAllArtifacts, selectedArtifactId, workspaceRestoring } from '../../app/artifacts/state'
import { loading } from '../../app/conversation/state'
import { cancelPeek, peekedArtifact } from '../../app/artifacts/peek'
import { MIN_ARTIFACT_LIST_WIDTH, maxArtifactListWidth } from '../../utils/artifactSplit'
import ArtifactList from './ArtifactList.vue'
import ArtifactPanel from './ArtifactPanel.vue'
import ArtifactPeek from './ArtifactPeek.vue'

onBeforeUnmount(cancelPeek)
</script>

<template>
  <aside ref="artifactPaneRef" class="artifact-pane artifact-workspace">
    <header class="artifact-collection-header">
      <div><strong>{{ $t('Artifacts') }}</strong><small>{{ $t('{count} in this conversation', { count: artifacts.length }) }}</small></div>
      <div class="artifact-collection-actions">
        <span v-if="loading" class="artifact-syncing"><i />{{ $t('Updating') }}</span>
        <button class="artifact-save-all" type="button" :disabled="savingAllArtifacts || saving || !artifactsNeedingSave.length" @click="saveAllArtifacts">{{ savingAllArtifacts ? 'Saving…' : 'Save all' }}</button>
        <button class="artifact-refresh" type="button" :title="$t('Refresh artifacts')" :aria-label="$t('Refresh artifacts')" :disabled="artifactRefreshing" @click="refreshSelectedArtifact">
          <svg :class="{ spinning: artifactRefreshing }"><use href="#icon-refresh" /></svg>
        </button>
      </div>
    </header>
    <div class="artifact-split">
      <ArtifactList v-if="artifacts.length" />
      <div
        v-if="artifacts.length && artifactContent"
        class="artifact-splitter"
        role="separator"
        :aria-label="$t('Resize artifact list and preview')"
        aria-orientation="vertical"
        tabindex="0"
        :aria-valuenow="Math.round(appliedArtifactListWidth ?? MIN_ARTIFACT_LIST_WIDTH)"
        :aria-valuemin="MIN_ARTIFACT_LIST_WIDTH"
        :aria-valuemax="maxArtifactListWidth(artifactPaneWidth)"
        :aria-valuetext="`${Math.round(appliedArtifactListWidth ?? MIN_ARTIFACT_LIST_WIDTH)} px`"
        @pointerdown="startArtifactSplit"
        @pointermove="moveArtifactSplit"
        @pointerup="endArtifactSplit"
        @pointercancel="endArtifactSplit"
        @lostpointercapture="endArtifactSplit"
        @keydown="keyArtifactSplit"
      ><span /></div>
      <div class="artifact-main">
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
        <ArtifactPanel v-else :key="selectedArtifactId ?? 'artifact-preview'" />
        <ArtifactPeek v-if="peekedArtifact" :key="peekedArtifact.id" :artifact="peekedArtifact" />
      </div>
    </div>
  </aside>
</template>
