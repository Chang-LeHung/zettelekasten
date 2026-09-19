// @vitest-environment jsdom
import { createApp, nextTick } from 'vue'
import { afterEach, expect, it, vi } from 'vitest'
import ModelUsageTrend from './ModelUsageTrend.vue'

vi.mock('vue-echarts', () => ({
  default: {
    name: 'VChart',
    props: ['option'],
    template: '<div class="echarts-stub" />',
  },
}))

const cleanups: (() => void)[] = []
afterEach(() => cleanups.splice(0).forEach(cleanup => cleanup()))

it('renders request and token trends for one model', async () => {
  const host = document.createElement('div')
  document.body.append(host)
  const app = createApp(ModelUsageTrend, {
    provider: 'deepseek',
    model: 'deepseek-flash',
    days: [
      {
        date: '2026-09-17',
        requests: 2,
        input_tokens: 100,
        output_tokens: 20,
        cache_read_tokens: 80,
        cache_write_tokens: 0,
        reasoning_tokens: 5,
        total_tokens: 120,
      },
      {
        date: '2026-09-18',
        requests: 5,
        input_tokens: 300,
        output_tokens: 40,
        cache_read_tokens: 120,
        cache_write_tokens: 0,
        reasoning_tokens: 7,
        total_tokens: 340,
      },
      {
        date: '2026-09-19',
        requests: 1,
        input_tokens: 50,
        output_tokens: 10,
        cache_read_tokens: 20,
        cache_write_tokens: 0,
        reasoning_tokens: 0,
        total_tokens: 60,
      },
    ],
  })
  app.mount(host)
  cleanups.push(() => { app.unmount(); host.remove() })
  await nextTick()

  expect(host.textContent).toContain('deepseek-flash')
  expect(host.textContent).toContain('deepseek')
  expect(host.textContent).toContain('API requests8')
  expect(host.textContent).toContain('Tokens520')
  expect(host.querySelectorAll('.echarts-stub')).toHaveLength(2)
})
