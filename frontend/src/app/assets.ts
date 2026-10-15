import { computed, nextTick, ref } from 'vue'
import { aiClient, assetClient } from '../api/client'
import type { MessageImagePart, SessionAsset, StaticAsset } from '../api/types'
import { assetOpenAction } from '../utils/assetOpen'
import { readPaneHidden, writePaneHidden } from '../utils/paneVisibility'
import { classifyAsset } from './format'
import { errorMessage, requestConfirmation, showNotice } from './notice'
import { conversationId } from './sessions'
import type { AssetEditorMode, AssetFilter } from './types'

export const assets = ref<SessionAsset[]>([])
export const previewAsset = ref<SessionAsset | null>(null)
export const assetEditorMode = ref<AssetEditorMode>('closed')
export const assetName = ref('')
export const assetValue = ref('')
export const assetUploading = ref(false)
export const assetQuery = ref('')
export const assetFilter = ref<AssetFilter>('all')
export const assetDragging = ref(false)
const assetsPaneKey = 'zett.assets-pane-hidden'
export const assetsPaneHidden = ref(readPaneHidden(assetsPaneKey))
//: The artifact pane's preview, which refits its pages when this pane changes width.
export const pdfPreviewRef = ref<{ refit: () => void } | null>(null)
export const staticAssetImportOpen = ref(false)
export const staticAssets = ref<StaticAsset[]>([])
export const staticAssetsView = ref<{ reload: () => Promise<void> } | null>(null)
export const staticAssetsLoading = ref(false)
export const staticAssetImportingId = ref<string | null>(null)
export const assetFileInput = ref<HTMLInputElement | null>(null)
export const assetFilters: Array<{ value: AssetFilter; label: string }> = [
  { value: 'all', label: 'All' },
  { value: 'documents', label: 'Documents' },
  { value: 'images', label: 'Images' },
  { value: 'links', label: 'Links' },
  { value: 'notes', label: 'Notes' },
  { value: 'code', label: 'Code' },
]
export const filteredAssets = computed(() => {
  const normalizedQuery = assetQuery.value.trim().toLowerCase()
  return [...assets.value]
    .filter((asset) => (
      (!normalizedQuery
        || asset.name.toLowerCase().includes(normalizedQuery)
        || asset.source_url?.toLowerCase().includes(normalizedQuery))
      && (assetFilter.value === 'all' || classifyAsset(asset) === assetFilter.value)
    ))
    .sort((left, right) => right.created_at.localeCompare(left.created_at))
})
export const importedStaticAssetIds = computed(() => assets.value.flatMap((asset) => (
  typeof asset.metadata.static_asset_id === 'string' ? [asset.metadata.static_asset_id] : []
)))
export function showAssetEditor(mode: Exclude<AssetEditorMode, 'closed'>): void {
  assetEditorMode.value = assetEditorMode.value === mode ? 'closed' : mode
  assetName.value = ''
  assetValue.value = ''
}
export function toggleAssetsPane(hidden: boolean): void {
  assetsPaneHidden.value = hidden
  writePaneHidden(assetsPaneKey, hidden)
  // The preview must refit before this frame paints: a resize observer reports the new
  // stage width only after the wrong-scale frame is already on screen.
  void nextTick().then(() => pdfPreviewRef.value?.refit())
}
export async function openStaticAssetImport(): Promise<void> {
  staticAssetImportOpen.value = true
  staticAssetsLoading.value = true
  try {
    staticAssets.value = await assetClient.list()
  } catch (error) {
    showNotice(errorMessage(error), 'error')
  } finally {
    staticAssetsLoading.value = false
  }
}
export async function renameAsset(asset: SessionAsset, name: string): Promise<void> {
  const updated = await aiClient.renameSessionAsset(asset.session_id, asset.id, name)
  // A late response from a previous session must not change the visible list.
  if (conversationId.value !== asset.session_id) return
  assets.value = assets.value.map(item => item.id === asset.id ? updated : item)
  if (previewAsset.value?.id === asset.id) previewAsset.value = updated
}
export function openAsset(asset: SessionAsset): void {
  const action = assetOpenAction(asset)
  if (!action) return
  if (action.kind === 'preview') {
    previewAsset.value = asset
    return
  }
  window.open(action.url, '_blank', 'noopener,noreferrer')
}
export function openImagePreview(image: { name: string; url: string }): void {
  previewAsset.value = {
    id: `message-image-${image.name}`,
    session_id: conversationId.value || '',
    asset_type: 'image',
    name: image.name,
    mime_type: null,
    size_bytes: 0,
    sha256: null,
    text_content: null,
    source_url: null,
    storage_path: null,
    source_path: null,
    content_url: image.url,
    metadata: {},
    created_at: '',
    updated_at: '',
  }
}
export function openMessageImage(part: MessageImagePart): void {
  openImagePreview({ name: part.name, url: part.content_url })
}
export async function removeAsset(asset: SessionAsset): Promise<void> {
  if (!conversationId.value) return
  const message = asset.metadata.import_mode === 'object'
    ? `“${asset.name}” will be removed from this conversation. The Static Asset itself will remain available.`
    : `“${asset.name}” will be removed from this conversation and its local file will be deleted.`
  const confirmed = await requestConfirmation(
    'Delete this asset?',
    message,
    'Delete asset',
  )
  if (!confirmed) return
  try {
    await aiClient.deleteSessionAsset(conversationId.value, asset.id)
    assets.value = assets.value.filter((item) => item.id !== asset.id)
    if (previewAsset.value?.id === asset.id) previewAsset.value = null
  } catch (error) {
    showNotice(errorMessage(error), 'error')
  }
}
