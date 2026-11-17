/**
 * Read one bounded slice of what `page-probe.ts` collected.
 *
 * Injected with `chrome.scripting.executeScript({ world: 'MAIN', func: readProbe })`,
 * so it is serialized into the page and must stay self-contained: no imports, no
 * references to module scope. The page owns that world and can tamper with what
 * this returns, so the result is untrusted data like any other page read.
 */
export function readProbe(kind: string, limit: number): Record<string, unknown> {
  interface Entry { level: string; text: string; source: string; line: number; at: number; count: number }
  interface Metrics { lcp_ms: number; cls: number; long_task_count: number; long_task_total_ms: number; long_task_worst_ms: number }
  const probe = (window as unknown as Record<string, { entries?: Entry[]; metrics?: Metrics } | undefined>)['__zettProbe']
  const installed = Boolean(probe)

  if (kind === 'console') {
    return { installed, entries: (probe?.entries ?? []).slice(-limit) }
  }

  const resources = performance.getEntriesByType('resource') as PerformanceResourceTiming[]
  if (kind === 'network') {
    return {
      installed,
      total: resources.length,
      entries: resources.slice(-limit).map(entry => ({
        name: entry.name.slice(0, 200),
        type: entry.initiatorType || 'other',
        start_ms: Math.round(entry.startTime),
        duration_ms: Math.round(entry.duration),
        transfer_bytes: entry.transferSize ?? 0,
        encoded_bytes: entry.encodedBodySize ?? 0,
        status: (entry as PerformanceResourceTiming & { responseStatus?: number }).responseStatus ?? null,
      })),
    }
  }

  const navigation = performance.getEntriesByType('navigation')[0] as PerformanceNavigationTiming | undefined
  return {
    installed,
    metrics: probe?.metrics ?? null,
    navigation: navigation
      ? {
          type: navigation.type,
          dom_content_loaded_ms: Math.round(navigation.domContentLoadedEventEnd),
          load_ms: Math.round(navigation.loadEventEnd),
          transfer_bytes: navigation.transferSize ?? 0,
        }
      : null,
    document: {
      ready_state: document.readyState,
      resources: resources.length,
      scripts: document.scripts.length,
      elements: document.getElementsByTagName('*').length,
    },
  }
}
