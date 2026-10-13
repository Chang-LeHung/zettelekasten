import { applyDOMCommand, describeSelector } from './dom-operations'
import { allowedPage, sameDocumentUrl, validateCommand } from './browser-protocol'

/** Installed on demand only in the connected top document. No page-world
 * messaging, eval, script tags, HTML insertion, or arbitrary attribute edits.
 * Re-injection reuses the listener. The frame remains an extension origin, not
 * page JavaScript, and the nonce plus documentId pins the DOM-operation peer.
 */
const scope = globalThis as typeof globalThis & { __zettDOMBridgeInstalled?: boolean }
if (!scope.__zettDOMBridgeInstalled) {
  scope.__zettDOMBridgeInstalled = true
  let binding: { nonce: string; url: string; seen: Set<string> } | undefined
  let panel: HTMLElement | undefined
  let panelNonce: string | undefined
  let panelTabId: number | undefined
  let lastUrl = location.href
  let pageTimer: ReturnType<typeof setInterval> | undefined
  const MIN_PANEL_WIDTH = 300
  const MIN_PANEL_HEIGHT = 360
  const CORNER_SIZE = 16
  /** Wide enough for the composer's `•••` menu and the context pie beside it. */
  const DEFAULT_PANEL_WIDTH = 520

  /** Removes the listener that carries drags started from inside the panel's header. */
  let detachFrameMessages: (() => void) | undefined

  function removePanel(): void {
    detachFrameMessages?.()
    detachFrameMessages = undefined
    panel?.remove()
    panel = undefined
    panelNonce = undefined
    panelTabId = undefined
    binding = undefined
    clearInterval(pageTimer)
    pageTimer = undefined
  }

  function mountPanel(tabId: number): void {
    if (panel) { removePanel(); return }
    const host = document.createElement('div')
    host.id = 'zettelekasten-panel-host'
    // Shadow DOM isolates the panel's chrome from the page's CSS/selectors.
    host.style.cssText = `position:fixed!important;top:3vh;right:16px;width:min(${DEFAULT_PANEL_WIDTH}px,calc(100vw - 32px));height:min(90vh,920px);min-width:min(${MIN_PANEL_WIDTH}px,100vw);min-height:min(${MIN_PANEL_HEIGHT}px,100dvh);z-index:2147483647!important;`
    const shadow = host.attachShadow({ mode: 'closed' })
    const shell = document.createElement('div')
    shell.style.cssText = 'position:relative;display:flex;flex-direction:column;width:100%;height:100%;overflow:hidden;border:1px solid rgba(32,46,37,.12);border-radius:20px;background:#fff;box-shadow:0 22px 70px rgba(22,31,26,.16),0 3px 16px rgba(22,31,26,.06);'
    const handle = document.createElement('div')
    handle.setAttribute('role', 'button')
    handle.setAttribute('aria-label', 'Move Zettelekasten panel')
    handle.title = 'Drag to move'
    handle.style.cssText = 'height:9px;flex:0 0 9px;cursor:grab;background:#fff;touch-action:none;'
    const frame = document.createElement('iframe')
    frame.title = 'Zettelekasten'
    frame.style.cssText = 'display:block;flex:1;min-height:0;border:0;width:100%;background:white;'
    // Every corner resizes; the zones stay invisible so no handle chrome sits
    // over the page the panel is describing, and only the cursor reveals them.
    const corners = (['nw', 'ne', 'sw', 'se'] as const).map(corner => {
      const zone = document.createElement('div')
      const westwards = corner === 'nw' || corner === 'sw'
      const northwards = corner === 'nw' || corner === 'ne'
      zone.setAttribute('role', 'button')
      zone.setAttribute('aria-label', `Resize Zettelekasten panel from the ${corner === 'nw' ? 'top left' : corner === 'ne' ? 'top right' : corner === 'sw' ? 'bottom left' : 'bottom right'}`)
      zone.title = 'Drag to resize'
      zone.style.cssText = `position:absolute;${westwards ? 'left' : 'right'}:0;${northwards ? 'top' : 'bottom'}:0;width:${CORNER_SIZE}px;height:${CORNER_SIZE}px;cursor:${westwards === northwards ? 'nwse' : 'nesw'}-resize;touch-action:none;z-index:2;`
      zone.addEventListener('pointerdown', event => drag(event, corner))
      return zone
    })
    const url = new URL(chrome.runtime.getURL('sidepanel.html'))
    url.searchParams.set('tabId', String(tabId))
    panelNonce = crypto.randomUUID()
    url.searchParams.set('panelNonce', panelNonce)
    frame.src = url.href
    shell.append(handle, frame, ...corners)
    shadow.append(shell)
    /** Move the panel by (dx, dy) from `start`, keeping it fully inside the viewport. */
    function placeFrom(start: DOMRect, dx: number, dy: number): void {
      host.style.left = `${Math.max(0, Math.min(innerWidth - start.width, start.left + dx))}px`
      host.style.top = `${Math.max(0, Math.min(innerHeight - start.height, start.top + dy))}px`
      host.style.right = 'auto'
    }
    // The panel's own header is the large drag target. It lives in the extension
    // iframe, whose pointer events never reach this page, so the frame reports
    // its pointer as screen-coordinate deltas (stable while the panel moves) and
    // this side moves the host. Only that frame, from the extension's origin,
    // is believed; `event.source` cannot be forged by the page, and the message
    // carries nothing secret because the page can read it.
    const extensionOrigin = chrome.runtime.getURL('').replace(/\/$/, '')
    let headerDrag: DOMRect | undefined
    const onFrameMessage = (event: MessageEvent): void => {
      const data = event.data as { zett?: unknown; type?: unknown; dx?: unknown; dy?: unknown } | null
      if (event.source !== frame.contentWindow || event.origin !== extensionOrigin) return
      if (!data || data.zett !== 'panel-drag') return
      if (data.type === 'start') headerDrag = host.getBoundingClientRect()
      else if (data.type === 'end') headerDrag = undefined
      else if (data.type === 'move' && headerDrag && Number.isFinite(data.dx) && Number.isFinite(data.dy)) {
        placeFrom(headerDrag, Number(data.dx), Number(data.dy))
      }
    }
    addEventListener('message', onFrameMessage)
    detachFrameMessages = () => removeEventListener('message', onFrameMessage)
    function drag(event: PointerEvent, kind: 'move' | 'nw' | 'ne' | 'sw' | 'se'): void {
      if (event.button !== 0) return
      event.preventDefault()
      const start = host.getBoundingClientRect()
      const x = event.clientX
      const y = event.clientY
      const target = event.currentTarget as HTMLElement
      target.setPointerCapture(event.pointerId)
      // A cross-origin iframe consumes pointer events once the cursor crosses
      // its surface. Cover it only for the duration of this drag so the
      // captured pointer keeps reaching our resize/move handle.
      frame.style.pointerEvents = 'none'
      const move = (next: PointerEvent) => {
        const dx = next.clientX - x
        const dy = next.clientY - y
        if (kind === 'move') {
          placeFrom(start, dx, dy)
          return
        }
        // Keep the opposite corner pinned while clamping to the viewport and
        // to the panel's CSS minimum size.
        const right = start.left + start.width
        const bottom = start.top + start.height
        const westwards = kind === 'nw' || kind === 'sw'
        const northwards = kind === 'nw' || kind === 'ne'
        const width = westwards
          ? Math.max(Math.min(MIN_PANEL_WIDTH, innerWidth), Math.min(right, start.width - dx))
          : Math.max(Math.min(MIN_PANEL_WIDTH, innerWidth), Math.min(innerWidth - start.left, start.width + dx))
        const height = northwards
          ? Math.max(Math.min(MIN_PANEL_HEIGHT, innerHeight), Math.min(bottom, start.height - dy))
          : Math.max(Math.min(MIN_PANEL_HEIGHT, innerHeight), Math.min(innerHeight - start.top, start.height + dy))
        host.style.left = `${westwards ? right - width : start.left}px`
        host.style.top = `${northwards ? bottom - height : start.top}px`
        host.style.right = 'auto'
        host.style.width = `${width}px`
        host.style.height = `${height}px`
      }
      const done = () => {
        frame.style.pointerEvents = ''
        target.removeEventListener('pointermove', move)
        target.removeEventListener('pointerup', done)
        target.removeEventListener('pointercancel', done)
      }
      target.addEventListener('pointermove', move)
      target.addEventListener('pointerup', done)
      target.addEventListener('pointercancel', done)
    }
    handle.addEventListener('pointerdown', event => drag(event, 'move'))

    ;(document.documentElement ?? document.body).append(host)
    panel = host
    panelTabId = tabId
    lastUrl = location.href
    pageTimer = setInterval(() => {
      // pushState may replace the page without unloading this content script.
      const previous = new URL(lastUrl)
      const current = new URL(location.href)
      previous.hash = ''
      current.hash = ''
      if (previous.href === current.href) return
      removePanel()
      mountPanel(tabId)
    }, 500)
  }

  chrome.runtime.onMessage.addListener((message, sender, respond) => {
    if (sender.id !== chrome.runtime.id || message?.channel !== 'zett-dom') return
    if ((message.type === 'toggle-panel' || message.type === 'ensure-panel')
      && sender.url === chrome.runtime.getURL('background.js')
      && Number.isSafeInteger(message.tabId) && message.tabId >= 0) {
      if (message.type === 'toggle-panel' || !panel) mountPanel(message.tabId)
      respond({ ok: true, open: Boolean(panel) })
      return
    }
    if (message.type === 'toggle-panel' || message.type === 'ensure-panel') return
    if (message.type === 'panel-hello' && panel && message.panelNonce === panelNonce
      && sender.url?.startsWith(chrome.runtime.getURL('sidepanel.html'))) {
      respond({ ok: true, url: location.href })
      return
    }
    if (message.type === 'close-panel' && panel && message.panelNonce === panelNonce
      && sender.url?.startsWith(chrome.runtime.getURL('sidepanel.html'))) {
      const tabId = panelTabId
      removePanel()
      if (tabId !== undefined) void chrome.runtime.sendMessage({ type: 'embedded-panel-closed', tabId })
      respond({ ok: true })
      return
    }
    if (message.type === 'close-panel' || message.type === 'panel-hello') return
    if (!sender.url?.startsWith(chrome.runtime.getURL('sidepanel.html'))) return
    if (typeof message.nonce !== 'string' || !/^[a-f0-9-]{36}$/.test(message.nonce)) return
    try {
      if (message.type === 'connect') {
        if (!allowedPage(location.href)) throw new Error('Page cannot be connected')
        binding = { nonce: message.nonce, url: location.href, seen: new Set() }
        respond({ ok: true, url: location.href })
        return
      }
      if (!binding || message.nonce !== binding.nonce) throw new Error('Page connection expired')
      if (message.type === 'disconnect') {
        binding = undefined
        respond({ ok: true })
        return
      }
      if (!sameDocumentUrl(location.href, binding.url) || !sameDocumentUrl(String(message.url ?? binding.url), binding.url)) {
        throw new Error('The page navigated to a different address. Read the new page with get_browser_page after the panel reconnects.')
      }
      if (message.type === 'describe') {
        // Read-only: names the element a pending action targets for the consent card.
        respond({ ok: true, target: describeSelector(String(message.selector ?? '').slice(0, 500)) })
        return
      }
      if (message.type !== 'command') throw new Error('Unknown page message')
      if (!Number.isFinite(message.expiresAt) || Date.now() > message.expiresAt || message.expiresAt > Date.now() + 11000) {
        throw new Error('DOM command expired')
      }
      const command = validateCommand(message.command)
      if (binding.seen.has(command.id) || binding.seen.size >= 1000) throw new Error('Duplicate command or connection limit reached')
      binding.seen.add(command.id)
      respond(applyDOMCommand(command))
    } catch (error) {
      respond({ ok: false, error: (error as Error).message.slice(0, 1000) })
    }
  })
}
