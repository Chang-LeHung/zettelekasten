import type { AnalysisMessage } from '../api/types'

export interface ConversationTurn {
  id: string
  prompt: AnalysisMessage
  response?: AnalysisMessage
}

/** Group a flat persisted message stream into user-initiated turns. */
export function buildConversationTurns(
  initialPrompt: string,
  messages: readonly AnalysisMessage[],
): ConversationTurn[] {
  const stream: AnalysisMessage[] = initialPrompt.trim()
    ? [{ role: 'user', content: initialPrompt }, ...messages]
    : [...messages]
  const turns: ConversationTurn[] = []

  for (const message of stream) {
    if (message.role === 'user') {
      turns.push({ id: `turn-${turns.length}`, prompt: message })
      continue
    }
    const current = turns.at(-1)
    if (current) current.response = message
  }
  return turns
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
