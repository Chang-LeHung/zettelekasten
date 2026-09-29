import { allowedPage, validateCommand, type BrowserCommand, type BrowserResult } from './browser-protocol'
export { allowedPage, validateCommand } from './browser-protocol'
export type { BrowserCommand, BrowserResult } from './browser-protocol'

/** Data-only messages to a bundled content script, pinned to a Chrome document.
 * No debugger permission, eval, Runtime.evaluate, or model-authored source.
 */
export class BrowserExecutor {
  private binding?: { documentId: string; nonce: string; url: string }
  constructor(readonly tabId: number) {}

  async connect(): Promise<void> {
    const tab = await chrome.tabs.get(this.tabId)
    if (!tab.url || !allowedPage(tab.url)) throw new Error('Connect an ordinary HTTP(S) webpage')
    const [injection] = await chrome.scripting.executeScript({
      target: { tabId: this.tabId, frameIds: [0] },
      files: ['content-script.js'],
      world: 'ISOLATED',
    })
    if (!injection?.documentId) throw new Error('Chrome did not return a document ID')
    const nonce = crypto.randomUUID()
    const ready = await chrome.tabs.sendMessage(this.tabId, { channel: 'zett-dom', type: 'connect', nonce }, { documentId: injection.documentId })
    if (ready?.ok !== true || ready.url !== tab.url) throw new Error('Page changed while connecting')
    this.binding = { documentId: injection.documentId, nonce, url: ready.url }
  }

  async disconnect(): Promise<void> {
    const binding = this.binding
    this.binding = undefined
    if (!binding) return
    await chrome.tabs.sendMessage(this.tabId, { channel: 'zett-dom', type: 'disconnect', nonce: binding.nonce }, { documentId: binding.documentId }).catch(() => {})
  }

  async execute(command: BrowserCommand): Promise<BrowserResult> {
    validateCommand(command)
    const binding = this.binding
    if (!binding) throw new Error('Browser is disconnected')
    const tab = await chrome.tabs.get(this.tabId)
    if (tab.url !== binding.url || this.binding !== binding) {
      await this.disconnect()
      throw new Error('Page navigated; reconnect before another DOM action')
    }
    let timer: ReturnType<typeof setTimeout> | undefined
    try {
      const result = await Promise.race([
        chrome.tabs.sendMessage(this.tabId, {
          channel: 'zett-dom', type: 'command', nonce: binding.nonce, url: binding.url,
          expiresAt: Date.now() + 10000, command,
        }, { documentId: binding.documentId }),
        new Promise<never>((_, reject) => { timer = setTimeout(() => reject(new Error('DOM operation timed out; inspect before retrying')), 10000) }),
      ])
      if (result?.ok === false && typeof result.error === 'string') return { ok: false, error: result.error.slice(0, 1000) }
      if (result?.ok !== true || typeof result.result !== 'string' || new TextEncoder().encode(result.result).length > 64000) {
        throw new Error('Invalid DOM operation result')
      }
      JSON.parse(result.result)
      return { ok: true, result: result.result }
    } catch (error) {
      await this.disconnect()
      throw error
    } finally { clearTimeout(timer) }
  }
}
