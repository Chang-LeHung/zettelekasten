// @vitest-environment jsdom
import { createApp, nextTick } from 'vue'
import { afterEach, expect, it } from 'vitest'
import UsageActivityGraph from './UsageActivityGraph.vue'

const cleanups: (() => void)[] = []
afterEach(() => cleanups.splice(0).forEach(cleanup => cleanup()))

it('renders daily model activity cells', async () => {
  const host = document.createElement('div')
  document.body.append(host)
  const app = createApp(UsageActivityGraph, {
    days: [
      {
        date: '2026-09-13',
        requests: 0,
        input_tokens: 0,
        output_tokens: 0,
        cache_read_tokens: 0,
        cache_write_tokens: 0,
        reasoning_tokens: 0,
        total_tokens: 0,
      },
      {
        date: '2026-09-14',
        requests: 2,
        input_tokens: 100,
        output_tokens: 20,
        cache_read_tokens: 80,
        cache_write_tokens: 0,
        reasoning_tokens: 5,
        total_tokens: 120,
      },
    ],
  })
  app.mount(host)
  cleanups.push(() => { app.unmount(); host.remove() })
  await nextTick()

  expect(host.textContent).toContain('2 requests · 1 active day')
  expect(host.textContent).toContain('120 tokens')
  expect(host.querySelectorAll('.activity-cell.level-4')).toHaveLength(1)
  expect(host.querySelector('.activity-cell.level-4')?.hasAttribute('title')).toBe(false)

  host.querySelector('.activity-cell.level-4')?.dispatchEvent(new MouseEvent('mouseenter', { bubbles: true }))
  await nextTick()
  expect(host.querySelector('.activity-tooltip')?.textContent).toContain('Mon, Sep 14, 2026')
  expect(host.querySelector('.activity-tooltip')?.textContent).toContain('Input100')
  expect(host.querySelector('.activity-tooltip')?.textContent).toContain('Total120')
  expect(host.querySelector('.activity-tooltip')?.textContent).toContain('Cache hit rate80.00%')
})

it('renders English month labels when the month changes', async () => {
  const host = document.createElement('div')
  document.body.append(host)
  const days = [
    '2026-09-27',
    '2026-09-28',
    '2026-09-29',
    '2026-09-30',
    '2026-10-01',
    '2026-10-02',
    '2026-10-03',
    '2026-10-04',
  ].map(date => ({
    date,
    requests: 1,
    input_tokens: 10,
    output_tokens: 2,
    cache_read_tokens: 0,
    cache_write_tokens: 0,
    reasoning_tokens: 0,
    total_tokens: 12,
  }))
  const app = createApp(UsageActivityGraph, {
    days,
  })
  app.mount(host)
  cleanups.push(() => { app.unmount(); host.remove() })
  await nextTick()

  const months = Array.from(host.querySelectorAll('.activity-month > span')).map(element => element.textContent)
  expect(months).toContain('Sep')
  expect(months).toContain('Oct')
})
