// @vitest-environment jsdom
import { createApp, h, nextTick } from 'vue'
import { afterEach, expect, it, vi } from 'vitest'
import AssetRename from './AssetRename.vue'

const cleanups: (() => void)[] = []
afterEach(() => cleanups.splice(0).forEach(cleanup => cleanup()))

async function editor(save = vi.fn().mockResolvedValue(undefined)) {
  const host = document.createElement('div')
  document.body.append(host)
  const app = createApp({ render: () => h(AssetRename, { name: 'Original.png', save }) })
  app.mount(host)
  cleanups.push(() => { app.unmount(); host.remove() })
  host.querySelector('button')!.click()
  await nextTick()
  return { host, save, input: host.querySelector('input')! }
}

it('focuses the current name and cancels on blur or Escape without saving', async () => {
  const { host, input, save } = await editor()
  expect(input.value).toBe('Original.png')
  expect(document.activeElement).toBe(input)
  input.dispatchEvent(new FocusEvent('blur'))
  await nextTick()
  expect(host.querySelector('input')).toBeNull()
  host.querySelector('button')!.click()
  await nextTick()
  host.querySelector('input')!.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
  await nextTick()
  expect(host.querySelector('input')).toBeNull()
  expect(save).not.toHaveBeenCalled()
})

it('trims the name and keeps failed edits available for retry', async () => {
  const save = vi.fn().mockRejectedValue(new Error('offline'))
  const { host, input } = await editor(save)
  input.value = '  University logo  '
  input.dispatchEvent(new Event('input', { bubbles: true }))
  host.querySelector('form')!.dispatchEvent(new Event('submit', { cancelable: true }))
  await nextTick()
  await nextTick()
  expect(save).toHaveBeenCalledWith('University logo')
  expect(host.querySelector('[role="alert"]')).not.toBeNull()
  expect(host.querySelector('input')!.value).toBe('  University logo  ')
})

it('does not issue duplicate requests while saving', async () => {
  let finish!: () => void
  const save = vi.fn(() => new Promise<void>(resolve => { finish = resolve }))
  const { host, input } = await editor(save)
  input.value = 'New name'
  input.dispatchEvent(new Event('input', { bubbles: true }))
  host.querySelector('form')!.dispatchEvent(new Event('submit', { cancelable: true }))
  host.querySelector('form')!.dispatchEvent(new Event('submit', { cancelable: true }))
  input.dispatchEvent(new FocusEvent('blur'))
  expect(save).toHaveBeenCalledTimes(1)
  finish()
  await nextTick()
  await nextTick()
  expect(host.querySelector('input')).toBeNull()
})
