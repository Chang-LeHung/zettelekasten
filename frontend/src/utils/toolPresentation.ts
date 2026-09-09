import type { AgentTodoItem, AgentTodoState, AgentToolActivity } from '../api/types'

function isTodo(value: unknown): value is AgentTodoItem {
  if (!value || typeof value !== 'object') return false
  const item = value as Record<string, unknown>
  return typeof item.content === 'string'
    && ['pending', 'processing', 'completed'].includes(String(item.status))
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
