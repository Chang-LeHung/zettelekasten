import { describe, expect, it } from 'vitest'
import { createAsyncRefreshScheduler } from './asyncRefresh'

describe('createAsyncRefreshScheduler', () => {
  it('does not block callers and coalesces requests queued before work starts', async () => {
    const values: string[] = []
    const scheduler = createAsyncRefreshScheduler(async (value: string) => { values.push(value) })

    scheduler.schedule('first')
    scheduler.schedule('latest')
    expect(values).toEqual([])

    await scheduler.whenIdle()
    expect(values).toEqual(['latest'])
  })

  it('retains one latest trailing refresh requested while another is running', async () => {
    let release!: () => void
    const blocked = new Promise<void>((resolve) => { release = resolve })
    const values: string[] = []
    const scheduler = createAsyncRefreshScheduler(async (value: string) => {
      values.push(value)
      if (value === 'first') await blocked
    })

    scheduler.schedule('first')
    await Promise.resolve()
    scheduler.schedule('obsolete')
    scheduler.schedule('latest')
    release()

    await scheduler.whenIdle()
    expect(values).toEqual(['first', 'latest'])
  })

  it('reports an error and continues with a trailing refresh', async () => {
    const errors: Array<[unknown, string]> = []
    const scheduler = createAsyncRefreshScheduler(
      async (value: string) => {
        if (value === 'bad') throw new Error('failed')
      },
      (error, value) => errors.push([error, value]),
    )

    scheduler.schedule('bad')
    await scheduler.whenIdle()
    scheduler.schedule('good')
    await scheduler.whenIdle()

    expect(errors).toHaveLength(1)
    expect(errors[0]?.[1]).toBe('bad')
  })
})
