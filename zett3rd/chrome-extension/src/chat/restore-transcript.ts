import type { AgentPersistedMessage, AgentModelUsage } from '../../../../frontend/src/api/types'
import { buildConversationTurns } from '../../../../frontend/src/utils/conversationTurns'
import { restorePersistedConversation } from '../../../../frontend/src/utils/persistedConversation'
import { addAgentUsage } from '../../../../frontend/src/utils/agentUsage'
import type { TranscriptEntry } from '../api/types'
import { settleTimeline } from './timeline'

/** A fallback page excerpt precedes a clearly delimited, user-authored prompt.
 * Browser-connected turns contain only the prompt and need no stripping.
 */
export const PAGE_PROMPT_MARKER = '\n\nUser request:\n'

export function visiblePrompt(content: string): string {
  const marker = content.lastIndexOf(PAGE_PROMPT_MARKER)
  return marker >= 0 ? content.slice(marker + PAGE_PROMPT_MARKER.length) : content
}

/** Recover Zett's persisted timeline so closing a webpage iframe does not
 * erase what that page's Agent already said or which tools it used.
 */
export function restoreTranscript(records: readonly AgentPersistedMessage[]): TranscriptEntry[] {
  const { initialPrompt, messages } = restorePersistedConversation(records)
  const turns = buildConversationTurns(initialPrompt, messages)
  const entries: TranscriptEntry[] = []
  for (const turn of turns) {
    entries.push({ id: entries.length + 1, role: 'user', text: visiblePrompt(turn.prompt.content) })
    let usage: AgentModelUsage | null = null
    for (const response of turn.responses) {
      if (response.usage) usage = addAgentUsage(usage, response.usage)
    }
    entries.push({
      id: entries.length + 1,
      role: 'assistant',
      text: '',
      timeline: settleTimeline(turn.responses.flatMap(response => response.timeline ?? [])),
      usage: usage ?? undefined,
      durationMs: turn.responses.reduce((sum, response) => sum + (response.duration_ms ?? 0), 0),
      generationDurationMs: turn.responses.reduce((sum, response) => sum + (response.generation_duration_ms ?? 0), 0),
    })
  }
  return entries
}
