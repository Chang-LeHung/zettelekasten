import type { AgentArtifact, ArtifactContent } from '../api/types'

/**
 * Address one previewable object for a specific revision.
 *
 * Recompiling a LaTeX artifact replaces the stored PDF without changing the
 * artifact row, so the pane's URL has to change when the user refreshes;
 * otherwise the browser serves the cached bytes and the preview looks stale.
 */
export function versionedPreviewUrl(url: string | null, nonce: number): string | null {
  if (!url) return null
  const separator = url.includes('?') ? '&' : '?'
  return `${url}${separator}v=${nonce}`
}

/**
 * The image an image artifact renders.
 *
 * An image artifact points either outside the application (`source_url`) or at
 * a file this conversation uploaded (`asset_path`), and the server turns that
 * local key into `content_url`. The external URL wins when both are present,
 * because that is the image the artifact was created from.
 */
export function artifactImageUrl(
  content: ArtifactContent | null,
  artifact: Pick<AgentArtifact, 'content_url'> | null,
): string | null {
  if (content?.artifact_type !== 'image') return null
  if (content.source_url) return content.source_url
  return artifact?.content_url ?? null
}
