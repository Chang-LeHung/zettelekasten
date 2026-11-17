import {
  COMMAND_EXPIRY_ALLOWANCE_MS, COMMAND_TIMEOUT_MS, allowedPage, encodeResult, sameDocumentUrl,
  validateCommand, type BrowserCommand, type BrowserResult,
} from './browser-protocol'
import { installProbe, readProbe } from './probe'
export { allowedPage, sameDocumentUrl, validateCommand } from './browser-protocol'
export type { BrowserCommand, BrowserResult } from './browser-protocol'

/** What a pending action would touch, in the page's own words. */
export interface BrowserTarget { matched: number; tag?: string; label?: string; href?: string }

/** A capture must decode to less than the server's image budget. */
const MAX_CAPTURE_BYTES = 4_000_000
const CAPTURE_PREFIX = 'data:image/jpeg;base64,'
const CAPTURE_QUALITY = 60

/** Data-only messages to a bundled content script, pinned to a Chrome document.
 * No debugger permission, eval, Runtime.evaluate, or model-authored source.
 */
export class BrowserExecutor {
  private binding?: { documentId: string; nonce: string; url: string }
  /** Per-connection key for the page-world probe, so a page cannot pre-seed it. */
  private probeKey?: string
  /** Whether this connection's install actually armed the document. */
  private probeArmed = false
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
    await this.installProbe()
    const nonce = crypto.randomUUID()
    const ready = await chrome.tabs.sendMessage(this.tabId, { channel: 'zett-dom', type: 'connect', nonce }, { documentId: injection.documentId })
    if (ready?.ok !== true || !sameDocumentUrl(String(ready.url), tab.url)) throw new Error('Page changed while connecting')
    this.binding = { documentId: injection.documentId, nonce, url: ready.url }
  }

  /**
   * Install the page-world probe under a key this connection chose.
   *
   * Best effort: a page that refuses the injection still gets every DOM tool, and
   * the diagnostics then report that no probe was found.
   */
  private async installProbe(): Promise<void> {
    const key = crypto.randomUUID()
    try {
      const [injected] = await chrome.scripting.executeScript({
        target: { tabId: this.tabId, frameIds: [0] }, world: 'MAIN', func: installProbe, args: [key],
      })
      this.probeKey = key
      this.probeArmed = injected?.result === true
    } catch {
      this.probeKey = undefined
      this.probeArmed = false
    }
  }

  /** Read the page's own console, network, or timing data from its world. */
  async diagnostics(kind: 'console' | 'network' | 'metrics', limit: number): Promise<BrowserResult> {
    const binding = this.binding
    if (!binding) throw new Error('Browser is disconnected')
    // `readProbe` reads page-owned objects, so it is raced like any other command:
    // a page can hang it with a getter and nothing else would bound the wait.
    let timer: ReturnType<typeof setTimeout> | undefined
    try {
      const [injected] = await Promise.race([
        chrome.scripting.executeScript({
          target: { tabId: this.tabId, frameIds: [0] }, world: 'MAIN',
          func: readProbe, args: [this.probeKey ?? '', kind, limit, this.probeArmed],
        }),
        new Promise<never>((_, reject) => {
          timer = setTimeout(
            () => reject(new Error('The page did not return diagnostics; it may be blocking the probe')),
            COMMAND_TIMEOUT_MS,
          )
        }),
      ])
      const data = injected?.result
      if (!data || typeof data !== 'object') throw new Error('The page returned no diagnostics')
      return encodeResult(data)
    } finally {
      clearTimeout(timer)
    }
  }

  async disconnect(): Promise<void> {
    const binding = this.binding
    this.binding = undefined
    if (!binding) return
    await chrome.tabs.sendMessage(this.tabId, { channel: 'zett-dom', type: 'disconnect', nonce: binding.nonce }, { documentId: binding.documentId }).catch(() => {})
  }

  /** Name the element a pending action targets, for the consent card. Best effort: never throws. */
  async describe(selector: string): Promise<BrowserTarget | null> {
    const binding = this.binding
    if (!binding) return null
    try {
      const reply = await Promise.race([
        chrome.tabs.sendMessage(this.tabId, {
          channel: 'zett-dom', type: 'describe', nonce: binding.nonce, url: binding.url, selector,
        }, { documentId: binding.documentId }),
        new Promise<null>(resolve => setTimeout(() => resolve(null), 1500)),
      ])
      const target = reply?.ok === true ? reply.target : null
      if (!target || typeof target.matched !== 'number') return null
      return {
        matched: target.matched,
        tag: typeof target.tag === 'string' ? target.tag.slice(0, 40) : undefined,
        label: typeof target.label === 'string' ? target.label.slice(0, 80) : undefined,
        href: typeof target.href === 'string' ? target.href.slice(0, 300) : undefined,
      }
    } catch { return null }
  }

  /** Hide or restore the panel's host element in the page, for one capture. */
  private async setPanelHidden(binding: { documentId: string; nonce: string; url: string }, hidden: boolean): Promise<void> {
    await chrome.tabs.sendMessage(this.tabId, {
      channel: 'zett-dom', type: hidden ? 'hide-panel' : 'show-panel', nonce: binding.nonce,
    }, { documentId: binding.documentId })
  }

  /** Capture the visible viewport as a JPEG data URL, without the panel in the shot. */
  private async capture(
    tab: chrome.tabs.Tab,
    binding: { documentId: string; nonce: string; url: string },
  ): Promise<BrowserResult> {
    // `captureVisibleTab` photographs whatever the window shows, not a tab id, so
    // the connection must still own the visible tab or the image is another page.
    const [active] = await chrome.tabs.query({ active: true, windowId: tab.windowId })
    if (!active || active.id !== this.tabId) {
      throw new Error('The connected tab is not the visible one; switch back to it and capture again')
    }
    let hidden = false
    try {
      await this.setPanelHidden(binding, true)
      hidden = true
    } catch {
      // The panel may not be mounted on this page; the capture still works.
    }
    try {
      const image = await chrome.tabs.captureVisibleTab(tab.windowId, { format: 'jpeg', quality: CAPTURE_QUALITY })
      if (typeof image !== 'string' || !image.startsWith(CAPTURE_PREFIX)) {
        throw new Error('Chrome returned no JPEG image for this tab')
      }
      // Bound the decoded bytes the server will accept, not the base64 length,
      // so a capture is never sent only to be refused at the far side.
      const decoded = Math.floor(((image.length - CAPTURE_PREFIX.length) * 3) / 4)
      if (decoded > MAX_CAPTURE_BYTES) {
        throw new Error('The capture is larger than 4 MB; make the window smaller and capture again')
      }
      return { ok: true, image }
    } finally {
      if (hidden) {
        await this.setPanelHidden(binding, false).catch(async () => {
          // A hidden panel must never be left behind: try once more before giving up.
          await this.setPanelHidden(binding, false).catch(() => {})
        })
      }
    }
  }

  async execute(command: BrowserCommand): Promise<BrowserResult> {
    validateCommand(command)
    const binding = this.binding
    if (!binding) throw new Error('Browser is disconnected')
    const tab = await chrome.tabs.get(this.tabId)
    // A wait on the address is the one read whose purpose is to observe the change,
    // so it survives the URL moving while it watches.
    const observingAddress = command.operation === 'wait' && command.wait?.condition === 'url_change'
    if (this.binding !== binding || (!observingAddress && (!tab.url || !sameDocumentUrl(tab.url, binding.url)))) {
      await this.disconnect()
      throw new Error('The page navigated, so the page tools were closed. The panel reconnects on its own; read the new page before acting.')
    }
    if (command.operation === 'screenshot') return await this.capture(tab, binding)
    if (command.operation === 'probe') return await this.diagnostics(command.probe!.kind, command.probe!.limit)
    const budget = command.operation === 'wait'
      ? Math.min(command.wait!.timeout_ms + 2000, COMMAND_EXPIRY_ALLOWANCE_MS - 500)
      : COMMAND_TIMEOUT_MS
    let timer: ReturnType<typeof setTimeout> | undefined
    try {
      const result = await Promise.race([
        chrome.tabs.sendMessage(this.tabId, {
          channel: 'zett-dom', type: 'command', nonce: binding.nonce, url: binding.url,
          expiresAt: Date.now() + budget, command,
        }, { documentId: binding.documentId }),
        new Promise<never>((_, reject) => { timer = setTimeout(() => reject(new Error('DOM operation timed out; inspect before retrying')), budget) }),
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
