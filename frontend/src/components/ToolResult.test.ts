// @vitest-environment jsdom
import { createApp, nextTick } from 'vue'
import { afterEach, expect, it, vi } from 'vitest'
import ToolResult from './ToolResult.vue'

const cleanups: (() => void)[] = []
afterEach(() => cleanups.splice(0).forEach(cleanup => cleanup()))

function mount(output: unknown, error: string | null = null): HTMLElement {
  const host = document.createElement('div')
  document.body.append(host)
  const app = createApp(ToolResult, { output, error })
  app.mount(host)
  cleanups.push(() => { app.unmount(); host.remove() })
  return host
}

it('renders image tool output as an image instead of base64 text', async () => {
  const host = mount([
    { text: 'before' },
    { type: 'image', url: 'data:image/png;base64,aW1hZ2U=', alt_text: 'preview.png' },
    { text: 'after' },
  ])
  await nextTick()

  expect(host.querySelector('img')?.getAttribute('src')).toBe('data:image/png;base64,aW1hZ2U=')
  expect(host.querySelector('img')?.getAttribute('alt')).toBe('preview.png')
  expect(host.textContent).toContain('before')
  expect(host.textContent).toContain('after')
  expect(host.textContent).not.toContain('data:image/png;base64')
})

it('emits a preview request when an image result is clicked', async () => {
  const host = document.createElement('div')
  document.body.append(host)
  const previewImage = vi.fn()
  const app = createApp(ToolResult, {
    output: [{ type: 'image', url: 'data:image/png;base64,aW1hZ2U=', alt_text: 'preview.png' }],
    onPreviewImage: previewImage,
  })
  app.mount(host)
  cleanups.push(() => { app.unmount(); host.remove() })
  await nextTick()

  host.querySelector<HTMLButtonElement>('.tool-result-image-button')?.click()
  expect(previewImage).toHaveBeenCalledWith({ name: 'preview.png', url: 'data:image/png;base64,aW1hZ2U=' })
})

it('keeps ordinary tool output and errors as text', async () => {
  const host = mount({ lines: 12 })
  await nextTick()
  expect(host.textContent).toContain('"lines": 12')

  const errorHost = mount(undefined, 'command failed')
  await nextTick()
  expect(errorHost.textContent).toContain('command failed')
})
