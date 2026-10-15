import { aiClient } from '../api/client'
import type { SessionAsset, StaticAsset } from '../api/types'
import { assetDragging, assetEditorMode, assetName, assetUploading, assetValue, assets, staticAssetImportingId } from './assets'
import { attachPastedImages } from './composer/actions'
import { ensureConversation } from './conversation/turns'
import { t } from './i18n'
import { errorMessage, showNotice } from './notice'

export async function addInlineAsset(): Promise<void> {
  if (!assetName.value.trim() || !assetValue.value.trim()) return
  assetUploading.value = true
  try {
    const sessionId = await ensureConversation()
    const asset = assetEditorMode.value === 'link'
      ? await aiClient.createLinkAsset(sessionId, assetName.value.trim(), assetValue.value.trim())
      : await aiClient.createTextAsset(sessionId, assetName.value.trim(), assetValue.value)
    assets.value.push(asset)
    assetEditorMode.value = 'closed'
    assetName.value = ''
    assetValue.value = ''
  } catch (error) {
    showNotice(errorMessage(error), 'error')
  } finally {
    assetUploading.value = false
  }
}
export async function importStaticAsset(asset: StaticAsset): Promise<void> {
  if (staticAssetImportingId.value !== null) return
  staticAssetImportingId.value = asset.id
  try {
    const sessionId = await ensureConversation()
    const imported = await aiClient.importStaticAsset(sessionId, asset.id)
    assets.value.push(imported)
    showNotice(t('Referenced “{name}” from Static Assets', { name: asset.name }))
  } catch (error) {
    showNotice(errorMessage(error), 'error')
  } finally {
    staticAssetImportingId.value = null
  }
}
export async function uploadAssets(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const files = Array.from(input.files || [])
  await uploadAssetFiles(files)
  input.value = ''
}
async function uploadAssetFiles(files: File[]): Promise<void> {
  if (!files.length || assetUploading.value) return
  assetUploading.value = true
  try {
    const sessionId = await ensureConversation()
    for (const file of files) assets.value.push(await aiClient.uploadAsset(sessionId, file))
  } catch (error) {
    showNotice(errorMessage(error), 'error')
  } finally {
    assetUploading.value = false
  }
}
export async function dropAssets(event: DragEvent): Promise<void> {
  assetDragging.value = false
  await uploadAssetFiles(Array.from(event.dataTransfer?.files || []))
}
export async function pasteAssets(event: ClipboardEvent): Promise<void> {
  const clipboard = event.clipboardData
  if (!clipboard) return
  const itemFiles = Array.from(clipboard.items)
    .filter((item) => item.kind === 'file')
    .map((item) => item.getAsFile())
    .filter((file): file is File => file !== null)
  const files = itemFiles.length ? itemFiles : Array.from(clipboard.files)
  const target = event.target
  const insideComposer = target instanceof Element && target.closest('.agent-input textarea') !== null
  const editableTarget = target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement
  if (insideComposer && files.some((file) => file.type.startsWith('image/'))) {
    event.preventDefault()
    const position = target instanceof HTMLTextAreaElement ? target.selectionStart ?? target.value.length : 0
    await attachPastedImages(files, position)
    return
  }
  if (editableTarget && files.length) return
  if (files.length) {
    if (assetUploading.value) return
    event.preventDefault()
    await uploadAssetFiles(files)
    showNotice(`${files.length} pasted ${files.length === 1 ? 'asset' : 'assets'} added`)
    return
  }

  const insideAssetPane = target instanceof Element && target.closest('.assets-pane') !== null
  if (!insideAssetPane || editableTarget) return
  const content = clipboard.getData('text/plain').trim()
  if (!content) return
  event.preventDefault()
  assetUploading.value = true
  try {
    const sessionId = await ensureConversation()
    let asset: SessionAsset
    try {
      const url = new URL(content)
      asset = await aiClient.createLinkAsset(sessionId, url.hostname || 'Pasted link', url.toString())
    } catch {
      const timestamp = new Date().toISOString().slice(0, 19).replaceAll(':', '-')
      asset = await aiClient.createTextAsset(sessionId, `Pasted note ${timestamp}`, content)
    }
    assets.value.push(asset)
    showNotice('Pasted asset added')
  } catch (error) {
    showNotice(errorMessage(error), 'error')
  } finally {
    assetUploading.value = false
  }
}
