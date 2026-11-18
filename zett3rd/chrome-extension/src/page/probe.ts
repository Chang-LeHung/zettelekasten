/**
 * The page-world probe: install it once per document, then read bounded slices.
 *
 * Console output, uncaught errors, largest-contentful-paint, layout shift, long
 * tasks, and resource timings only exist in the page's own JavaScript world, so
 * an isolated content script cannot see them. Both functions here are injected
 * with `chrome.scripting.executeScript({ world: 'MAIN', func })`, which means
 * they are serialized into the page: everything they need is declared inside
 * them, and they must never reference module scope.
 *
 * The page owns that world. It can read, ignore, or rewrite everything the probe
 * keeps, so every value these functions return is untrusted data, and
 * `probe_found` only says this connection's key was accepted at install time —
 * never that the page let the hooks run untouched.
 *
 * One document keeps one host and one set of hooks: a reconnecting panel adds a
 * key to the existing host instead of wrapping `console` again. Otherwise every
 * page-identity change inside an SPA would stack another wrapper, another three
 * observers, and another buffer that nothing reads.
 */

/** One buffered console line, capped when it is recorded and again when it is read. */
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

export interface ProbeHost {
  kind: string
  keys: string[]
  installed_at: number
  entries: ProbeEntry[]
  metrics: ProbeMetrics
}

/**
 * Install the hooks once per document, then accept one connection's key.
 *
 * Returns whether this call left the document armed: the executor keeps that
 * answer, because "a buffer with our key exists" is weaker evidence than "our
 * install succeeded", and only the second may be reported as `probe_found`.
 *
 * The key is random per connection, so a page cannot pre-seed a buffer that
 * looks found; the page can still block the installation, which shows up as
 * `probe_found: false` on every read.
 */
export function installProbe(key: string): boolean {
  const HOST = Symbol.for('zett.probe.host')
  const KIND = 'zett-probe'
  const MAX_ENTRIES = 200
  const MAX_TEXT = 300
  const MAX_SOURCE = 120

  const scope = window as unknown as Record<symbol, ProbeHost | undefined>
  if (!key) return false
  // Anything under our symbol that we did not create is the page's own object:
  // refuse rather than adopt it, and never dereference a field we did not write.
  const existing = scope[HOST]
  const usable = (candidate: ProbeHost): boolean => (
    candidate.kind === KIND
    && Array.isArray(candidate.keys)
    && Array.isArray(candidate.entries)
    && typeof candidate.metrics === 'object'
    && candidate.metrics !== null
  )
  if (existing && !usable(existing)) return false
  const host: ProbeHost = existing ?? {
    kind: KIND,
    keys: [],
    installed_at: 0,
    entries: [],
    metrics: { lcp_ms: 0, cls: 0, long_task_count: 0, long_task_total_ms: 0, long_task_worst_ms: 0 },
  }
  scope[HOST] = host
  if (!host.keys.includes(key)) host.keys.push(key)
  if (host.installed_at) return true
  host.installed_at = Date.now()

  // Keep the buffers we just validated: the page can replace `host.entries` or
  // `host.metrics` after this call, and a hook that re-read them would throw into
  // the page's own `console.error` or observer callback.
  const entries = host.entries
  const metrics = host.metrics

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
    if (!text || !Array.isArray(entries)) return
    const last = entries[entries.length - 1]
    // A page that logs the same line in a loop must not push the rest out.
    if (last && last.level === level && last.text === text) {
      last.count += 1
      last.at = Date.now()
      return
    }
    entries.push({ level, text, source: source.slice(0, MAX_SOURCE), line, at: Date.now(), count: 1 })
    while (entries.length > MAX_ENTRIES) entries.shift()
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
  return true
}

/** Read one bounded slice of the host, re-clamped because the page owns it. */
export function readProbe(key: string, kind: string, limit: number, armed: boolean): Record<string, unknown> {
  interface Entry { level?: unknown; text?: unknown; source?: unknown; line?: unknown; at?: unknown; count?: unknown }
  interface Host {
    kind?: unknown
    keys?: unknown
    entries?: Entry[]
    metrics?: {
      lcp_ms?: unknown
      cls?: unknown
      long_task_count?: unknown
      long_task_total_ms?: unknown
      long_task_worst_ms?: unknown
    }
  }
  const HOST = Symbol.for('zett.probe.host')
  const KIND = 'zett-probe'
  const MAX_TEXT = 300
  const MAX_SOURCE = 120

  const host = (window as unknown as Record<symbol, Host | undefined>)[HOST]
  const keys = Array.isArray(host?.keys) ? host!.keys : []
  // `armed` is what this connection's install returned; a well-shaped object a
  // page wrote under our symbol must never read as an installed probe.
  const found = armed === true && host?.kind === KIND && keys.includes(key)
  const metrics = found ? host?.metrics : undefined
  const rows = Math.max(1, Math.min(50, Math.trunc(limit) || 1))
  const number = (value: unknown, fallback = 0): number => (
    typeof value === 'number' && Number.isFinite(value) ? Math.round(value) : fallback
  )

  if (kind === 'console') {
    const entries = found && Array.isArray(host?.entries) ? host.entries : []
    return {
      probe_found: found,
      entries: entries.slice(-rows).map(entry => ({
        level: String(entry?.level ?? 'log').slice(0, 10),
        text: String(entry?.text ?? '').slice(0, MAX_TEXT),
        source: String(entry?.source ?? '').slice(0, MAX_SOURCE),
        line: number(entry?.line),
        at: number(entry?.at),
        count: Math.max(1, number(entry?.count, 1)),
      })),
    }
  }

  const resources = performance.getEntriesByType('resource') as PerformanceResourceTiming[]
  if (kind === 'network') {
    return {
      probe_found: found,
      total: resources.length,
      entries: resources.slice(-rows).map(entry => ({
        name: String(entry.name).slice(0, 200),
        type: String(entry.initiatorType || 'other').slice(0, 40),
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
    probe_found: found,
    metrics: metrics
      ? {
          lcp_ms: number(metrics.lcp_ms),
          cls: typeof metrics.cls === 'number' ? Math.round(metrics.cls * 1000) / 1000 : 0,
          long_task_count: number(metrics.long_task_count),
          long_task_total_ms: number(metrics.long_task_total_ms),
          long_task_worst_ms: number(metrics.long_task_worst_ms),
        }
      : null,
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
