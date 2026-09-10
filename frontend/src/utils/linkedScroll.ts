export interface ScrollMetrics {
  scrollTop: number
  scrollHeight: number
  clientHeight: number
}

/** Return normalized scroll progress, treating non-scrollable content as the top. */
export function scrollProgress(metrics: ScrollMetrics): number {
  const range = Math.max(0, metrics.scrollHeight - metrics.clientHeight)
  if (range === 0) return 0
  return Math.min(1, Math.max(0, metrics.scrollTop / range))
}

/** Map one pane's scroll position onto a differently sized linked pane. */
export function linkedScrollTop(source: ScrollMetrics, target: ScrollMetrics): number {
  const targetRange = Math.max(0, target.scrollHeight - target.clientHeight)
  return scrollProgress(source) * targetRange
}
