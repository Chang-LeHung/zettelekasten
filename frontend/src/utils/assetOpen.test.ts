import { describe, expect, it } from 'vitest'
import type { SessionAsset } from '../api/types'
import { assetOpenAction } from './assetOpen'

function asset(overrides: Partial<SessionAsset>): SessionAsset {
  return {
    id: 'asset-1',
    session_id: 'session-1',
    asset_type: 'file',
    name: 'reference.bin',
    mime_type: 'application/octet-stream',
    size_bytes: 10,
    sha256: null,
    text_content: null,
    source_url: null,
    content_url: '/api/assets/asset-1/content',
    metadata: {},
    created_at: '2026-09-10T00:00:00Z',
    updated_at: '2026-09-10T00:00:00Z',
    ...overrides,
  }
}

describe('asset open action', () => {
  it('previews assets explicitly classified as images', () => {
    expect(assetOpenAction(asset({ asset_type: 'image', mime_type: 'image/png' }))).toEqual({
      kind: 'preview',
      preview: 'image',
      url: '/api/assets/asset-1/content',
    })
  })

  it('previews inline text without requiring a content URL', () => {
    expect(assetOpenAction(asset({
      asset_type: 'text',
      content_url: null,
      text_content: 'A persisted note',
    }))).toEqual({ kind: 'preview', preview: 'text' })
  })

  it('previews image MIME types even when stored as generic files', () => {
    expect(assetOpenAction(asset({ mime_type: 'image/webp' }))?.kind).toBe('preview')
  })

  it('opens links and non-image files externally', () => {
    expect(assetOpenAction(asset({ asset_type: 'link', source_url: 'https://example.com' }))).toEqual({
      kind: 'external',
      url: 'https://example.com',
    })
    expect(assetOpenAction(asset({}))?.kind).toBe('external')
  })

  it('does nothing when an asset has no accessible URL', () => {
    expect(assetOpenAction(asset({ content_url: null, source_url: null }))).toBeNull()
  })
})
