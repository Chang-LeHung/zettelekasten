import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { BrowserBridgeClient, type BrowserConsent } from './browser-bridge'
import { BrowserExecutor } from '../page/browser-executor'

vi.mock('../page/browser-executor', async importOriginal => {
  const original = await importOriginal<typeof import('../page/browser-executor')>()
  return { ...original, BrowserExecutor: vi.fn() }
})

class Socket {
  static OPEN = 1
  static instances: Socket[] = []
  readyState = 1
  onmessage?: ((event: { data: string }) => void) | null
  onerror?: (() => void) | null
  onclose?: (() => void) | null
  sent: unknown[] = []
  constructor() { Socket.instances.push(this) }
  send(value: string) { this.sent.push(JSON.parse(value)) }
  close() { this.readyState = 3; this.onclose?.() }
  emit(value: unknown) { this.onmessage?.({ data: JSON.stringify(value) }) }
}
const execute = vi.fn()
const disconnect = vi.fn()
const highlight = vi.fn()
let bridge: BrowserBridgeClient
let consent: BrowserConsent | null
let socket: Socket
async function flush() { for (let i = 0; i < 12; i++) await Promise.resolve() }
const command = { type: 'command', id: 'a'.repeat(32), operation: 'update', change: { action: 'fill', selector: '#name', value: 'Ada', description: 'Fill a field' }, query: null }

beforeEach(async () => {
  Socket.instances = []
  consent = null
  vi.stubGlobal('WebSocket', Socket)
  execute.mockReset().mockResolvedValue({ ok: true, result: '1' })
  disconnect.mockReset().mockResolvedValue(undefined)
  highlight.mockReset().mockResolvedValue(undefined)
  vi.mocked(BrowserExecutor).mockImplementation(() => (
    { connect: vi.fn().mockResolvedValue(undefined), execute, disconnect, highlight } as unknown as BrowserExecutor
  ))
  bridge = new BrowserBridgeClient(value => { consent = value }, vi.fn())
  const connected = bridge.connect('ws://localhost/browser', 5)
  await flush()
  socket = Socket.instances[0]
  socket.emit({ type: 'ready', token: 't'.repeat(43) })
  await connected
})
afterEach(async () => { await bridge.disconnect(); vi.unstubAllGlobals() })

it('never changes the DOM before approval and never replays duplicate commands', async () => {
  socket.emit(command)
  await flush()
  expect(consent?.command.change?.value).toBe('Ada')
  expect(execute).not.toHaveBeenCalled()
  // The card names the element in words; the page outlines the same element.
  expect(highlight).toHaveBeenCalledWith('#name')
  consent!.approve()
  await flush()
  expect(execute).toHaveBeenCalledTimes(1)
  expect(highlight).toHaveBeenLastCalledWith(null)
  expect(socket.sent).toContainEqual({ type: 'result', id: command.id, ok: true, result: '1' })
  socket.emit(command)
  await flush()
  expect(execute).toHaveBeenCalledTimes(1)
})

it('denial returns an error without touching the page', async () => {
  socket.emit(command)
  consent!.reject()
  await flush()
  expect(execute).not.toHaveBeenCalled()
  expect(socket.sent).toContainEqual(expect.objectContaining({ id: command.id, ok: false }))
})

it('applies page edits without consent once the session always allows them', async () => {
  bridge.autoApprove = true
  socket.emit(command)
  await flush()
  expect(consent).toBeNull()
  expect(execute).toHaveBeenCalledTimes(1)
  expect(socket.sent).toContainEqual({ type: 'result', id: command.id, ok: true, result: '1' })
})

it('runs a read-only inspection without asking for consent', async () => {
  const inspect = {
    type: 'command', id: 'b'.repeat(32), operation: 'inspect',
    change: null, query: null, interaction: null, inspect: { selector: '#buy' },
  }
  socket.emit(inspect)
  await flush()
  expect(consent).toBeNull()
  expect(execute).toHaveBeenCalledTimes(1)
  expect(execute).toHaveBeenCalledWith(expect.objectContaining({ operation: 'inspect', inspect: { selector: '#buy' } }))
  expect(socket.sent).toContainEqual({ type: 'result', id: inspect.id, ok: true, result: '1' })
})

it('forwards a captured image without asking for consent', async () => {
  const image = 'data:image/jpeg;base64,AAAA'
  execute.mockResolvedValue({ ok: true, image })
  const shot = {
    type: 'command', id: 'e'.repeat(32), operation: 'screenshot',
    change: null, query: null, interaction: null, inspect: null, wait: null,
  }
  socket.emit(shot)
  await flush()
  expect(consent).toBeNull()
  expect(socket.sent).toContainEqual({ type: 'result', id: shot.id, ok: true, image })
})

it('a disconnect cancels consent and prevents stale approval execution', async () => {
  socket.emit(command)
  const old = consent!
  await bridge.disconnect()
  old.approve()
  await flush()
  expect(execute).not.toHaveBeenCalled()
  expect(bridge.token).toBeUndefined()
  expect(disconnect).toHaveBeenCalled()
})

it('cancellation clears a pending approval', async () => {
  socket.emit(command)
  socket.emit({ type: 'cancel', id: command.id })
  await flush()
  expect(consent).toBeNull()
  expect(execute).not.toHaveBeenCalled()
})

it('asks before an attribute change, and never for an accessibility audit', async () => {
  const attribute = {
    type: 'command', id: 'd'.repeat(32), operation: 'attribute',
    change: null, query: null, interaction: null, inspect: null, wait: null, probe: null,
    attribute: { name: 'alt', selector: '#chart', value: 'A chart', remove: false, description: 'Describe the chart' },
  }
  socket.emit(attribute)
  await flush()
  expect(consent?.command.attribute?.name).toBe('alt')
  expect(execute).not.toHaveBeenCalled()
  consent!.approve()
  await flush()
  expect(execute).toHaveBeenCalledWith(expect.objectContaining({ operation: 'attribute' }))

  const audit = {
    type: 'command', id: 'e'.repeat(32), operation: 'audit',
    change: null, query: null, interaction: null, inspect: null, wait: null, probe: null, attribute: null,
  }
  execute.mockClear()
  socket.emit(audit)
  await flush()
  expect(consent).toBeNull()
  expect(execute).toHaveBeenCalledTimes(1)
})
