export const MIN_ARTIFACT_LIST_HEIGHT = 96
// Includes the preview header and action footer; leave enough room for the
// actual document body rather than only its title.
export const MIN_ARTIFACT_PREVIEW_HEIGHT = 340
export const ARTIFACT_SPLITTER_HEIGHT = 14

/** Keep both sides usable even in a short workspace. */
export function clampArtifactListHeight(requested: number, paneHeight: number, headerHeight: number): number {
  const available = Math.max(0, paneHeight - headerHeight - ARTIFACT_SPLITTER_HEIGHT)
  const maximum = Math.max(0, available - MIN_ARTIFACT_PREVIEW_HEIGHT)
  const minimum = Math.min(MIN_ARTIFACT_LIST_HEIGHT, maximum)
  return Math.min(maximum, Math.max(minimum, requested))
}
