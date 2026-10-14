<script setup lang="ts">
import { deleteSelectedArtifact, saveSelectedArtifact, selectArtifact, setConversationCardStatus } from '../../app/artifacts/actions'
import { editArtifactFromList } from '../../app/artifacts/editor'
import { artifactListHeight, artifacts, saving, savingAllArtifacts, selectedArtifactId } from '../../app/artifacts/state'
import { artifactTitle } from '../../app/format'
import { t } from '../../app/i18n'
import { cardStatusUpdatingIds } from '../../app/library/state'
import CardStatusMark from '../../components/CardStatusMark.vue'
import { artifactEditableContent } from '../../utils/artifactEditor'
import { artifactLifecycle, lifecycleClass, lifecycleHint, lifecycleLabel } from '../../utils/artifactLifecycle'
import { artifactListExcerpt, artifactListImage } from '../../utils/artifactListPresentation'
import { artifactTone } from '../../utils/artifactTone'
import { cardStatusLabel, cardStatusType, isStruck, statusTone } from '../../utils/cardStatus'
</script>

<template>
  <div class="artifact-list" :style="artifactListHeight === null ? undefined : { height: `${artifactListHeight}px` }" aria-label="Conversation artifacts">
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
</template>
