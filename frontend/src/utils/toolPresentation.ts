import type { AgentTodoItem, AgentTodoState, AgentToolActivity } from '../api/types'

export type ToolOutputPart =
  | { type: 'text'; text: string }
  | { type: 'image'; url: string; alt_text: string | null }

function isTodo(value: unknown): value is AgentTodoItem {
  if (!value || typeof value !== 'object') return false
  const item = value as Record<string, unknown>
  return typeof item.content === 'string'
    && ['pending', 'processing', 'completed'].includes(String(item.status))
}

function imageUrl(value: unknown): string | null {
  if (typeof value !== 'string') return null
  if (!value.startsWith('data:image/') && !/^https?:\/\//i.test(value)) return null
  return value
}

function toolOutputPart(value: unknown): ToolOutputPart | null {
  if (typeof value === 'string' && value.startsWith('data:image/')) {
    return { type: 'image', url: value, alt_text: null }
  }
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null

  const part = value as Record<string, unknown>
  if (typeof part.text === 'string') return { type: 'text', text: part.text }
  if (part.type !== 'image') return null

  const url = imageUrl(part.url) || imageUrl(part.content_url)
  if (!url) return null
  return {
    type: 'image',
    url,
    alt_text: typeof part.alt_text === 'string' ? part.alt_text : null,
  }
}

/** Recognize multimodal tool output without treating arbitrary tool JSON as an image. */
export function toolOutputParts(value: unknown): ToolOutputPart[] | null {
  const candidates = Array.isArray(value) ? value : [value]
  if (!candidates.length) return null
  const parts = candidates.map(toolOutputPart)
  return parts.every((part): part is ToolOutputPart => part !== null) ? parts : null
}

export interface ServerToolView {
  /** Short name for the tool the provider ran, such as "Web search" or "Code execution". */
  label: string
  /** One line describing what happened, e.g. the queries that ran. */
  summary: string
  /** Pages the hosted tool cited, already projected by the backend. */
  pages: Array<{ url: string; title?: string }>
  /** Readable text the hosted tool returned, or the provider's error code. */
  text: string
  error: string
}

const serverToolLabels: Readonly<Record<string, string>> = {
  web_search: 'Web search',
  web_fetch: 'Web fetch',
  google_search: 'Google Search',
  url_context: 'URL context',
  code_execution: 'Code execution',
}

/** Name a provider-hosted tool the way a reader thinks of it, keeping an unknown type visible. */
export function serverToolLabel(name: string): string {
  return serverToolLabels[name] ?? (name.replaceAll('_', ' ') || 'Provider tool')
}

/**
 * Project one hosted tool result for the transcript.
 *
 * The backend already dropped sealed payloads and capped lengths; this only picks the
 * shape each tool returns: a search reports pages and queries, a fetch reports text, and
 * a failed call reports its own error code instead of an empty result.
 */
export function serverToolView(name: string, output: unknown, errorCode: string | null | undefined): ServerToolView {
  const label = serverToolLabel(name)
  const error = errorCode || ''
  if (!output || typeof output !== 'object' || Array.isArray(output)) {
    return { label, summary: '', pages: [], text: typeof output === 'string' ? output : '', error }
  }
  const value = output as Record<string, unknown>
  const pages = Array.isArray(value.pages)
    ? value.pages.flatMap((page) => {
        if (!page || typeof page !== 'object') return []
        const item = page as Record<string, unknown>
        if (typeof item.url !== 'string') return []
        return [{ url: item.url, title: typeof item.title === 'string' ? item.title : undefined }]
      })
    : []
  const queries = Array.isArray(value.queries) ? value.queries.filter((query): query is string => typeof query === 'string') : []
  const text = typeof value.text === 'string' ? value.text : ''
  const summary = queries.length
    ? queries.join(' · ')
    : pages.length
      ? `${pages.length} page${pages.length === 1 ? '' : 's'}`
      : typeof value.status === 'string' ? value.status : ''
  return {
    label,
    summary,
    pages: pages.slice(0, 8),
    text,
    error: error || (typeof value.error === 'string' ? value.error : ''),
  }
}

/** Interpret task progress only in the presentation layer, never in the SSE protocol. */
export function todoFromTool(activity: AgentToolActivity): AgentTodoState | null {
  if (activity.name !== 'todo_write' || activity.state !== 'succeeded') return null
  if (!activity.output || typeof activity.output !== 'object') return null
  const value = activity.output as Record<string, unknown>
  if (!Array.isArray(value.todos) || !value.todos.every(isTodo)) return null
  if (typeof value.completed !== 'boolean') return null
  if (value.processing_index !== null && (
    typeof value.processing_index !== 'number' || !Number.isInteger(value.processing_index)
    || value.processing_index < 0 || value.processing_index >= value.todos.length
  )) return null
  if (value.processing !== null && !isTodo(value.processing)) return null
  return {
    todos: value.todos,
    processing_index: value.processing_index as number | null,
    processing: value.processing as AgentTodoItem | null,
    completed: value.completed,
  }
}
