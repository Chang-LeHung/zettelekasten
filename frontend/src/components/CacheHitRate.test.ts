// @vitest-environment jsdom
import { createApp, nextTick } from 'vue'
import { afterEach, expect, it } from 'vitest'
import CacheHitRate from './CacheHitRate.vue'

const cleanups: (() => void)[] = []
afterEach(() => cleanups.splice(0).forEach(cleanup => cleanup()))

function mount(props: Record<string, unknown>): HTMLElement {
  const host = document.createElement('div')
  document.body.append(host)
  const app = createApp(CacheHitRate, props)
  app.mount(host)
  cleanups.push(() => { app.unmount(); host.remove() })
  return host
}

it('falls back to usage and highlights a high cache hit rate', async () => {
  const host = mount({
    usage: {
      input_tokens: 100,
      output_tokens: 20,
      cache_read_tokens: 80,
      cache_write_tokens: 0,
      reasoning_tokens: 0,
    },
  })
  await nextTick()

  const badge = host.querySelector('.cache-hit-rate')
  expect(badge?.textContent).toContain('Cache hit 80%')
  expect(badge?.classList.contains('high')).toBe(true)
})

it('uses an explicit persisted rate and hides when no usage exists', async () => {
  const host = mount({ rate: 0.4 })
  await nextTick()

  const badge = host.querySelector('.cache-hit-rate')
  expect(badge?.textContent).toContain('Cache hit 40%')
  expect(badge?.classList.contains('medium')).toBe(true)

  const emptyHost = mount({})
  await nextTick()
  expect(emptyHost.querySelector('.cache-hit-rate')).toBeNull()
})
