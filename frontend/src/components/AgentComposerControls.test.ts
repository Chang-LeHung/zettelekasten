// @vitest-environment jsdom
import { createApp, nextTick } from 'vue'
import { afterEach, expect, it, vi } from 'vitest'
import AgentComposerControls from './AgentComposerControls.vue'

const cleanups: Array<() => void> = []
afterEach(() => cleanups.splice(0).forEach(cleanup => cleanup()))

it('allows changing shell approval while the Agent is running', async () => {
  const updateShellApproval = vi.fn()
  const host = document.createElement('div')
  document.body.append(host)
  const app = createApp(AgentComposerControls, {
    providers: [],
    selectedProviderId: null,
    effort: 'medium',
    shellApproval: 'review',
    disabled: true,
    usage: null,
    currentUsage: null,
    contextComposition: null,
    compactionMaxTokens: 128_000,
    'onUpdate:shellApproval': updateShellApproval,
  })
  app.mount(host)
  cleanups.push(() => { app.unmount(); host.remove() })
  await nextTick()

  host.querySelector<HTMLButtonElement>('.shell-trigger')?.click()
  await nextTick()
  expect(host.querySelector('.shell-popover')).not.toBeNull()

  host.querySelectorAll<HTMLButtonElement>('.shell-option')[1]?.click()
  expect(updateShellApproval).toHaveBeenCalledWith('allow_all')
})

it('keeps cache hit rate available in the compact composer layout', async () => {
  const host = document.createElement('div')
  document.body.append(host)
  const app = createApp(AgentComposerControls, {
    providers: [],
    selectedProviderId: null,
    effort: 'medium',
    shellApproval: 'review',
    disabled: false,
    usage: {
      input_tokens: 20_000,
      output_tokens: 153_000,
      cache_read_tokens: 19_880,
      cache_write_tokens: 0,
      reasoning_tokens: 0,
      total_tokens: 173_000,
      cache_hit_rate: 0.994,
      tokens_per_second: 189.4,
    },
    currentUsage: null,
    contextComposition: null,
    compactionMaxTokens: 128_000,
  })
  app.mount(host)
  cleanups.push(() => { app.unmount(); host.remove() })
  await nextTick()

  expect(host.querySelector('.compact-cache')?.textContent).toContain('99.4%')
  expect(host.querySelector('.compact-speed')?.textContent).toContain('189.4 tok/s')
})
