import { describe, expect, it } from 'vitest'

import { versionedPreviewUrl } from './artifactPreview'

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
