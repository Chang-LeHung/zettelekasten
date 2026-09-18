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
