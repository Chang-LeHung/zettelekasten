import type { AgentModelUsage, AgentPersistedMessage } from '../api/types'
import { addAgentUsage } from './agentUsage'

export interface InteractionTraceModel {
  model: string | null
  provider: string | null
}

export interface InteractionTraceTurn {
  id: string
  index: number
  messages: AgentPersistedMessage[]
  provider: string | null
  model: string | null
  models: InteractionTraceModel[]
  usage: AgentModelUsage | null
  started_at: string
  completed_at: string
  duration_ms: number
}

export type InteractionTraceEventKind = 'user' | 'system' | 'agent' | 'model' | 'tool'

export interface InteractionTraceSections {
  previous: AgentPersistedMessage[]
  current: AgentPersistedMessage[]
}

function messageUsage(message: AgentPersistedMessage): AgentModelUsage | null {
  if (message.input_tokens === null || message.output_tokens === null) return null
  return {
    input_tokens: message.input_tokens,
    output_tokens: message.output_tokens,
    cache_read_tokens: message.cache_read_tokens || 0,
    cache_write_tokens: message.cache_write_tokens || 0,
    reasoning_tokens: message.reasoning_tokens || 0,
  }
}

export function interactionTraceUsage(message: AgentPersistedMessage): AgentModelUsage | null {
  return messageUsage(message)
}

export function interactionTraceEventKind(message: AgentPersistedMessage): InteractionTraceEventKind {
  if (message.role === 'assistant') return 'model'
  if (message.role === 'tool') return 'tool'
  if (message.role === 'system') return 'system'
  if (message.role === 'agent') return 'agent'
  return 'user'
}

export function interactionTraceEventLabel(message: AgentPersistedMessage): string {
  if (message.role === 'assistant') {
    return message.tool_calls.length ? 'Model response with tool calls' : 'Model response'
  }
  if (message.role === 'tool') return message.tool_success === false ? 'Tool failed' : 'Tool result'
  if (message.role === 'system') return 'System instruction'
  if (message.role === 'agent') return 'Internal agent message'
  return 'User message'
}

/** Split the raw log into prior context and the selected request. */
export function splitInteractionTraceMessages(
  allMessages: readonly AgentPersistedMessage[],
  turn: InteractionTraceTurn,
): InteractionTraceSections {
  const ordered = [...allMessages].sort((left, right) => left.sequence - right.sequence)
  const firstCurrent = turn.messages[0]
  if (!firstCurrent) return { previous: [], current: [] }
  const currentStart = ordered.findIndex((message) => message.id === firstCurrent.id)
  if (currentStart <= 0) return { previous: [], current: [...turn.messages] }
  return {
    previous: ordered.slice(0, currentStart),
    current: [...turn.messages],
  }
}

/** Group immutable Raw Log messages into LLM turns without using snapshots. */
export function buildInteractionTrace(messages: readonly AgentPersistedMessage[]): InteractionTraceTurn[] {
  const turns: InteractionTraceTurn[] = []
  const byId = new Map<string, InteractionTraceTurn>()

  for (const message of [...messages].sort((left, right) => left.sequence - right.sequence)) {
    const id = message.request_id || `sequence-${message.sequence}`
    let turn = byId.get(id)
    if (!turn) {
      turn = {
        id,
        index: turns.length + 1,
        messages: [],
        provider: null,
        model: null,
        models: [],
        usage: null,
        started_at: message.started_at,
        completed_at: message.completed_at,
        duration_ms: 0,
      }
      byId.set(id, turn)
      turns.push(turn)
    }
    turn.messages.push(message)
    if (message.provider || message.model) {
      const identity = { provider: message.provider, model: message.model }
      if (!turn.models.some((item) => item.provider === identity.provider && item.model === identity.model)) {
        turn.models.push(identity)
      }
      turn.provider ||= message.provider
      turn.model ||= message.model
    }
    const usage = messageUsage(message)
    if (usage) turn.usage = addAgentUsage(turn.usage, usage)
    turn.completed_at = message.completed_at
    turn.duration_ms += message.duration_ns / 1_000_000
  }
  return turns
}
