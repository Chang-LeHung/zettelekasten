import type { AgentArtifact } from '../api/types'

/** Return whether two snapshots represent the same persisted artifact revision. */
export function sameArtifactRevision(left: AgentArtifact, right: AgentArtifact): boolean {
  return (
    left.id === right.id
    && left.version === right.version
    && left.status === right.status
    && left.updated_at === right.updated_at
    && left.artifact_type === right.artifact_type
  )
}

/** Reuse existing object references for artifact revisions that did not change. */
export function stabilizeArtifactReferences(
  previous: readonly AgentArtifact[],
  next: readonly AgentArtifact[],
): AgentArtifact[] {
  const previousById = new Map(previous.map((artifact) => [artifact.id, artifact]))
  return next.map((artifact) => {
    const existing = previousById.get(artifact.id)
    return existing && sameArtifactRevision(existing, artifact) ? existing : artifact
  })
}

/** Compare artifact lists including their display order. */
export function artifactListsEquivalent(
  left: readonly AgentArtifact[],
  right: readonly AgentArtifact[],
): boolean {
  return left.length === right.length && left.every((artifact, index) => (
    sameArtifactRevision(artifact, right[index]!)
  ))
}
