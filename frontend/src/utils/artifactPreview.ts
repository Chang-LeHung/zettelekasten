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
