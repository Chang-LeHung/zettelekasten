// @vitest-environment jsdom
import { createApp, nextTick } from 'vue'
import { afterEach, expect, it, vi } from 'vitest'
import TraceCopyBlock from './TraceCopyBlock.vue'

const cleanups: (() => void)[] = []
afterEach(() => cleanups.splice(0).forEach(cleanup => cleanup()))

it('copies trace content and shows feedback', async () => {
  const writeText = vi.fn().mockResolvedValue(undefined)
  Object.defineProperty(navigator, 'clipboard', {
    configurable: true,
    value: { writeText },
  })
  const host = document.createElement('div')
  document.body.append(host)
  const app = createApp(TraceCopyBlock, {
    content: '{"ok":true}',
    label: 'JSON',
  })
  app.mount(host)
  cleanups.push(() => { app.unmount(); host.remove() })
  await nextTick()

  const button = host.querySelector<HTMLButtonElement>('.trace-copy-button')!
  button.click()
  await Promise.resolve()
  await nextTick()

  expect(writeText).toHaveBeenCalledWith('{"ok":true}')
  expect(button.textContent).toContain('Copied')
})
