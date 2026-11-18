// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { applyDOMCommand, waitFor } from './dom-operations'
import { clearOutline } from './outline'
import type { BrowserCommand, BrowserDOMPatch, BrowserWaitQuery } from './browser-protocol'

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
  expect(() => interact('click', { selector: '#text' })).toThrow('plain content')
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
  expect(() => interact('drag', { target_selector: '#missing' })).toThrow('No element matches')
  vi.unstubAllGlobals()
})

function mutate(selector: string) {
  return () => applyDOMCommand({ ...read, query: { selector } })
}

it('names the candidates when a selector is ambiguous, so the next call can be exact', () => {
  document.body.innerHTML = '<button class="buy" name="first">Add to cart</button><button class="buy">Add to cart</button>'
  try {
    mutate('.buy')()
    expect.unreachable()
  } catch (error) {
    const message = (error as Error).message
    expect(message).toContain('matches 2 elements')
    expect(message).toContain('button[name="first"]')
    expect(message).toContain('"Add to cart"')
    expect(message.length).toBeLessThanOrEqual(1000)
  }
})

it('explains missing, invalid, and hidden selectors in words the model can act on', () => {
  document.body.innerHTML = '<div style="display:none"><button id="gone">Gone</button></div>'
  expect(mutate('#nope')).toThrow('get_browser_page again')
  expect(mutate('###')).toThrow('not a valid CSS selector')
  expect(mutate('#gone')).toThrow('ancestor has display: none')
})

it('finds elements by their visible text and returns usable selectors', () => {
  document.body.innerHTML = '<p>Intro</p><button id="pay">Pay now</button><a href="/x">Pay later</a><div style="display:none">Pay hidden</div>'
  const result = JSON.parse(applyDOMCommand({ ...read, query: { selector: null, text: 'pay' } }).result!)
  expect(result.total).toBe(2)
  expect(result.matches.map((match: { selector: string }) => match.selector)).toContain('#pay')
  expect(result.matches.every((match: { interactive: boolean }) => match.interactive)).toBe(true)
  const none = JSON.parse(applyDOMCommand({ ...read, query: { selector: null, text: 'absent' } }).result!)
  expect(none).toMatchObject({ total: 0, matches: [] })
})

it('clicks the control a child sits in, and refuses plain content with guidance', () => {
  document.body.innerHTML = '<button id="b"><span id="inner">Go</span></button><p id="para">Words</p><div id="card" onclick="void 0">Card</div>'
  const clicked = vi.fn()
  document.querySelector('#b')!.addEventListener('click', clicked)
  expect(() => interact('click', { selector: '#inner' })).not.toThrow()
  expect(clicked).toHaveBeenCalledTimes(1)
  expect(() => interact('click', { selector: '#para' })).toThrow('plain content')
  expect(() => interact('click', { selector: '#card' })).not.toThrow()
})

it('reports where the page is scrolled and each control’s link target', () => {
  document.body.innerHTML = '<a id="link" href="https://example.com/next">Next</a>'
  const page = JSON.parse(applyDOMCommand(read).result!)
  expect(page.scroll).toMatchObject({ y: 0 })
  expect(page.controls[0]).toMatchObject({ selector: '#link', href: 'https://example.com/next' })
})

function inspectElement(selector: string): BrowserCommand {
  return {
    type: 'command', id: 'd'.repeat(32), operation: 'inspect', query: null, change: null, interaction: null,
    inspect: { selector },
  } as BrowserCommand
}

/** jsdom lays nothing out, so a test that cares about geometry places the box itself. */
function place(element: Element, rect: Partial<DOMRect>) {
  element.getBoundingClientRect = () => ({
    x: 0, y: 0, left: 0, top: 0, right: 0, bottom: 0, width: 0, height: 0,
    toJSON: () => ({}), ...rect,
  }) as DOMRect
}

// A hit-test stub must not leak into the tests that run after it.
afterEach(() => {
  delete (document as unknown as { elementFromPoint?: unknown }).elementFromPoint
  // An inspection outlines its element; the next test must start clean.
  clearOutline()
})

it('inspects one element without changing the page', () => {
  document.body.innerHTML = '<button id="buy" class="cta" aria-label="Buy now">Buy</button>'
  place(document.querySelector('#buy')!, { left: 20, top: 30, width: 120, height: 40, right: 140, bottom: 70 })
  const before = document.body.innerHTML
  const receipt = JSON.parse(applyDOMCommand(inspectElement('#buy')).result!)
  expect(document.body.innerHTML).toBe(before)
  expect(receipt).toMatchObject({
    selector: '#buy', tag: 'button', label: 'Buy now', rendered: true, in_viewport: true,
    url: location.href,
    spacing: { order: 'top,right,bottom,left' },
    box: { x: 20, y: 30, width: 120, height: 40 },
    hit: { point: [80, 50] },
    states: { interactive: true, disabled: false, focused: false, resolved_selector: '#buy' },
  })
  expect(receipt.style).toHaveProperty('display')
  expect(receipt.viewport).toMatchObject({ width: expect.any(Number), scroll_x: 0 })
})

it('diagnoses an element an ancestor hides instead of refusing to inspect it', () => {
  document.body.innerHTML = '<div style="display:none"><button id="gone">Gone</button></div>'
  const receipt = JSON.parse(applyDOMCommand(inspectElement('#gone')).result!)
  expect(receipt.rendered).toBe(false)
  expect(receipt.hidden_reason).toContain('display: none')
  expect(receipt.findings.join(' ')).toContain('not rendered')
  expect(receipt.accepts).toMatchObject({ set_text: false, fill: false, click: null })
})

it('keeps a visibility override visible in every tool, not only in a diagnosis', () => {
  document.body.innerHTML = '<div style="visibility:hidden"><p id="shown" style="visibility:visible">Shown</p></div>'
  place(document.querySelector('#shown')!, { left: 10, top: 10, width: 60, height: 20, right: 70, bottom: 30 })
  const receipt = JSON.parse(applyDOMCommand(inspectElement('#shown')).result!)
  expect(receipt).toMatchObject({ rendered: true, refused_reason: null })
  expect(receipt.accepts).toMatchObject({ set_text: true })
  const page = JSON.parse(applyDOMCommand(read).result!)
  expect(page.elements.map((item: { selector: string }) => item.selector)).toContain('#shown')
  expect(JSON.parse(edit({ action: 'set_text', selector: '#shown', value: 'Changed' }).result!))
    .toMatchObject({ applied: true })
})

it('separates "not rendered" from "page tools exclude it"', () => {
  document.body.innerHTML = '<div aria-hidden="true"><button id="icon">Settings</button></div>'
    + '<input id="pw" type="password" placeholder="Enter SECRET" value="SECRET">'
  place(document.querySelector('#icon')!, { left: 10, top: 10, width: 40, height: 40, right: 50, bottom: 50 })
  const icon = JSON.parse(applyDOMCommand(inspectElement('#icon')).result!)
  expect(icon).toMatchObject({ rendered: true, refused_reason: expect.stringContaining('aria-hidden') })
  expect(icon.findings.join(' ')).toContain('refuse')
  expect(icon.accepts).toMatchObject({ set_text: false, fill: false, select: false, set_checked: false, click: null })

  const password = JSON.parse(applyDOMCommand(inspectElement('#pw')).result!)
  expect(password).toMatchObject({ rendered: true, refused_reason: expect.stringContaining('password') })
  expect(password.text).toBe('')
  expect(password.label).toBe('')
  expect(JSON.stringify(password)).not.toContain('SECRET')
})

it('keeps script and template source out of a diagnosis', () => {
  document.body.innerHTML = '<script id="code">var token = "SCRIPT SECRET"</script><template id="tpl">TEMPLATE SECRET</template>'
  for (const [selector, rule] of [['#code', 'script'], ['#tpl', 'template']]) {
    const receipt = JSON.parse(applyDOMCommand(inspectElement(selector)).result!)
    expect(receipt.text).toBe('')
    expect(receipt.refused_reason).toContain(rule)
    expect(JSON.stringify(receipt)).not.toContain('SECRET')
  }
})

it('refuses an excluded element with the rule that applies and advice that fits', () => {
  document.body.innerHTML = '<input id="pw" type="password" value="SECRET">'
    + '<div style="display:none"><button id="gone">Gone</button></div>'
  expect(() => edit({ selector: '#pw' })).toThrow('it is a password field')
  expect(() => edit({ selector: '#pw' })).toThrow('Page tools never touch this element')
  expect(() => edit({ selector: '#gone' })).toThrow('Read the page again for a visible element')
})

it('treats content-visibility: hidden as not rendered', () => {
  document.body.innerHTML = '<div style="content-visibility:hidden"><button id="skip">Skip</button></div>'
  const receipt = JSON.parse(applyDOMCommand(inspectElement('#skip')).result!)
  expect(receipt.rendered).toBe(false)
  expect(receipt.hidden_reason).toContain('content-visibility')
  expect(receipt.accepts).toMatchObject({ click: null })
})

it('names what covers an element, and says a pointer cannot reach it', () => {
  document.body.innerHTML = '<button id="buy">Buy</button><div id="banner">Cookies</div>'
  const button = document.querySelector('#buy')!
  const banner = document.querySelector('#banner')!
  place(button, { left: 20, top: 20, width: 120, height: 40, right: 140, bottom: 60 })
  place(banner, { left: 0, top: 0, width: 400, height: 200, right: 400, bottom: 200 })
  Object.defineProperty(document, 'elementFromPoint', { configurable: true, value: () => banner })
  const covered = JSON.parse(applyDOMCommand(inspectElement('#buy')).result!)
  expect(covered.hit).toMatchObject({ reaches_target: false, covered_by: { selector: '#banner' } })
  expect(covered.findings.join(' ')).toContain('#banner')
  // The extension's own click dispatches on the element, so the receipt must not
  // read as proof that clicking this element is pointless.
  expect(covered.notice).toContain('dispatches on the element itself')

  Object.defineProperty(document, 'elementFromPoint', { configurable: true, value: () => button })
  const reachable = JSON.parse(applyDOMCommand(inspectElement('#buy')).result!)
  expect(reachable.hit).toMatchObject({ reaches_target: true })
})

it('says a point cannot reach an element that is off screen or has no box', () => {
  document.body.innerHTML = '<button id="far">Far</button><button id="flat">Flat</button>'
  place(document.querySelector('#far')!, { left: 0, top: -400, width: 80, height: 20, right: 80, bottom: -380 })
  const offscreen = JSON.parse(applyDOMCommand(inspectElement('#far')).result!)
  expect(offscreen).toMatchObject({ in_viewport: false, hit: { point: null } })
  expect(offscreen.findings.join(' ')).toContain('viewport')

  const flat = JSON.parse(applyDOMCommand(inspectElement('#flat')).result!)
  expect(flat.findings.join(' ')).toContain('box is 0x0')
})

it('names the ancestor that clips an element, with its scroll position', () => {
  document.body.innerHTML = '<div id="scroller" style="overflow-x:hidden;overflow-y:hidden"><button id="inside">Buy</button></div>'
  place(document.querySelector('#scroller')!, { left: 0, top: 0, width: 200, height: 100, right: 200, bottom: 100 })
  place(document.querySelector('#inside')!, { left: 40, top: 160, width: 80, height: 20, right: 120, bottom: 180 })
  const receipt = JSON.parse(applyDOMCommand(inspectElement('#inside')).result!)
  expect(receipt.clipped_by).toMatchObject({ selector: '#scroller', overflow: 'hidden/hidden', scroll_top: 0 })
  expect(receipt.findings.join(' ')).toContain('#scroller')
})

it('does not call an in-flow overflow ancestor a clipper of a fixed element', () => {
  document.body.innerHTML = '<div id="shell" style="overflow-x:hidden;overflow-y:hidden">'
    + '<div id="modal" style="position:fixed">Dialog</div></div>'
  place(document.querySelector('#shell')!, { left: 0, top: 0, width: 100, height: 100, right: 100, bottom: 100 })
  place(document.querySelector('#modal')!, { left: 300, top: 300, width: 200, height: 100, right: 500, bottom: 400 })
  const receipt = JSON.parse(applyDOMCommand(inspectElement('#modal')).result!)
  expect(receipt.clipped_by).toBeNull()
})

it('clips a fixed element through the ancestor that is its containing block', () => {
  document.body.innerHTML = '<div id="frame" style="transform:translateZ(0);overflow-x:hidden;overflow-y:hidden">'
    + '<div id="dialog" style="position:fixed">Dialog</div></div>'
  place(document.querySelector('#frame')!, { left: 0, top: 0, width: 100, height: 100, right: 100, bottom: 100 })
  place(document.querySelector('#dialog')!, { left: 300, top: 300, width: 200, height: 100, right: 500, bottom: 400 })
  const receipt = JSON.parse(applyDOMCommand(inspectElement('#dialog')).result!)
  expect(receipt.clipped_by).toMatchObject({ selector: '#frame' })
})

it('does not clip an absolute element through a static overflow ancestor', () => {
  document.body.innerHTML = '<div id="wrap" style="overflow-x:hidden;overflow-y:hidden">'
    + '<div id="tip" style="position:absolute">Tip</div></div>'
  place(document.querySelector('#wrap')!, { left: 0, top: 0, width: 100, height: 100, right: 100, bottom: 100 })
  place(document.querySelector('#tip')!, { left: 300, top: 20, width: 120, height: 40, right: 420, bottom: 60 })
  const receipt = JSON.parse(applyDOMCommand(inspectElement('#tip')).result!)
  expect(receipt.clipped_by).toBeNull()
})

it('measures clipping at the padding box, not the border box', () => {
  document.body.innerHTML = '<div id="box" style="overflow-x:hidden;overflow-y:hidden;'
    + 'border-left-width:10px;border-right-width:10px;border-top-width:10px;border-bottom-width:10px">'
    + '<button id="edge">Edge</button></div>'
  place(document.querySelector('#box')!, { left: 0, top: 0, width: 200, height: 100, right: 200, bottom: 100 })
  place(document.querySelector('#edge')!, { left: 2, top: 15, width: 80, height: 20, right: 82, bottom: 35 })
  const receipt = JSON.parse(applyDOMCommand(inspectElement('#edge')).result!)
  expect(receipt.clipped_by).toMatchObject({ selector: '#box' })
})

it('reports pointer-events: none as a reason a person cannot click it', () => {
  document.body.innerHTML = '<button id="ghost" style="pointer-events:none">Ghost</button>'
  place(document.querySelector('#ghost')!, { left: 10, top: 10, width: 80, height: 30, right: 90, bottom: 40 })
  const receipt = JSON.parse(applyDOMCommand(inspectElement('#ghost')).result!)
  expect(receipt.style['pointer-events']).toBe('none')
  expect(receipt.findings.join(' ')).toContain('pointer-events')
})

it('resolves the control an SVG element sits in instead of calling it plain content', () => {
  document.body.innerHTML = '<button id="btn"><svg><path id="shape"></path></svg>Button</button>'
  place(document.querySelector('#btn')!, { left: 10, top: 10, width: 100, height: 40, right: 110, bottom: 50 })
  const receipt = JSON.parse(applyDOMCommand(inspectElement('#shape')).result!)
  expect(receipt.states.resolved_selector).toBe('#btn')
  expect(receipt.findings.join(' ')).toContain('#btn')
})

it('names the candidates for an ambiguous inspection selector', () => {
  document.body.innerHTML = '<button class="buy">Add to cart</button><button class="buy">Buy</button>'
  try {
    applyDOMCommand(inspectElement('.buy'))
    expect.unreachable()
  } catch (error) {
    expect((error as Error).message).toContain('matches 2 elements')
  }
})

it('reports the panel itself as the covering element instead of inventing page content', () => {
  document.body.innerHTML = '<button id="buy">Buy</button><div id="zettelekasten-panel-host"></div>'
  const host = document.querySelector('#zettelekasten-panel-host')!
  place(document.querySelector('#buy')!, { left: 20, top: 20, width: 120, height: 40, right: 140, bottom: 60 })
  Object.defineProperty(document, 'elementFromPoint', { configurable: true, value: () => host })
  const receipt = JSON.parse(applyDOMCommand(inspectElement('#buy')).result!)
  expect(receipt.hit.covered_by).toBeUndefined()
  expect(receipt.hit.reaches_target).toBeUndefined()
  expect(receipt.hit.skipped).toContain('Zett panel')
  expect(receipt.findings.join(' ')).not.toContain('Zett panel')
})

it('uses the same disabled and read-only rules the mutating tools enforce', () => {
  document.body.innerHTML = '<fieldset disabled><input id="wrapped"></fieldset>'
    + '<input id="plain" readonly><input id="aria" aria-readonly="true">'
  const wrapped = JSON.parse(applyDOMCommand(inspectElement('#wrapped')).result!)
  expect(wrapped.states.disabled).toBe(true)
  expect(wrapped.accepts).toMatchObject({ set_text: false, fill: false, click: null })
  expect(wrapped.findings.join(' ')).toContain('disabled')

  const readonly = JSON.parse(applyDOMCommand(inspectElement('#plain')).result!)
  expect(readonly.states.readonly).toBe(true)
  expect(readonly.findings.join(' ')).toContain('every action')

  // `aria-readonly` is not a rule either tool applies, so inspect must not claim it is.
  const aria = JSON.parse(applyDOMCommand(inspectElement('#aria')).result!)
  expect(aria.states.readonly).toBe(false)
  expect(aria.findings.join(' ')).not.toContain('read-only')
})

it('says which tool would accept the element', () => {
  document.body.innerHTML = '<p id="prose">Words</p><input id="text"><input id="box" type="checkbox">'
    + '<select id="many" multiple><option>a</option><option>b</option></select><button id="go">Go</button>'
  const accepts = (selector: string) => JSON.parse(applyDOMCommand(inspectElement(selector)).result!).accepts
  expect(accepts('#prose')).toMatchObject({ set_text: true, fill: false, click: null })
  expect(accepts('#text')).toMatchObject({ fill: true, set_text: false })
  expect(accepts('#box')).toMatchObject({ set_checked: true, fill: false })
  expect(accepts('#many')).toMatchObject({ select: false })
  expect(accepts('#go')).toMatchObject({ click: '#go', set_text: false })
})

it('flags a nested editable region its editor refuses to fill', () => {
  document.body.innerHTML = '<div contenteditable="false"><div id="nested" contenteditable="true">Text</div></div>'
  const receipt = JSON.parse(applyDOMCommand(inspectElement('#nested')).result!)
  expect(receipt.accepts).toMatchObject({ fill: false, set_text: false })
  expect(receipt.findings.join(' ')).toContain('outer editor')
})

it('does not promise a click through a control that is disabled', () => {
  document.body.innerHTML = '<button id="save" disabled><span id="lib">Save</span></button>'
  const receipt = JSON.parse(applyDOMCommand(inspectElement('#lib')).result!)
  expect(receipt.accepts.click).toBeNull()
  expect(receipt.findings.join(' ')).toContain('disabled')
})

function waitQuery(partial: Partial<BrowserWaitQuery>): BrowserWaitQuery {
  return { condition: 'appear', selector: null, text: null, timeout_ms: 500, ...partial }
}

it('waits for a condition that already holds without spending the timeout', async () => {
  document.body.innerHTML = '<p id="saved">Saved</p>'
  const bySelector = JSON.parse((await waitFor(waitQuery({ selector: '#saved' }))).result!)
  expect(bySelector).toMatchObject({ matched: true, condition: 'appear' })
  expect(bySelector.waited_ms).toBeLessThan(400)
  const byText = JSON.parse((await waitFor(waitQuery({ text: 'SAVED' }))).result!)
  expect(byText.matched).toBe(true)
  const alreadyGone = JSON.parse((await waitFor(waitQuery({ condition: 'disappear', selector: '#missing' }))).result!)
  expect(alreadyGone.matched).toBe(true)
})

it('answers a timeout as information, not as a failed call', async () => {
  document.body.innerHTML = '<p id="saved">Saved</p>'
  const receipt = JSON.parse((await waitFor(waitQuery({ selector: '#missing' }))).result!)
  expect(receipt).toMatchObject({ matched: false, condition: 'appear' })
  expect(receipt.notice).toContain('did not hold')
  expect(receipt.waited_ms).toBeGreaterThanOrEqual(400)
})

it('reacts to a text change as it happens, not on a polling tick', async () => {
  document.body.innerHTML = '<p id="status">Loading</p>'
  const pending = waitFor(waitQuery({ text: 'ready', timeout_ms: 1500 }))
  setTimeout(() => { document.querySelector('#status')!.textContent = 'Ready' }, 60)
  const receipt = JSON.parse((await pending).result!)
  expect(receipt.matched).toBe(true)
  // A 250 ms poll would land near 250 ms; a mutation check lands right after the change.
  expect(receipt.waited_ms).toBeLessThan(200)
})

it('sees a text condition become false again', async () => {
  document.body.innerHTML = '<p id="status">Uploading</p>'
  const pending = waitFor(waitQuery({ condition: 'disappear', text: 'uploading', timeout_ms: 1500 }))
  setTimeout(() => { document.querySelector('#status')!.textContent = 'Done' }, 60)
  const receipt = JSON.parse((await pending).result!)
  expect(receipt.matched).toBe(true)
  expect(receipt.waited_ms).toBeLessThan(200)
})

it('waits for the address to change only when the page navigates', async () => {
  const pending = waitFor(waitQuery({ condition: 'url_change', timeout_ms: 1500 }))
  setTimeout(() => window.history.pushState({}, '', `${location.href}#moved`), 100)
  const receipt = JSON.parse((await pending).result!)
  expect(receipt.matched).toBe(true)
})

it('counts an address change that happened before the wait started', async () => {
  // The panel tells the wait which address it connected to, so a navigation that
  // landed before the model asked is still visible to it.
  const receipt = JSON.parse((await waitFor(waitQuery({ condition: 'url_change' }), 'https://elsewhere.example/')).result!)
  expect(receipt.matched).toBe(true)
})

it('does not call a hidden element "appeared"', async () => {
  document.body.innerHTML = '<div id="toast" style="display:none">Saved</div>'
  const receipt = JSON.parse((await waitFor(waitQuery({ selector: '#toast' }))).result!)
  expect(receipt.matched).toBe(false)
  const gone = JSON.parse((await waitFor(waitQuery({ condition: 'disappear', selector: '#toast' }))).result!)
  expect(gone.matched).toBe(true)
})

function attributeCommand(change: Partial<BrowserCommand['attribute']>): BrowserCommand {
  return {
    type: 'command', id: 'f'.repeat(32), operation: 'attribute',
    change: null, query: null, interaction: null, inspect: null, wait: null, probe: null,
    attribute: {
      name: 'alt', selector: '#chart', value: 'A chart', remove: false, description: 'Describe the chart', ...change,
    },
  } as BrowserCommand
}

it('sets and removes one allowlisted accessibility attribute', () => {
  document.body.innerHTML = '<img id="chart" src="a.png">'
  expect(JSON.parse(applyDOMCommand(attributeCommand({})).result!)).toMatchObject({ applied: true, value: 'A chart' })
  expect(document.querySelector('#chart')!.getAttribute('alt')).toBe('A chart')

  const removed = JSON.parse(applyDOMCommand(attributeCommand({ value: null, remove: true })).result!)
  expect(removed).toMatchObject({ applied: true, value: null })
  expect(document.querySelector('#chart')!.hasAttribute('alt')).toBe(false)
})

it('can repair an excluded or non-HTML element, which is what the audit reports', () => {
  document.body.innerHTML = '<div aria-hidden="true"><button id="hidden-btn">x</button></div>'
    + '<button id="icon"><svg id="shape"><title>Close</title></svg></button>'
  expect(JSON.parse(applyDOMCommand(attributeCommand({
    selector: '#hidden-btn', name: 'aria-hidden', value: 'false',
  })).result!)).toMatchObject({ applied: true, value: 'false' })
  expect(JSON.parse(applyDOMCommand(attributeCommand({
    selector: '#shape', name: 'aria-label', value: 'Close',
  })).result!)).toMatchObject({ applied: true, value: 'Close' })
  expect(document.querySelector('#shape')!.getAttribute('aria-label')).toBe('Close')
})

it('refuses an attribute outside the allowlist even at the content script', () => {
  document.body.innerHTML = '<img id="chart" src="a.png">'
  const forged = {
    ...attributeCommand({}),
    attribute: { name: 'href', selector: '#chart', value: 'javascript:alert(1)', description: 'Rewrite the link' },
  } as unknown as BrowserCommand
  expect(() => applyDOMCommand(forged)).toThrow()
  expect(document.querySelector('#chart')!.hasAttribute('href')).toBe(false)
})

it('audits the accessibility problems a static pass can name', () => {
  document.body.innerHTML = '<img id="noalt" src="a.png"><img id="ok" src="b.png" alt="B">'
    + '<input id="bare"><button id="silent"><svg></svg></button>'
    + '<div aria-hidden="true"><button id="hidden-btn">x</button></div>'
    + '<span tabindex="3">x</span><h1>Title</h1><h3>Skip</h3>'
  const report = JSON.parse(applyDOMCommand({
    type: 'command', id: 'e'.repeat(32), operation: 'audit',
    change: null, query: null, interaction: null, inspect: null, wait: null, probe: null, attribute: null,
  } as BrowserCommand).result!)
  const byId = Object.fromEntries(report.checks.map((check: { id: string }) => [check.id, check]))
  expect(byId.image_without_alt).toMatchObject({ count: 1, examples: ['#noalt'] })
  expect(byId.control_without_name.count).toBeGreaterThanOrEqual(1)
  expect(byId.control_without_text.count).toBeGreaterThanOrEqual(1)
  expect(byId.aria_hidden_focusable.count).toBe(1)
  expect(byId.positive_tabindex.count).toBe(1)
  expect(byId.heading_level_skipped.count).toBe(1)
  expect(byId.missing_lang.count).toBe(1)
  expect(report.notice).toContain('contrast')
})

it('reports a clean, accessible page as clean', () => {
  document.documentElement.lang = 'en'
  try {
    document.body.innerHTML = '<h1>Title</h1><h2>Section</h2>'
      + '<img src="a.png" alt="A chart">'
      + '<label for="name">Name</label><input id="name">'
      + '<button aria-label="Close">✕</button>'
      // A closed menu is aria-hidden *and* unrendered; nothing in it can take focus.
      + '<div aria-hidden="true" style="display:none"><button>Menu item</button></div>'
      // An icon named through the svg's own title is named.
      + '<button><svg><title>Settings</title></svg></button>'
      // An aria-labelledby that resolves names the control.
      + '<span id="field-label">Email</span><input aria-labelledby="field-label">'
    const report = JSON.parse(applyDOMCommand({
      type: 'command', id: 'd'.repeat(32), operation: 'audit',
      change: null, query: null, interaction: null, inspect: null, wait: null, probe: null, attribute: null,
    } as BrowserCommand).result!)
    const findings = report.checks.filter((check: { count: number }) => check.count > 0)
    expect(findings).toEqual([])
  } finally {
    document.documentElement.removeAttribute('lang')
  }
})
