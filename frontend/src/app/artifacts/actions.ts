import { aiClient } from '../../api/client'
import type { AgentArtifact, CardStatus } from '../../api/types'
import { artifactEditableContent } from '../../utils/artifactEditor'
import { MIN_ARTIFACT_LIST_HEIGHT, clampArtifactListHeight } from '../../utils/artifactSplit'
import { artifactListsEquivalent, sameArtifactRevision, stabilizeArtifactReferences } from '../../utils/artifactStability'
import { createAsyncRefreshScheduler } from '../../utils/asyncRefresh'
import { jsonSnapshot } from '../../utils/jsonSnapshot'
import { assets } from '../assets'
import { artifactTitle, artifactTypeLabel } from '../format'
import { announceCardStatus, loadLibrary, markCardStatusUpdating } from '../library/actions'
import { cardStatusUpdatingIds } from '../library/state'
import { refreshTags } from '../library/tags'
import { errorMessage, requestConfirmation, showNotice } from '../notice'
import { conversationId } from '../sessions'
import { artifactContent, artifactDiff, artifactHeaderRef, artifactListHeight, artifactPaneRef, artifactPreview, artifactPreviewNonce, artifactRefreshing, artifacts, artifactsNeedingSave, artifactsScratch, saving, savingAllArtifacts, selectedArtifact, selectedArtifactId, selectedSuggestions } from './state'

export function setArtifactListHeight(height: number): void {
  const pane = artifactPaneRef.value
  const header = artifactHeaderRef.value
  if (!pane || !header) return
  const bounded = clampArtifactListHeight(height, pane.clientHeight, header.offsetHeight)
  if (artifactListHeight.value !== bounded) artifactListHeight.value = bounded
}
export function startArtifactSplit(event: PointerEvent): void {
  if (event.button !== 0) return
  const pane = artifactPaneRef.value
  if (!pane) return
  event.preventDefault()
  artifactsScratch.artifactSplitPointer = event.pointerId
  artifactsScratch.artifactSplitStartY = event.clientY
  artifactsScratch.artifactSplitStartHeight = pane.querySelector('.artifact-list')?.getBoundingClientRect().height ?? MIN_ARTIFACT_LIST_HEIGHT
  ;(event.currentTarget as HTMLElement).setPointerCapture(event.pointerId)
}
export function moveArtifactSplit(event: PointerEvent): void {
  if (artifactsScratch.artifactSplitPointer !== event.pointerId) return
  setArtifactListHeight(artifactsScratch.artifactSplitStartHeight + event.clientY - artifactsScratch.artifactSplitStartY)
}
export function endArtifactSplit(event: PointerEvent): void {
  if (artifactsScratch.artifactSplitPointer !== event.pointerId) return
  artifactsScratch.artifactSplitPointer = null
}
export function keyArtifactSplit(event: KeyboardEvent): void {
  const list = artifactPaneRef.value?.querySelector('.artifact-list')
  if (!list || !['ArrowUp', 'ArrowDown', 'Home', 'End'].includes(event.key)) return
  event.preventDefault()
  const current = list.getBoundingClientRect().height
  const desired = event.key === 'Home' ? 0 : event.key === 'End' ? Number.MAX_SAFE_INTEGER
    : current + (event.key === 'ArrowDown' ? 32 : -32)
  setArtifactListHeight(desired)
}
export const agentResourceRefresh = createAsyncRefreshScheduler(
  async (sessionId: string) => {
    const [currentArtifacts, currentAssets] = await Promise.all([
      aiClient.listAgentArtifacts(sessionId),
      aiClient.listSessionAssets(sessionId),
    ])
    if (conversationId.value === sessionId) {
      applyArtifacts(currentArtifacts)
      assets.value = currentAssets
    }
  },
  (error, sessionId) => {
    if (conversationId.value === sessionId) showNotice(errorMessage(error), 'error')
  },
)
/** Move a conversation's card to a new status, without touching its draft. */
export async function setConversationCardStatus(artifact: AgentArtifact, status: CardStatus): Promise<void> {
  const activeConversationId = conversationId.value
  if (!activeConversationId || cardStatusUpdatingIds.value.has(artifact.id)) return
  markCardStatusUpdating(artifact.id, true)
  try {
    const updated = await aiClient.setAgentCardStatus(activeConversationId, artifact.id, status)
    if (conversationId.value !== activeConversationId) return
    const index = artifacts.value.findIndex((candidate) => candidate.id === updated.id)
    // Replace only the status: a refresh built from this response would also
    // reset the draft the editor is showing if the model changed it meanwhile.
    if (index >= 0) artifacts.value.splice(index, 1, { ...artifacts.value[index]!, card_status: updated.card_status, updated_at: updated.updated_at })
    announceCardStatus(artifactTitle(artifactEditableContent(updated)), status)
    void loadLibrary()
  } catch (error) {
    showNotice(errorMessage(error), 'error')
  } finally {
    markCardStatusUpdating(artifact.id, false)
  }
}
export function selectArtifact(artifact: AgentArtifact): void {
  const artifactChanged = selectedArtifactId.value !== artifact.id
  const current = selectedArtifact.value
  if (!artifactChanged && current && artifactContent.value && sameArtifactRevision(current, artifact)) return
  const content = artifactEditableContent(artifact)
  if (!content) return
  selectedArtifactId.value = artifact.id
  artifactContent.value = jsonSnapshot(content)
  selectedSuggestions.value = content.artifact_type === 'latex_pdf' ? [] : content.suggested_tags.map((tag) => tag.path)
  if (artifactChanged) {
    artifactPreview.value = true
    artifactDiff.value = false
  }
}
export function applyArtifacts(nextArtifacts: AgentArtifact[], preferLatest = true): void {
  const stableArtifacts = stabilizeArtifactReferences(artifacts.value, nextArtifacts)
  if (artifactListsEquivalent(artifacts.value, stableArtifacts)) return
  artifacts.value = stableArtifacts
  if (!stableArtifacts.length) {
    selectedArtifactId.value = null
    artifactContent.value = null
    return
  }
  const current = stableArtifacts.find((artifact) => artifact.id === selectedArtifactId.value)
  const target = preferLatest
    ? [...stableArtifacts].sort((left, right) => right.updated_at.localeCompare(left.updated_at))[0]
    : current || stableArtifacts[0]
  if (target) selectArtifact(target)
}
async function refreshArtifacts(preferLatest = false): Promise<void> {
  const activeConversationId = conversationId.value
  if (!activeConversationId) return
  const listed = await aiClient.listAgentArtifacts(activeConversationId)
  // A conversation switch while this request was open must not move another session's artifacts into view.
  if (conversationId.value !== activeConversationId) return
  applyArtifacts(listed, preferLatest)
}
/**
 * Re-read the conversation's artifacts and force the preview to load again, so a
 * PDF compiled after the pane opened replaces the bytes shown in the pane.
 */
export async function refreshSelectedArtifact(): Promise<void> {
  const activeConversationId = conversationId.value
  if (!activeConversationId || artifactRefreshing.value) return
  artifactRefreshing.value = true
  try {
    const listed = await aiClient.listAgentArtifacts(activeConversationId)
    if (conversationId.value !== activeConversationId) return
    applyArtifacts(listed)
    artifactPreviewNonce.value += 1
  } catch (error) {
    showNotice(errorMessage(error), 'error')
  } finally {
    artifactRefreshing.value = false
  }
}
export async function refreshArtifactsAfterTurn(sessionId: string | null): Promise<void> {
  if (!sessionId) return
  await agentResourceRefresh.whenIdle()
  if (conversationId.value !== sessionId) return
  try {
    await refreshArtifacts(true)
  } catch (error) {
    showNotice(errorMessage(error), 'error')
  }
}
/**
 * Persist the panel's edits as a draft. Editing never rewrites published
 * content; the save action is what publishes a draft.
 */
export async function syncSelectedArtifactDraft(): Promise<void> {
  const current = selectedArtifact.value
  if (!conversationId.value || !selectedArtifactId.value || !artifactContent.value || !current) return
  const updated = await aiClient.updateAgentArtifactDraft(
    conversationId.value,
    selectedArtifactId.value,
    artifactContent.value,
  )
  const index = artifacts.value.findIndex((artifact) => artifact.id === updated.id)
  if (index >= 0) artifacts.value.splice(index, 1, updated)
}
export async function saveSelectedArtifact(artifact: AgentArtifact | null = selectedArtifact.value): Promise<boolean> {
  if (savingAllArtifacts.value || saving.value) return false
  const artifactId = artifact?.id
  const activeConversationId = conversationId.value
  const isSelected = artifactId === selectedArtifactId.value
  const currentContent = isSelected ? artifactContent.value : artifact ? artifactEditableContent(artifact) : null
  const editorSnapshot = currentContent ? JSON.stringify(currentContent) : null
  const content = currentContent ? jsonSnapshot(currentContent) : null
  if (!content || !activeConversationId || !artifactId) return false
  saving.value = true
  try {
    if (isSelected && content.artifact_type !== 'latex_pdf') {
      content.suggested_tags = content.suggested_tags.filter((tag) => selectedSuggestions.value.includes(tag.path))
    }
    if (isSelected) {
      const updated = await aiClient.updateAgentArtifactDraft(activeConversationId, artifactId, content)
      if (conversationId.value !== activeConversationId) return false
      const draftIndex = artifacts.value.findIndex(item => item.id === updated.id)
      if (draftIndex >= 0) artifacts.value.splice(draftIndex, 1, updated)
    }
    const saved = await aiClient.saveAgentArtifact(activeConversationId, artifactId)
    if (conversationId.value !== activeConversationId) return false
    const index = artifacts.value.findIndex((artifact) => artifact.id === saved.id)
    if (index >= 0) artifacts.value.splice(index, 1, saved)
    if (isSelected && selectedArtifactId.value === artifactId
      && JSON.stringify(artifactContent.value) === editorSnapshot) {
      artifactContent.value = jsonSnapshot(saved.content)
      // The published draft is gone, so leave the comparison view.
      artifactDiff.value = false
    }
    if (content.artifact_type !== 'image') {
      await loadLibrary()
      await refreshTags()
    }
    showNotice(
      content.artifact_type === 'image'
        ? 'Image changes saved'
        : `${artifactTypeLabel(content.artifact_type)} saved to artifacts`,
    )
    return true
  } catch (error) {
    showNotice(errorMessage(error), 'error')
    return false
  } finally {
    saving.value = false
  }
}
export async function saveAllArtifacts(): Promise<void> {
  const sessionId = conversationId.value
  if (!sessionId || saving.value || savingAllArtifacts.value) return
  const pending = [...artifactsNeedingSave.value]
  if (!pending.length) {
    showNotice('All artifacts are already saved')
    return
  }
  savingAllArtifacts.value = true
  const selectedId = selectedArtifactId.value
  const selectedDraft = selectedId && artifactContent.value ? jsonSnapshot(artifactContent.value) : null
  let savedCount = 0
  const failed: string[] = []
  try {
    for (const artifact of pending) {
      if (conversationId.value !== sessionId) break
      try {
        // Save All must include an edit still open in the selected editor.
        if (artifact.id === selectedId && selectedDraft) {
          const updated = await aiClient.updateAgentArtifactDraft(sessionId, artifact.id, selectedDraft)
          if (conversationId.value !== sessionId) break
          const draftIndex = artifacts.value.findIndex(item => item.id === updated.id)
          if (draftIndex >= 0) artifacts.value.splice(draftIndex, 1, updated)
        }
        if (conversationId.value !== sessionId) break
        const saved = await aiClient.saveAgentArtifact(sessionId, artifact.id)
        if (conversationId.value !== sessionId) break
        const index = artifacts.value.findIndex(item => item.id === saved.id)
        if (index >= 0) artifacts.value.splice(index, 1, saved)
        // An edit typed during the request must remain in the editor for a later save.
        if (selectedArtifactId.value === saved.id && selectedDraft
          && JSON.stringify(artifactContent.value) === JSON.stringify(selectedDraft)) {
          artifactContent.value = jsonSnapshot(saved.content)
          artifactDiff.value = false
        }
        savedCount += 1
      } catch (error) {
        failed.push(`${artifactTitle(artifactEditableContent(artifact))}: ${errorMessage(error)}`)
      }
    }
    if (savedCount && conversationId.value === sessionId) {
      await loadLibrary()
      await refreshTags()
    }
    if (conversationId.value !== sessionId) return
    showNotice(
      failed.length
        ? `Saved ${savedCount} of ${pending.length}. Failed: ${failed.join('; ')}`
        : `Saved ${savedCount} artifact${savedCount === 1 ? '' : 's'}`,
      failed.length ? 'error' : 'success',
    )
  } finally {
    savingAllArtifacts.value = false
  }
}
export async function deleteSelectedArtifact(artifact: AgentArtifact | null = selectedArtifact.value): Promise<void> {
  const sessionId = conversationId.value
  if (!sessionId || !artifact || saving || savingAllArtifacts.value) return
  const title = artifactEditableContent(artifact)
  const name = title?.artifact_type === 'latex_pdf' ? title.pdf_name : title?.title || 'Untitled artifact'
  const confirmed = await requestConfirmation(
    'Delete this artifact?',
    `“${name}” will be permanently removed from this conversation. A linked artifact will also be deleted.`,
    'Delete artifact',
  )
  if (!confirmed || conversationId.value !== sessionId || saving || savingAllArtifacts.value) return
  try {
    await aiClient.deleteAgentArtifact(sessionId, artifact.id)
    if (conversationId.value !== sessionId) return
    await refreshArtifacts(false)
    showNotice('Artifact deleted')
  } catch (error) {
    showNotice(errorMessage(error), 'error')
  }
}
