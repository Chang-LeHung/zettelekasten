import type { AgentModelUsage, AgentServerToolActivity } from '../types'

/**
 * Endpoint of a container-registered capability that runs one turn: either a
 * slash command ID or an `@` reference ID.
 */
export type AgentCommandTarget = { slug: 'slash-commands' | 'at-commands'; id: string }

function asNonNegativeNumber(value: unknown): number {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0 ? value : 0
}

export function asModelUsage(value: unknown): AgentModelUsage | null {
  if (!value || typeof value !== 'object') return null
  const usage = value as Record<string, unknown>
  return {
    input_tokens: asNonNegativeNumber(usage.input_tokens),
    output_tokens: asNonNegativeNumber(usage.output_tokens),
    cache_read_tokens: asNonNegativeNumber(usage.cache_read_tokens),
    cache_write_tokens: asNonNegativeNumber(usage.cache_write_tokens),
    reasoning_tokens: asNonNegativeNumber(usage.reasoning_tokens),
  }
}

export function asServerToolActivity(event: string, payload: Record<string, unknown>): AgentServerToolActivity | null {
  const call = payload.server_tool_call as Record<string, unknown> | undefined
  const inputDelta = payload.server_tool_input_delta as Record<string, unknown> | undefined
  const result = payload.server_tool_result as Record<string, unknown> | undefined
  const id = String(call?.id || inputDelta?.call_id || result?.call_id || '')
  const name = String(call?.name || result?.name || '')
  if (!id || (event !== 'server_tool_input_delta' && !name)) return null
  return {
    id,
    name,
    state: event === 'server_tool_started'
      ? 'started'
      : event === 'server_tool_input_delta'
        ? 'streaming'
        : event === 'server_tool_completed'
          ? 'succeeded'
          : 'failed',
    input: call?.input && typeof call.input === 'object' ? call.input as Record<string, unknown> : null,
    input_delta: event === 'server_tool_input_delta' ? String(inputDelta?.delta || '') : undefined,
    output: result?.output,
    error_code: typeof result?.error_code === 'string' ? result.error_code : null,
  }
}

export function asToolCalls(value: unknown): Array<{ id: string; name: string; arguments: Record<string, unknown> }> {
  if (!Array.isArray(value)) return []
  return value.flatMap((call) => {
    if (!call || typeof call !== 'object') return []
    const item = call as Record<string, unknown>
    if (typeof item.id !== 'string' || typeof item.name !== 'string') return []
    return [{
      id: item.id,
      name: item.name,
      arguments: item.arguments && typeof item.arguments === 'object'
        ? item.arguments as Record<string, unknown>
        : {},
    }]
  })
}
