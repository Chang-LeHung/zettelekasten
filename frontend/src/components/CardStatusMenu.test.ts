// @vitest-environment jsdom
import { createApp, h, nextTick } from 'vue'
import { afterEach, expect, it, vi } from 'vitest'
import type { CardStatus } from '../api/types'
import { i18nPlugin } from '../i18n'
import CardStatusMark from './CardStatusMark.vue'
import CardStatusMenu from './CardStatusMenu.vue'

const cleanups: (() => void)[] = []
afterEach(() => cleanups.splice(0).forEach((cleanup) => cleanup()))

function mount(component: typeof CardStatusMark | typeof CardStatusMenu, status: CardStatus, onSelect = vi.fn(), busy = false) {
  const host = document.createElement('div')
  document.body.append(host)
  const app = createApp({ render: () => h(component, { status, busy, onSelect }) })
  app.use(i18nPlugin).mount(host)
  cleanups.push(() => { app.unmount(); host.remove() })
  return { host, onSelect }
}

it('completes an unfinished task and reopens a finished one with the status mark', async () => {
  const open = mount(CardStatusMark, 'in_progress')
  open.host.querySelector('button')!.click()
  expect(open.onSelect).toHaveBeenCalledWith('done')

  const done = mount(CardStatusMark, 'done')
  done.host.querySelector('button')!.click()
  expect(done.onSelect).toHaveBeenCalledWith('open')
})

it('reports the check state to assistive technology', () => {
  const states = (['open', 'in_progress', 'done'] as const).map((status) => (
    mount(CardStatusMark, status).host.querySelector('button')!.getAttribute('aria-checked')
  ))
  expect(states).toEqual(['false', 'mixed', 'true'])
})

it('does not let a click on the circle reach the card that holds it', () => {
  const outer = vi.fn()
  const host = document.createElement('div')
  host.addEventListener('click', outer)
  document.body.append(host)
  const app = createApp({ render: () => h(CardStatusMark, { status: 'open' }) })
  app.use(i18nPlugin).mount(host)
  cleanups.push(() => { app.unmount(); host.remove() })

  host.querySelector('button')!.click()

  expect(outer).not.toHaveBeenCalled()
})

it('ignores the check circle while a change is in flight', () => {
  const { host, onSelect } = mount(CardStatusMark, 'open', vi.fn(), true)
  const button = host.querySelector('button')!
  expect(button.disabled).toBe(true)
  button.click()
  expect(onSelect).not.toHaveBeenCalled()
})

it('opens a menu of the card type\'s own statuses outside the card and selects one', async () => {
  const { host, onSelect } = mount(CardStatusMenu, 'open')
  expect(host.querySelector('.status-pill')!.textContent).toContain('To do')
  expect(document.querySelector('.status-menu')).toBeNull()

  host.querySelector<HTMLButtonElement>('.status-pill')!.click()
  await nextTick()

  // Teleported: a card that clips its overflow cannot cut the menu off.
  expect(host.querySelector('.status-menu')).toBeNull()
  const items = [...document.querySelectorAll<HTMLButtonElement>('.status-menu [role="menuitemradio"]')]
  expect(items.map((item) => item.textContent?.trim())).toEqual(['To do', 'In progress', 'On hold', 'Done', 'Cancelled'])
  expect(items.map((item) => item.getAttribute('aria-checked'))).toEqual(['true', 'false', 'false', 'false', 'false'])

  items[1]!.click()
  await nextTick()

  expect(onSelect).toHaveBeenCalledWith('in_progress')
  expect(document.querySelector('.status-menu')).toBeNull()
})

it('closes without a change on Escape, on an outside press, and when the current status is chosen again', async () => {
  const { host, onSelect } = mount(CardStatusMenu, 'done')
  const pill = () => host.querySelector<HTMLButtonElement>('.status-pill')!

  pill().click()
  await nextTick()
  document.querySelector('.status-menu')!.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
  await nextTick()
  expect(document.querySelector('.status-menu')).toBeNull()

  pill().click()
  await nextTick()
  document.body.dispatchEvent(new Event('pointerdown', { bubbles: true }))
  await nextTick()
  expect(document.querySelector('.status-menu')).toBeNull()

  pill().click()
  await nextTick()
  document.querySelector<HTMLButtonElement>('.status-menu [aria-checked="true"]')!.click()
  await nextTick()
  expect(onSelect).not.toHaveBeenCalled()
})


it('lists only the statuses of the card type that owns the current one', async () => {
  for (const [status, expected] of [
    ['exploring', ['Captured', 'Exploring', 'Adopted', 'Dropped']],
    ['reading', ['Unread', 'Reading', 'Read']],
  ] as const) {
    const { host } = mount(CardStatusMenu, status)
    host.querySelector<HTMLButtonElement>('.status-pill')!.click()
    await nextTick()
    const labels = [...document.querySelectorAll('.status-menu [role="menuitemradio"]')].map((item) => item.textContent?.trim())
    expect(labels).toEqual(expected)
    document.body.dispatchEvent(new Event('pointerdown', { bubbles: true }))
    await nextTick()
  }
})

it('reads and unreads a reference with one click, but never decides an idea', () => {
  const unread = mount(CardStatusMark, 'unread')
  unread.host.querySelector('button')!.click()
  expect(unread.onSelect).toHaveBeenCalledWith('read')

  const read = mount(CardStatusMark, 'read')
  read.host.querySelector('button')!.click()
  expect(read.onSelect).toHaveBeenCalledWith('unread')

  const idea = mount(CardStatusMark, 'exploring')
  expect(idea.host.querySelector('button')).toBeNull()
  expect(idea.host.querySelector('[role="img"]')).not.toBeNull()
})
