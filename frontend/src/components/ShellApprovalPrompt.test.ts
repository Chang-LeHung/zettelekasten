// @vitest-environment jsdom
import { createApp, nextTick } from 'vue'
import { afterEach, expect, it, vi } from 'vitest'
import ShellApprovalPrompt from './ShellApprovalPrompt.vue'

const cleanups: (() => void)[] = []
afterEach(() => cleanups.splice(0).forEach(cleanup => cleanup()))

it('sends execute with the remembered allowlist choice', async () => {
  const execute = vi.fn()
  const abort = vi.fn()
  const host = document.createElement('div')
  document.body.append(host)
  const app = createApp(ShellApprovalPrompt, {
    command: 'git status --short',
    timeoutSeconds: 30,
    rememberSupported: true,
    submitting: false,
    onExecute: execute,
    onAbort: abort,
  })
  app.mount(host)
  cleanups.push(() => { app.unmount(); host.remove() })
  await nextTick()

  host.querySelector<HTMLInputElement>('.remember input')?.click()
  host.querySelector<HTMLButtonElement>('.execute')?.click()
  expect(execute).toHaveBeenCalledWith(true)
  host.querySelector<HTMLButtonElement>('.abort')?.click()
  expect(abort).toHaveBeenCalledOnce()
})
