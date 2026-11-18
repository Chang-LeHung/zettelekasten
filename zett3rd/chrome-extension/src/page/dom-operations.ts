import {
  ALLOWED_ATTRIBUTES, encodeResult, validateCommand,
  type BrowserAttributeName, type BrowserCommand, type BrowserResult, type BrowserWaitQuery,
} from './browser-protocol'
import { PANEL_HOST_ID } from './panel-host'

const TEXT_INPUTS = new Set(['text', 'search', 'email', 'tel', 'url', 'number', 'date', 'datetime-local', 'month', 'week', 'time'])
const TEXT_ELEMENTS = new Set(['P', 'SPAN', 'DIV', 'H1', 'H2', 'H3', 'H4', 'H5', 'H6', 'LI', 'TD', 'TH', 'PRE', 'CODE', 'LABEL', 'CAPTION'])
const INTERACTIVE = 'button,a[href],input,textarea,select,[role="button"],[role="link"],[role="checkbox"],[tabindex],[contenteditable="true"]'

/** One list for every rule that keeps tools and page reads away from an element. */
const EXCLUSION_RULES: Array<[selector: string, label: string]> = [
  ['script', 'a script element'],
  ['style', 'a style element'],
  ['noscript', 'a noscript element'],
  ['template', 'a template element'],
  ['iframe', 'an iframe'],
  ['object', 'an object element'],
  ['embed', 'an embed element'],
  ['input[type="password"]', 'a password field'],
  ['input[type="hidden"]', 'a hidden input'],
  ['input[type="file"]', 'a file input'],
  ['[hidden]', 'marked hidden'],
  ['[aria-hidden="true"]', 'marked aria-hidden="true"'],
]
const EXCLUDED = EXCLUSION_RULES.map(([selector]) => selector).join(',')

/**
 * Why nothing is painted for an element.
 *
 * The element's own computed `visibility` already carries inheritance, so a
 * `visibility: visible` child of a hidden parent is correctly painted; only
 * `display` needs the ancestor walk. Reading it this way keeps `visible`,
 * `hiddenReason` and an inspection from disagreeing about the same element.
 */
function notDisplayed(element: Element): string | null {
  const own = getComputedStyle(element)
  if (own.visibility === 'hidden' || own.visibility === 'collapse') return `it has visibility: ${own.visibility}`
  for (let parent: Element | null = element; parent; parent = parent.parentElement) {
    const subject = parent === element ? 'it' : 'an ancestor'
    const computed = getComputedStyle(parent)
    // Display, not the attribute: author CSS can re-enable a `[hidden]` element.
    if (computed.display === 'none') return `${subject} has display: none`
    if (computed.contentVisibility === 'hidden') return `${subject} has content-visibility: hidden`
  }
  return null
}

function visible(element: Element): boolean {
  return hiddenReason(element) === null
}

/** Why an element cannot be acted on, in words a model can act on. */
function hiddenReason(element: Element): string | null {
  // One compound match on the common path: `readableText` asks this for every
  // element node, so the twelve rules are only walked when one of them matches.
  if (!element.closest(EXCLUDED)) return notDisplayed(element)
  return exclusionReason(element) ?? notDisplayed(element)
}

/**
 * Why nothing is painted for an element, which is not the same question as why a
 * tool refuses it: `[aria-hidden]`, a password field, or an iframe is excluded
 * from edits while still rendering on screen.
 */
function renderReason(element: Element): string | null {
  return notDisplayed(element)
}

/** Why a tool refuses an element even when it renders: `[aria-hidden]`, password, iframe, … */
function exclusionReason(element: Element): string | null {
  for (let parent: Element | null = element; parent; parent = parent.parentElement) {
    const rule = EXCLUSION_RULES.find(([selector]) => parent!.matches(selector))
    if (!rule) continue
    return parent === element
      ? `it is ${rule[1]}`
      : `an ancestor (${selectorFor(parent).slice(0, 120)}) is ${rule[1]}`
  }
  return null
}

/** Reading surfaces never carry script, template, hidden, or password content. */
function textReadable(element: Element): boolean {
  return element.closest(EXCLUDED) === null
}

/** The element a click would land on: a non-HTML element resolves its own control. */
function resolveClickable(element: Element): HTMLElement | null {
  if (element instanceof HTMLElement) return clickable(element)
  const ancestor = element.closest<HTMLElement>(INTERACTIVE)
  return ancestor && !hiddenReason(ancestor) ? ancestor : null
}

/** A computed length in pixels, or 0 when the engine gives a keyword such as `medium`. */
function pxValue(value: string): number {
  const parsed = Number.parseFloat(value)
  return Number.isFinite(parsed) ? round(parsed) : 0
}

function labelOf(element: Element): string {
  // Every surface that names an element for a person or a model goes through
  // here, so the excluded rules are enforced once, not per call site.
  if (!textReadable(element)) return ''
  const control = element as HTMLInputElement
  const raw = element.getAttribute('aria-label') || control.labels?.[0]?.textContent
    || (element instanceof HTMLInputElement && ['button', 'submit', 'reset'].includes(element.type) ? element.value : '')
    || element.textContent || control.placeholder || element.getAttribute('title') || ''
  return raw.replace(/\s+/g, ' ').trim().slice(0, 80)
}

/** One element in words: the shape of every candidate list and consent card. */
function brief(element: Element): { selector: string; tag: string; label: string } {
  return { selector: selectorFor(element), tag: element.tagName.toLowerCase(), label: labelOf(element) }
}

/** Exactly one element for a selector, or a message that names what to use instead. */
function singleMatch(selector: string): Element {
  let matches: NodeListOf<Element>
  try {
    matches = document.querySelectorAll(selector)
  } catch {
    throw new Error(`"${selector.slice(0, 120)}" is not a valid CSS selector. Copy a selector from get_browser_page instead of writing one.`)
  }
  if (matches.length === 0) {
    throw new Error(`No element matches "${selector.slice(0, 120)}". The page may have changed: call get_browser_page again, or pass its text argument to find the element by its visible words.`)
  }
  if (matches.length > 1) {
    const candidates = Array.from(matches).slice(0, 5).map((element, index) => {
      const item = brief(element)
      return `${index + 1}. ${item.selector || item.tag}${item.label ? ` "${item.label}"` : ''}`
    })
    throw new Error(`"${selector.slice(0, 120)}" matches ${matches.length} elements. Retry with one exact selector: ${candidates.join(' | ')}`.slice(0, 950))
  }
  return matches[0]
}

function target(selector: string): HTMLElement {
  const element = singleMatch(selector)
  if (!(element instanceof HTMLElement)) throw new Error('That element is not an HTML element (for example an SVG shape); target its enclosing button or link instead')
  const reason = hiddenReason(element)
  if (reason) {
    // The two refusals need different advice: an excluded element must be
    // replaced, while an unpainted one may come back after the page changes.
    const next = exclusionReason(element)
      ? 'Page tools never touch this element; choose the one the page exposes instead'
      : 'Read the page again for a visible element'
    throw new Error(`Cannot use "${selector.slice(0, 120)}": ${reason}. ${next}.`)
  }
  return element
}

function plainTextTarget(element: Element): boolean {
  return TEXT_ELEMENTS.has(element.tagName) && !element.children.length && !element.closest('form,button,a,[contenteditable]')
}

function editableRoot(element: HTMLElement): boolean {
  return element.getAttribute('contenteditable') === 'true'
    && !element.closest('[contenteditable="false"]')
    && !element.closest('input,textarea,button,a')
    && !element.matches('[role="textbox"][aria-readonly="true"]')
}

/** Which clause of `editableRoot` refused this editor, so a finding says why. */
function editableRefusal(element: HTMLElement): string {
  if (element.closest('[contenteditable="false"]')) return 'the surrounding region is contenteditable="false"; target the outer editor'
  if (element.closest('input,textarea,button,a')) return 'it sits inside an input, textarea, button, or link; target that control'
  if (element.matches('[role="textbox"][aria-readonly="true"]')) return 'it is a read-only textbox'
  return 'the editor does not accept inserted text'
}

/** Attributes authors keep stable, tried before a structural path. */
const STABLE_ATTRIBUTES = ['data-testid', 'data-test', 'data-qa', 'name', 'aria-label', 'placeholder', 'title']

/** Return selectors the model can actually use, without adding IDs to the DOM. */
function selectorFor(element: Element): string {
  if (element.id) {
    const id = `#${CSS.escape(element.id)}`
    if (document.querySelectorAll(id).length === 1 && id.length <= 500) return id
  }
  const tag = element.tagName.toLowerCase()
  for (const attribute of STABLE_ATTRIBUTES) {
    const value = element.getAttribute(attribute)
    if (!value || value.length > 80) continue
    const selector = `${tag}[${attribute}="${value.replace(/["\\]/g, '\\$&')}"]`
    if (document.querySelectorAll(selector).length === 1) return selector
  }
  const path: string[] = []
  let fallback = ''
  for (let node: Element | null = element; node && node !== document.documentElement; node = node.parentElement) {
    const siblings = Array.from(node.parentElement?.children ?? []).filter(sibling => sibling.tagName === node!.tagName)
    path.unshift(`${node.tagName.toLowerCase()}:nth-of-type(${siblings.indexOf(node) + 1})`)
    const selector = path.join(' > ')
    if (selector.length > 500) break
    fallback = selector
    if (document.querySelectorAll(selector).length === 1) return selector
  }
  return fallback.length <= 500 ? fallback : ''
}

/** Walk bounded visible text; never serialize HTML, script source, or passwords.
 * A node budget also bounds work on very large pages and reports truncation.
 */
function readableText(root: Element): { text: string; truncated: boolean } {
  const chunks: string[] = []
  let length = 0
  let nodes = 0
  let truncated = false
  function visit(node: Node): void {
    if (++nodes > 10000 || length >= 20000) { truncated = true; return }
    if (node instanceof Element && !visible(node)) return
    if (node.nodeType === Node.TEXT_NODE) {
      const text = (node.textContent || '').replace(/\s+/g, ' ').trim()
      if (text) {
        const remaining = 20000 - length
        chunks.push(text.slice(0, remaining))
        length += Math.min(text.length, remaining) + 1
        if (text.length > remaining) truncated = true
      }
      return
    }
    for (const child of node.childNodes) {
      visit(child)
      if (nodes > 10000 || length >= 20000) break
    }
  }
  visit(root)
  return { text: chunks.join('\n').slice(0, 20000), truncated }
}

/** Visible elements whose own text contains `needle`, nearest actionable ancestor first. */
function findByText(root: Element, needle: string): BrowserResult {
  const wanted = needle.toLowerCase()
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT)
  const seen = new Set<Element>()
  const matches: Array<Record<string, unknown>> = []
  let total = 0
  let visited = 0
  for (let node = walker.nextNode(); node && visited < 20000; node = walker.nextNode(), visited++) {
    const text = node.textContent || ''
    if (!text.toLowerCase().includes(wanted)) continue
    const owner = node.parentElement
    if (!owner) continue
    const element = owner.closest(INTERACTIVE) ?? owner
    if (seen.has(element) || !visible(element)) continue
    seen.add(element)
    total++
    if (matches.length >= 20) continue
    matches.push({
      ...brief(element), interactive: element.matches(INTERACTIVE),
      in_viewport: inViewport(element), text: text.replace(/\s+/g, ' ').trim().slice(0, 160),
    })
  }
  return encodeResult({
    title: document.title.slice(0, 500), url: location.href.slice(0, 2000),
    query: needle, total, matches,
    ...(total === 0 ? { notice: 'No visible element contains that text. Try fewer words, or scroll and read the page again.' } : {}),
  })
}

function inViewport(element: Element): boolean {
  const rect = element.getBoundingClientRect()
  return rect.bottom > 0 && rect.right > 0 && rect.top < innerHeight && rect.left < innerWidth
}

function snapshot(selector: string | null | undefined, text?: string | null): BrowserResult {
  const root = selector ? target(selector) : document.body
  if (!root) throw new Error('Page has no body')
  if (text) return findByText(root, text)
  const controls: Array<Record<string, unknown>> = []
  const candidates = [root, ...root.querySelectorAll(INTERACTIVE)].slice(0, 2000)
  for (const el of candidates) {
    if (!el.matches(INTERACTIVE) || !visible(el)) continue
    if (el instanceof HTMLInputElement && ['password', 'hidden', 'file'].includes(el.type)) continue
    if (el.matches('[contenteditable="true"]') && !editableRoot(el as HTMLElement)) continue
    const control = el as HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement | HTMLButtonElement
    controls.push({
      selector: selectorFor(el), tag: el.tagName.toLowerCase(), in_viewport: inViewport(el),
      ...(el instanceof HTMLAnchorElement && el.href ? { href: el.href.slice(0, 300) } : {}),
      type: el.matches('[contenteditable="true"]') ? 'contenteditable' : control.type || el.getAttribute('role') || el.tagName.toLowerCase(),
      label: (el.getAttribute('aria-label') || control.labels?.[0]?.textContent || el.textContent || '').slice(0, 160),
      name: (control.name || '').slice(0, 160), disabled: control.disabled || el.getAttribute('aria-disabled') === 'true',
      ...(el instanceof HTMLTextAreaElement || el instanceof HTMLSelectElement
        || el instanceof HTMLInputElement && TEXT_INPUTS.has(el.type) ? { value: control.value.slice(0, 300) } : {}),
      ...(editableRoot(el as HTMLElement) ? { value: (el.textContent || '').slice(0, 300) } : {}),
      ...(el instanceof HTMLInputElement && el.type === 'checkbox' ? { checked: el.checked } : {}),
      ...(el instanceof HTMLSelectElement ? {
        options: Array.from(el.options).slice(0, 30).map(option => ({ value: option.value.slice(0, 160), text: option.text.slice(0, 160), disabled: option.disabled })),
      } : {}),
    })
    if (controls.length >= 100) break
  }
  const elements = [root, ...root.querySelectorAll('h1,h2,h3,h4,h5,h6,p,span,div,li,td,th,pre,code,caption')]
    .slice(0, 2000).filter(el => plainTextTarget(el) && visible(el) && el.textContent?.trim())
    .slice(0, 40).map(el => ({ selector: selectorFor(el), text: el.textContent!.trim().slice(0, 240) }))
  return encodeResult({
    title: document.title.slice(0, 500), url: location.href.slice(0, 2000),
    scroll: {
      y: Math.round(scrollY), page_height: document.documentElement.scrollHeight, viewport_height: innerHeight,
      more_below: scrollY + innerHeight < document.documentElement.scrollHeight - 8,
    },
    ...readableText(root), controls, elements,
  })
}

/** Layout properties that decide position, size, and reachability. */
const INSPECT_STYLES = [
  'display', 'position', 'inset', 'z-index', 'float', 'box-sizing', 'width', 'height', 'min-width', 'max-width',
  'margin', 'padding', 'overflow', 'opacity', 'visibility', 'pointer-events', 'transform',
  'flex-direction', 'justify-content', 'align-items', 'gap', 'font-size', 'font-weight', 'line-height',
  'color', 'background-color', 'white-space', 'text-overflow',
]

/** Overflow values that make an ancestor clip what leaves its box. */
const CLIPPING_OVERFLOW = new Set(['hidden', 'clip', 'scroll', 'auto'])

interface HitTest {
  point: number[] | null
  reaches_target?: boolean
  covered_by?: { selector: string; tag: string; label: string }
  skipped?: string
}

function round(value: number): number {
  return Math.round(value * 10) / 10
}

function measured(rect: DOMRect): Record<string, number> {
  return { x: round(rect.left), y: round(rect.top), width: round(rect.width), height: round(rect.height) }
}

function spacingOf(computed: CSSStyleDeclaration) {
  return {
    order: 'top,right,bottom,left',
    padding: [pxValue(computed.paddingTop), pxValue(computed.paddingRight), pxValue(computed.paddingBottom), pxValue(computed.paddingLeft)],
    border: [pxValue(computed.borderTopWidth), pxValue(computed.borderRightWidth), pxValue(computed.borderBottomWidth), pxValue(computed.borderLeftWidth)],
    margin: [pxValue(computed.marginTop), pxValue(computed.marginRight), pxValue(computed.marginBottom), pxValue(computed.marginLeft)],
  }
}

/** Properties that make an ancestor the containing block of a fixed descendant. */
function isFixedContainingBlock(computed: CSSStyleDeclaration): boolean {
  const set = (property: string): boolean => {
    const value = computed.getPropertyValue(property)
    return value !== '' && value !== 'none'
  }
  if (set('transform') || set('filter') || set('backdrop-filter') || set('perspective')) return true
  if (set('translate') || set('rotate') || set('scale')) return true
  if (/paint|layout|content|strict/.test(computed.contain)) return true
  return ['transform', 'filter', 'perspective'].some(name => computed.willChange.includes(name))
}

/** The nearest ancestor that would cut the element off, so "it is not there" has a reason. */
function clippingAncestor(
  element: Element,
  rect: DOMRect,
): { selector: string; overflow: string; scroll_left: number; scroll_top: number } | null {
  // A positioned box escapes every ancestor outside its containing-block chain,
  // so an `overflow: hidden` wrapper clips a fixed modal only when it establishes
  // that block, and clips an absolute one only when it is positioned itself.
  const position = getComputedStyle(element).position
  let inChain = !(position === 'fixed' || position === 'absolute')
  let depth = 0
  for (let parent = element.parentElement; parent && depth < 20; parent = parent.parentElement, depth++) {
    const computed = getComputedStyle(parent)
    if (!inChain) {
      inChain = position === 'fixed'
        ? isFixedContainingBlock(computed)
        : computed.position !== 'static' || isFixedContainingBlock(computed)
      if (!inChain) continue
    }
    if (!CLIPPING_OVERFLOW.has(computed.overflowX) && !CLIPPING_OVERFLOW.has(computed.overflowY)) continue
    // Overflow clips at the padding box, never at the border box.
    const box = parent.getBoundingClientRect()
    const left = box.left + pxValue(computed.borderLeftWidth)
    const top = box.top + pxValue(computed.borderTopWidth)
    const right = box.right - pxValue(computed.borderRightWidth)
    const bottom = box.bottom - pxValue(computed.borderBottomWidth)
    const inside = rect.left >= left - 0.5 && rect.top >= top - 0.5 && rect.right <= right + 0.5 && rect.bottom <= bottom + 0.5
    if (inside) continue
    return {
      selector: selectorFor(parent).slice(0, 120), overflow: `${computed.overflowX}/${computed.overflowY}`,
      scroll_left: Math.round(parent.scrollLeft), scroll_top: Math.round(parent.scrollTop),
    }
  }
  return null
}

/** What a click at the middle of the box would actually reach. */
function hitTest(element: Element, rect: DOMRect): HitTest {
  const x = Math.min(Math.max(rect.left + rect.width / 2, 0), Math.max(innerWidth - 1, 0))
  const y = Math.min(Math.max(rect.top + rect.height / 2, 0), Math.max(innerHeight - 1, 0))
  const point = [round(x), round(y)]
  if (typeof document.elementFromPoint !== 'function') return { point, skipped: 'This browser cannot hit-test a point.' }
  let top: Element | null = null
  try {
    top = document.elementFromPoint(x, y)
  } catch {
    return { point, skipped: 'The browser refused to hit-test this point.' }
  }
  if (!top) return { point, skipped: 'Nothing is painted at that point.' }
  if (top.closest(`#${PANEL_HOST_ID}`)) {
    return { point, skipped: 'This Zett panel covers that point, not page content; move or resize the panel to reach it.' }
  }
  const reaches = top === element || element.contains(top)
  return reaches ? { point, reaches_target: true } : { point, reaches_target: false, covered_by: brief(top) }
}

/** Read-only diagnosis: why an element looks or behaves the way it does, without touching it. */
function inspect(query: { selector: string }): BrowserResult {
  const element = singleMatch(query.selector)
  const rect = element.getBoundingClientRect()
  const computed = getComputedStyle(element)
  const notRendered = renderReason(element)
  const refused = exclusionReason(element)
  const onScreen = inViewport(element)
  const clipped = clippingAncestor(element, rect)
  const interactive = element.matches(INTERACTIVE)
  const reachable = resolveClickable(element)
  // The same predicates the mutating tools apply, so a finding explains a refusal.
  const disabled = element.matches(':disabled') || element.getAttribute('aria-disabled') === 'true'
  const readonly = element.hasAttribute('readonly')
  // `target()` refuses an excluded or unpainted element before it reads a value,
  // so `accepts` applies that gate too instead of promising a refused tool.
  const available = hiddenReason(element) === null && !disabled && !readonly
  const clickTarget = element instanceof HTMLElement ? reachable : null
  const clickBlocked = clickTarget !== null && clickTarget.matches(':disabled,[aria-disabled="true"],[readonly]')
  const accepts = {
    set_text: available && element instanceof HTMLElement && plainTextTarget(element),
    fill: available && (element instanceof HTMLTextAreaElement
      || element instanceof HTMLInputElement && TEXT_INPUTS.has(element.type)
      || element instanceof HTMLElement && editableRoot(element)),
    select: available && element instanceof HTMLSelectElement && !element.multiple,
    set_checked: available && element instanceof HTMLInputElement && element.type === 'checkbox',
    click: available && clickTarget !== null && !clickBlocked ? selectorFor(clickTarget).slice(0, 300) : null,
  }
  // A hit test describes a user's pointer. The extension's own click dispatches on
  // the element itself, occlusion and pointer-events included, so this neither
  // predicts nor explains what interact_with_browser just did.
  const hit = notRendered
    ? { point: null, skipped: `Nothing is painted, so no pointer can reach it: ${notRendered}.` }
    : onScreen
      ? hitTest(element, rect)
      : { point: null, skipped: 'Outside the current viewport, so a user\'s pointer cannot reach it until it is scrolled into view.' }
  const readable = textReadable(element)
  const findings: string[] = []
  if (notRendered) findings.push(`It is not rendered: ${notRendered}.`)
  else if (computed.opacity === '0') findings.push('opacity: 0 keeps it invisible while it still takes clicks.')
  else if (refused) findings.push(`Edits and clicks are refused: ${refused}, even though it renders.`)
  if (!notRendered && !onScreen) findings.push('It is outside the current viewport; scrolling brings it into view.')
  if (rect.width < 1 || rect.height < 1) findings.push(`Its box is ${round(rect.width)}x${round(rect.height)}, so no point lands on it.`)
  if (computed.pointerEvents === 'none') findings.push('pointer-events: none makes a real pointer pass through it; the extension still dispatches on the element itself.')
  if (hit.covered_by) findings.push(`"${hit.covered_by.selector}" covers its middle, so a real pointer cannot click it.`)
  if (clipped) findings.push(`The ancestor "${clipped.selector}" clips it (overflow ${clipped.overflow}).`)
  if (disabled || readonly) {
    findings.push(`It is ${disabled ? 'disabled' : 'read-only'}, so interact_with_browser and update_browser_dom refuse every action on it.`)
  }
  if (!(element instanceof HTMLElement)) {
    findings.push(`It is not an HTML element, so no mutation targets it${reachable ? `; pass "${selectorFor(reachable).slice(0, 120)}" instead` : ''}.`)
  } else if (!interactive) {
    const resolved = reachable ? selectorFor(reachable).slice(0, 120) : ''
    findings.push(reachable
      ? clickBlocked
        ? `It is not itself a control; a click resolves "${resolved}", which is disabled or read-only.`
        : `It is not itself a control; a click resolves "${resolved}".`
      : 'It is plain content: no click target, and set_text applies only to a plain text element without interactive children.')
  }
  if (element instanceof HTMLElement && element.matches('[contenteditable="true"]') && !editableRoot(element)) {
    findings.push(`fill refuses this editable region because ${editableRefusal(element)}.`)
  }
  const ancestors: Array<{ selector: string; tag: string }> = []
  for (let parent = element.parentElement; parent && ancestors.length < 5; parent = parent.parentElement) {
    ancestors.push({ selector: selectorFor(parent).slice(0, 120), tag: parent.tagName.toLowerCase() })
  }
  const style: Record<string, string> = {}
  for (const property of INSPECT_STYLES) style[property] = computed.getPropertyValue(property).slice(0, 120)
  return encodeResult({
    selector: selectorFor(element).slice(0, 300),
    title: document.title.slice(0, 500),
    url: location.href.slice(0, 2000),
    tag: element.tagName.toLowerCase(),
    role: element.getAttribute('role'),
    label: labelOf(element),
    text: readable ? (element.textContent ?? '').replace(/\s+/g, ' ').trim().slice(0, 200) : '',
    box: measured(rect),
    spacing: spacingOf(computed),
    viewport: {
      width: innerWidth, height: innerHeight, device_pixel_ratio: round(devicePixelRatio),
      scroll_x: Math.round(scrollX), scroll_y: Math.round(scrollY),
    },
    rendered: notRendered === null,
    hidden_reason: notRendered,
    refused_reason: refused,
    in_viewport: onScreen,
    overflow: {
      x: computed.overflowX, y: computed.overflowY,
      scroll_width: element.scrollWidth, scroll_height: element.scrollHeight,
      client_width: element.clientWidth, client_height: element.clientHeight,
    },
    clipped_by: clipped,
    hit,
    accepts,
    states: {
      interactive,
      resolved_selector: reachable ? selectorFor(reachable).slice(0, 300) : null,
      disabled,
      readonly,
      checked: element instanceof HTMLInputElement && ['checkbox', 'radio'].includes(element.type) ? element.checked : null,
      focused: document.activeElement === element,
      focusable: interactive && element instanceof HTMLElement && element.tabIndex >= 0 && !disabled,
      tab_index: element instanceof HTMLElement ? element.tabIndex : null,
    },
    style,
    ancestors,
    findings,
    notice: 'Read-only. `hit` is what a user\'s pointer would reach; interact_with_browser dispatches on the element itself, '
      + 'so reachability neither predicts nor explains its result. The page may change; inspect again after acting.',
  })
}

/** What a click on `element` would reach: itself, its button/link ancestor, or a pointer-styled box. */
function clickable(element: HTMLElement): HTMLElement | null {
  const ancestor = element.closest<HTMLElement>(INTERACTIVE)
  if (ancestor && !hiddenReason(ancestor)) return ancestor
  if (element.hasAttribute('onclick') || getComputedStyle(element).cursor === 'pointer') return element
  return null
}

function notActionable(element: HTMLElement, what: string): Error {
  const item = brief(element)
  return new Error(`${what} needs a button, link, or other control, but "${item.selector || item.tag}"${item.label ? ` ("${item.label}")` : ''} is plain content. Pick a control from get_browser_page, or search with its text argument.`)
}

function interact(command: BrowserCommand): BrowserResult {
  const item = command.interaction!
  let element = target(item.selector)
  if (item.action === 'click' || item.action === 'double_click' || item.action === 'press_key') {
    const resolved = element.matches(INTERACTIVE) ? element : clickable(element)
    if (!resolved) throw notActionable(element, item.action === 'press_key' ? 'A key press' : 'A click')
    element = resolved
  }
  if (element.matches(':disabled,[aria-disabled="true"],[readonly]')) throw new Error('Target is disabled or read-only')
  const receipt = { action: item.action, selector: item.selector, dispatched: true, verified: false }
  switch (item.action) {
    case 'click':
    case 'double_click': {
      element.click()
      if (item.action === 'double_click') element.dispatchEvent(new MouseEvent('dblclick', { bubbles: true, cancelable: true }))
      break
    }
    case 'hover': {
      element.dispatchEvent(new PointerEvent('pointerover', { bubbles: true, pointerType: 'mouse' }))
      element.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }))
      break
    }
    case 'focus':
      element.focus()
      return encodeResult({ ...receipt, verified: document.activeElement === element })
    case 'scroll': {
      const amount = item.distance!
      const direction = item.direction!
      const deltaX = direction === 'left' ? -amount : direction === 'right' ? amount : 0
      const deltaY = direction === 'up' ? -amount : direction === 'down' ? amount : 0
      const page = element === document.body || element === document.documentElement
      const scroller = page ? window : element
      const before = page ? [window.scrollX, window.scrollY] : [element.scrollLeft, element.scrollTop]
      scroller.scrollBy({ left: deltaX, top: deltaY, behavior: 'instant' })
      const after = page ? [window.scrollX, window.scrollY] : [element.scrollLeft, element.scrollTop]
      return encodeResult({
        ...receipt, verified: before[0] !== after[0] || before[1] !== after[1],
        before, after,
        notice: 'Scroll requested; inspect newly visible page content before claiming it loaded.',
      })
    }
    case 'press_key': {
      element.focus()
      const key = item.key === 'Space' ? ' ' : item.key!
      element.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true }))
      element.dispatchEvent(new KeyboardEvent('keyup', { key, bubbles: true }))
      break
    }
    case 'drag': {
      const destination = target(item.target_selector!)
      const start = element.getBoundingClientRect()
      const end = destination.getBoundingClientRect()
      const dataTransfer = new DataTransfer()
      element.dispatchEvent(new DragEvent('dragstart', { bubbles: true, cancelable: true, dataTransfer }))
      destination.dispatchEvent(new DragEvent('dragenter', { bubbles: true, cancelable: true, dataTransfer }))
      destination.dispatchEvent(new DragEvent('dragover', { bubbles: true, cancelable: true, dataTransfer }))
      destination.dispatchEvent(new DragEvent('drop', { bubbles: true, cancelable: true, dataTransfer }))
      element.dispatchEvent(new DragEvent('dragend', { bubbles: true, dataTransfer }))
      return encodeResult({
        ...receipt, from: [start.x, start.y], to: [end.x, end.y],
        notice: 'Synthetic drag/drop events dispatched; the website may require trusted pointer input. Inspect page state.',
      })
    }
  }
  return encodeResult({
    ...receipt,
    notice: 'Event dispatched; inspect the page to confirm the intended effect before reporting success.',
  })
}

/** How often a selector or address condition is re-checked while waiting. */
const WAIT_POLL_MS = 100

function waitConditionMet(query: BrowserWaitQuery, startUrl: string): boolean {
  if (query.condition === 'url_change') return location.href !== startUrl
  let present: boolean
  if (query.selector) {
    const element = document.querySelector(query.selector)
    // "Appeared" means painted, not merely parsed: a hidden toast has not appeared.
    present = element !== null && notDisplayed(element) === null
  } else {
    const body = document.body
    // `innerText` is what the page shows; it is absent only in DOM emulators,
    // where textContent is the closest available answer.
    const visible = (body?.innerText ?? body?.textContent ?? '').toLowerCase()
    present = visible.includes((query.text ?? '').toLowerCase())
  }
  return query.condition === 'appear' ? present : !present
}

/** Poll a cheap predicate until the deadline; resolves whether it holds at the end. */
async function pollUntil(matches: () => boolean, deadline: number): Promise<boolean> {
  while (Date.now() < deadline) {
    if (matches()) return true
    const remaining = deadline - Date.now()
    await new Promise(resolve => setTimeout(resolve, Math.max(0, Math.min(WAIT_POLL_MS, remaining))))
  }
  return matches()
}

/**
 * Resolve when a text condition holds, driven by DOM mutations.
 *
 * A text condition rebuilds the whole visible text, which forces a layout flush.
 * Repeating that on a timer for eight seconds is thirty-odd full rebuilds on the
 * page's main thread while the user watches; a mutation observer checks once per
 * frame and only when the page changed, and the caller's deadline stays the
 * outer bound.
 */
function waitForText(matches: () => boolean, deadline: number): Promise<boolean> {
  if (matches()) return Promise.resolve(true)
  return new Promise<boolean>(resolve => {
    let observer: MutationObserver | undefined
    let settled = false
    let scheduled = false
    const finish = (matched: boolean): void => {
      if (settled) return
      settled = true
      observer?.disconnect()
      clearTimeout(timer)
      resolve(matched)
    }
    const check = (): void => {
      scheduled = false
      if (settled) return
      if (matches()) finish(true)
      else if (Date.now() >= deadline) finish(false)
    }
    const schedule = (): void => {
      if (scheduled || settled) return
      scheduled = true
      // jsdom has no compositor; a short timer is the honest stand-in.
      if (typeof requestAnimationFrame === 'function') requestAnimationFrame(check)
      else setTimeout(check, 16)
    }
    observer = new MutationObserver(schedule)
    observer.observe(document.body!, { childList: true, subtree: true, characterData: true })
    const timer = setTimeout(() => finish(matches()), Math.max(0, deadline - Date.now()))
  })
}

/**
 * Wait until the page reaches one condition, or report the timeout as an answer.
 *
 * `startUrl` is the address the panel connected to, so an address change that
 * happened between the click and this call still counts. A timeout is
 * `ok: true` with `matched: false`: a page that stays unchanged is information
 * the model acts on, not a tool failure that invites a blind retry.
 */
export async function waitFor(query: BrowserWaitQuery, startUrl: string = location.href): Promise<BrowserResult> {
  const started = Date.now()
  const deadline = started + query.timeout_ms
  const matches = (): boolean => waitConditionMet(query, startUrl)
  const byMutation = Boolean(query.text) && !query.selector
    && typeof MutationObserver === 'function' && document.body !== null
  const matched = byMutation ? await waitForText(matches, deadline) : await pollUntil(matches, deadline)
  return encodeResult({
    matched,
    condition: query.condition,
    waited_ms: Date.now() - started,
    ...(matched ? {} : {
      notice: 'The condition did not hold before the timeout. The page may still be loading: read it before retrying.',
    }),
  })
}

/**
 * Every edit is code owned by the extension; remote values remain plain data.
 *
 * `attribute` is here rather than in the update payload because it is a
 * different promise to the user: one allowlisted accessibility attribute, not a
 * value a control reads.
 */
export function applyAttribute(command: BrowserCommand): BrowserResult {
  const item = command.attribute!
  if (!ALLOWED_ATTRIBUTES.includes(item.name)) throw new Error('Unsupported attribute name')
  // `target()` refuses an excluded element, and the attribute this tool exists to
  // fix — `aria-hidden` — is exactly such an exclusion, so only rendering is
  // required here: writing `alt` or an `aria-*` value into an excluded subtree is
  // the intended repair, and a non-HTML element (an `<svg>` image) has attributes.
  const element = singleMatch(item.selector)
  const notRendered = notDisplayed(element)
  if (notRendered) throw new Error(`Cannot use "${item.selector.slice(0, 120)}": ${notRendered}. Read the page again.`)
  if (item.remove) element.removeAttribute(item.name)
  else element.setAttribute(item.name, item.value ?? '')
  const applied = element.getAttribute(item.name)
  return encodeResult({
    selector: item.selector,
    name: item.name,
    value: applied,
    applied: item.remove ? applied === null : applied === item.value,
    notice: 'The attribute changed. Read the page again to confirm how it now renders.',
  })
}

/** Elements a keyboard user can reach, used by the focusability checks. */
const FOCUSABLE = 'a[href],button,input:not([type="hidden"]),select,textarea,[tabindex]:not([tabindex="-1"]),[contenteditable="true"]'
const AUDIT_EXAMPLES = 3

/**
 * One finding with selectors the model can actually use.
 *
 * `selectorFor` can outgrow the 500-character limit on deep elements, and a
 * truncated selector is worse than none: copying it only produces "not a valid
 * CSS selector". An element whose selector does not fit is counted, not shown.
 */
function auditFinding(id: string, problem: string, elements: Element[]) {
  const examples: string[] = []
  for (const element of elements) {
    if (examples.length >= AUDIT_EXAMPLES) break
    const selector = selectorFor(element)
    if (selector.length <= 120) examples.push(selector)
  }
  return { id, problem, count: elements.length, examples }
}

/** Resolve an `aria-labelledby` list to the text it actually names, if any. */
function referencedText(ids: string): string {
  return ids
    .split(/\s+/)
    .map(id => document.getElementById(id)?.textContent ?? '')
    .join(' ')
    .replace(/\s+/g, ' ')
    .trim()
}

/** Whether an element is reachable by a keyboard user in this document right now. */
function focusableElements(element: Element): Element[] {
  const candidates = [
    ...(element.matches(FOCUSABLE) ? [element] : []),
    ...Array.from(element.querySelectorAll(FOCUSABLE)),
  ]
  return candidates.filter(candidate => !candidate.matches(':disabled') && notDisplayed(candidate) === null)
}

/**
 * The accessibility problems a static DOM pass can name.
 *
 * It answers what it can see — missing `alt`, unnamed controls, `aria-hidden`
 * over something focusable, positive tabindex, skipped heading levels, a missing
 * `lang` — and never claims contrast, reading order, or whether a label makes
 * sense, which need a person.
 */
export function auditAccessibility(): BrowserResult {
  const images = Array.from(document.querySelectorAll(
    'img:not([alt]),input[type="image"]:not([alt]),area[href]:not([alt])',
  ))
  const unnamed = Array.from(document.querySelectorAll(
    'input:not([type="hidden"]):not([type="submit"]):not([type="button"]):not([type="reset"]),textarea,select',
  )).filter(element => {
    const control = element as HTMLInputElement
    const labelledby = element.getAttribute('aria-labelledby')
    // A dangling `aria-labelledby` names nothing, which is exactly the re-render
    // bug this check should catch.
    const referenced = labelledby
      ? referencedText(labelledby)
      : ''
    const label = element.getAttribute('aria-label') || referenced
      || element.getAttribute('title') || control.placeholder || control.labels?.[0]?.textContent || ''
    return !label.trim()
  })
  const unlabeledControls = Array.from(document.querySelectorAll('button,a[href]')).filter(element => {
    const text = (element.textContent ?? '').replace(/\s+/g, ' ').trim()
    const named = element.getAttribute('aria-label') || element.getAttribute('title')
      || (element.getAttribute('aria-labelledby') ? referencedText(element.getAttribute('aria-labelledby')!) : '')
      || element.querySelector('img[alt]:not([alt=""]), svg[aria-label], [aria-label]')
      || (element.querySelector('svg title')?.textContent ?? '').trim()
    return !text && !named
  })
  const hiddenFocusable = Array.from(document.querySelectorAll('[aria-hidden="true"]'))
    // A closed menu is `aria-hidden` *and* unrendered; only a visible subtree
    // really takes focus away from a keyboard user.
    .filter(element => notDisplayed(element) === null && focusableElements(element).length > 0)
  const positiveTabindex = Array.from(document.querySelectorAll('[tabindex]'))
    .filter(element => Number(element.getAttribute('tabindex')) > 0)

  const headings = Array.from(document.querySelectorAll('h1,h2,h3,h4,h5,h6'))
  const skipped: Element[] = []
  let previous = 0
  for (const heading of headings) {
    const level = Number(heading.tagName.slice(1))
    if (previous > 0 && level > previous + 1) skipped.push(heading)
    previous = level
  }

  const lang = document.documentElement.getAttribute('lang') ?? document.documentElement.getAttribute('xml:lang')
  const checks = [
    auditFinding('image_without_alt', 'Image, image input, or image map area has no alt text', images),
    auditFinding('control_without_name', 'Form control has no label, name, or placeholder', unnamed),
    auditFinding('control_without_text', 'Button or link has no text and no accessible name', unlabeledControls),
    auditFinding('aria_hidden_focusable', 'aria-hidden hides something a keyboard user can focus', hiddenFocusable),
    auditFinding('positive_tabindex', 'Positive tabindex overrides the natural focus order', positiveTabindex),
    auditFinding('heading_level_skipped', 'Heading level skips a level', skipped),
    ...(lang && lang.trim() ? [] : [{
      id: 'missing_lang', problem: 'The document has no lang attribute', count: 1, examples: ['html'],
    }]),
  ]
  return encodeResult({
    url: location.href.slice(0, 2000),
    title: document.title.slice(0, 300),
    checks,
    notice: 'A static DOM check only: contrast, reading order, and whether a label makes sense are not judged.',
  })
}

/** Every edit is code owned by the extension; remote values remain plain data. */
export function applyDOMCommand(command: BrowserCommand): BrowserResult {
  validateCommand(command)
  if (command.operation === 'snapshot') return snapshot(command.query?.selector, command.query?.text)
  if (command.operation === 'inspect') return inspect(command.inspect!)
  if (command.operation === 'interact') return interact(command)
  if (command.operation === 'audit') return auditAccessibility()
  if (command.operation === 'attribute') return applyAttribute(command)
  // Explicit, not an else: a new operation must never fall through into an edit.
  if (command.operation !== 'update') throw new Error('Unknown browser operation')
  const patch = command.change!
  const element = target(patch.selector)
  const disabled = element.matches(':disabled') || element.getAttribute('aria-disabled') === 'true'
  if (disabled || element.hasAttribute('readonly')) throw new Error('Target is disabled or read-only')
  switch (patch.action) {
    case 'set_text': {
      if (!plainTextTarget(element)) {
        throw new Error('set_text requires a plain text element with no child elements outside form/interactive controls')
      }
      // textContent makes strings such as <script> literal text, never markup.
      element.textContent = patch.value as string
      break
    }
    case 'fill': {
      if (editableRoot(element)) {
        // ProseMirror/React editors maintain their own document state. Replacing
        // textContent (or a child <p>) is immediately undone on rerender. A
        // browser editing command follows the same input path as user typing.
        // Never fall back to innerHTML or arbitrary page-world JavaScript.
        const selection = window.getSelection()
        if (!selection) throw new Error('Cannot select this editor')
        const range = document.createRange()
        range.selectNodeContents(element)
        element.focus()
        selection.removeAllRanges()
        selection.addRange(range)
        if (!document.execCommand('insertText', false, patch.value as string)) {
          throw new Error('This contenteditable editor refused text input')
        }
      } else {
        const prototype = element instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype
          : element instanceof HTMLInputElement && TEXT_INPUTS.has(element.type) ? HTMLInputElement.prototype : null
        if (!prototype) throw new Error('fill supports only text-like inputs, textareas and contenteditable editors')
        Object.getOwnPropertyDescriptor(prototype, 'value')!.set!.call(element, patch.value)
      }
      break
    }
    case 'select': {
      if (!(element instanceof HTMLSelectElement) || element.multiple) throw new Error('select requires a single-choice select')
      const option = Array.from(element.options).find(item => item.value === patch.value)
      if (!option || option.disabled || option.parentElement?.matches('optgroup:disabled')) throw new Error('Requested option is missing or disabled')
      Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value')!.set!.call(element, patch.value)
      break
    }
    case 'set_checked': {
      if (!(element instanceof HTMLInputElement) || element.type !== 'checkbox') throw new Error('set_checked requires a checkbox')
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'checked')!.set!.call(element, patch.value)
      break
    }
  }
  if (patch.action !== 'set_text' && !(patch.action === 'fill' && editableRoot(element))) {
    // Controlled forms need these events. A site's own handlers may auto-save;
    // the UI explains that effect before consent, but we never click or submit.
    element.dispatchEvent(new Event('input', { bubbles: true }))
    element.dispatchEvent(new Event('change', { bubbles: true }))
  }
  const actual = patch.action === 'set_text' || patch.action === 'fill' && editableRoot(element) ? element.textContent
    : patch.action === 'set_checked' ? (element as HTMLInputElement).checked
      : (element as HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement).value
  return encodeResult({
    selector: patch.selector, action: patch.action, applied: actual === patch.value,
    value: typeof actual === 'string' ? actual.slice(0, 10000) : actual,
  })
}

/** What the user is about to act on, in the page's own words, for the consent card. */
export function describeSelector(selector: string): { matched: number; tag?: string; label?: string; href?: string; selector?: string } {
  let matches: NodeListOf<Element>
  try {
    matches = document.querySelectorAll(selector)
  } catch {
    return { matched: 0 }
  }
  if (matches.length !== 1) return { matched: matches.length }
  const element = matches[0]
  const target = element.matches(INTERACTIVE) ? element : element.closest(INTERACTIVE) ?? element
  const item = brief(target)
  return {
    matched: 1, tag: item.tag, label: item.label, selector: item.selector,
    ...(target instanceof HTMLAnchorElement && target.href ? { href: target.href.slice(0, 300) } : {}),
  }
}
