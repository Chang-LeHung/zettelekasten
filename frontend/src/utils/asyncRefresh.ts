/** Coalesce repeated refresh requests while retaining one trailing refresh. */
export interface AsyncRefreshScheduler<T> {
  schedule(value: T): void
  whenIdle(): Promise<void>
}

/**
 * Run at most one refresh at a time and retain the latest request received
 * while it is running. The caller never awaits `schedule`, so stream event
 * consumption cannot be blocked by network refreshes.
 */
export function createAsyncRefreshScheduler<T>(
  refresh: (value: T) => Promise<void>,
  onError: (error: unknown, value: T) => void = () => {},
): AsyncRefreshScheduler<T> {
  let pending: T | undefined
  let running: Promise<void> | null = null

  async function drain(): Promise<void> {
    await Promise.resolve()
    while (pending !== undefined) {
      const value = pending
      pending = undefined
      try {
        await refresh(value)
      } catch (error) {
        onError(error, value)
      }
    }
    running = null
  }

  return {
    schedule(value: T): void {
      pending = value
      running ??= drain()
    },
    async whenIdle(): Promise<void> {
      while (running) await running
    },
  }
}
