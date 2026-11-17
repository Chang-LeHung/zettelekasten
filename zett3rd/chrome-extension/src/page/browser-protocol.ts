/** Data-only browser RPC. Adding an action requires validation on both sides. */
/** How long one command may run before the panel calls it lost. */
export const COMMAND_TIMEOUT_MS = 10000
/** The furthest `expiresAt` a content script accepts; both ends must agree. */
export const COMMAND_EXPIRY_ALLOWANCE_MS = 11000

export interface BrowserDOMPatch {
  action: 'set_text' | 'fill' | 'select' | 'set_checked'
  selector: string
  value: string | boolean
  description: string
}
export interface BrowserInteraction {
  action: 'click' | 'double_click' | 'hover' | 'focus' | 'scroll' | 'press_key' | 'drag'
  selector: string
  description: string
  target_selector: string | null
  key: 'Enter' | 'Tab' | 'Escape' | 'Backspace' | 'Delete' | 'ArrowUp' | 'ArrowDown' | 'ArrowLeft' | 'ArrowRight' | 'Space' | null
  direction: 'up' | 'down' | 'left' | 'right' | null
  distance: number | null
}
export interface BrowserInspectQuery {
  selector: string
}
export interface BrowserWaitQuery {
  condition: 'appear' | 'disappear' | 'url_change'
  selector: string | null
  text: string | null
  timeout_ms: number
}
export interface BrowserProbeQuery {
  kind: 'console' | 'network' | 'metrics'
  limit: number
}
/** The only attributes a page edit may touch: accessibility, never behaviour. */
export const ALLOWED_ATTRIBUTES = ['alt', 'title', 'aria-label', 'aria-labelledby', 'aria-hidden', 'role'] as const
export type BrowserAttributeName = (typeof ALLOWED_ATTRIBUTES)[number]
export interface BrowserAttributeChange {
  name: BrowserAttributeName
  selector: string
  value: string | null
  remove: boolean
  description: string
}
export interface BrowserCommand {
  type: 'command'
  id: string
  operation: 'snapshot' | 'screenshot' | 'inspect' | 'wait' | 'probe' | 'audit' | 'update' | 'attribute' | 'interact'
  change: BrowserDOMPatch | null
  query: { selector: string | null; text?: string | null } | null
  interaction: BrowserInteraction | null
  inspect: BrowserInspectQuery | null
  wait: BrowserWaitQuery | null
  probe: BrowserProbeQuery | null
  attribute: BrowserAttributeChange | null
}
export interface BrowserResult { ok: boolean; result?: string; image?: string; error?: string }

function record(value: unknown, keys: string[]): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('Expected an object')
  if (Object.keys(value).some(key => !keys.includes(key))) throw new Error('Unexpected browser command field')
  return value as Record<string, unknown>
}

function text(value: unknown, limit: number, blank = false): value is string {
  return typeof value === 'string' && value.length <= limit && (blank || Boolean(value.trim()))
}

export function validateCommand(value: unknown): BrowserCommand {
  const cmd = record(value, ['type', 'id', 'operation', 'change', 'query', 'interaction', 'inspect', 'wait', 'probe', 'attribute'])
  if (cmd.type !== 'command' || typeof cmd.id !== 'string' || !/^[a-f0-9]{32}$/.test(cmd.id)) throw new Error('Invalid command ID')
  if (cmd.operation === 'snapshot') {
    if (cmd.change != null || cmd.interaction != null || cmd.inspect != null || cmd.wait != null
      || cmd.probe != null || cmd.attribute != null) throw new Error('A read cannot include a mutation')
    if (cmd.query != null) {
      const query = record(cmd.query, ['selector', 'text'])
      if (query.selector != null && !text(query.selector, 500)) throw new Error('Invalid selector')
      if (query.text != null && !text(query.text, 200)) throw new Error('Invalid search text')
    }
  } else if (cmd.operation === 'screenshot' || cmd.operation === 'audit') {
    if (cmd.change != null || cmd.query != null || cmd.interaction != null || cmd.inspect != null
      || cmd.wait != null || cmd.probe != null || cmd.attribute != null) {
      throw new Error(`${cmd.operation} carries no payload`)
    }
  } else if (cmd.operation === 'attribute') {
    if (cmd.change != null || cmd.query != null || cmd.interaction != null || cmd.inspect != null
      || cmd.wait != null || cmd.probe != null) {
      throw new Error('An attribute change cannot include another operation')
    }
    const attribute = record(cmd.attribute, ['name', 'selector', 'value', 'remove', 'description'])
    if (!ALLOWED_ATTRIBUTES.includes(String(attribute.name) as BrowserAttributeName)) throw new Error('Unsupported attribute name')
    if (!text(attribute.selector, 500) || !text(attribute.description, 300)) throw new Error('Invalid attribute change')
    if (typeof attribute.remove !== 'boolean') throw new Error('Invalid attribute removal flag')
    if (attribute.value != null && !text(attribute.value, 200, true)) throw new Error('Invalid attribute value')
    if (attribute.remove ? attribute.value != null : attribute.value == null) {
      throw new Error('An attribute change sets a value or removes the attribute, never both')
    }
  } else if (cmd.operation === 'probe') {
    if (cmd.change != null || cmd.query != null || cmd.interaction != null || cmd.inspect != null
      || cmd.wait != null || cmd.attribute != null) {
      throw new Error('A probe cannot include another operation')
    }
    const probe = record(cmd.probe, ['kind', 'limit'])
    if (!['console', 'network', 'metrics'].includes(String(probe.kind))) throw new Error('Unsupported probe kind')
    if (!Number.isInteger(probe.limit) || Number(probe.limit) < 1 || Number(probe.limit) > 50) throw new Error('Invalid probe limit')
  } else if (cmd.operation === 'wait') {
    if (cmd.change != null || cmd.query != null || cmd.interaction != null || cmd.inspect != null
      || cmd.probe != null || cmd.attribute != null) throw new Error('A wait cannot include another operation')
    const wait = record(cmd.wait, ['condition', 'selector', 'text', 'timeout_ms'])
    if (!['appear', 'disappear', 'url_change'].includes(String(wait.condition))) throw new Error('Unsupported wait condition')
    if (wait.selector != null && !text(wait.selector, 500)) throw new Error('Invalid wait selector')
    if (wait.text != null && !text(wait.text, 200)) throw new Error('Invalid wait text')
    if (!Number.isInteger(wait.timeout_ms) || Number(wait.timeout_ms) < 500 || Number(wait.timeout_ms) > 8000) {
      throw new Error('Invalid wait timeout')
    }
    if (wait.condition === 'url_change'
      ? wait.selector != null || wait.text != null
      : (wait.selector == null) === (wait.text == null)) {
      throw new Error('Invalid wait arguments for this condition')
    }
  } else if (cmd.operation === 'inspect') {
    if (cmd.change != null || cmd.query != null || cmd.interaction != null || cmd.wait != null
      || cmd.probe != null || cmd.attribute != null) throw new Error('An inspection cannot include another operation')
    const inspect = record(cmd.inspect, ['selector'])
    if (!text(inspect.selector, 500)) throw new Error('Invalid inspect selector')
  } else if (cmd.operation === 'update') {
    if (cmd.query != null || cmd.interaction != null || cmd.inspect != null || cmd.wait != null
      || cmd.probe != null || cmd.attribute != null) throw new Error('An update cannot include another operation')
    const patch = record(cmd.change, ['action', 'selector', 'value', 'description'])
    if (!['set_text', 'fill', 'select', 'set_checked'].includes(String(patch.action))) throw new Error('Unsupported DOM action')
    if (!text(patch.selector, 500) || !text(patch.description, 300)) throw new Error('Invalid DOM change')
    if (patch.action === 'set_checked' ? typeof patch.value !== 'boolean' : !text(patch.value, 10000, true)) {
      throw new Error('Invalid value for this DOM action')
    }
  } else if (cmd.operation === 'interact') {
    if (cmd.query != null || cmd.change != null || cmd.inspect != null || cmd.wait != null
      || cmd.probe != null || cmd.attribute != null) throw new Error('An interaction cannot include another operation')
    const item = record(cmd.interaction, ['action', 'selector', 'description', 'target_selector', 'key', 'direction', 'distance'])
    if (!['click', 'double_click', 'hover', 'focus', 'scroll', 'press_key', 'drag'].includes(String(item.action))
      || !text(item.selector, 500) || !text(item.description, 300)) throw new Error('Invalid interaction')
    if (item.action === 'drag' ? !text(item.target_selector, 500) : item.target_selector != null) throw new Error('Invalid drag target')
    if (item.action === 'press_key'
      ? !['Enter', 'Tab', 'Escape', 'Backspace', 'Delete', 'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'Space'].includes(String(item.key))
      : item.key != null) throw new Error('Invalid key')
    if (item.action === 'scroll'
      ? !['up', 'down', 'left', 'right'].includes(String(item.direction)) || !Number.isInteger(item.distance)
        || Number(item.distance) < 1 || Number(item.distance) > 2000
      : item.direction != null || item.distance != null) throw new Error('Invalid scroll')
  } else {
    throw new Error('Unknown browser operation')
  }
  return value as BrowserCommand
}

export function allowedPage(url: string): boolean {
  try {
    const parsed = new URL(url)
    return ['http:', 'https:'].includes(parsed.protocol)
      && !['chromewebstore.google.com', 'chrome.google.com'].includes(parsed.hostname)
  } catch { return false }
}

export function encodeResult(value: unknown): BrowserResult {
  const result = JSON.stringify(value)
  if (typeof result !== 'string' || new TextEncoder().encode(result).length > 64000) {
    throw new Error('Result exceeds 64 KB; read a smaller subtree with a selector')
  }
  return { ok: true, result }
}

/** Fragment-only changes keep the same document, so they must not drop the connection. */
export function sameDocumentUrl(left: string, right: string): boolean {
  try {
    const a = new URL(left)
    const b = new URL(right)
    a.hash = ''
    b.hash = ''
    return a.href === b.href
  } catch { return left === right }
}
