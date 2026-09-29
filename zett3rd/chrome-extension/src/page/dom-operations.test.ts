// @vitest-environment jsdom
import { beforeEach, expect, it, vi } from 'vitest'
import { applyDOMCommand } from './dom-operations'
import type { BrowserCommand, BrowserDOMPatch } from './browser-protocol'

function edit(change: Partial<BrowserDOMPatch> = {}) {
  return applyDOMCommand({
    type: 'command', id: 'a'.repeat(32), operation: 'update', query: null,
    change: { action: 'fill', selector: '#name', value: 'Ada', description: 'Fill field', ...change },
  })
}
const read: BrowserCommand = { type: 'command', id: 'b'.repeat(32), operation: 'snapshot', change: null, query: null }
function interact(action: 'click' | 'hover' | 'focus' | 'scroll' | 'press_key' | 'drag', changes: Record<string, unknown> = {}) {
  return applyDOMCommand({
    type: 'command', id: 'c'.repeat(32), operation: 'interact', query: null, change: null,
    interaction: {
      action, selector: '#submit', description: 'Inspect interaction',
      target_selector: null, key: null, direction: null, distance: null, ...changes,
    },
  } as BrowserCommand)
}

beforeEach(() => {
  document.body.innerHTML = `<h1 id="title">Original</h1>
    <p id="text">Visible words</p><div id="parent"><span>Child</span></div>
    <form id="form"><label for="name">Name</label><input id="name">
    <input id="password" type="password" value="SECRET"><input type="hidden" value="HIDDEN">
    <input id="file" type="file"><input id="readonly" readonly><input id="disabled" disabled>
    <textarea id="note"></textarea><input id="opt" type="checkbox">
    <div id="prompt-textarea" contenteditable="true" role="textbox"><p><br></p></div>
    <select id="choice"><option value="a">Alpha</option><option value="b">Beta</option><option value="c" disabled>Gamma</option></select>
    <button id="submit" type="submit">Submit</button></form>
    <div hidden>HIDDEN TEXT</div><div style="display:none">INVISIBLE</div><script>var token="SCRIPT SECRET"</script>`
  // jsdom lacks CSS.escape; simple fixture IDs need no escaping.
  if (!globalThis.CSS) vi.stubGlobal('CSS', { escape: (value: string) => value })
  else if (!CSS.escape) CSS.escape = value => value
})

it('fills text/textarea using native setters and emits input/change, never submit', () => {
  const form = document.querySelector('form')!
  const submit = vi.fn()
  form.addEventListener('submit', submit)
  const events: string[] = []
  form.addEventListener('input', () => events.push('input'))
  form.addEventListener('change', () => events.push('change'))
  expect(JSON.parse(edit().result!)).toMatchObject({ applied: true, value: 'Ada' })
  expect((document.querySelector('#name') as HTMLInputElement).value).toBe('Ada')
  expect(events).toEqual(['input', 'change'])
  edit({ selector: '#note', value: 'A note' })
  expect((document.querySelector('#note') as HTMLTextAreaElement).value).toBe('A note')
  expect(submit).not.toHaveBeenCalled()
})

it('sets plain text literally without creating markup or removing child elements', () => {
  edit({ action: 'set_text', selector: '#title', value: '<img src=x onerror=alert(1)>' })
  expect(document.querySelector('#title')!.textContent).toBe('<img src=x onerror=alert(1)>')
  expect(document.querySelector('#title img')).toBeNull()
  expect(() => edit({ action: 'set_text', selector: '#parent' })).toThrow('plain text')
  expect(() => edit({ action: 'set_text', selector: '#submit' })).toThrow('plain text')
})

it('supports only existing enabled options and checkbox booleans', () => {
  expect(JSON.parse(edit({ action: 'select', selector: '#choice', value: 'b' }).result!)).toMatchObject({ applied: true, value: 'b' })
  expect(() => edit({ action: 'select', selector: '#choice', value: 'missing' })).toThrow('option')
  expect(() => edit({ action: 'select', selector: '#choice', value: 'c' })).toThrow('option')
  expect(JSON.parse(edit({ action: 'set_checked', selector: '#opt', value: true }).result!)).toMatchObject({ applied: true, value: true })
  expect(() => edit({ action: 'set_checked', selector: '#opt', value: 'true' })).toThrow('value')
})

it('refuses ambiguous/missing selectors and sensitive or disabled fields', () => {
  for (const selector of ['input', '#missing', '#password', '#file', '#readonly', '#disabled']) {
    expect(() => edit({ selector })).toThrow()
  }
})

it('reads bounded visible text and actionable selectors without hidden/script/password data', () => {
  const result = applyDOMCommand(read)
  const page = JSON.parse(result.result!)
  expect(page.text).toContain('Visible words')
  for (const secret of ['SECRET', 'HIDDEN', 'INVISIBLE']) expect(result.result).not.toContain(secret)
  expect(page.controls.some((control: { selector: string }) => control.selector === '#name')).toBe(true)
  expect(page.controls.some((control: { selector: string }) => control.selector === '#password')).toBe(false)
  expect(JSON.parse(applyDOMCommand({ ...read, query: { selector: '#text' } }).result!).text).toBe('Visible words')
})

it('does not claim success when website handlers replace an entered value', () => {
  document.querySelector('#name')!.addEventListener('input', event => { (event.target as HTMLInputElement).value = 'Rejected' })
  expect(JSON.parse(edit().result!)).toMatchObject({ applied: false, value: 'Rejected' })
})

it('offers contenteditable editors in the page snapshot and fills a nested paragraph using editing input', () => {
  const page = JSON.parse(applyDOMCommand(read).result!)
  expect(page.controls).toEqual(expect.arrayContaining([
    expect.objectContaining({ selector: '#prompt-textarea', type: 'contenteditable' }),
  ]))
  const editor = document.querySelector<HTMLElement>('#prompt-textarea')!
  const input = vi.fn()
  editor.addEventListener('input', input)
  const command = vi.fn((_action: string) => {
    const selection = window.getSelection()!
    expect(selection.toString()).toBe('')
    editor.replaceChildren(document.createElement('p'))
    editor.querySelector('p')!.textContent = '那 gpt6 astra 的价格呢'
    editor.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText', data: '那 gpt6 astra 的价格呢' }))
    return true
  })
  Object.defineProperty(document, 'execCommand', { configurable: true, value: command })
  expect(JSON.parse(edit({ selector: '#prompt-textarea', value: '那 gpt6 astra 的价格呢' }).result!))
    .toMatchObject({ action: 'fill', applied: true, value: '那 gpt6 astra 的价格呢' })
  expect(command).toHaveBeenCalledWith('insertText', false, '那 gpt6 astra 的价格呢')
  expect(input).toHaveBeenCalledTimes(1)
})

it('fails closed when the editor refuses insertion; does not overwrite children with textContent', () => {
  const editor = document.querySelector<HTMLElement>('#prompt-textarea')!
  Object.defineProperty(document, 'execCommand', { configurable: true, value: vi.fn(() => false) })
  expect(() => edit({ selector: '#prompt-textarea', value: 'A question' })).toThrow('refused text input')
  expect(editor.innerHTML).toBe('<p><br></p>')
})

it('dispatches one reviewed click but does not claim the website accepted it', () => {
  const click = vi.fn(event => event.preventDefault())
  document.querySelector('#submit')!.addEventListener('click', click)
  const receipt = JSON.parse(interact('click').result!)
  expect(click).toHaveBeenCalledTimes(1)
  expect(receipt).toMatchObject({ action: 'click', dispatched: true, verified: false })
  expect(receipt.notice).toContain('inspect the page')
  expect(() => interact('click', { selector: '#text' })).toThrow('interactive')
  expect(() => interact('click', { selector: '#disabled' })).toThrow('disabled')
})

it('focuses and sends only bounded synthetic key events', () => {
  const field = document.querySelector<HTMLInputElement>('#name')!
  const received: string[] = []
  field.addEventListener('keydown', event => received.push(event.key))
  const focus = JSON.parse(interact('focus', { selector: '#name' }).result!)
  expect(focus.verified).toBe(true)
  const press = JSON.parse(interact('press_key', { selector: '#name', key: 'Enter' }).result!)
  expect(received).toEqual(['Enter'])
  expect(press.verified).toBe(false)
  expect(() => interact('press_key', { key: 'eval()' })).toThrow('Invalid key')
})

it('scrolls the selected container without arbitrary code', () => {
  const scroller = document.querySelector<HTMLElement>('#parent')!
  scroller.scrollBy = vi.fn()
  const receipt = JSON.parse(interact('scroll', { selector: '#parent', direction: 'down', distance: 240 }).result!)
  expect(scroller.scrollBy).toHaveBeenCalledWith({ left: 0, top: 240, behavior: 'instant' })
  expect(receipt.verified).toBe(false)
  expect(() => interact('scroll', { distance: 100000 })).toThrow('Invalid scroll')
})

it('scrolls the page viewport when the selected container is body', () => {
  const scroll = vi.spyOn(window, 'scrollBy').mockImplementation(() => {})
  const receipt = JSON.parse(interact('scroll', { selector: 'body', direction: 'down', distance: 600 }).result!)
  expect(scroll).toHaveBeenCalledWith({ left: 0, top: 600, behavior: 'instant' })
  expect(receipt.notice).toContain('newly visible page content')
  scroll.mockRestore()
})

it('dispatches drag/drop events with a bounded target and an unverified receipt', () => {
  vi.stubGlobal('DataTransfer', class {})
  vi.stubGlobal('DragEvent', class extends MouseEvent {
    dataTransfer: unknown
    constructor(type: string, options: DragEventInit) {
      super(type, options)
      this.dataTransfer = options.dataTransfer
    }
  })
  const source = document.querySelector('#title')!
  const destination = document.querySelector('#parent')!
  const events: string[] = []
  source.addEventListener('dragstart', () => events.push('start'))
  destination.addEventListener('drop', () => events.push('drop'))
  const receipt = JSON.parse(interact('drag', { selector: '#title', target_selector: '#parent' }).result!)
  expect(events).toEqual(['start', 'drop'])
  expect(receipt).toMatchObject({ dispatched: true, verified: false })
  expect(receipt.notice).toContain('trusted pointer input')
  expect(() => interact('drag', { target_selector: '#missing' })).toThrow('exactly one')
  vi.unstubAllGlobals()
})
