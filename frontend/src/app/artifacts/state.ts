import { computed, ref } from 'vue'
import type { AgentArtifact, ArtifactContent } from '../../api/types'
import { diffArtifactContent } from '../../utils/artifactDiff'
import { artifactEditableContent } from '../../utils/artifactEditor'
import { artifactImageUrl, versionedPreviewUrl } from '../../utils/artifactPreview'
import { clampArtifactListWidth, parseArtifactListWidth } from '../../utils/artifactSplit'
import { pendingArtifactSaves } from '../../utils/artifactSaveAll'
import { readStored } from '../../utils/workspaceLayout'

export const artifactContent = ref<ArtifactContent | null>(null)
export const artifactPreview = ref(true)
// Bumped on refresh so a recompiled PDF is fetched again instead of reusing cached bytes.
export const artifactPreviewNonce = ref(0)
export const artifactRefreshing = ref(false)
/** Show the draft-versus-published diff instead of the editor or preview. */
export const artifactDiff = ref(false)
export const artifacts = ref<AgentArtifact[]>([])
export const selectedArtifactId = ref<string | null>(null)
export const artifactPaneRef = ref<HTMLElement | null>(null)
export const ARTIFACT_LIST_WIDTH_KEY = 'zett.artifact-list-width'
/** The width the user chose; only a drag or the keyboard writes it, so a narrow pane never erases it. */
export const artifactListWidth = ref<number | null>(parseArtifactListWidth(readStored(ARTIFACT_LIST_WIDTH_KEY)))
/** The pane's measured width, 0 while it is hidden. */
export const artifactPaneWidth = ref(0)
/** The preference fitted to the current pane; null leaves the stylesheet's default. */
export const appliedArtifactListWidth = computed(() => {
  if (artifactListWidth.value === null || artifactPaneWidth.value === 0) return artifactListWidth.value
  return clampArtifactListWidth(artifactListWidth.value, artifactPaneWidth.value)
})
export const artifactsScratch = {
  artifactSplitPointer: null as number | null,
  artifactSplitStartX: 0,
  artifactSplitStartWidth: 0,
  artifactPaneResizeObserver: null as ResizeObserver | null,
}
//: True until the persisted conversation, including its artifacts, has loaded.
export const workspaceRestoring = ref(true)
export const saving = ref(false)
export const savingAllArtifacts = ref(false)
//: The editor holds edits nothing has stored yet, so the saved look would overstate it.
export const selectedArtifactDirty = computed(() => {
  const selected = selectedArtifact.value
  return Boolean(selected && artifactContent.value
    && JSON.stringify(artifactContent.value) !== JSON.stringify(artifactEditableContent(selected)))
})
export const artifactsNeedingSave = computed(() => {
  const pending = pendingArtifactSaves(artifacts.value)
  const selected = selectedArtifact.value
  if (selected && artifactContent.value && !pending.some(item => item.id === selected.id)
    && JSON.stringify(artifactContent.value) !== JSON.stringify(artifactEditableContent(selected))) {
    pending.push(selected)
  }
  return pending
})
export const selectedSuggestions = ref<string[]>([])
export const selectedArtifact = computed(() => artifacts.value.find((artifact) => artifact.id === selectedArtifactId.value) || null)
/**
 * The artifact pane's preview source. The nonce makes every refresh a new URL,
 * because recompiling replaces the PDF bytes without changing the artifact row.
 */
export const artifactPreviewAsset = computed(() => {
  const artifact = selectedArtifact.value
  if (!artifact) return artifact
  return { ...artifact, content_url: versionedPreviewUrl(artifact.content_url, artifactPreviewNonce.value) }
})
export const selectedArtifactDiff = computed(() => diffArtifactContent(
  selectedArtifact.value?.content ?? null,
  selectedArtifact.value?.draft_content ?? null,
))
export const selectedImageUrl = computed(() => {
  return artifactImageUrl(artifactContent.value, selectedArtifact.value)
})
