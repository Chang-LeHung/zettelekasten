import { beforeEach, expect, it, vi } from 'vitest'
import { pageKey } from './chat/page-sessions'

type Click = (tab: chrome.tabs.Tab) => Promise<void>
type Updated = (tabId: number, change: chrome.tabs.TabChangeInfo, tab: chrome.tabs.Tab) => void
type Removed = (tabId: number) => void
type Message = (message: { type: string; tabId: number }, sender: chrome.runtime.MessageSender) => void

let click: Click
let updated: Updated
let removed: Removed
let message: Message
let entries: Record<string, unknown>
let pageEntries: Record<string, unknown>
let send: ReturnType<typeof vi.fn>

async function flush() { for (let i = 0; i < 15; i++) await Promise.resolve() }

beforeEach(async () => {
  vi.resetModules()
  entries = {}
  pageEntries = {}
  send = vi.fn(async (_tabId, packet) => ({
    ok: true, open: packet.type === 'ensure-panel' || entries[`embeddedPanelTab:${_tabId}`] !== true,
  }))
  vi.stubGlobal('chrome', {
    action: { onClicked: { addListener: (handler: Click) => { click = handler } } },
    tabs: {
      sendMessage: send,
      onUpdated: { addListener: (handler: Updated) => { updated = handler } },
      onRemoved: { addListener: (handler: Removed) => { removed = handler } },
    },
    runtime: {
      id: 'extension',
      onMessage: { addListener: (handler: Message) => { message = handler } },
    },
    scripting: { executeScript: vi.fn(async () => [{ frameId: 0 }]) },
    storage: { session: {
      get: vi.fn(async (key: string) => ({ [key]: entries[key] })),
      set: vi.fn(async (value: Record<string, unknown>) => { Object.assign(entries, value) }),
      remove: vi.fn(async (key: string) => { delete entries[key] }),
    }, local: {
      get: vi.fn(async () => ({ ...pageEntries })),
      remove: vi.fn(async (keys: string[]) => { keys.forEach(key => { delete pageEntries[key] }) }),
    } },
  })
  await import('./background')
})

it('toggles only the clicked webpage and reopens on full navigation', async () => {
  await click({ id: 7, url: 'https://example.com/one' } as chrome.tabs.Tab)
  expect(entries['embeddedPanelTab:7']).toBe(true)
  updated(7, { status: 'complete' }, { url: 'https://example.com/two' } as chrome.tabs.Tab)
  await flush()
  expect(send).toHaveBeenLastCalledWith(7, {
    channel: 'zett-dom', type: 'ensure-panel', tabId: 7,
  }, { frameId: 0 })
  expect(entries['embeddedPanelTab:7']).toBe(true)

  updated(8, { status: 'complete' }, { url: 'https://example.com/other' } as chrome.tabs.Tab)
  await flush()
  expect(send.mock.calls.some(([id]) => id === 8)).toBe(false)
  await click({ id: 7, url: 'https://example.com/two' } as chrome.tabs.Tab)
  expect(entries['embeddedPanelTab:7']).toBeUndefined()
  updated(7, { status: 'complete' }, { url: 'https://example.com/three' } as chrome.tabs.Tab)
  await flush()
  expect(send.mock.calls.at(-1)?.[1].type).toBe('toggle-panel')
})

it('removes the flag on explicit close or tab removal', async () => {
  await click({ id: 7, url: 'https://example.com' } as chrome.tabs.Tab)
  message({ type: 'embedded-panel-closed', tabId: 7 }, { id: 'another', tab: { id: 7 } } as chrome.runtime.MessageSender)
  await flush()
  expect(entries['embeddedPanelTab:7']).toBe(true)
  message({ type: 'embedded-panel-closed', tabId: 7 }, { id: 'extension', tab: { id: 7 } } as chrome.runtime.MessageSender)
  await flush()
  expect(entries['embeddedPanelTab:7']).toBeUndefined()
  await click({ id: 7, url: 'https://example.com' } as chrome.tabs.Tab)
  pageEntries[pageKey('http://localhost:6280', 7, 'https://example.com')!] = 'old-session'
  pageEntries[pageKey('http://localhost:6280', 8, 'https://example.com')!] = 'other-session'
  removed(7)
  await flush()
  expect(entries['embeddedPanelTab:7']).toBeUndefined()
  expect(Object.keys(pageEntries)).toHaveLength(1)
  expect(Object.values(pageEntries)).toEqual(['other-session'])
})
