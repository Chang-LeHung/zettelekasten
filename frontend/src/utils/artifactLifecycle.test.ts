import { describe, expect, it } from 'vitest'
import type { AgentArtifact, CardArtifactContent } from '../api/types'
import { artifactLifecycle, lifecycleClass, lifecycleHint, lifecycleLabel, lifecycleOf } from './artifactLifecycle'

function card(content: string): CardArtifactContent {
  return { artifact_type: 'card', card_type: 'note', title: 'Idea', summary: '', suggested_tags: [], keywords: [], content }
}

function artifact(overrides: Partial<AgentArtifact>): AgentArtifact {
  return {
    id: 'a', session_id: 's', artifact_type: 'card', status: 'draft', content: null, draft_content: card('v1'),
    raw_content: null, version: 1, metadata: {}, tags: [], content_url: null,
    created_at: '2026-10-13T00:00:00Z', updated_at: '2026-10-13T00:00:00Z', ...overrides,
  }
}

describe('artifact lifecycle', () => {
  it('is new until the user saves the first draft', () => {
    expect(artifactLifecycle(artifact({}))).toBe('new')
    // A saved flag with nothing published cannot be trusted either.
    expect(artifactLifecycle(artifact({ status: 'saved', content: null }))).toBe('new')
  })

  it('is saved when the draft equals what the user kept', () => {
    expect(artifactLifecycle(artifact({ status: 'saved', content: card('v1'), draft_content: card('v1') }))).toBe('saved')
    expect(artifactLifecycle(artifact({ status: 'saved', content: card('v1'), draft_content: null }))).toBe('saved')
  })

  it('is changed when a saved artifact has a different draft', () => {
    expect(artifactLifecycle(artifact({ status: 'saved', content: card('v1'), draft_content: card('v2') }))).toBe('changed')
  })

  it('reads the same states from the two facts a receipt carries', () => {
    expect(lifecycleOf(false, false)).toBe('new')
    expect(lifecycleOf(false, true)).toBe('new')
    expect(lifecycleOf(true, true)).toBe('changed')
    expect(lifecycleOf(true, false)).toBe('saved')
  })

  it('names one class and two message keys per state', () => {
    for (const state of ['new', 'changed', 'saved'] as const) {
      expect(lifecycleClass(state)).toBe(`lifecycle-${state}`)
      expect(lifecycleLabel(state)).toBe(`artifact.lifecycle.${state}`)
      expect(lifecycleHint(state)).toBe(`artifact.lifecycle.${state}.hint`)
    }
  })
})
