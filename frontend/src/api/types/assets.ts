import type { SessionAssetType } from './common'

export interface SessionAsset {
  id: string
  session_id: string
  asset_type: SessionAssetType
  name: string
  mime_type: string | null
  size_bytes: number
  sha256: string | null
  /** Inline content stored directly in the database; no file URL exists. */
  text_content: string | null
  /** External URL only. It is not an ObjectStore key. */
  source_url: string | null
  /**
   * Relative ObjectKey for bytes owned by this asset.
   * Example: `assets/sessions/<session_id>/<asset_id>.png`.
   */
  storage_path: string | null
  /**
   * Relative ObjectKey for another stored object referenced by this asset.
   * Importing a StaticAsset stores `assets/static/<asset_id>.pdf` here.
   */
  source_path: string | null
  /**
   * Response-only URL derived from `storage_path` or `source_path`.
   * Example: `/api/files/assets/static/<asset_id>.pdf`. Never persisted.
   */
  content_url: string | null
  metadata: Record<string, unknown>
  created_at: string
  updated_at: string
}

export interface StaticAsset {
  id: string
  name: string
  mime_type: string | null
  size_bytes: number
  sha256: string
  /**
   * Relative ObjectKey for the globally owned file.
   * Example: `assets/static/<asset_id>.pdf`.
   */
  storage_path: string
  /** Derived `/api/files/...` URL; clients should not construct it themselves. */
  content_url: string
  metadata: Record<string, unknown>
  /** Confirmed library tags; the same taxonomy artifacts carry. */
  tags: Array<{ id: string; path: string; name: string }>
  created_at: string
  updated_at: string
}
