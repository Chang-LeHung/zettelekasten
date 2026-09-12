import type { AgentModelUsage, AgentTimelineEntry, AgentToolActivity, AnalysisMessage } from '../api/types'

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
    activities: [...snapshot.activities],
    timeline: structuredClone(snapshot.timeline),
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
