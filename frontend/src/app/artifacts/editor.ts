import { libraryClient } from '../../api/client'
import type { AgentArtifact, LibraryItem, LibraryItemUpdate } from '../../api/types'
import { artifactContentFromLibraryUpdate, artifactEditableContent, libraryItemFromArtifact } from '../../utils/artifactEditor'
import { artifactTypeLabel } from '../format'
import { libraryEditorArtifactId, libraryEditorItem, libraryEditorSaving, libraryItems, selectedLibraryItem } from '../library/state'
import { refreshTags } from '../library/tags'
import { errorMessage, requestConfirmation, showNotice } from '../notice'
import { selectArtifact, syncSelectedArtifactDraft } from './actions'
import { artifactContent, artifactDiff, artifactPreview, artifacts, selectedArtifact } from './state'

export function openLibraryEditor(item: LibraryItem): void {
  if (item.item_type === 'latex_pdf') return
  selectedLibraryItem.value = null
  libraryEditorArtifactId.value = null
  libraryEditorItem.value = item
}
function openSelectedArtifactEditor(): void {
  const artifact = selectedArtifact.value
  if (!artifact) return
  const item = libraryItemFromArtifact(artifact)
  if (!item) return
  libraryEditorArtifactId.value = artifact.id
  libraryEditorItem.value = item
}
export function editArtifactFromList(artifact: AgentArtifact): void {
  selectArtifact(artifact)
  if (['card', 'article', 'slides'].includes(artifact.artifact_type)) {
    openSelectedArtifactEditor()
    return
  }
  artifactPreview.value = false
  artifactDiff.value = false
}
export async function closeLibraryEditor(dirty: boolean): Promise<void> {
  if (libraryEditorSaving.value) return
  if (dirty) {
    const confirmed = await requestConfirmation(
      'Discard unsaved changes?',
      'Your edits have not been saved. Leaving the editor will discard them.',
      'Discard changes',
    )
    if (!confirmed) return
  }
  libraryEditorItem.value = null
  libraryEditorArtifactId.value = null
}
export async function saveLibraryEditor(payload: LibraryItemUpdate): Promise<void> {
  const item = libraryEditorItem.value
  if (!item || libraryEditorSaving.value) return
  libraryEditorSaving.value = true
  try {
    const artifactId = libraryEditorArtifactId.value
    if (artifactId !== null) {
      const artifact = artifacts.value.find((candidate) => candidate.id === artifactId)
      if (!artifact) return
      const content = artifactEditableContent(artifact)
      if (!content) return
      artifactContent.value = artifactContentFromLibraryUpdate(content, payload)
      // The editor stages the draft; publishing stays a separate action.
      await syncSelectedArtifactDraft()
      const updated = artifacts.value.find((candidate) => candidate.id === artifactId)
      const updatedItem = updated ? libraryItemFromArtifact(updated) : null
      if (updatedItem) libraryEditorItem.value = updatedItem
      showNotice('Draft updated — review the diff and save to publish it')
      return
    }

    const updated = await libraryClient.update(item.item_type, item.id, payload)
    libraryItems.value = libraryItems.value.map((candidate) => (
      candidate.item_type === updated.item_type && candidate.id === updated.id ? updated : candidate
    ))
    libraryEditorItem.value = updated
    if (selectedLibraryItem.value?.item_type === updated.item_type && selectedLibraryItem.value.id === updated.id) {
      selectedLibraryItem.value = updated
    }
    await refreshTags()
    showNotice(`${artifactTypeLabel(updated.item_type)} saved`)
  } catch (error) {
    showNotice(errorMessage(error), 'error')
  } finally {
    libraryEditorSaving.value = false
  }
}
