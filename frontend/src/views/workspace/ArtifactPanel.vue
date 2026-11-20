<script setup lang="ts">
import { defineAsyncComponent, ref } from 'vue'
import { setConversationCardStatus } from '../../app/artifacts/actions'
import PdfTypesetDiff from '../../components/PdfTypesetDiff.vue'
import { artifactContent, artifactDiff, artifactPreview, artifactPreviewAsset, artifactPreviewNonce, selectedArtifact, selectedArtifactDiff, selectedArtifactDirty, selectedImageUrl, selectedSuggestions } from '../../app/artifacts/state'
import { t } from '../../app/i18n'
import { cardStatusUpdatingIds, cardTypes } from '../../app/library/state'
import MarkdownDiff from '../../components/MarkdownDiff.vue'
import { artifactParts } from '../../utils/markdownDiff'
import type { AgentArtifact } from '../../api/types'
import { rewriteArtifactDraft } from '../../app/artifacts/actions'
import BlockEditor from '../../components/BlockEditor.vue'
import CardStatusMenu from '../../components/CardStatusMenu.vue'
import { artifactLifecycle, lifecycleClass, lifecycleHint, lifecycleLabel } from '../../utils/artifactLifecycle'
import { artifactTone } from '../../utils/artifactTone'
import { cardStatusType } from '../../utils/cardStatus'

const latexView = ref<'preview' | 'changes'>('preview')
const rejecting = ref(false)

async function rejectBody(artifact: AgentArtifact, body: string): Promise<void> {
  const draft = artifact.draft_content
  if (rejecting.value || !draft || !('content' in draft)) return
  rejecting.value = true
  try {
    await rewriteArtifactDraft(artifact, { ...draft, content: body })
  } finally {
    rejecting.value = false
  }
}

/** Rejecting everything puts the draft back to what the user last saved. */
async function rejectAll(artifact: AgentArtifact): Promise<void> {
  if (rejecting.value || !artifact.content) return
  rejecting.value = true
  try {
    await rewriteArtifactDraft(artifact, artifact.content)
  } finally {
    rejecting.value = false
  }
}
const MarkdownContent = defineAsyncComponent(() => import('../../components/MarkdownContent.vue'))
const PdfPreview = defineAsyncComponent(() => import('../../components/PdfPreview.vue'))
const SlidesPreview = defineAsyncComponent(() => import('../../components/SlidesPreview.vue'))
</script>

<template>
  <div v-if="artifactContent" class="artifact-panel artifact-editor" :class="[artifactTone(artifactContent.artifact_type), selectedArtifact ? lifecycleClass(artifactLifecycle(selectedArtifact)) : '', { editing: selectedArtifactDirty }]">
    <div class="artifact-editor-accent" />
    <header class="artifact-editor-header">
      <div class="artifact-state"><i /><span><strong>{{ selectedArtifact?.card_status ? $t(cardStatusType(selectedArtifact.card_status)) : selectedArtifact?.artifact_type }} artifact</strong><small v-if="selectedArtifact" :title="t(lifecycleHint(artifactLifecycle(selectedArtifact)))"><span class="artifact-life-note">{{ t(lifecycleLabel(artifactLifecycle(selectedArtifact))) }}</span> · version {{ selectedArtifact.version }}<em v-if="selectedArtifactDirty" class="artifact-dirty-badge">{{ t('artifact.editing') }}</em></small></span></div>
      <CardStatusMenu v-if="selectedArtifact?.card_status" :status="selectedArtifact.card_status" :busy="cardStatusUpdatingIds.has(selectedArtifact.id)" @select="setConversationCardStatus(selectedArtifact, $event)" />
      <div v-if="selectedArtifact && artifactContent.artifact_type === 'latex_pdf' && artifactPreview" class="artifact-mode-switch" :aria-label="$t('Artifact display mode')"><button type="button" :class="{ active: latexView === 'preview' }" @click="latexView = 'preview'">{{ $t('Preview') }}</button><button type="button" :class="{ active: latexView === 'changes' }" @click="latexView = 'changes'">{{ $t('Changes') }}</button></div>
      <div v-if="selectedArtifactDiff?.changed || !artifactPreview" class="artifact-mode-switch" :aria-label="$t('Artifact display mode')"><button v-if="selectedArtifactDiff?.changed" type="button" :class="{ active: artifactDiff }" @click="artifactDiff = true; artifactPreview = false">{{ $t('Diff') }}</button><button v-if="!artifactPreview || artifactDiff" type="button" @click="artifactPreview = true; artifactDiff = false">{{ $t('Preview') }}</button></div>
    </header>
    <div class="artifact-editor-body">
      <MarkdownDiff
        v-if="artifactDiff && selectedArtifactDiff && selectedArtifact"
        class="artifact-typeset"
        :before="artifactParts(selectedArtifact.content)?.body ?? ''"
        :after="artifactParts(selectedArtifact.draft_content)?.body ?? ''"
        :header-before="artifactParts(selectedArtifact.content)?.header"
        :header-after="artifactParts(selectedArtifact.draft_content)?.header"
        rejectable
        :busy="rejecting"
        @reject="rejectBody(selectedArtifact, $event)"
        @reject-all="rejectAll(selectedArtifact)"
      />
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
        <PdfTypesetDiff v-else-if="latexView === 'changes' && selectedArtifact" class="artifact-typeset" :artifact-id="selectedArtifact.id" :session-id="selectedArtifact.session_id" :nonce="artifactPreviewNonce" @restored="artifactPreviewNonce += 1" />
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
</template>
