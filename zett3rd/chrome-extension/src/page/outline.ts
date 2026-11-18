/**
 * Outline one page element, so the user can see what the model is talking about.
 *
 * The panel names a target in words; this draws the same target on the page for
 * a moment. It is page chrome, not content: it never intercepts a click
 * (`pointer-events: none`), sits below the panel's own stacking order, and is
 * removed when its time is up or when the connection ends.
 */

const OUTLINE_HOST_ID = 'zettelekasten-outline-host'
/** Above the page, below the panel host (2147483647). */
const OUTLINE_Z_INDEX = '2147483646'

let host: HTMLElement | undefined
let box: HTMLElement | undefined
let target: Element | null = null
let frame: number | ReturnType<typeof setTimeout> | undefined
let timer: ReturnType<typeof setTimeout> | undefined

/** Stop drawing and remove the outline element. */
export function clearOutline(): void {
  if (frame !== undefined) {
    if (typeof cancelAnimationFrame === 'function' && typeof frame === 'number') cancelAnimationFrame(frame)
    else clearTimeout(frame as ReturnType<typeof setTimeout>)
  }
  frame = undefined
  clearTimeout(timer)
  timer = undefined
  target = null
  host?.remove()
  host = undefined
  box = undefined
}

function position(): void {
  const element = target
  if (!host || !box || !element) return
  if (!element.isConnected) {
    clearOutline()
    return
  }
  const rect = element.getBoundingClientRect()
  const visible = rect.width >= 1 && rect.height >= 1
    && rect.bottom > 0 && rect.right > 0 && rect.top < innerHeight && rect.left < innerWidth
  // An off-screen target has nothing to outline; the panel already names it.
  box.style.setProperty('display', visible ? 'block' : 'none', 'important')
  if (!visible) return
  box.style.setProperty('left', `${Math.round(rect.left)}px`, 'important')
  box.style.setProperty('top', `${Math.round(rect.top)}px`, 'important')
  box.style.setProperty('width', `${Math.round(rect.width)}px`, 'important')
  box.style.setProperty('height', `${Math.round(rect.height)}px`, 'important')
}

function tick(): void {
  position()
  if (!host) return
  // The element moves with scrolling, animation, and layout, so follow it.
  frame = typeof requestAnimationFrame === 'function'
    ? requestAnimationFrame(tick)
    : setTimeout(tick, 16)
}

/**
 * Draw an outline over `element`.
 *
 * `ttlMs` of 0 keeps it until `clearOutline`; any other value removes it on its
 * own, which is what a one-off diagnosis wants.
 */
export function showOutline(element: Element, ttlMs: number): void {
  clearOutline()
  if (!element.isConnected) return
  host = document.createElement('div')
  host.id = OUTLINE_HOST_ID
  for (const [property, value] of [
    ['position', 'fixed'], ['inset', '0'], ['pointer-events', 'none'],
    ['z-index', OUTLINE_Z_INDEX], ['margin', '0'], ['padding', '0'],
    ['border', '0'], ['background', 'transparent'],
  ]) {
    host.style.setProperty(property, value, 'important')
  }
  box = document.createElement('div')
  for (const [property, value] of [
    ['position', 'absolute'], ['display', 'none'], ['pointer-events', 'none'],
    ['box-sizing', 'border-box'], ['border', '2px solid #2f7d57'],
    ['border-radius', '4px'], ['background', 'rgba(47, 125, 87, 0.10)'],
    ['box-shadow', '0 0 0 1px rgba(255, 255, 255, 0.9), 0 0 12px rgba(47, 125, 87, 0.45)'],
    ['transition', 'none'], ['filter', 'none'], ['opacity', '1'], ['transform', 'none'],
  ]) {
    box.style.setProperty(property, value, 'important')
  }
  host.appendChild(box)
  ;(document.documentElement ?? document.body).appendChild(host)
  target = element
  position()
  tick()
  if (ttlMs > 0) timer = setTimeout(clearOutline, ttlMs)
}

/** The element currently outlined, or null; used by tests and the content script. */
export function outlinedElement(): Element | null {
  return host ? target : null
}
