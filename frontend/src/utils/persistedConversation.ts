import type {
  AgentPersistedMessage,
  AgentModelUsage,
  AgentTimelineEntry,
  AgentToolActivity,
  AnalysisMessage,
  MessagePart,
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

/**
 * Original user message recorded when an application extension rewrote the
 * model prompt, such as a slash command that loaded a skill or an `@` reference
 * that named a conversation resource. The expanded prompt stays in `content`,
 * so the UI must not show it back to the user as if they had typed it. Images
 * travel with the recorded parts.
 */
function originalUserParts(record: AgentPersistedMessage): MessagePart[] | null {
  for (const key of ['slash_command', 'at_command']) {
    const rewrite = record.attributes?.[key]
    if (!rewrite || typeof rewrite !== 'object') continue
    const rawParts = (rewrite as { raw_parts?: unknown }).raw_parts
    if (!Array.isArray(rawParts)) continue
    const parts = rawParts.filter(isRecordedPart)
    if (parts.length) return parts
  }
  return null
}

function isRecordedPart(part: unknown): part is MessagePart {
  if (!part || typeof part !== 'object') return false
  const candidate = part as { type?: unknown; text?: unknown; content_url?: unknown }
  if (candidate.type === 'text') return typeof candidate.text === 'string'
  if (candidate.type === 'image') return typeof candidate.content_url === 'string'
  return false
}

function userPrompt(record: AgentPersistedMessage): Pick<AgentPersistedMessage, 'content' | 'parts'> {
  const parts = originalUserParts(record)
  if (parts === null) return { content: record.content, parts: record.parts }
  return {
    content: parts.filter(part => part.type === 'text').map(part => part.text).join('\n'),
    parts,
  }
}

/** Restore visible turns and correlate persisted Tool results with Assistant calls. */
export function restorePersistedConversation(records: readonly AgentPersistedMessage[]): RestoredConversation {
  const firstUserRecord = records.find((message) => message.role === 'user')
  const firstUser = firstUserRecord ? userPrompt(firstUserRecord) : null
  const messages: AnalysisMessage[] = []
  const pendingTools = new Map<string, AgentToolActivity>()
  let skippedFirstUser = false

  for (const record of records) {
    if (record.role === 'user') {
      if (!skippedFirstUser) {
        skippedFirstUser = true
        continue
      }
      const prompt = userPrompt(record)
      messages.push({ role: 'user', content: prompt.content, parts: prompt.parts })
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
      activity.output = record.parts?.length
        ? record.parts.map(part => part.type === 'image'
          ? { type: 'image', url: part.content_url, alt_text: part.name }
          : { text: part.text })
        : toolOutput(record.content)
      activity.error_message = record.tool_success === false ? record.content : null
      activity.duration_ms = record.duration_ns / 1_000_000
      pendingTools.delete(record.tool_call_id)
    }
  }

  return { initialPrompt: firstUser?.content || '', initialParts: firstUser?.parts || [], messages }
}
