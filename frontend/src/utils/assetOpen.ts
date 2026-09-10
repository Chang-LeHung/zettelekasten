import type { SessionAsset } from '../api/types'

export type AssetOpenAction =
  | { kind: 'preview'; preview: 'image'; url: string }
  | { kind: 'preview'; preview: 'text' }
  | { kind: 'external'; url: string }

/** Select the UI behavior for an asset without performing the side effect. */
export function assetOpenAction(asset: SessionAsset): AssetOpenAction | null {
  if (asset.asset_type === 'text' && asset.text_content !== null) {
    return { kind: 'preview', preview: 'text' }
  }

  const url = asset.source_url || asset.content_url
  if (!url) return null

  const isImage = asset.asset_type === 'image' || asset.mime_type?.startsWith('image/') === true
  return isImage ? { kind: 'preview', preview: 'image', url } : { kind: 'external', url }
}
