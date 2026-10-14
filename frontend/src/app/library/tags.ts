import { tagClient } from '../../api/client'
import type { AgentArtifact, LibraryItem, StaticAsset, Tag } from '../../api/types'
import { addTagPath } from '../../utils/tagAssignment'
import { staticAssets, staticAssetsView } from '../assets'
import { errorMessage, showNotice } from '../notice'
import type { DraggedResource } from '../types'
import { collapsedTagIds, collectionTags, collectionTarget, draggingLibraryItem, draggingStaticAsset, libraryItems, selectedLibraryItem, tagAssignmentBusy, tagDropTargetId, tagManagerBusy, tagManagerFeedback, tagManagerFeedbackKind, tagManagerOpen } from './state'

export function toggleTag(tagId: string): void {
  const next = new Set(collapsedTagIds.value)
  if (next.has(tagId)) next.delete(tagId)
  else next.add(tagId)
  collapsedTagIds.value = next
}
export async function createTag(path: string): Promise<void> {
  if (tagManagerBusy.value) return
  tagManagerFeedback.value = ''
  tagManagerBusy.value = true
  try {
    const created = await tagClient.create({ path, target: collectionTarget.value })
    await refreshTags()
    tagManagerFeedbackKind.value = 'success'
    tagManagerFeedback.value = `Created “${created.path}”.`
    showNotice(`Tag “${created.path}” added`)
  } catch (error) {
    const message = errorMessage(error)
    tagManagerFeedbackKind.value = 'error'
    tagManagerFeedback.value = message
    showNotice(message, 'error')
  } finally {
    tagManagerBusy.value = false
  }
}
export function openTagManager(): void {
  tagManagerFeedback.value = ''
  tagManagerFeedbackKind.value = 'success'
  tagManagerOpen.value = true
}
export function tagSubtreeContains(tag: Tag, tagId: string): boolean {
  return tag.id === tagId || tag.children.some((child) => tagSubtreeContains(child, tagId))
}
/** Reload the collection tree of the library being browsed. */
export async function loadCollectionTags(): Promise<void> {
  collectionTags.value = await tagClient.list(collectionTarget.value)
}
/** Refresh that tree after an assignment or a collection changes. */
export async function refreshTags(): Promise<void> {
  collectionTags.value = await tagClient.list(collectionTarget.value)
}
export function startLibraryItemDrag(item: LibraryItem, event: DragEvent): void {
  draggingLibraryItem.value = item
  tagDropTargetId.value = null
  if (!event.dataTransfer) return
  event.dataTransfer.effectAllowed = 'copy'
  event.dataTransfer.setData('application/x-zett-artifact-id', item.id)
  event.dataTransfer.setData('text/plain', item.id)
}
export function endLibraryItemDrag(): void {
  draggingLibraryItem.value = null
  tagDropTargetId.value = null
}
export function startStaticAssetDrag(asset: StaticAsset): void {
  draggingStaticAsset.value = asset
  tagDropTargetId.value = null
}
export function endStaticAssetDrag(): void {
  draggingStaticAsset.value = null
  tagDropTargetId.value = null
}
function draggedResource(event: DragEvent): DraggedResource | null {
  if (draggingLibraryItem.value) return { kind: 'artifact', item: draggingLibraryItem.value }
  if (draggingStaticAsset.value) return { kind: 'asset', asset: draggingStaticAsset.value }
  const artifactId = event.dataTransfer?.getData('application/x-zett-artifact-id')
    || event.dataTransfer?.getData('text/plain')
  const item = libraryItems.value.find((candidate) => candidate.id === artifactId)
  return item ? { kind: 'artifact', item } : null
}
export function handleTagDragOver(tag: Tag, event: DragEvent): void {
  const dragged = draggedResource(event)
  if (!dragged || tagAssignmentBusy.value) return
  event.preventDefault()
  if (event.dataTransfer) event.dataTransfer.dropEffect = 'copy'
  tagDropTargetId.value = tag.id
}
export function handleTagDragLeave(tag: Tag, event: DragEvent): void {
  const row = event.currentTarget
  if (row instanceof HTMLElement && event.relatedTarget instanceof Node && row.contains(event.relatedTarget)) return
  if (tagDropTargetId.value === tag.id) tagDropTargetId.value = null
}
function applyArtifactTags(artifact: AgentArtifact): void {
  const paths = artifact.tags.map((tag) => tag.path)
  const updateItem = (item: LibraryItem): LibraryItem => (
    item.id === artifact.id ? { ...item, tags: paths, updated_at: artifact.updated_at } : item
  )
  libraryItems.value = libraryItems.value.map(updateItem)
  if (selectedLibraryItem.value) selectedLibraryItem.value = updateItem(selectedLibraryItem.value)
}
export async function dropResourceOnTag(tag: Tag, event: DragEvent): Promise<void> {
  const dragged = draggedResource(event)
  if (!dragged || tagAssignmentBusy.value) return
  event.preventDefault()
  const current = dragged.kind === 'artifact' ? dragged.item.tags : dragged.asset.tags.map((item) => item.path)
  const assignment = addTagPath(current, tag.path)
  const label = dragged.kind === 'artifact' ? dragged.item.title : dragged.asset.name
  if (!assignment.changed) {
    showNotice(`“${label}” is already in ${tag.path}`)
    endLibraryItemDrag()
    endStaticAssetDrag()
    return
  }

  tagAssignmentBusy.value = true
  try {
    if (dragged.kind === 'artifact') {
      applyArtifactTags(await tagClient.replaceArtifactTags(dragged.item.id, assignment.paths))
    } else {
      applyAssetTags(await tagClient.replaceAssetTags(dragged.asset.id, assignment.paths))
    }
    await refreshTags()
    showNotice(`Added “${label}” to ${tag.path}`)
  } catch (error) {
    showNotice(errorMessage(error), 'error')
  } finally {
    tagAssignmentBusy.value = false
    endLibraryItemDrag()
    endStaticAssetDrag()
  }
}
/** Keep both asset lists in step: this view's, and the one the asset view owns. */
function applyAssetTags(asset: StaticAsset): void {
  staticAssets.value = staticAssets.value.map((item) => (item.id === asset.id ? asset : item))
  void staticAssetsView.value?.reload()
}
