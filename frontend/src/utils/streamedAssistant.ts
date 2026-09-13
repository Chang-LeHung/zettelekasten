import type { AgentModelUsage, AgentTimelineEntry, AgentToolActivity, AnalysisMessage } from '../api/types'
import { jsonSnapshot } from './jsonSnapshot'

export interface StreamedAssistantSnapshot {
  content: string
  reasoning?: string
  activities: AgentToolActivity[]
  timeline: AgentTimelineEntry[]
  duration_ms: number
  generation_duration_ms: number
  usage?: AgentModelUsage
}

export interface StreamedAssistantOptions {
  fallbackContent?: string
  error?: string
}

/** Build the durable UI representation of a completed, cancelled, or failed stream. */
export function createStreamedAssistantMessage(
  snapshot: StreamedAssistantSnapshot,
  options: StreamedAssistantOptions = {},
): AnalysisMessage {
  return {
    role: 'assistant',
    content: snapshot.content || options.fallbackContent || '',
    reasoning: snapshot.reasoning,
    // Vue wraps live stream collections in proxies. structuredClone rejects
    // proxies with DataCloneError exactly when the completed turn is handed
    // off from transient stream state to durable conversation state.
    activities: jsonSnapshot(snapshot.activities),
    timeline: jsonSnapshot(snapshot.timeline),
    duration_ms: snapshot.duration_ms,
    generation_duration_ms: snapshot.generation_duration_ms,
    usage: snapshot.usage ? { ...snapshot.usage } : undefined,
    error: options.error,
  }
}

/** Append a stream snapshot without mutating or replacing earlier conversation messages. */
export function appendStreamedAssistantMessage(
  messages: readonly AnalysisMessage[],
  snapshot: StreamedAssistantSnapshot,
  options: StreamedAssistantOptions = {},
): AnalysisMessage[] {
  return [...messages, createStreamedAssistantMessage(snapshot, options)]
}
