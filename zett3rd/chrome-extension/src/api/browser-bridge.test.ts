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
  vi.mocked(BrowserExecutor).mockImplementation(() => ({ connect: vi.fn().mockResolvedValue(undefined), execute, disconnect }) as unknown as BrowserExecutor)
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
  consent!.approve()
  await flush()
  expect(execute).toHaveBeenCalledTimes(1)
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
