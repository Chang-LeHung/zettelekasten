import { expect, it } from 'vitest'
import type { AgentArtifact, ArticleArtifactContent, CardArtifactContent } from '../api/types'
import { artifactContentFromLibraryUpdate, libraryItemFromArtifact } from './artifactEditor'

function artifact(content: CardArtifactContent | ArticleArtifactContent): AgentArtifact {
  return {
    id: 'artifact-1',
    session_id: 'session-1',
    artifact_type: content.artifact_type,
    status: 'draft',
    content,
    raw_content: 'original request',
    version: 1,
    metadata: { source: 'conversation' },
    tags: [{ id: 'tag-1', path: 'Topic/Example', name: 'Example' }],
    created_at: '2026-09-19T00:00:00Z',
    updated_at: '2026-09-19T01:00:00Z',
  }
}

it('projects card artifacts into the full editor without losing type-specific fields', () => {
  const item = libraryItemFromArtifact(artifact({
    artifact_type: 'card',
    card_type: 'idea',
    title: 'Card title',
    summary: 'Card summary',
    content: 'Card body',
    suggested_tags: [],
    keywords: ['card'],
  }))

  expect(item).toMatchObject({
    id: 'artifact-1',
    session_id: 'session-1',
    item_type: 'card',
    card_type: 'idea',
    subtitle: null,
    content: 'Card body',
    tags: ['Topic/Example'],
  })
})

it('projects article artifacts and applies editor updates while preserving metadata', () => {
  const content: ArticleArtifactContent = {
    artifact_type: 'article',
    title: 'Old title',
    subtitle: 'Old subtitle',
    summary: 'Old summary',
    content: 'Old body',
    suggested_tags: [{ path: 'Topic/Example', existing: true, confidence: 1 }],
    keywords: ['article'],
  }
  const item = libraryItemFromArtifact(artifact(content))

  expect(item).toMatchObject({
    item_type: 'article',
    subtitle: 'Old subtitle',
    card_type: null,
  })
  expect(artifactContentFromLibraryUpdate(content, {
    title: 'New title',
    subtitle: null,
    summary: null,
    content: 'New body',
  })).toEqual({
    ...content,
    title: 'New title',
    subtitle: '',
    summary: '',
    content: 'New body',
  })
})

it('leaves image and PDF artifacts in their specialized inline editors', () => {
  const image = artifact({
    artifact_type: 'card',
    card_type: 'note',
    title: 'Placeholder',
    summary: '',
    content: '',
    suggested_tags: [],
    keywords: [],
  })
  image.content = {
    artifact_type: 'image',
    title: 'Image',
    summary: '',
    prompt: '',
    alt_text: '',
    source_url: null,
    asset_path: null,
    suggested_tags: [],
    keywords: [],
  }

  expect(libraryItemFromArtifact(image)).toBeNull()

  image.content = {
    artifact_type: 'latex_pdf',
    project_path: '/server/latex/project',
    pdf_name: 'paper.pdf',
  }
  expect(libraryItemFromArtifact(image)).toBeNull()
})
