// @vitest-environment jsdom
import { afterEach, expect, it, vi } from 'vitest'
import { readProbe } from './probe-read'

afterEach(() => {
  delete (window as unknown as { __zettProbe?: unknown }).__zettProbe
  vi.restoreAllMocks()
})

it('reads a bounded slice of the console buffer the probe collected', () => {
  (window as unknown as { __zettProbe: unknown }).__zettProbe = {
    entries: [
      { level: 'warn', text: 'slow', source: 'app.js', line: 1, at: 1, count: 1 },
      { level: 'error', text: 'boom', source: 'app.js', line: 3, at: 2, count: 2 },
    ],
    metrics: { lcp_ms: 1200, cls: 0.1, long_task_count: 1, long_task_total_ms: 60, long_task_worst_ms: 60 },
  }
  const console = readProbe('console', 1) as { installed: boolean; entries: Array<{ text: string }> }
  expect(console.installed).toBe(true)
  expect(console.entries.map(entry => entry.text)).toEqual(['boom'])
})

it('maps resource timings, and reports an absent probe without failing', () => {
  vi.spyOn(performance, 'getEntriesByType').mockImplementation((type: string) => (
    type === 'resource'
      ? [{
          name: 'https://example.com/app.js', initiatorType: 'script', startTime: 12.4,
          duration: 3.2, transferSize: 100, encodedBodySize: 80,
        } as PerformanceResourceTiming]
      : []
  ))
  const data = readProbe('network', 10) as { installed: boolean; total: number; entries: Array<Record<string, unknown>> }
  expect(data).toMatchObject({
    installed: false,
    total: 1,
    entries: [{
      name: 'https://example.com/app.js', type: 'script', start_ms: 12,
      duration_ms: 3, transfer_bytes: 100, encoded_bytes: 80, status: null,
    }],
  })
})

it('reports metrics and document size without a probe', () => {
  vi.spyOn(performance, 'getEntriesByType').mockImplementation(() => [])
  const data = readProbe('metrics', 5) as {
    installed: boolean
    metrics: unknown
    navigation: unknown
    document: { ready_state: string; elements: number }
  }
  expect(data.installed).toBe(false)
  expect(data.metrics).toBeNull()
  expect(data.navigation).toBeNull()
  expect(data.document.elements).toBeGreaterThan(0)
  expect(['loading', 'interactive', 'complete']).toContain(data.document.ready_state)
})
