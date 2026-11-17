/**
 * Observe the page from its own JavaScript world.
 *
 * Console output, uncaught errors, largest-contentful-paint, layout shift, long
 * tasks, and resource timings only exist in the page's world: an isolated
 * content script cannot see the page's `console` or its paint timeline. This
 * file is bundled to `page-probe.js` and injected with `world: 'MAIN'` when the
 * panel connects. It installs hooks once and keeps bounded buffers; the model
 * reads them later through `readProbe` (`probe-read.ts`), injected the same way.
 *
 * Nothing here executes page-supplied code: the hooks forward calls and copy
 * bounded strings into an array. The page can see and tamper with that array,
 * so everything it returns is untrusted data.
 *
 * This module is imported only by the injected bundle; the panel imports
 * `readProbe` from its own file so that opening the panel never hooks its own
 * console.
 */

/** Longest single console line kept, before the entry list is capped. */
const MAX_TEXT = 300
const MAX_ENTRIES = 200
const MAX_SOURCE = 120

export interface ProbeEntry {
  level: string
  text: string
  source: string
  line: number
  at: number
  count: number
}

export interface ProbeMetrics {
  lcp_ms: number
  cls: number
  long_task_count: number
  long_task_total_ms: number
  long_task_worst_ms: number
}

export interface ProbeState {
  entries: ProbeEntry[]
  metrics: ProbeMetrics
  installed_at: number
}

const PROBE_KEY = '__zettProbe'

function install(): void {
  const scope = window as unknown as Record<string, ProbeState | undefined>
  if (scope[PROBE_KEY]) return

  const entries: ProbeEntry[] = []
  const metrics: ProbeMetrics = {
    lcp_ms: 0, cls: 0, long_task_count: 0, long_task_total_ms: 0, long_task_worst_ms: 0,
  }

  const describe = (value: unknown): string => {
    try {
      if (typeof value === 'string') return value
      if (value instanceof Error) return `${value.name}: ${value.message}`
      return JSON.stringify(value) ?? String(value)
    } catch {
      return String(value)
    }
  }

  const record = (level: string, values: unknown[], source = '', line = 0): void => {
    const text = values.map(describe).join(' ').replace(/\s+/g, ' ').trim().slice(0, MAX_TEXT)
    if (!text) return
    const last = entries[entries.length - 1]
    // A page that logs the same line in a loop must not push the rest out.
    if (last && last.level === level && last.text === text) {
      last.count += 1
      last.at = Date.now()
      return
    }
    entries.push({ level, text, source: source.slice(0, MAX_SOURCE), line, at: Date.now(), count: 1 })
    if (entries.length > MAX_ENTRIES) entries.shift()
  }

  for (const level of ['error', 'warn'] as const) {
    const original = console[level]
    console[level] = (...values: unknown[]): void => {
      record(level, values)
      original.apply(console, values)
    }
  }
  window.addEventListener('error', event => {
    record('error', [event.message], event.filename, event.lineno)
  })
  window.addEventListener('unhandledrejection', event => {
    record('error', ['Unhandled rejection', event.reason])
  })

  try {
    new PerformanceObserver(list => {
      for (const entry of list.getEntries()) metrics.lcp_ms = Math.max(metrics.lcp_ms, Math.round(entry.startTime))
    }).observe({ type: 'largest-contentful-paint', buffered: true })
  } catch {
    // A browser without that entry type simply reports no LCP.
  }
  try {
    new PerformanceObserver(list => {
      for (const entry of list.getEntries() as Array<PerformanceEntry & { value?: number; hadRecentInput?: boolean }>) {
        if (!entry.hadRecentInput) metrics.cls += entry.value ?? 0
      }
    }).observe({ type: 'layout-shift', buffered: true })
  } catch {
    // Same for layout shift.
  }
  try {
    new PerformanceObserver(list => {
      for (const entry of list.getEntries()) {
        metrics.long_task_count += 1
        metrics.long_task_total_ms += Math.round(entry.duration)
        metrics.long_task_worst_ms = Math.max(metrics.long_task_worst_ms, Math.round(entry.duration))
      }
    }).observe({ type: 'longtask', buffered: true })
  } catch {
    // Same for long tasks.
  }

  scope[PROBE_KEY] = { entries, metrics, installed_at: Date.now() }
}

install()
