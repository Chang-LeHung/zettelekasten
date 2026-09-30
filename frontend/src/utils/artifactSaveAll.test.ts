import { expect, it } from 'vitest'
import type { AgentArtifact, CardArtifactContent } from '../api/types'
import { pendingArtifactSaves } from './artifactSaveAll'

const content: CardArtifactContent = {
  artifact_type: 'card', card_type: 'note', title: 'Note', summary: '',
  content: 'Published', suggested_tags: [], keywords: [],
}

it('keeps only unpublished artifacts and changed drafts', () => {
  const saved = { id: 'saved', status: 'saved', content, draft_content: { ...content } } as AgentArtifact
  const changed = { ...saved, id: 'changed', draft_content: { ...content, content: 'Draft' } }
  const newArtifact = { ...saved, id: 'new', status: 'draft', content: null, draft_content: content }
  expect(pendingArtifactSaves([saved, changed, newArtifact]).map(item => item.id)).toEqual(['changed', 'new'])
})
