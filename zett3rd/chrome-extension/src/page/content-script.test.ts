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
  const resize = shadow!.querySelector<HTMLElement>('[aria-label="Resize Zettelekasten panel"]')!
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
  resize.dispatchEvent(pointer('pointerdown', 780, 580))
  resize.dispatchEvent(pointer('pointermove', 900, 640))
  expect(host.style.width).toBe('540px')
  expect(host.style.height).toBe('560px')
  expect(host.style.left).toBe('360px')
  resize.dispatchEvent(pointer('pointerup', 900, 640))
  // A blank pointerdown inside the panel hands the move to the page. Panel
  // coordinates are frame-relative, so the frame's offset must be applied.
  const frame = shadow!.querySelector<HTMLIFrameElement>('iframe')!
  const panelNonce = new URL(frame.src).searchParams.get('panelNonce')!
  vi.spyOn(frame, 'getBoundingClientRect').mockReturnValue({
    left: 361, top: 89, right: 781, bottom: 579, width: 420, height: 490,
  } as DOMRect)
  expect(send({ type: 'panel-drag-start', panelNonce: 'wrong', x: 100, y: 20 })).toBeUndefined()
  expect(send({ type: 'panel-drag-start', panelNonce, x: 100, y: 20 })).toEqual({ ok: true })
  expect(frame.style.pointerEvents).toBe('none')
  document.dispatchEvent(pointer('pointermove', 341, 159))
  expect(host.style.left).toBe('240px')
  expect(host.style.top).toBe('130px')
  document.dispatchEvent(pointer('pointerup', 341, 159))
  expect(frame.style.pointerEvents).toBe('')
  attach.mockRestore()
})
