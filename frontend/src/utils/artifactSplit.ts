export const MIN_ARTIFACT_LIST_WIDTH = 176
// The preview needs room for a readable page, not only its toolbar.
export const MIN_ARTIFACT_PREVIEW_WIDTH = 320
export const ARTIFACT_SPLITTER_WIDTH = 12
/** One arrow-key step on the divider. */
export const ARTIFACT_SPLIT_STEP = 24
// Below 520px of pane width (a container query in workspace-artifacts.css) the list stacks above the preview.

/** The widest list that still leaves the preview its minimum. */
export function maxArtifactListWidth(paneWidth: number): number {
  return Math.max(0, paneWidth - ARTIFACT_SPLITTER_WIDTH - MIN_ARTIFACT_PREVIEW_WIDTH)
}

/** Keep both sides usable even in a narrow workspace. */
export function clampArtifactListWidth(requested: number, paneWidth: number): number {
  const maximum = maxArtifactListWidth(paneWidth)
  const minimum = Math.min(MIN_ARTIFACT_LIST_WIDTH, maximum)
  return Math.min(maximum, Math.max(minimum, requested))
}

/** The stored width, or null when nothing usable was saved. */
export function parseArtifactListWidth(value: string | null): number | null {
  if (value === null || value.trim() === '') return null
  const parsed = Number(value)
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null
}
