import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { BrowserExecutor, validateCommand, allowedPage } from './browser-executor'

const url = 'https://example.com/form'
const command = { type: 'command' as const, id: 'a'.repeat(32), operation: 'update' as const, query: null,
  change: { action: 'fill' as const, selector: '#name', value: 'Ada', description: 'Fill field' } }
let sendMessage: ReturnType<typeof vi.fn>
beforeEach(() => {
  sendMessage = vi.fn(async (_tab, message) => message.type === 'connect'
    ? { ok: true, url } : { ok: true, result: '{"applied":true}' })
  vi.stubGlobal('chrome', {
    tabs: { get: vi.fn().mockResolvedValue({ url }), sendMessage },
    scripting: { executeScript: vi.fn().mockResolvedValue([{ documentId: 'doc-1' }]) },
  })
})
afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks() })

it('injects only the bundled content script and pins messages to its document', async () => {
  const executor = new BrowserExecutor(5)
  await executor.connect()
  expect(chrome.scripting.executeScript).toHaveBeenCalledWith({
    target: { tabId: 5, frameIds: [0] }, files: ['content-script.js'], world: 'ISOLATED',
  })
  expect(await executor.execute(command)).toEqual({ ok: true, result: '{"applied":true}' })
  expect(sendMessage).toHaveBeenCalledWith(5, expect.objectContaining({
    type: 'command', command, nonce: expect.any(String), expiresAt: expect.any(Number),
  }), { documentId: 'doc-1' })
  await executor.disconnect()
})

it('rejects navigation before forwarding an edit', async () => {
  const executor = new BrowserExecutor(5)
  await executor.connect()
  vi.mocked(chrome.tabs.get).mockResolvedValue({ url: 'https://example.com/other' } as chrome.tabs.Tab)
  await expect(executor.execute(command)).rejects.toThrow('navigated')
  expect(sendMessage.mock.calls.some(call => call[1].type === 'command')).toBe(false)
})

it('same-URL reload failure never retries against the new document', async () => {
  const executor = new BrowserExecutor(5)
  await executor.connect()
  sendMessage.mockRejectedValue(new Error('No document with ID doc-1'))
  await expect(executor.execute(command)).rejects.toThrow('doc-1')
  expect(sendMessage.mock.calls.filter(call => call[1].type === 'command')).toHaveLength(1)
  expect(chrome.scripting.executeScript).toHaveBeenCalledTimes(1)
})

it('prohibits executable payloads and browser-internal targets', () => {
  for (const page of ['chrome://settings', 'file:///etc/passwd', 'https://chromewebstore.google.com/detail/test']) expect(allowedPage(page)).toBe(false)
  expect(allowedPage(url)).toBe(true)
  for (const action of ['click', 'submit', 'set_html', 'set_attribute', 'execute']) {
    expect(() => validateCommand({ ...command, change: { ...command.change, action } })).toThrow()
  }
  expect(() => validateCommand({ ...command, script: { code: 'alert(1)' } })).toThrow()
})
