// @vitest-environment jsdom
import { afterEach, expect, it, vi } from 'vitest'
import { installProbe, readProbe } from './probe'

const HOST = Symbol.for('zett.probe.host')
const key = 'probe-key'

function seedHost(overrides: Record<string, unknown> = {}) {
  const host = {
    kind: 'zett-probe',
    keys: [key],
    installed_at: 1,
    entries: [] as Array<Record<string, unknown>>,
    metrics: { lcp_ms: 0, cls: 0, long_task_count: 0, long_task_total_ms: 0, long_task_worst_ms: 0 },
    ...overrides,
  }
  ;(window as unknown as Record<symbol, unknown>)[HOST] = host
  return host
}

afterEach(() => {
  delete (window as unknown as Record<symbol, unknown>)[HOST]
  vi.restoreAllMocks()
})

it('reads a bounded slice of the console buffer, re-clamping what the page stored', () => {
  const host = seedHost()
  host.entries = [
    { level: 'warn', text: 'slow', source: 'app.js', line: 1, at: 1, count: 1 },
    { level: 'error', text: 'x'.repeat(1000), source: 'y'.repeat(500), line: 'nope', at: 2, count: 'many' },
  ]
  const console = readProbe(key, 'console', 500, true) as {
    probe_found: boolean
    entries: Array<{ text: string; source: string; line: number; count: number }>
  }
  // A page owns this buffer, so the read re-applies every bound and the row cap.
  expect(console.probe_found).toBe(true)
  expect(console.entries).toHaveLength(2)
  expect(console.entries[1].text).toHaveLength(300)
  expect(console.entries[1].source).toHaveLength(120)
  expect(console.entries[1].line).toBe(0)
  expect(console.entries[1].count).toBe(1)
})

it('returns only the newest rows the caller asked for', () => {
  const host = seedHost()
  host.entries = Array.from({ length: 10 }, (_, index) => ({
    level: 'error', text: `line ${index}`, source: '', line: index, at: index, count: 1,
  }))
  const console = readProbe(key, 'console', 3, true) as { entries: Array<{ text: string }> }
  expect(console.entries.map(entry => entry.text)).toEqual(['line 7', 'line 8', 'line 9'])
})

it('maps resource timings, and reports a missing probe without failing', () => {
  vi.spyOn(performance, 'getEntriesByType').mockImplementation((type: string) => (
    type === 'resource'
      ? [{
          name: 'https://example.com/app.js', initiatorType: 'script', startTime: 12.4,
          duration: 3.2, transferSize: 100, encodedBodySize: 80,
        } as PerformanceResourceTiming]
      : []
  ))
  const data = readProbe(key, 'network', 10, false) as {
    probe_found: boolean
    total: number
    entries: Array<Record<string, unknown>>
  }
  expect(data).toMatchObject({
    probe_found: false,
    total: 1,
    entries: [{
      name: 'https://example.com/app.js', type: 'script', start_ms: 12,
      duration_ms: 3, transfer_bytes: 100, encoded_bytes: 80, status: null,
    }],
  })
})

it('reports metrics and document size without a probe', () => {
  vi.spyOn(performance, 'getEntriesByType').mockImplementation(() => [])
  const data = readProbe(key, 'metrics', 5, false) as {
    probe_found: boolean
    metrics: unknown
    navigation: unknown
    document: { ready_state: string; elements: number }
  }
  expect(data.probe_found).toBe(false)
  expect(data.metrics).toBeNull()
  expect(data.navigation).toBeNull()
  expect(data.document.elements).toBeGreaterThan(0)
  expect(['loading', 'interactive', 'complete']).toContain(data.document.ready_state)
})

it('refuses a host the page created before us', () => {
  // A page that pre-seeds our symbol must not look like an installed probe.
  ;(window as unknown as Record<symbol, unknown>)[HOST] = {
    kind: 'page-forgery', keys: [key], entries: [{ text: 'forged' }], metrics: {},
  }
  expect(installProbe('another-key')).toBe(false)
  const data = readProbe(key, 'console', 5, true) as { probe_found: boolean; entries: unknown[] }
  expect(data.probe_found).toBe(false)
  expect(data.entries).toEqual([])
  const again = readProbe('another-key', 'console', 5, false) as { probe_found: boolean }
  expect(again.probe_found).toBe(false)
})

it('does not report a well-shaped host this connection never installed into', () => {
  // The shape passes every structural check; only the install result says whether
  // the document is really armed.
  seedHost()
  const data = readProbe(key, 'console', 5, false) as { probe_found: boolean }
  expect(data.probe_found).toBe(false)
})

it('installs the hooks once per document and accepts each connection key', () => {
  const originalError = console.error
  const originalWarn = console.warn
  try {
    expect(installProbe('first')).toBe(true)
    const installed = console.error
    expect(installProbe('second')).toBe(true)
    // A second connection must not wrap the page's console a second time.
    expect(console.error).toBe(installed)
    expect(console.error).not.toBe(originalError)
    const host = (window as unknown as Record<symbol, { keys: string[] }>)[HOST]
    expect(host.keys).toEqual(['first', 'second'])
  } finally {
    console.error = originalError
    console.warn = originalWarn
  }
})
