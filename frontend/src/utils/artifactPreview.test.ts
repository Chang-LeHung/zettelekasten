import { describe, expect, it } from 'vitest'

import { artifactImageUrl, versionedPreviewUrl } from './artifactPreview'

describe('versioned preview urls', () => {
  it('adds the revision to a plain object url', () => {
    expect(versionedPreviewUrl('/api/files/artifacts/session/paper/paper.pdf', 3)).toBe(
      '/api/files/artifacts/session/paper/paper.pdf?v=3',
    )
  })

  it('extends a url that already carries a query', () => {
    expect(versionedPreviewUrl('/api/files/asset.pdf?download=1', 0)).toBe('/api/files/asset.pdf?download=1&v=0')
  })

  it('keeps a missing url empty so the pane can show its waiting state', () => {
    expect(versionedPreviewUrl(null, 2)).toBeNull()
  })
})

describe('artifactImageUrl', () => {
  const image = {
    artifact_type: 'image' as const,
    title: 'Chart',
    summary: '',
    suggested_tags: [],
    keywords: [],
    prompt: '',
    alt_text: '',
    source_url: null,
    asset_path: null,
  }

  it('prefers the external URL and otherwise falls back to the stored file', () => {
    const stored = { content_url: '/api/files/assets/sessions/session-1/asset-1.png' }

    expect(artifactImageUrl({ ...image, source_url: 'https://example.com/a.png', asset_path: 'assets/sessions/session-1/asset-1.png' }, stored)).toBe('https://example.com/a.png')
    expect(artifactImageUrl({ ...image, asset_path: 'assets/sessions/session-1/asset-1.png' }, stored)).toBe(stored.content_url)
  })

  it('renders nothing for an image with neither source, and for other kinds', () => {
    expect(artifactImageUrl(image, { content_url: null })).toBeNull()
    expect(artifactImageUrl({ ...image, asset_path: 'assets/sessions/session-1/asset-1.png' }, null)).toBeNull()
    expect(artifactImageUrl({ ...image, artifact_type: 'card', card_type: 'note', content: 'body' }, { content_url: '/api/files/x.png' })).toBeNull()
  })
})
