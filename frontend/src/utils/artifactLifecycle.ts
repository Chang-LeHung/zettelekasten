import type { AgentArtifact } from '../api/types'
import { hasPendingDraft } from './artifactEditor'

/**
 * How far an artifact is from being saved.
 *
 * - `new`: never saved; everything on screen is still a proposal.
 * - `changed`: saved, but a newer draft differs from what the user kept.
 * - `saved`: saved and current.
 *
 * The state is derived, never stored, so it cannot disagree with the artifact.
 */
export type ArtifactLifecycle = 'new' | 'changed' | 'saved'

export function artifactLifecycle(artifact: AgentArtifact): ArtifactLifecycle {
  return lifecycleOf(artifact.status === 'saved' && Boolean(artifact.content), hasPendingDraft(artifact))
}

/**
 * The same rule from the two facts it needs, for callers that hold a receipt
 * instead of the stored artifact (the Chrome panel): was it ever saved, and
 * does a draft still differ from what the user kept.
 */
export function lifecycleOf(saved: boolean, pendingDraft: boolean): ArtifactLifecycle {
  if (!saved) return 'new'
  return pendingDraft ? 'changed' : 'saved'
}

/** CSS class carrying the lifecycle look. */
export function lifecycleClass(lifecycle: ArtifactLifecycle): string {
  return `lifecycle-${lifecycle}`
}

/** i18n key of the short badge word. */
export function lifecycleLabel(lifecycle: ArtifactLifecycle): string {
  return `artifact.lifecycle.${lifecycle}`
}

/** i18n key of the one-line explanation shown beside the editor's state. */
export function lifecycleHint(lifecycle: ArtifactLifecycle): string {
  return `artifact.lifecycle.${lifecycle}.hint`
}
