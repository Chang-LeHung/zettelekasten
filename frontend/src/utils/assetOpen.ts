import type { SessionAsset } from '../api/types'

export type AssetOpenAction =
  | { kind: 'preview'; preview: 'image'; url: string }
  | { kind: 'preview'; preview: 'pdf'; url: string }
  | { kind: 'preview'; preview: 'text' }
  | { kind: 'external'; url: string }

/** Return whether the asset can be rendered by the built-in PDF viewer. */
export function isPdfAsset(asset: Pick<SessionAsset, 'mime_type' | 'name'>): boolean {
  return asset.mime_type === 'application/pdf' || asset.name.toLowerCase().endsWith('.pdf')
}

/** Select the UI behavior for an asset without performing the side effect. */
export function assetOpenAction(asset: SessionAsset): AssetOpenAction | null {
  if (asset.asset_type === 'text' && asset.text_content !== null) {
    return { kind: 'preview', preview: 'text' }
  }

  const url = asset.source_url || asset.content_url
  if (!url) return null

  const isImage = asset.asset_type === 'image' || asset.mime_type?.startsWith('image/') === true
  if (isImage) return { kind: 'preview', preview: 'image', url }

  return isPdfAsset(asset) ? { kind: 'preview', preview: 'pdf', url } : { kind: 'external', url }
}
