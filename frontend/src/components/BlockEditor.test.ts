// @vitest-environment jsdom
import { createApp, h, nextTick, ref } from 'vue'
import { afterEach, expect, it } from 'vitest'
import { i18nPlugin } from '../i18n'
import BlockEditor from './BlockEditor.vue'

const cleanups: Array<() => void> = []
afterEach(() => {
  cleanups.splice(0).forEach((cleanup) => cleanup())
  document.body.innerHTML = ''
})

/** Mount the editor over a ref, the way a page binds `v-model`, and record each write-back. */
async function editor(initial: string, props: Record<string, unknown> = {}) {
  const model = ref(initial)
  const writes: string[] = []
  const host = document.createElement('div')
  document.body.append(host)
  const app = createApp({
    render: () => h(BlockEditor, {
      modelValue: model.value,
      'onUpdate:modelValue': (value: string) => { writes.push(value); model.value = value },
      ...props,
    }),
  })
  app.use(i18nPlugin).mount(host)
  cleanups.push(() => { app.unmount(); host.remove() })
  await nextTick()
  return { host, model, writes }
}

const settle = async () => { for (let index = 0; index < 4; index += 1) await nextTick() }
const rows = (host: HTMLElement) => [...host.querySelectorAll<HTMLElement>('.block-row')]
const input = (host: HTMLElement) => host.querySelector<HTMLTextAreaElement>('.block-input')

async function open(host: HTMLElement, index: number) {
  rows(host)[index]!.querySelector<HTMLElement>('.block-view')!.click()
  await settle()
  return input(host)!
}

async function type(area: HTMLTextAreaElement, value: string) {
  area.value = value
  area.setSelectionRange(value.length, value.length)
  area.dispatchEvent(new Event('input', { bubbles: true }))
  await settle()
}

async function press(area: HTMLElement, key: string, init: KeyboardEventInit = {}) {
  area.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true, ...init }))
  await settle()
}

it('shows one rendered block per paragraph and writes nothing back until you edit', async () => {
  const { host, writes } = await editor('# Title\n\nFirst paragraph.\n\n- a\n- b')

  expect(rows(host)).toHaveLength(3)
  expect(rows(host)[0]!.classList.contains('kind-heading')).toBe(true)
  expect(rows(host)[2]!.classList.contains('kind-list')).toBe(true)
  expect(host.querySelector('.block-input')).toBeNull()
  expect(writes).toEqual([])
})

it('turns a clicked block into its Markdown source, and back, without changing the document', async () => {
  const { host, writes } = await editor('# Title\n\nText with **bold**.')

  const area = await open(host, 1)
  expect(area.value).toBe('Text with **bold**.')
  await press(area, 'Escape')

  expect(host.querySelector('.block-input')).toBeNull()
  expect(writes).toEqual([])
})

it('writes back exactly what was typed, leaving every other block as it was', async () => {
  const source = 'one\n\n\n\ntwo\n\n```\nx\n\ny\n```\n'
  const { host, writes } = await editor(source)

  const area = await open(host, 1)
  await type(area, 'two!')

  expect(writes.at(-1)).toBe('one\n\n\n\ntwo!\n\n```\nx\n\ny\n```\n')
})

it('splits a block at the caret on Enter, and joins the words back with Backspace', async () => {
  const { host, writes } = await editor('hello world')
  const area = await open(host, 0)
  area.setSelectionRange(5, 5)

  await press(area, 'Enter')

  expect(rows(host)).toHaveLength(2)
  expect(writes.at(-1)).toBe('hello\n\n world')
  const second = input(host)!
  expect(second.value).toBe(' world')
  second.setSelectionRange(0, 0)

  await press(second, 'Backspace')

  expect(rows(host)).toHaveLength(1)
  expect(writes.at(-1)).toBe('hello world')
})

it('does not leave an empty block behind in the written document', async () => {
  const { host, writes, model } = await editor('only line\n')
  const area = await open(host, 0)

  await press(area, 'Enter')

  expect(rows(host)).toHaveLength(2)
  // A block you have not typed in yet is not part of the document.
  expect(model.value).toBe('only line\n')
  await type(input(host)!, 'next')
  expect(writes.at(-1)).toBe('only line\n\nnext\n')
})

it('keeps Enter inside a code fence as a line break', async () => {
  const { host } = await editor('```js\nlet a = 1')
  const area = await open(host, 0)

  await press(area, 'Enter')

  expect(rows(host)).toHaveLength(1)
})

it('continues a list on Enter and leaves it on an empty item', async () => {
  const { host, writes } = await editor('- one')
  const area = await open(host, 0)

  await press(area, 'Enter')
  expect(input(host)!.value).toBe('- one\n- ')
  await type(input(host)!, '- one\n- two')
  await press(input(host)!, 'Enter')
  expect(input(host)!.value).toBe('- one\n- two\n- ')

  await press(input(host)!, 'Enter')

  expect(rows(host)).toHaveLength(2)
  expect(writes.at(-1)).toBe('- one\n- two')
})

it('turns a pasted run of paragraphs into separate blocks', async () => {
  const { host, writes } = await editor('start')
  const area = await open(host, 0)

  await type(area, 'start\n\nsecond\n\nthird')

  expect(rows(host)).toHaveLength(3)
  expect(writes.at(-1)).toBe('start\n\nsecond\n\nthird')
})

it('opens the slash menu, filters it, and turns the block into the chosen kind', async () => {
  const { host, writes } = await editor('intro')
  const area = await open(host, 0)
  await press(area, 'Enter')
  const fresh = input(host)!

  await type(fresh, '/h2')
  expect(document.querySelector('.slash-menu')).not.toBeNull()
  expect(document.querySelectorAll('.slash-item')).toHaveLength(1)

  await press(fresh, 'Enter')

  expect(input(host)!.value).toBe('## ')
  await type(input(host)!, '## Section')
  expect(writes.at(-1)).toBe('intro\n\n## Section')
  expect(document.querySelector('.slash-menu')).toBeNull()
})

it('lists deck commands only for a slide deck', async () => {
  const prose = await editor('x')
  await type(await open(prose.host, 0), '/')
  expect(document.body.textContent).not.toContain('New slide')
  cleanups.pop()!()

  const deck = await editor('x', { slides: true })
  await type(await open(deck.host, 0), '/')
  expect(document.body.textContent).toContain('New slide')
})

it('does not open the slash menu inside code, or in the middle of a word', async () => {
  const { host } = await editor('```\n')
  await type(await open(host, 0), '```\nhttp://example.com/')
  expect(document.querySelector('.slash-menu')).toBeNull()
  cleanups.pop()!()

  const prose = await editor('a')
  await type(await open(prose.host, 0), 'a/b')
  expect(document.querySelector('.slash-menu')).toBeNull()
})

it('draws a deck page break as a labelled divider and splits it without blank lines', async () => {
  const { host } = await editor('# A\n--\n# B\n---\n# C', { slides: true })

  expect(rows(host).map((row) => [...row.classList].find((name) => name.startsWith('kind-')))).toEqual([
    'kind-heading', 'kind-slideBreak', 'kind-heading', 'kind-sectionBreak', 'kind-heading',
  ])
  expect(host.querySelector('.slide-break.slideBreak')!.textContent).toContain('New slide')
})

it('follows a change made somewhere else instead of keeping stale blocks', async () => {
  const { host, model } = await editor('one\n\ntwo')

  model.value = 'one\n\ntwo\n\nthree'
  await settle()

  expect(rows(host)).toHaveLength(3)
})

it('undoes and redoes a whole step', async () => {
  const { host, writes } = await editor('keep')
  const area = await open(host, 0)
  await type(area, 'keep this')

  await press(input(host)!, 'z', { metaKey: true })
  expect(writes.at(-1)).toBe('keep')

  await press(input(host)!, 'z', { metaKey: true, shiftKey: true })
  expect(writes.at(-1)).toBe('keep this')
})

it('wraps the selection with the bold shortcut, and unwraps it again', async () => {
  const { host, writes } = await editor('make this bold')
  const area = await open(host, 0)
  area.setSelectionRange(5, 9)

  await press(area, 'b', { metaKey: true })
  expect(writes.at(-1)).toBe('make **this** bold')
  const again = input(host)!
  again.setSelectionRange(7, 11)

  await press(again, 'b', { metaKey: true })
  expect(writes.at(-1)).toBe('make this bold')
})

it('ignores Enter while an input method is composing', async () => {
  const { host } = await editor('你好')
  const area = await open(host, 0)

  area.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', isComposing: true, bubbles: true, cancelable: true }))
  await settle()

  expect(rows(host)).toHaveLength(1)
})

it('ticks a task with one click, without opening the block or touching other text', async () => {
  const { host, writes } = await editor('- [ ] write the docs\n- [x] ship it')

  host.querySelector<HTMLElement>('.task-box[data-task="0"]')!.click()
  await settle()

  expect(writes.at(-1)).toBe('- [x] write the docs\n- [x] ship it')
  expect(host.querySelector('.block-input')).toBeNull()
  host.querySelector<HTMLElement>('.task-box[data-task="1"]')!.click()
  await settle()
  expect(writes.at(-1)).toBe('- [x] write the docs\n- [ ] ship it')
})
