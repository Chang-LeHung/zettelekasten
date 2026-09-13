import type { AgentContextComposition } from '../api/types'

export const contextCompositionKeys = [
  'system_prompt',
  'tool_prompt',
  'tool_output',
  'user',
  'assistant',
] as const

/** Accept only the bounded ratio payload emitted by the backend estimator. */
export function asContextComposition(payload: Record<string, unknown>): AgentContextComposition | null {
  const result = {} as AgentContextComposition
  for (const key of contextCompositionKeys) {
    const value = payload[key]
    if (typeof value !== 'number' || !Number.isFinite(value) || value < 0 || value > 1) return null
    result[key] = value
  }
  const total = contextCompositionKeys.reduce((sum, key) => sum + result[key], 0)
  return total > 0 && Math.abs(total - 1) < 0.001 ? result : null
}
