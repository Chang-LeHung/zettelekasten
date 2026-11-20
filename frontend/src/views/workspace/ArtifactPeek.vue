<script setup lang="ts">
import { computed, defineAsyncComponent } from 'vue'
import type { AgentArtifact } from '../../api/types'
import { artifactEditableContent } from '../../utils/artifactEditor'
import { artifactListImage } from '../../utils/artifactListPresentation'

const props = defineProps<{ artifact: AgentArtifact }>()

const MarkdownContent = defineAsyncComponent(() => import('../../components/MarkdownContent.vue'))
const PdfThumbnail = defineAsyncComponent(() => import('../../components/PdfThumbnail.vue'))

/** A long body is cut here: the preview is a glance, the full text opens on click. */
const MAX_CHARS = 3200
const content = computed(() => artifactEditableContent(props.artifact))
const image = computed(() => artifactListImage(props.artifact))
const title = computed(() => content.value && 'title' in content.value ? content.value.title : '')
const summary = computed(() => content.value && 'summary' in content.value ? content.value.summary : '')
const body = computed(() => {
  const value = content.value
  if (!value || !('content' in value)) return ''
  return value.content.length > MAX_CHARS ? `${value.content.slice(0, MAX_CHARS)}…` : value.content
})
</script>

<template>
  <div class="artifact-peek" inert>
    <span class="artifact-peek-hint">{{ $t('Preview') }}</span>
    <div v-if="content?.artifact_type === 'latex_pdf'" class="artifact-peek-pdf">
      <PdfThumbnail :asset="artifact" artifact fit="contain" />
    </div>
    <article v-else class="artifact-peek-page">
      <h1>{{ title }}</h1>
      <img v-if="image" :src="image" :alt="title" />
      <MarkdownContent v-if="summary" class="artifact-peek-summary" :content="summary" />
      <MarkdownContent v-if="body" :content="body" />
    </article>
  </div>
</template>

<style scoped>
.artifact-peek { position: absolute; inset: 0; z-index: 6; display: flex; flex-direction: column; overflow: hidden; pointer-events: none; background: #f4f6f4; animation: peek-in .14s ease-out both; }
.artifact-peek-hint { position: absolute; top: .6rem; right: .8rem; z-index: 2; padding: .15rem .55rem; border-radius: 999px; color: #fff; background: rgba(40, 55, 47, .66); font-size: .62rem; font-weight: 600; }
.artifact-peek-pdf { flex: 1 1 auto; min-height: 0; padding: 1.1rem; }
.artifact-peek-pdf :deep(.pdf-thumbnail) { border-radius: .4rem; background: transparent; box-shadow: none; }
.artifact-peek-pdf :deep(canvas) { box-shadow: 0 8px 30px rgba(28, 37, 31, .16); }
.artifact-peek-page { flex: 1 1 auto; min-height: 0; margin: 1rem; padding: 1.4rem 1.7rem; overflow: hidden; border-radius: .35rem; background: #fff; box-shadow: 0 8px 30px rgba(28, 37, 31, .12); -webkit-mask-image: linear-gradient(#000 82%, transparent); mask-image: linear-gradient(#000 82%, transparent); }
.artifact-peek-page h1 { margin: 0 0 .7rem; font-size: 1.4rem; line-height: 1.15; letter-spacing: -.03em; }
.artifact-peek-page img { display: block; max-width: 100%; max-height: 16rem; margin: 0 0 .8rem; border-radius: .4rem; object-fit: contain; }
@keyframes peek-in { from { opacity: 0; } }
@media (prefers-reduced-motion: reduce) { .artifact-peek { animation: none; } }
</style>
