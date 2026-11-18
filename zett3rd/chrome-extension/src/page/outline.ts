/**
 * Outline one page element, so the user can see what the model is talking about.
 *
 * The panel names a target in words; this draws the same target on the page for
 * a moment. It is page chrome, not content: it never intercepts a click
 * (`pointer-events: none`), sits below the panel's own stacking order, and is
 * removed when its time is up, when the card closes, or when the connection ends.
 *
 * There is exactly one outline per document. It follows the element through
 * scrolling and layout with a slow refresh plus listeners rather than a
 * per-frame `getBoundingClientRect`, because a read on every animation frame
 * would flush layout on someone else's page sixty times a second.
 */

const OUTLINE_HOST_ID = 'zettelekasten-outline-host'
/** Above the page, below the panel host (2147483647). */
const OUTLINE_Z_INDEX = '2147483646'
/** A CSS animation can outrun this; a two-pixel lag is invisible, a 60 Hz flush is not. */
const REFRESH_MS = 250

let host: HTMLElement | undefined
let box: HTMLElement | undefined
let target: Element | null = null
let refreshTimer: ReturnType<typeof setInterval> | undefined
let expiryTimer: ReturnType<typeof setTimeout> | undefined
let stopWatching: (() => void) | undefined

/** Stop drawing and remove the outline element, including a stale one from an older world. */
export function clearOutline(): void {
  clearInterval(refreshTimer)
  refreshTimer = undefined
  clearTimeout(expiryTimer)
  expiryTimer = undefined
  stopWatching?.()
  stopWatching = undefined
  target = null
  // Remove our own node when this world owns one; otherwise look the id up, because
  // a previous extension world may have left a node this world cannot reach.
  if (host) host.remove()
  else document.getElementById(OUTLINE_HOST_ID)?.remove()
  host = undefined
  box = undefined
}

/** Whether the panel covers the whole visible box, leaving nothing to outline. */
function underPanel(rect: DOMRect, avoid: () => DOMRect | null): boolean {
  const panel = avoid()
  // A detached or hidden panel host reports a zero-size rect: there is no panel.
  if (!panel || panel.width < 1 || panel.height < 1) return false
  // Coverage, not the centre: a wide element that pokes out from under the panel
  // is still worth drawing, and an outline whose middle is covered is not.
  const visibleLeft = Math.max(rect.left, 0)
  const visibleTop = Math.max(rect.top, 0)
  const visibleRight = Math.min(rect.right, innerWidth)
  const visibleBottom = Math.min(rect.bottom, innerHeight)
  return visibleLeft >= panel.left && visibleRight <= panel.right
    && visibleTop >= panel.top && visibleBottom <= panel.bottom
}

function position(avoid: () => DOMRect | null): void {
  const element = target
  if (!host || !box || !element) return
  if (!host.isConnected || !element.isConnected) {
    // The page removed our node or the target: nothing left to draw.
    clearOutline()
    return
  }
  const rect = element.getBoundingClientRect()
  const visible = rect.width >= 1 && rect.height >= 1
    && rect.bottom > 0 && rect.right > 0 && rect.top < innerHeight && rect.left < innerWidth
  const show = visible && !underPanel(rect, avoid)
  // An off-screen or hidden target has nothing to outline; the card names it.
  box.style.setProperty('display', show ? 'block' : 'none', 'important')
  if (!show) return
  box.style.setProperty('left', `${Math.round(rect.left)}px`, 'important')
  box.style.setProperty('top', `${Math.round(rect.top)}px`, 'important')
  box.style.setProperty('width', `${Math.round(rect.width)}px`, 'important')
  box.style.setProperty('height', `${Math.round(rect.height)}px`, 'important')
}

function watch(avoid: () => DOMRect | null): void {
  const refresh = (): void => position(avoid)
  window.addEventListener('scroll', refresh, { passive: true, capture: true })
  window.addEventListener('resize', refresh, { passive: true })
  let observer: ResizeObserver | undefined
  if (typeof ResizeObserver === 'function' && target) {
    observer = new ResizeObserver(refresh)
    observer.observe(target)
  }
  stopWatching = () => {
    window.removeEventListener('scroll', refresh, { capture: true })
    window.removeEventListener('resize', refresh)
    observer?.disconnect()
  }
}

const HOST_STYLE: Array<[string, string]> = [
  ['position', 'fixed'], ['inset', '0'], ['display', 'block'], ['visibility', 'visible'],
  ['opacity', '1'], ['pointer-events', 'none'], ['z-index', OUTLINE_Z_INDEX],
  ['margin', '0'], ['padding', '0'], ['border', '0'], ['background', 'transparent'],
  ['transform', 'none'], ['filter', 'none'],
]

const BOX_STYLE: Array<[string, string]> = [
  ['position', 'absolute'], ['display', 'none'], ['visibility', 'visible'], ['z-index', '0'],
  ['pointer-events', 'none'], ['box-sizing', 'border-box'], ['border', '2px solid #2f7d57'],
  ['border-radius', '4px'], ['background', 'rgba(47, 125, 87, 0.10)'],
  ['box-shadow', '0 0 0 1px rgba(255, 255, 255, 0.9), 0 0 12px rgba(47, 125, 87, 0.45)'],
  ['transition', 'none'], ['filter', 'none'], ['opacity', '1'], ['transform', 'none'],
]

function styled(styles: Array<[string, string]>): HTMLElement {
  const element = document.createElement('div')
  for (const [property, value] of styles) element.style.setProperty(property, value, 'important')
  return element
}

/**
 * Draw an outline over `element`.
 *
 * `ttlMs` of 0 keeps it until `clearOutline`; any other value removes it on its
 * own, which is what a one-off diagnosis wants. `avoid` names the panel's
 * rectangle, so a target hidden behind the panel is not outlined uselessly.
 */
export function showOutline(element: Element, ttlMs: number, avoid: () => DOMRect | null = () => null): void {
  clearOutline()
  if (!element.isConnected) return
  host = styled(HOST_STYLE)
  host.id = OUTLINE_HOST_ID
  box = styled(BOX_STYLE)
  host.appendChild(box)
  ;(document.documentElement ?? document.body).appendChild(host)
  target = element
  position(avoid)
  watch(avoid)
  refreshTimer = setInterval(() => position(avoid), REFRESH_MS)
  if (ttlMs > 0) expiryTimer = setTimeout(clearOutline, ttlMs)
}

/** The element currently outlined in this document, or null. */
export function outlinedElement(): Element | null {
  if (!host?.isConnected || !target?.isConnected) return null
  return target
}
