/** Data-only browser RPC. Adding an action requires validation on both sides. */
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
export interface BrowserCommand {
  type: 'command'
  id: string
  operation: 'snapshot' | 'update' | 'interact'
  change: BrowserDOMPatch | null
  query: { selector: string | null } | null
  interaction: BrowserInteraction | null
}
export interface BrowserResult { ok: boolean; result?: string; error?: string }

function record(value: unknown, keys: string[]): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('Expected an object')
  if (Object.keys(value).some(key => !keys.includes(key))) throw new Error('Unexpected browser command field')
  return value as Record<string, unknown>
}

function text(value: unknown, limit: number, blank = false): value is string {
  return typeof value === 'string' && value.length <= limit && (blank || Boolean(value.trim()))
}

export function validateCommand(value: unknown): BrowserCommand {
  const cmd = record(value, ['type', 'id', 'operation', 'change', 'query', 'interaction'])
  if (cmd.type !== 'command' || typeof cmd.id !== 'string' || !/^[a-f0-9]{32}$/.test(cmd.id)) throw new Error('Invalid command ID')
  if (cmd.operation === 'snapshot') {
    if (cmd.change != null || cmd.interaction != null) throw new Error('A read cannot include a mutation')
    if (cmd.query != null) {
      const query = record(cmd.query, ['selector'])
      if (query.selector != null && !text(query.selector, 500)) throw new Error('Invalid selector')
    }
  } else if (cmd.operation === 'update') {
    if (cmd.query != null || cmd.interaction != null) throw new Error('An update cannot include another operation')
    const patch = record(cmd.change, ['action', 'selector', 'value', 'description'])
    if (!['set_text', 'fill', 'select', 'set_checked'].includes(String(patch.action))) throw new Error('Unsupported DOM action')
    if (!text(patch.selector, 500) || !text(patch.description, 300)) throw new Error('Invalid DOM change')
    if (patch.action === 'set_checked' ? typeof patch.value !== 'boolean' : !text(patch.value, 10000, true)) {
      throw new Error('Invalid value for this DOM action')
    }
  } else if (cmd.operation === 'interact') {
    if (cmd.query != null || cmd.change != null) throw new Error('An interaction cannot include another operation')
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
