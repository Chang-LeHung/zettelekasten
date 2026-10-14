// @vitest-environment jsdom
import { createApp, h, nextTick, ref } from 'vue'
import { afterEach, expect, it, vi } from 'vitest'
import type { CardStatus } from '../api/types'
import { i18nPlugin } from '../i18n'
import LibraryStatusFilter from './LibraryStatusFilter.vue'

const cleanups: Array<() => void> = []
afterEach(() => {
  cleanups.splice(0).forEach((cleanup) => cleanup())
  document.body.innerHTML = ''
})

function mount(initial: CardStatus[] = [], narrow = false) {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({ matches: narrow && query.includes('600px'), media: query })) as never
  const selected = ref<CardStatus[]>(initial)
  const host = document.createElement('div')
  document.body.append(host)
  const app = createApp({
    render: () => h(LibraryStatusFilter, { modelValue: selected.value, 'onUpdate:modelValue': (value: CardStatus[]) => { selected.value = value } }),
  })
  app.use(i18nPlugin).mount(host)
  cleanups.push(() => { app.unmount(); host.remove() })
  return { host, selected }
}

const settle = async () => { for (let index = 0; index < 4; index += 1) await nextTick() }
const trigger = (host: HTMLElement) => host.querySelector<HTMLButtonElement>('.status-filter-trigger')!
const panel = () => document.querySelector<HTMLElement>('.status-panel')
const options = () => [...document.querySelectorAll<HTMLButtonElement>('.status-option')]

it('shows one button, and no tags until something is chosen', () => {
  const { host } = mount()
  expect(trigger(host).textContent).toContain('Status')
  expect(host.querySelector('.status-filter-count')).toBeNull()
  expect(host.querySelector('.status-tag')).toBeNull()
  expect(panel()).toBeNull()
})

it('opens a panel of every status, grouped by card type', async () => {
  const { host } = mount()
  trigger(host).click()
  await settle()

  expect(panel()).not.toBeNull()
  expect([...document.querySelectorAll('.status-panel h3')].map((heading) => heading.textContent)).toEqual(['Todo', 'Idea', 'Reference'])
  expect(options()).toHaveLength(12)
  expect(options().filter((option) => option.getAttribute('aria-checked') === 'true')).toHaveLength(0)
})

it('selects several statuses across types and lists them as tags with a count', async () => {
  const { host, selected } = mount()
  trigger(host).click()
  await settle()

  options().find((option) => option.textContent!.includes('Exploring'))!.click()
  await settle()
  options().find((option) => option.textContent!.includes('To do'))!.click()
  await settle()

  // Kept in menu order whatever order they were picked in.
  expect(selected.value).toEqual(['open', 'exploring'])
  expect(host.querySelector('.status-filter-count')!.textContent).toBe('2')
  expect([...host.querySelectorAll('.status-tag')].map((tag) => tag.textContent!.replace('×', '').trim())).toEqual(['To do', 'Exploring'])
  expect(trigger(host).classList.contains('engaged')).toBe(true)
})

it('removes one status from its tag and clears them all', async () => {
  const { host, selected } = mount(['done', 'read', 'adopted'])

  host.querySelector<HTMLButtonElement>('.status-tag.status-read')!.click()
  await settle()
  expect(selected.value).toEqual(['done', 'adopted'])

  host.querySelector<HTMLButtonElement>('.status-clear')!.click()
  await settle()
  expect(selected.value).toEqual([])
  expect(host.querySelector('.status-tag')).toBeNull()
})

it('closes on Escape, on an outside press, and on Done, giving focus back to the button', async () => {
  const { host } = mount()
  trigger(host).click()
  await settle()
  panel()!.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
  await settle()
  expect(panel()).toBeNull()
  expect(document.activeElement).toBe(trigger(host))

  trigger(host).click()
  await settle()
  document.body.dispatchEvent(new Event('pointerdown', { bubbles: true }))
  await settle()
  expect(panel()).toBeNull()

  trigger(host).click()
  await settle()
  document.querySelector<HTMLButtonElement>('.status-apply')!.click()
  await settle()
  expect(panel()).toBeNull()
})

it('stays open while you pick, and tells assistive technology what is checked', async () => {
  const { host } = mount(['reading'])
  trigger(host).click()
  await settle()

  const reading = options().find((option) => option.textContent!.includes('Reading'))!
  expect(reading.getAttribute('aria-checked')).toBe('true')
  options().find((option) => option.textContent!.includes('Read') && !option.textContent!.includes('Reading') && !option.textContent!.includes('Unread'))!.click()
  await settle()
  expect(panel()).not.toBeNull()
})

it('becomes a bottom sheet on a narrow screen', async () => {
  const { host } = mount([], true)
  trigger(host).click()
  await settle()

  expect(panel()!.classList.contains('sheet')).toBe(true)
  expect(panel()!.style.top).toBe('')
})
