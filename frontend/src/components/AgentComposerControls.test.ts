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
