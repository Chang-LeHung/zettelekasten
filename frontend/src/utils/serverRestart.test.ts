import { describe, expect, it } from 'vitest'
import { waitForRestart } from './serverRestart'

function clock() {
  let time = 0
  return {
    now: () => time,
    sleep: async (milliseconds: number) => { time += milliseconds },
  }
}

describe('waiting for a restarted server', () => {
  it('keeps asking through the outage and the old process, and stops at the new one', async () => {
    const { now, sleep } = clock()
    const answers: Array<boolean | Error> = [true, new Error('connection refused'), new Error('connection refused'), true, false]
    const asked: number[] = []
    const ok = await waitForRestart({
      now,
      sleep,
      stillNeedsRestart: async () => {
        asked.push(now())
        const next = answers.shift()
        if (next instanceof Error) throw next
        return next === true
      },
    })
    expect(ok).toBe(true)
    // The first question waits for the helper's head start, so an early answer from
    // the old process is not mistaken for the new one.
    expect(asked[0]).toBe(1_500)
    expect(asked).toHaveLength(5)
  })

  it('gives up when nothing ever answers', async () => {
    const { now, sleep } = clock()
    let asked = 0
    const ok = await waitForRestart({
      now,
      sleep,
      timeoutMs: 10_000,
      stillNeedsRestart: async () => { asked += 1; throw new Error('down') },
    })
    expect(ok).toBe(false)
    expect(asked).toBeGreaterThan(3)
    expect(now()).toBeGreaterThanOrEqual(10_000)
  })

  it('gives up on a server that keeps asking for a restart', async () => {
    const { now, sleep } = clock()
    const ok = await waitForRestart({ now, sleep, timeoutMs: 5_000, stillNeedsRestart: async () => true })
    expect(ok).toBe(false)
  })
})
