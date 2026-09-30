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

it('keeps the full year in a fluid grid without an internal scrollbar', async () => {
  const host = document.createElement('div')
  document.body.append(host)
  const start = Date.UTC(2025, 9, 1)
  const days = Array.from({ length: 365 }, (_, index) => ({
    date: new Date(start + index * 86_400_000).toISOString().slice(0, 10),
    requests: 0,
    input_tokens: 0,
    output_tokens: 0,
    cache_read_tokens: 0,
    cache_write_tokens: 0,
    reasoning_tokens: 0,
    total_tokens: 0,
  }))
  const app = createApp(UsageActivityGraph, { days })
  app.mount(host)
  cleanups.push(() => { app.unmount(); host.remove() })
  await nextTick()

  expect(host.querySelectorAll('.activity-cell:not(.empty)')).toHaveLength(365)
  expect(host.querySelector('.activity-scroll')).toBeNull()
  expect(host.querySelector('.activity-calendar')).not.toBeNull()
  expect(host.querySelectorAll('.activity-week').length).toBeGreaterThan(52)
  expect(Array.from(host.querySelectorAll('.activity-week')).every(week => week.children.length === 7)).toBe(true)
  expect(host.querySelector('.activity-week:last-child .activity-cell.level-0')).not.toBeNull()
})

it('pads the last week so active days cannot stretch when most of that week is absent', async () => {
  const host = document.createElement('div')
  document.body.append(host)
  const app = createApp(UsageActivityGraph, { days: [{
    date: '2026-09-27',
    requests: 1,
    input_tokens: 20,
    output_tokens: 5,
    cache_read_tokens: 0,
    cache_write_tokens: 0,
    reasoning_tokens: 0,
    total_tokens: 25,
  }] })
  app.mount(host)
  cleanups.push(() => { app.unmount(); host.remove() })
  await nextTick()

  const days = host.querySelectorAll('.activity-week:last-child .activity-cell')
  expect(days).toHaveLength(7)
  expect(days[0]?.classList.contains('level-4')).toBe(true)
  expect(Array.from(days).slice(1).every(day => day.classList.contains('empty'))).toBe(true)
})
