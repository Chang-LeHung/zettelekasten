import { ref } from 'vue'
import { aiClient } from '../../api/client'
import type { AgentPersistedMessage } from '../../api/types'
import { errorMessage } from '../notice'
import { conversationId } from '../sessions'

const initialTraceLocation = traceLocationFromHash()
export const workspaceView = ref<'workspace' | 'trace'>(initialTraceLocation ? 'trace' : 'workspace')
export const selectedTraceTurnId = ref<string | null>(initialTraceLocation?.turnId || null)
export const traceMessages = ref<AgentPersistedMessage[]>([])
export const traceLoading = ref(false)
export const traceError = ref('')
export function traceLocationFromHash(): { sessionId: string; turnId: string | null } | null {
  const prefix = '#trace/'
  if (!window.location.hash.startsWith(prefix)) return null
  const parts = window.location.hash.slice(prefix.length).split('/')
  if ((parts.length !== 1 && parts.length !== 2) || !parts[0]) return null
  return {
    sessionId: decodeURIComponent(parts[0]),
    turnId: parts[1] ? decodeURIComponent(parts[1]) : null,
  }
}
function replaceTraceHash(turnId: string | null = selectedTraceTurnId.value): void {
  const sessionId = conversationId.value
  const hash = sessionId
    ? `#trace/${encodeURIComponent(sessionId)}${turnId ? `/${encodeURIComponent(turnId)}` : ''}`
    : '#trace'
  window.history.replaceState(null, '', `${window.location.pathname}${window.location.search}${hash}`)
}
export function clearTraceHash(): void {
  if (!window.location.hash.startsWith('#trace')) return
  window.history.replaceState(null, '', `${window.location.pathname}${window.location.search}`)
}
export function updateTraceTurn(turnId: string): void {
  selectedTraceTurnId.value = turnId
  if (workspaceView.value === 'trace') replaceTraceHash(turnId)
}
export function setWorkspaceView(next: 'workspace' | 'trace'): void {
  workspaceView.value = next
  if (next === 'trace') {
    const hash = traceLocationFromHash()
    if (hash?.sessionId === conversationId.value) selectedTraceTurnId.value = hash.turnId
    replaceTraceHash()
    void loadInteractionTrace()
  } else {
    clearTraceHash()
  }
}
export async function loadInteractionTrace(sessionId = conversationId.value): Promise<void> {
  if (!sessionId) {
    traceMessages.value = []
    traceError.value = ''
    traceLoading.value = false
    return
  }
  traceLoading.value = true
  traceError.value = ''
  try {
    const messages = await aiClient.getAgentSessionMessages(sessionId)
    if (conversationId.value === sessionId) traceMessages.value = messages
  } catch (error) {
    if (conversationId.value === sessionId) traceError.value = errorMessage(error)
  } finally {
    if (conversationId.value === sessionId) traceLoading.value = false
  }
}
