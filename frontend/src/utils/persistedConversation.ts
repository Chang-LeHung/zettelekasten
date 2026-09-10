import type {
  AgentPersistedMessage,
  AgentModelUsage,
  AgentTimelineEntry,
  AgentToolActivity,
  AnalysisMessage,
} from '../api/types'

export interface RestoredConversation {
  initialPrompt: string
  initialParts: AgentPersistedMessage['parts']
  messages: AnalysisMessage[]
}

function usage(message: AgentPersistedMessage): AgentModelUsage | undefined {
  if (message.input_tokens === null || message.output_tokens === null) return undefined
  return {
    input_tokens: message.input_tokens,
    output_tokens: message.output_tokens,
    cache_read_tokens: message.cache_read_tokens || 0,
    cache_write_tokens: message.cache_write_tokens || 0,
    reasoning_tokens: message.reasoning_tokens || 0,
  }
}

function toolOutput(content: string): unknown {
  try {
    return JSON.parse(content) as unknown
  } catch {
    return content
  }
}

/** Restore visible turns and correlate persisted Tool results with Assistant calls. */
export function restorePersistedConversation(records: readonly AgentPersistedMessage[]): RestoredConversation {
  const firstUser = records.find((message) => message.role === 'user')
  const messages: AnalysisMessage[] = []
  const pendingTools = new Map<string, AgentToolActivity>()
  let skippedFirstUser = false

  for (const record of records) {
    if (record.role === 'user') {
      if (!skippedFirstUser) {
        skippedFirstUser = true
        continue
      }
      messages.push({ role: 'user', content: record.content, parts: record.parts })
      continue
    }

    if (record.role === 'assistant') {
      const activities = record.tool_calls.map((call): AgentToolActivity => ({
        id: call.id,
        name: call.name,
        state: 'started',
        arguments: call.arguments,
      }))
      const timeline: AgentTimelineEntry[] = []
      if (record.reasoning_content) {
        timeline.push({ id: `reasoning-${record.id}`, type: 'reasoning', content: record.reasoning_content })
      }
      if (record.content) timeline.push({ id: `message-${record.id}`, type: 'message', content: record.content })
      for (const activity of activities) {
        pendingTools.set(activity.id, activity)
        timeline.push({ id: `tool-${activity.id}`, type: 'tool', activity })
      }
      messages.push({
        role: 'assistant',
        content: record.content,
        reasoning: record.reasoning_content || undefined,
        activities,
        timeline,
        duration_ms: record.duration_ns / 1_000_000,
        generation_duration_ms: record.duration_ns / 1_000_000,
        usage: usage(record),
      })
      continue
    }

    if (record.role === 'tool' && record.tool_call_id) {
      const activity = pendingTools.get(record.tool_call_id)
      if (!activity) continue
      activity.name = record.tool_name || activity.name
      activity.state = record.tool_success === false ? 'failed' : 'succeeded'
      activity.output = toolOutput(record.content)
      activity.error_message = record.tool_success === false ? record.content : null
      activity.duration_ms = record.duration_ns / 1_000_000
      pendingTools.delete(record.tool_call_id)
    }
  }

  return { initialPrompt: firstUser?.content || '', initialParts: firstUser?.parts || [], messages }
}
