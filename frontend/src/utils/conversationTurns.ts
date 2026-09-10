import type { AgentTimelineEntry, AnalysisMessage } from '../api/types'

export type MessageTimelineEntry = Extract<AgentTimelineEntry, { type: 'message' }>

export interface TurnTimelineSections {
  execution: AgentTimelineEntry[]
  answer: MessageTimelineEntry[]
}

export interface ConversationTurn {
  id: string
  prompt: AnalysisMessage
  responses: AnalysisMessage[]
  response?: AnalysisMessage
}

/** Group a flat persisted message stream into user-initiated turns. */
export function buildConversationTurns(
  initialPrompt: string,
  messages: readonly AnalysisMessage[],
  initialParts: AnalysisMessage['parts'] = [],
): ConversationTurn[] {
  const initialMessage: AnalysisMessage = initialParts.length
    ? { role: 'user', content: initialPrompt, parts: initialParts }
    : { role: 'user', content: initialPrompt }
  const stream: AnalysisMessage[] = initialPrompt.trim() || initialParts.length
    ? [initialMessage, ...messages]
    : [...messages]
  const turns: ConversationTurn[] = []

  for (const message of stream) {
    if (message.role === 'user') {
      turns.push({ id: `turn-${turns.length}`, prompt: message, responses: [] })
      continue
    }
    const current = turns.at(-1)
    if (current) {
      current.responses.push(message)
      current.response = message
    }
  }
  return turns
}

/** Keep only a terminal text segment visible and place every earlier event in execution details. */
export function splitTurnTimeline(timeline: readonly AgentTimelineEntry[]): TurnTimelineSections {
  const finalIndex = timeline.length - 1
  const finalEntry = timeline[finalIndex]
  if (finalEntry?.type !== 'message') return { execution: [...timeline], answer: [] }
  return {
    execution: timeline.slice(0, finalIndex),
    answer: [finalEntry],
  }
}

/** Format a live or persisted millisecond duration without noisy precision. */
export function formatTurnDuration(milliseconds: number): string {
  const seconds = Math.max(0, Math.floor(milliseconds / 1000))
  if (seconds < 60) return `${seconds}s`
  const minutes = Math.floor(seconds / 60)
  const remainingSeconds = seconds % 60
  return remainingSeconds ? `${minutes}m ${remainingSeconds}s` : `${minutes}m`
}

/** Keep a prompt readable in a one-line turn summary. */
export function summarizeTurnPrompt(content: string, limit = 88): string {
  const normalized = content.replace(/\s+/g, ' ').trim()
  if (normalized.length <= limit) return normalized
  return `${normalized.slice(0, Math.max(0, limit - 1)).trimEnd()}…`
}
