import type { AgentArtifact } from '../api/types'
import { hasPendingDraft } from './artifactEditor'

/** An unsaved initial artifact or a published artifact with pending edits. */
export function pendingArtifactSaves(artifacts: readonly AgentArtifact[]): AgentArtifact[] {
  return artifacts.filter(artifact => artifact.status !== 'saved' || hasPendingDraft(artifact))
}
