import { encodeResult, validateCommand, type BrowserCommand, type BrowserResult } from './browser-protocol'

const TEXT_INPUTS = new Set(['text', 'search', 'email', 'tel', 'url', 'number', 'date', 'datetime-local', 'month', 'week', 'time'])
const TEXT_ELEMENTS = new Set(['P', 'SPAN', 'DIV', 'H1', 'H2', 'H3', 'H4', 'H5', 'H6', 'LI', 'TD', 'TH', 'PRE', 'CODE', 'LABEL', 'CAPTION'])
const EXCLUDED = 'script,style,noscript,template,iframe,object,embed,input[type="password"],input[type="hidden"],input[type="file"],[hidden],[aria-hidden="true"]'
const INTERACTIVE = 'button,a[href],input,textarea,select,[role="button"],[role="link"],[role="checkbox"],[tabindex],[contenteditable="true"]'

function visible(element: Element): boolean {
  for (let parent: Element | null = element; parent; parent = parent.parentElement) {
    if (parent.matches(EXCLUDED)) return false
    const style = getComputedStyle(parent)
    if (style.display === 'none' || style.visibility === 'hidden' || style.visibility === 'collapse') return false
  }
  return true
}

/** Why an element cannot be acted on, in words a model can act on. */
function hiddenReason(element: Element): string | null {
  for (let parent: Element | null = element; parent; parent = parent.parentElement) {
    const subject = parent === element ? 'it' : 'an ancestor'
    if (parent.matches(EXCLUDED)) return `${subject} is hidden or excluded (hidden/aria-hidden/script)`
    const style = getComputedStyle(parent)
    if (style.display === 'none') return `${subject} has display: none`
    if (style.visibility === 'hidden' || style.visibility === 'collapse') return `${subject} has visibility: ${style.visibility}`
  }
  return null
}

function labelOf(element: Element): string {
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

function target(selector: string): HTMLElement {
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
  const element = matches[0]
  if (!(element instanceof HTMLElement)) throw new Error('That element is not an HTML element (for example an SVG shape); target its enclosing button or link instead')
  const reason = hiddenReason(element)
  if (reason) throw new Error(`Cannot use "${selector.slice(0, 120)}": ${reason}. Read the page again for a visible element.`)
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

/** Every edit is code owned by the extension; remote values remain plain data. */
export function applyDOMCommand(command: BrowserCommand): BrowserResult {
  validateCommand(command)
  if (command.operation === 'snapshot') return snapshot(command.query?.selector, command.query?.text)
  if (command.operation === 'interact') return interact(command)
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
