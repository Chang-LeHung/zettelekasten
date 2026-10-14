/**
 * Waiting for Zett to come back after it restarted itself.
 *
 * The restart is carried out by a helper that stops the server which answered
 * the request, so for a few seconds nothing answers at all. The old process may
 * also still answer once or twice before it is stopped, and an answer from it is
 * not an answer from the new one: only a server that no longer asks for a restart
 * counts, because that is a process running the installed release.
 */

export interface RestartWaitOptions {
  /** Ask the server whether it still needs a restart; rejects while it is down. */
  stillNeedsRestart: () => Promise<boolean>
  sleep: (milliseconds: number) => Promise<void>
  now: () => number
  /** How long to wait before giving up. */
  timeoutMs?: number
  /** Gap between questions, and the head start the helper gets before the first. */
  intervalMs?: number
  headStartMs?: number
}

export const RESTART_TIMEOUT_MS = 90_000
export const RESTART_INTERVAL_MS = 1_000
export const RESTART_HEAD_START_MS = 1_500

/** Resolve true once a restarted server answers, or false when it never does. */
export async function waitForRestart(options: RestartWaitOptions): Promise<boolean> {
  const timeout = options.timeoutMs ?? RESTART_TIMEOUT_MS
  const interval = options.intervalMs ?? RESTART_INTERVAL_MS
  const deadline = options.now() + timeout
  await options.sleep(options.headStartMs ?? RESTART_HEAD_START_MS)
  while (options.now() < deadline) {
    try {
      if (!(await options.stillNeedsRestart())) return true
    } catch {
      // The old server is down and the new one is not listening yet.
    }
    await options.sleep(interval)
  }
  return false
}
