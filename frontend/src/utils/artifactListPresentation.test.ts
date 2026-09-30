import { expect, it } from 'vitest'
import type { AgentArtifact, CardArtifactContent, ImageArtifactContent } from '../api/types'
import { artifactListExcerpt, artifactListImage } from './artifactListPresentation'

it('shows body text in a card list without rendering markup', () => {
  const content = {
    artifact_type: 'card', card_type: 'note', title: 'A card',
    summary: 'Short summary', content: '# Heading\n\nA **useful** detail.',
    suggested_tags: [], keywords: [],
  } satisfies CardArtifactContent
  expect(artifactListExcerpt(content)).toBe('Short summary A useful detail.')
  expect(artifactListExcerpt({ ...content, summary: '' })).toBe('A useful detail.')
})

it('keeps an image thumbnail linked to its selected draft or published source', () => {
  const content = {
    artifact_type: 'image', title: 'Cover', summary: 'A cover', prompt: '',
    alt_text: '', source_url: 'https://example.com/cover.png', asset_path: null,
    suggested_tags: [], keywords: [],
  } satisfies ImageArtifactContent
  const artifact = {
    draft_content: content, content: null, content_url: '/api/files/cover.png',
  } as AgentArtifact
  expect(artifactListExcerpt(content)).toBe('A cover')
  expect(artifactListImage(artifact)).toBe('https://example.com/cover.png')
})
