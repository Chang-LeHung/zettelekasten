import type { ArtifactContent, LibraryItem, SessionAsset } from '../api/types'
import { isPdfAsset } from '../utils/assetOpen'
import { libraryExcerptText } from '../utils/libraryExcerpt'
import { parseUtcTimestamp } from '../utils/timestamps'
import { locale, t } from './i18n'
import type { AssetFilter } from './types'

export const DEFAULT_SESSION_TITLE = '新会话'
export function artifactTypeLabel(type: ArtifactContent['artifact_type']): string {
  return ({ card: 'Card', article: 'Article', image: 'Image', slides: 'Slides', latex_pdf: 'LaTeX PDF' })[type]
}
export function artifactTitle(content: ArtifactContent | null): string {
  if (!content) return 'Untitled artifact'
  return content.artifact_type === 'latex_pdf' ? content.pdf_name.replace(/\.pdf$/, '') : content.title
}
export function libraryExcerpt(item: LibraryItem): string {
  const source = item.summary || (item.item_type === 'slides' ? item.subtitle : '') || item.content
  return libraryExcerptText(source) || 'Open to explore this item.'
}
/** Stagger a freshly filtered grid so it blooms instead of snapping in at once. */
export function cardFloatDelay(index: number): string {
  return `${Math.min(index, 8) * 40}ms`
}
/**
 * Stop an inner control's key from also activating the card, without swallowing
 * Escape: the global handler owns it, and a focused card button must not hide it.
 */
export function stopCardKey(event: KeyboardEvent): void {
  if (event.key !== 'Escape') event.stopPropagation()
}
export function isEditableTarget(target: EventTarget | null): boolean {
  return target instanceof HTMLElement && Boolean(target.closest('input, textarea, select, [contenteditable="true"]'))
}
export function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError'
}
export function formatBytes(value: number): string {
  if (value < 1024) return `${value} B`
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`
  return `${(value / (1024 * 1024)).toFixed(1)} MB`
}
export function assetExtension(asset: SessionAsset): string {
  const extension = asset.name.split('.').pop()
  if (extension && extension !== asset.name && extension.length <= 5) return extension.toUpperCase()
  if (asset.asset_type === 'image') return 'IMG'
  if (asset.asset_type === 'link') return 'URL'
  if (asset.asset_type === 'text') return 'TXT'
  return 'FILE'
}
export function classifyAsset(asset: SessionAsset): Exclude<AssetFilter, 'all'> {
  if (asset.asset_type === 'image' || asset.mime_type?.startsWith('image/')) return 'images'
  if (asset.metadata.import_mode === 'object' && isPdfAsset(asset)) return 'documents'
  if (asset.asset_type === 'link') return 'links'
  const extension = asset.name.split('.').pop()?.toLowerCase() || ''
  const codeExtensions = new Set(['py', 'js', 'ts', 'tsx', 'jsx', 'vue', 'json', 'yaml', 'yml', 'toml', 'sh', 'sql', 'html', 'css'])
  if (codeExtensions.has(extension) || /javascript|typescript|json|python|shell|yaml|xml/.test(asset.mime_type || '')) return 'code'
  if (asset.asset_type === 'text' || extension === 'md' || asset.mime_type === 'text/markdown') return 'notes'
  return 'documents'
}
export function assetTypeLabel(asset: SessionAsset): string {
  const category = classifyAsset(asset)
  if (category === 'images') return 'Image'
  if (category === 'links') return 'Link'
  if (category === 'notes') return 'Note'
  if (category === 'code') return 'Code'
  return 'Document'
}
export function assetSourceLabel(asset: SessionAsset): string | null {
  if (asset.metadata.import_mode === 'object') return t('Static asset')
  if (!asset.source_url) return null
  try {
    return new URL(asset.source_url).hostname
  } catch {
    return asset.source_url
  }
}
export function formatAssetDate(value: string): string {
  return new Intl.DateTimeFormat(undefined, {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(parseUtcTimestamp(value))
}
export function formatDate(value: string): string {
  return new Intl.DateTimeFormat(locale.value === 'zh' ? 'zh-CN' : 'en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  }).format(parseUtcTimestamp(value))
}
export function formatDateTime(value: string): string {
  return new Intl.DateTimeFormat(locale.value === 'zh' ? 'zh-CN' : 'en-US', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(parseUtcTimestamp(value))
}
