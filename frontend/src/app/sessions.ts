import { computed, nextTick, ref } from 'vue'
import { aiClient } from '../api/client'
import type { AgentSession } from '../api/types'
import { DEFAULT_SESSION_TITLE } from './format'
import { errorMessage, showNotice } from './notice'
import type { SessionScope } from './types'

export const conversationId = ref<string | null>(null)
export const editingSessionId = ref<string | null>(null)
export const sessionTitleDraft = ref('')
export const sessions = ref<AgentSession[]>([])
export const scheduledSessions = ref<AgentSession[]>([])
export const channelSessions = ref<AgentSession[]>([])
export const sessionListRef = ref<HTMLElement | null>(null)
export const sessionScope = ref<SessionScope>('normal')
const sessionsLoading = ref(false)
const scheduledSessionsLoading = ref(false)
const channelSessionsLoading = ref(false)
//: Scopes whose first list request has settled; until then the sidebar is loading,
//: not empty, so a startup or scope switch never flashes the empty state.
const loadedSessionScopes = ref<Set<SessionScope>>(new Set())
export const switchingSessionId = ref<string | null>(null)
export const sessionDetailRequests = new Map<string, Promise<AgentSession>>()
const sessionsHaveMore = ref(true)
const scheduledSessionsHaveMore = ref(true)
const channelSessionsHaveMore = ref(true)
const sessionPageSize = 20
let titleRefreshTimer: number | null = null
export const sessionsScratch = {
  sessionSwitchGeneration: 0,
}
export const activeSessionKey = 'zett.active-session-id'
const activeSessions = computed(() => (
  sessionScope.value === 'scheduled' ? scheduledSessions.value
  : sessionScope.value === 'channel' ? channelSessions.value
  : sessions.value
))
export const activeSessionsLoading = computed(() => (
  sessionScope.value === 'scheduled' ? scheduledSessionsLoading.value
  : sessionScope.value === 'channel' ? channelSessionsLoading.value
  : sessionsLoading.value
))
const activeSessionsHaveMore = computed(() => (
  sessionScope.value === 'scheduled' ? scheduledSessionsHaveMore.value
  : sessionScope.value === 'channel' ? channelSessionsHaveMore.value
  : sessionsHaveMore.value
))
export const activeSessionsPending = computed(() => (
  activeSessionsLoading.value || !loadedSessionScopes.value.has(sessionScope.value)
))
export const visibleSessions = computed(() => activeSessions.value.filter((session) => (
  session.message_count > 0
  || session.id === conversationId.value
)))
export function clearSessionTitleRefresh(): void {
  if (titleRefreshTimer !== null) window.clearTimeout(titleRefreshTimer)
  titleRefreshTimer = null
}
async function refreshSessionTitleUntilResolved(sessionId: string, deadline: number): Promise<void> {
  if (conversationId.value !== sessionId) return
  await loadSessions(true)
  const session = sessions.value.find((candidate) => candidate.id === sessionId)
  if (session?.title && session.title !== DEFAULT_SESSION_TITLE) return
  if (Date.now() >= deadline) return
  titleRefreshTimer = window.setTimeout(
    () => void refreshSessionTitleUntilResolved(sessionId, deadline),
    1_000,
  )
}
export function scheduleSessionTitleRefresh(sessionId: string): void {
  clearSessionTitleRefresh()
  const deadline = Date.now() + 30_000
  titleRefreshTimer = window.setTimeout(
    () => void refreshSessionTitleUntilResolved(sessionId, deadline),
    800,
  )
}
export function startSessionTitleEdit(session: AgentSession): void {
  editingSessionId.value = session.id
  sessionTitleDraft.value = session.title || '新会话'
}
export function cancelSessionTitleEdit(): void {
  editingSessionId.value = null
  sessionTitleDraft.value = ''
}
export function handleSessionTitleFocusOut(event: FocusEvent): void {
  const editor = event.currentTarget
  const nextTarget = event.relatedTarget
  if (!(editor instanceof HTMLFormElement)) return
  if (nextTarget instanceof Node && editor.contains(nextTarget)) return
  cancelSessionTitleEdit()
}
export async function saveSessionTitle(sessionId: string): Promise<void> {
  const title = sessionTitleDraft.value.trim()
  if (!title) return
  try {
    const updated = await aiClient.updateAgentSessionTitle(sessionId, title)
    sessions.value = sessions.value.map((session) => session.id === updated.id ? updated : session)
    scheduledSessions.value = scheduledSessions.value.map((session) => session.id === updated.id ? updated : session)
    cancelSessionTitleEdit()
  } catch (error) {
    showNotice(errorMessage(error), 'error')
  }
}
export async function loadSessions(reset = false): Promise<void> {
  if (sessionsLoading.value) return
  sessionsLoading.value = true
  try {
    const offset = reset ? 0 : sessions.value.length
    const nextSessions = await aiClient.listAgentSessions(sessionPageSize, offset)
    sessions.value = reset ? nextSessions : [...sessions.value, ...nextSessions]
    sessionsHaveMore.value = nextSessions.length === sessionPageSize
  } catch (error) {
    showNotice(errorMessage(error), 'error')
  } finally {
    sessionsLoading.value = false
    markSessionScopeLoaded('normal')
    if (sessionScope.value === 'normal') void fillSessionList()
  }
}
export async function loadScheduledSessions(reset = false): Promise<void> {
  if (scheduledSessionsLoading.value) return
  scheduledSessionsLoading.value = true
  try {
    const offset = reset ? 0 : scheduledSessions.value.length
    const nextSessions = await aiClient.listAgentSessions(sessionPageSize, offset, ['scheduled'])
    scheduledSessions.value = reset ? nextSessions : [...scheduledSessions.value, ...nextSessions]
    scheduledSessionsHaveMore.value = nextSessions.length === sessionPageSize
  } catch (error) {
    showNotice(errorMessage(error), 'error')
  } finally {
    scheduledSessionsLoading.value = false
    markSessionScopeLoaded('scheduled')
    if (sessionScope.value === 'scheduled') void fillSessionList()
  }
}
export async function loadChannelSessions(reset = false): Promise<void> {
  if (channelSessionsLoading.value) return
  channelSessionsLoading.value = true
  try {
    const offset = reset ? 0 : channelSessions.value.length
    const nextSessions = await aiClient.listAgentSessions(sessionPageSize, offset, ['channel'])
    channelSessions.value = reset ? nextSessions : [...channelSessions.value, ...nextSessions]
    channelSessionsHaveMore.value = nextSessions.length === sessionPageSize
  } catch (error) {
    showNotice(errorMessage(error), 'error')
  } finally {
    channelSessionsLoading.value = false
    markSessionScopeLoaded('channel')
    if (sessionScope.value === 'channel') void fillSessionList()
  }
}
function markSessionScopeLoaded(scope: SessionScope): void {
  if (loadedSessionScopes.value.has(scope)) return
  const next = new Set(loadedSessionScopes.value)
  next.add(scope)
  loadedSessionScopes.value = next
}
function loadMoreSessions(): void {
  if (sessionScope.value === 'scheduled') void loadScheduledSessions()
  else if (sessionScope.value === 'channel') void loadChannelSessions()
  else void loadSessions()
}
/** How close to the list's end a scroll must come before the next page loads. */
const SESSION_LIST_LOAD_REMAINING_PX = 96
export function handleSessionListScroll(): void {
  const element = sessionListRef.value
  if (!element || !activeSessionsHaveMore.value || activeSessionsLoading.value) return
  const remaining = element.scrollHeight - element.scrollTop - element.clientHeight
  if (remaining <= SESSION_LIST_LOAD_REMAINING_PX) loadMoreSessions()
}
/** Fill a list that is too short to scroll, where scrolling cannot reach another page. */
async function fillSessionList(): Promise<void> {
  await nextTick()
  const element = sessionListRef.value
  if (!element || !activeSessionsHaveMore.value || activeSessionsLoading.value) return
  if (element.scrollHeight <= element.clientHeight) loadMoreSessions()
}
