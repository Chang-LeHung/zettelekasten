import type { ArtifactType } from '../api/types'

/** One palette across the artifact list and its detail header. */
export function artifactTone(type: ArtifactType): string {
  return `artifact-tone-${type.replace('_', '-')}`
}
