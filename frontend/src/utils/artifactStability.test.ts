import { describe, expect, it } from 'vitest'
import type { AgentArtifact } from '../api/types'
import {
  artifactListsEquivalent,
  sameArtifactRevision,
  stabilizeArtifactReferences,
} from './artifactStability'

function artifact(id: string, version = 1): AgentArtifact {
  return {
    id,
    session_id: 'session',
    artifact_type: 'latex_pdf',
    status: 'draft',
    content: { artifact_type: 'latex_pdf', pdf_name: `${id}.pdf`, project_path: `/tmp/${id}` },
    raw_content: null,
    version,
    metadata: {},
    tags: [],
    created_at: '2026-09-19T00:00:00Z',
    updated_at: `2026-09-19T00:00:0${version}Z`,
  }
}

describe('artifact stability', () => {
  it('reuses references for unchanged revisions', () => {
    const original = artifact('paper')
    const refreshed = artifact('paper')

    expect(sameArtifactRevision(original, refreshed)).toBe(true)
    expect(stabilizeArtifactReferences([original], [refreshed])[0]).toBe(original)
    expect(artifactListsEquivalent([original], [refreshed])).toBe(true)
  })

  it('does not reuse references after a version change', () => {
    const original = artifact('paper', 1)
    const updated = artifact('paper', 2)

    expect(stabilizeArtifactReferences([original], [updated])[0]).toBe(updated)
    expect(artifactListsEquivalent([original], [updated])).toBe(false)
  })
})
