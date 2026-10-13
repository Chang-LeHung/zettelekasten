// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

let listener: (message: unknown, sender: unknown, respond: (result: unknown) => void) => void
const sender = { id: 'extension', url: 'chrome-extension://extension/sidepanel.html' }
const nonce = 'a'.repeat(8) + '-aaaa-aaaa-aaaa-' + 'a'.repeat(12)
const background = { id: 'extension', url: 'chrome-extension://extension/background.js' }
const command = {
  type: 'command', id: 'a'.repeat(32), operation: 'update', query: null,
  change: { action: 'set_text', selector: '#title', value: 'New title', description: 'Replace title' },
}

beforeEach(async () => {
  vi.resetModules()
  delete (globalThis as { __zettDOMBridgeInstalled?: boolean }).__zettDOMBridgeInstalled
  vi.stubGlobal('chrome', {
    runtime: {
      id: 'extension', getURL: (path: string) => `chrome-extension://extension/${path}`,
      onMessage: { addListener: vi.fn(fn => { listener = fn }) },
      sendMessage: vi.fn(async () => undefined),
    },
  })
  document.body.innerHTML = '<h1 id="title">Old title</h1>'
  await import('./content-script')
})
afterEach(() => {
  vi.unstubAllGlobals()
  delete (globalThis as { __zettDOMBridgeInstalled?: boolean }).__zettDOMBridgeInstalled
})

function send(payload: object, source = sender): unknown {
  let response: unknown
  listener({ channel: 'zett-dom', nonce, ...payload }, source, result => { response = result })
  return response
}

it('accepts only the extension panel, never webpage or other-extension senders', () => {
  expect(send({ type: 'connect' }, { id: 'extension', url: 'https://example.com' })).toBeUndefined()
  expect(send({ type: 'connect' }, { ...sender, id: 'another' })).toBeUndefined()
  expect(send({ type: 'command', command, url: location.href, expiresAt: Date.now() + 10000 })).toMatchObject({ ok: false })
  expect(document.querySelector('h1')!.textContent).toBe('Old title')
})

it('validates the binding, expiration, duplicate ID and disconnection at the final DOM boundary', () => {
  expect(send({ type: 'connect' })).toMatchObject({ ok: true })
  const packet = { type: 'command', command, url: location.href, expiresAt: Date.now() + 10000 }
  expect(send({ ...packet, nonce: 'b'.repeat(36) })).toMatchObject({ ok: false })
  expect(send({ ...packet, expiresAt: Date.now() - 1 })).toMatchObject({ ok: false })
  expect(document.querySelector('h1')!.textContent).toBe('Old title')
  expect(send(packet)).toMatchObject({ ok: true })
  expect(document.querySelector('h1')!.textContent).toBe('New title')
  expect(send(packet)).toMatchObject({ ok: false, error: expect.stringContaining('Duplicate') })
  send({ type: 'disconnect' })
  expect(send({ ...packet, command: { ...command, id: 'b'.repeat(32) } })).toMatchObject({ ok: false })
})

it('rejects arbitrary source even when a command reaches the content script', () => {
  send({ type: 'connect' })
  expect(send({ type: 'command', command: { ...command, script: 'alert(1)' }, url: location.href, expiresAt: Date.now() + 10000 }))
    .toMatchObject({ ok: false })
  expect(document.querySelector('h1')!.textContent).toBe('Old title')
})

it('mounts an embedded panel only from the toolbar and closes it only from the matching frame', () => {
  expect(send({ type: 'toggle-panel', tabId: 7 }, sender)).toBeUndefined()
  expect(document.querySelector('#zettelekasten-panel-host')).toBeNull()
  expect(send({ type: 'toggle-panel', tabId: 7 }, background)).toEqual({ ok: true, open: true })
  expect(document.querySelector('#zettelekasten-panel-host')).not.toBeNull()
  expect((document.querySelector('#zettelekasten-panel-host') as HTMLElement).shadowRoot).toBeNull()
  expect(send({ type: 'close-panel', panelNonce: 'wrong' })).toBeUndefined()
  expect(document.querySelector('#zettelekasten-panel-host')).not.toBeNull()
  // The toolbar toggle closes the currently mounted panel.
  expect(send({ type: 'ensure-panel', tabId: 7 }, background)).toEqual({ ok: true, open: true })
  expect(send({ type: 'toggle-panel', tabId: 7 }, background)).toEqual({ ok: true, open: false })
  expect(document.querySelector('#zettelekasten-panel-host')).toBeNull()
})

it('moves and resizes the floating panel without covering the whole viewport', () => {
  const original = HTMLElement.prototype.attachShadow
  let shadow: ShadowRoot | undefined
  const attach = vi.spyOn(HTMLElement.prototype, 'attachShadow').mockImplementation(function (this: HTMLElement, init) {
    shadow = original.call(this, { ...init, mode: 'open' })
    return shadow
  })
  Object.defineProperty(HTMLElement.prototype, 'setPointerCapture', {
    configurable: true, value: vi.fn(),
  })
  expect(send({ type: 'toggle-panel', tabId: 7 }, background)).toMatchObject({ open: true })
  const host = document.querySelector<HTMLElement>('#zettelekasten-panel-host')!
  // jsdom cannot parse CSS min() in the initial inline rule; the browser
  // geometry is covered separately in Chrome. Exercise pointer transitions.
  expect(host.style.right).toBe('16px')
  const handle = shadow!.querySelector<HTMLElement>('[aria-label="Move Zettelekasten panel"]')!
  const corner = (label: string) => shadow!.querySelector<HTMLElement>(`[aria-label="Resize Zettelekasten panel from the ${label}"]`)!
  // jsdom does not implement layout or pointer capture; supply deterministic
  // geometry while exercising the exact production pointer handlers.
  vi.spyOn(host, 'getBoundingClientRect').mockReturnValue({
    left: 360, top: 80, right: 780, bottom: 580, width: 420, height: 500,
  } as DOMRect)
  function pointer(type: string, x: number, y: number): Event {
    return Object.assign(new Event(type, { bubbles: true, cancelable: true }), {
      button: 0, pointerId: 1, clientX: x, clientY: y,
    })
  }
  handle.dispatchEvent(pointer('pointerdown', 700, 90))
  handle.dispatchEvent(pointer('pointermove', 580, 140))
  expect(host.style.left).toBe('240px')
  expect(host.style.top).toBe('130px')
  handle.dispatchEvent(pointer('pointerup', 580, 140))
  // All four corners resize through invisible zones: no handle chrome is left
  // over the page, and only the cursor advertises the corner.
  expect(shadow!.querySelectorAll('[aria-label^="Resize Zettelekasten panel"]')).toHaveLength(4)
  expect(corner('bottom right').style.background).toBe('')
  corner('bottom right').dispatchEvent(pointer('pointerdown', 780, 580))
  corner('bottom right').dispatchEvent(pointer('pointermove', 900, 640))
  expect(host.style.width).toBe('540px')
  expect(host.style.height).toBe('560px')
  expect(host.style.left).toBe('360px')
  expect(host.style.top).toBe('80px')
  corner('bottom right').dispatchEvent(pointer('pointerup', 900, 640))
  // A top-left drag pins the opposite corner, and dragging past the minimum
  // stops at the panel's CSS size instead of collapsing it.
  corner('top left').dispatchEvent(pointer('pointerdown', 360, 80))
  corner('top left').dispatchEvent(pointer('pointermove', 300, 40))
  expect(host.style.left).toBe('300px')
  expect(host.style.top).toBe('40px')
  expect(host.style.width).toBe('480px')
  expect(host.style.height).toBe('540px')
  corner('top left').dispatchEvent(pointer('pointermove', 1000, 700))
  expect(host.style.left).toBe('480px')
  expect(host.style.top).toBe('220px')
  expect(host.style.width).toBe('300px')
  expect(host.style.height).toBe('360px')
  corner('top left').dispatchEvent(pointer('pointerup', 1000, 700))
  attach.mockRestore()
})

it('moves the panel when its own header reports a drag, and believes nobody else', () => {
  document.querySelectorAll('#zettelekasten-panel-host').forEach(old => old.remove())
  const frameWindow = {} as Window
  Object.defineProperty(HTMLIFrameElement.prototype, 'contentWindow', { configurable: true, get: () => frameWindow })
  Object.defineProperty(window, 'innerWidth', { configurable: true, value: 1200 })
  Object.defineProperty(window, 'innerHeight', { configurable: true, value: 900 })
  expect(send({ type: 'toggle-panel', tabId: 7 }, background)).toEqual({ ok: true, open: true })
  const host = document.querySelector<HTMLElement>('#zettelekasten-panel-host')!
  host.getBoundingClientRect = () => ({ left: 300, top: 40, width: 500, height: 600, right: 800, bottom: 640, x: 300, y: 40, toJSON() {} })
  const post = (data: object, source: unknown = frameWindow, origin = 'chrome-extension://extension') => {
    const event = new MessageEvent('message', { data, origin })
    Object.defineProperty(event, 'source', { value: source })
    window.dispatchEvent(event)
  }

  post({ zett: 'panel-drag', type: 'start' })
  post({ zett: 'panel-drag', type: 'move', dx: -100, dy: 25 })
  expect([host.style.left, host.style.top]).toEqual(['200px', '65px'])
  // The panel never leaves the viewport, however far the pointer goes.
  post({ zett: 'panel-drag', type: 'move', dx: 5000, dy: -5000 })
  expect([host.style.left, host.style.top]).toEqual(['700px', '0px'])

  // A page script posting to itself, another origin, or junk deltas move nothing.
  post({ zett: 'panel-drag', type: 'move', dx: 1, dy: 1 }, window)
  post({ zett: 'panel-drag', type: 'move', dx: 1, dy: 1 }, frameWindow, 'https://evil.example')
  post({ zett: 'panel-drag', type: 'move', dx: 'NaN', dy: null })
  expect([host.style.left, host.style.top]).toEqual(['700px', '0px'])

  post({ zett: 'panel-drag', type: 'end' })
  post({ zett: 'panel-drag', type: 'move', dx: -50, dy: 0 })
  expect(host.style.left).toBe('700px')
})
