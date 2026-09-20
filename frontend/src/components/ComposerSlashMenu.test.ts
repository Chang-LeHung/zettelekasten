// @vitest-environment jsdom
import { createApp, defineComponent, h, nextTick, ref } from 'vue'
import { afterEach, expect, it, vi } from 'vitest'
import type { AgentSlashCommand } from '../api/types'
import ComposerSlashMenu from './ComposerSlashMenu.vue'

const cleanups: (() => void)[] = []
const originalScrollIntoView = Element.prototype.scrollIntoView

afterEach(() => {
  cleanups.splice(0).forEach(cleanup => cleanup())
  if (originalScrollIntoView) {
    Element.prototype.scrollIntoView = originalScrollIntoView
  } else {
    delete (Element.prototype as { scrollIntoView?: unknown }).scrollIntoView
  }
})

function slashCommands(count: number): AgentSlashCommand[] {
  return Array.from({ length: count }, (_, index) => ({
    id: `command-${index}`,
    name: `skill-${index}`,
    description: `Skill ${index}`,
    type: 'skill',
  }))
}

function mountMenu(count: number, activeIndex: number) {
  const commands = slashCommands(count)
  const active = ref(activeIndex)
  const host = document.createElement('div')
  document.body.append(host)
  const app = createApp(defineComponent({
    setup() {
      return () => h(ComposerSlashMenu, {
        commands,
        activeIndex: active.value,
        loading: false,
        heading: 'Slash commands',
        hint: 'Select one command',
        emptyLabel: 'No slash commands available.',
      })
    },
  }))
  app.mount(host)
  cleanups.push(() => { app.unmount(); host.remove() })
  return { host, active }
}

it('renders every command and highlights the active one', async () => {
  const { host, active } = mountMenu(8, 0)
  await nextTick()

  const rows = host.querySelectorAll<HTMLButtonElement>('.slash-menu-list button')
  expect(rows).toHaveLength(8)
  expect(rows[0].classList.contains('active')).toBe(true)

  active.value = 3
  await nextTick()
  expect(host.querySelectorAll<HTMLButtonElement>('.slash-menu-list button')[3].classList.contains('active')).toBe(true)
  expect(host.querySelectorAll<HTMLButtonElement>('.slash-menu-list button')[0].classList.contains('active')).toBe(false)
})

it('scrolls the arrow-key selection back into the visible window', async () => {
  const scrollIntoView = vi.fn()
  Object.defineProperty(Element.prototype, 'scrollIntoView', {
    value: scrollIntoView,
    configurable: true,
    writable: true,
  })
  const { host, active } = mountMenu(8, 0)
  await nextTick()
  scrollIntoView.mockClear()

  active.value = 7
  await nextTick()
  await nextTick()

  const rows = host.querySelectorAll<HTMLButtonElement>('.slash-menu-list button')
  expect(scrollIntoView).toHaveBeenCalledTimes(1)
  expect(scrollIntoView.mock.instances[0]).toBe(rows[7])
})
