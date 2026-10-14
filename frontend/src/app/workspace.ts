import { nextTick } from 'vue'
import { aiClient, libraryClient, settingsClient, tagClient, updateClient } from '../api/client'
import type { AgentSession, LibraryItem } from '../api/types'
import { latestAgentUsage } from '../utils/agentUsage'
import { restorePersistedConversation } from '../utils/persistedConversation'
import { applyArtifacts } from './artifacts/actions'
import { artifactContent, artifactDiff, artifactPreview, artifacts, selectedArtifactId, selectedSuggestions, workspaceRestoring } from './artifacts/state'
import { assets, previewAsset } from './assets'
import { clearSlashCommand } from './composer/actions'
import { atCommands, atCommandsLoaded, followUp, initialMessageParts, pendingMessageImages, raw, slashCommands, slashCommandsLoaded } from './composer/state'
import { contextComposition, conversation, conversationScratch, conversationStarted, currentContextUsage, loading, pendingShellApprovals, shellApprovalSubmittingIds, streamingStatus, turnDetails } from './conversation/state'
import { resetStreamState, scrollAgentThread } from './conversation/stream'
import { clearTraceHash, selectedTraceTurnId, traceError, traceLoading, traceLocationFromHash, traceMessages, workspaceView } from './conversation/trace'
import { isEditableTarget } from './format'
import { clearLibrarySelection, closeSlidesFullscreen, loadLibrary, openSearch, selectAllLibraryItems } from './library/actions'
import { LIBRARY_PAGE_SIZE, activeQuery, collectionTags, collectionTarget, fullscreenSlidesItem, libraryEditorItem, libraryHasMore, libraryItems, libraryPdfLaunch, libraryTotal, query, selectedLibraryIds, selectedLibraryItem, selectedTag } from './library/state'
import { view } from './nav'
import { confirmation, errorMessage, notice, requestConfirmation, showNotice } from './notice'
import { providers, selectProvider, selectedProviderId, shellApprovalMode } from './providers'
import { activeSessionKey, cancelSessionTitleEdit, channelSessions, conversationId, editingSessionId, loadChannelSessions, loadScheduledSessions, loadSessions, scheduledSessions, sessionDetailRequests, sessionScope, sessions, sessionsScratch, switchingSessionId } from './sessions'
import { closeSettings, modelUsageActivity, runtimeSettings, settingsDialog, settingsOpen, settingsScratch, settingsSection, usageActivity, usageActivityLoading } from './settings'
import type { View } from './types'
import { updateStatus } from './updates'

async function loadInitialData(): Promise<void> {
  usageActivityLoading.value = true
  try {
    const [
      tagData,
      libraryPage,
      libraryCount,
      providerData,
      runtimeSettingsData,
      usageActivityData,
      modelUsageActivityData,
    ] = await Promise.all([
      tagClient.list(collectionTarget.value),
      libraryClient.list({ limit: LIBRARY_PAGE_SIZE + 1 }),
      libraryClient.count(),
      aiClient.listProviders(),
      settingsClient.get(),
      settingsClient.getUsageActivity().catch(() => []),
      settingsClient.getModelUsageActivity(30).catch(() => []),
    ])
    collectionTags.value = tagData
    libraryHasMore.value = libraryPage.length > LIBRARY_PAGE_SIZE
    libraryItems.value = libraryHasMore.value ? libraryPage.slice(0, LIBRARY_PAGE_SIZE) : libraryPage
    libraryTotal.value = libraryCount
    providers.value = providerData
    runtimeSettings.value = runtimeSettingsData
    settingsScratch.persistedRuntimeSettings = { ...runtimeSettingsData }
    usageActivity.value = usageActivityData
    modelUsageActivity.value = modelUsageActivityData
    // The update check may wait on PyPI for seconds. It must never hold up the
    // library, nor land late enough to overwrite what the user has since changed.
    void updateClient.get().then((status) => { updateStatus.value = status }).catch(() => {})
    const firstProvider = providerData.find((provider) => provider.enabled)
    if (firstProvider) {
      selectedProviderId.value = firstProvider.id
      await selectProvider(firstProvider)
    }
  } catch (error) {
    showNotice(errorMessage(error), 'error')
  } finally {
    usageActivityLoading.value = false
  }
}
export function navigate(nextView: View): void {
  if (nextView === 'settings') {
    settingsOpen.value = true
    settingsSection.value = 'usage'
    void nextTick(() => settingsDialog.value?.focus())
    return
  }
  settingsOpen.value = false
  view.value = nextView
  notice.value = ''
  if (nextView !== 'new') clearTraceHash()
  if (nextView === 'new') {
    sessionScope.value = 'normal'
    if (conversationStarted.value) scrollAgentThread(true)
  } else if (nextView === 'scheduledTasks') {
    sessionScope.value = 'scheduled'
    void loadScheduledSessions(true)
  } else if (nextView === 'channels') {
    // Channel chats stay out of the user's own conversation list, so this view
    // is the only place they can be reopened.
    sessionScope.value = 'channel'
    void loadChannelSessions(true)
  }
  if (nextView === 'library') {
    activeQuery.value = ''
    query.value = ''
    selectedTag.value = null
    void loadLibrary()
  }
}
export function handleShortcut(event: KeyboardEvent): void {
  if (event.key === 'Escape' && settingsOpen.value) {
    event.preventDefault()
    closeSettings()
    return
  }
  if (event.key === 'Escape' && fullscreenSlidesItem.value) {
    void closeSlidesFullscreen()
    return
  }
  if (event.key === 'Escape' && libraryEditorItem.value) return
  if (event.key === 'Escape' && selectedLibraryItem.value) {
    selectedLibraryItem.value = null
    return
  }
  if (event.key === 'Escape' && selectedLibraryIds.value.size && !confirmation.value.open) {
    clearLibrarySelection()
    return
  }
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'a' && view.value === 'library' && !isEditableTarget(event.target)) {
    event.preventDefault()
    selectAllLibraryItems()
    return
  }
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
    event.preventDefault()
    openSearch()
  }
}
export function applySession(session: AgentSession): void {
  conversationId.value = session.id
  turnDetails.clear()
  const traceLocation = traceLocationFromHash()
  const restoreTrace = traceLocation?.sessionId === session.id
  if (!restoreTrace) clearTraceHash()
  workspaceView.value = restoreTrace ? 'trace' : 'workspace'
  selectedTraceTurnId.value = restoreTrace ? traceLocation.turnId : null
  window.localStorage.setItem(activeSessionKey, session.id)
  applyArtifacts(session.artifacts, false)
  assets.value = session.assets
  const restored = restorePersistedConversation(session.messages)
  raw.value = restored.initialPrompt
  initialMessageParts.value = restored.initialParts
  pendingMessageImages.value = []
  slashCommands.value = []
  slashCommandsLoaded.value = false
  atCommands.value = []
  atCommandsLoaded.value = false
  clearSlashCommand()
  conversation.value = restored.messages
  traceMessages.value = session.messages
  traceError.value = ''
  traceLoading.value = false
  currentContextUsage.value = latestAgentUsage(restored.messages)
  contextComposition.value = null
  shellApprovalMode.value = 'review'
  pendingShellApprovals.value = []
  shellApprovalSubmittingIds.value = []
  followUp.value = ''
  conversationScratch.followAgentOutput = true
  void nextTick(() => scrollAgentThread(true))
}
async function restoreSessionModel(sessionId: string): Promise<void> {
  const fallback = providers.value.find((provider) => provider.enabled) || null
  try {
    const preference = await aiClient.getAgentSessionModel(sessionId)
    const selected = providers.value.find(
      (provider) => provider.enabled && provider.id === preference?.provider_id,
    ) || fallback
    selectedProviderId.value = selected?.id ?? null
  } catch {
    selectedProviderId.value = fallback?.id ?? null
  }
}
export async function restoreSessionContextComposition(sessionId: string): Promise<void> {
  try {
    const composition = await aiClient.getAgentSessionContextComposition(sessionId)
    if (conversationId.value === sessionId) contextComposition.value = composition
  } catch {
    if (conversationId.value === sessionId) contextComposition.value = null
  }
}
async function restoreSessionShellApproval(sessionId: string): Promise<void> {
  try {
    const settings = await aiClient.getAgentSessionShellApproval(sessionId)
    if (conversationId.value === sessionId) shellApprovalMode.value = settings.mode
  } catch {
    if (conversationId.value === sessionId) shellApprovalMode.value = 'review'
  }
}
export async function restoreSessionRuntime(sessionId: string): Promise<void> {
  await Promise.all([
    restoreSessionModel(sessionId),
    restoreSessionContextComposition(sessionId),
    restoreSessionShellApproval(sessionId),
  ])
}
function loadSessionDetail(sessionId: string): Promise<AgentSession> {
  const existing = sessionDetailRequests.get(sessionId)
  if (existing) return existing
  const request = aiClient.getAgentSession(sessionId)
  sessionDetailRequests.set(sessionId, request)
  void request.finally(() => {
    if (sessionDetailRequests.get(sessionId) === request) sessionDetailRequests.delete(sessionId)
  }).catch(() => undefined)
  return request
}
export function prefetchSession(sessionId: string): void {
  if (sessionId === conversationId.value || loading.value || sessionDetailRequests.has(sessionId)) return
  void loadSessionDetail(sessionId).catch(() => undefined)
}
export async function openSession(sessionId: string): Promise<void> {
  if (sessionId === conversationId.value) {
    selectedLibraryItem.value = null
    view.value = 'new'
    await nextTick()
    scrollAgentThread(true)
    return
  }
  if (loading.value) {
    // Silently ignoring the click looks like a broken conversation list.
    showNotice('Stop the running turn before switching conversations', 'error')
    return
  }
  const generation = ++sessionsScratch.sessionSwitchGeneration
  switchingSessionId.value = sessionId
  view.value = 'new'
  try {
    const session = await loadSessionDetail(sessionId)
    if (generation !== sessionsScratch.sessionSwitchGeneration) return
    applySession(session)
    const targetSessions = (
      sessionScope.value === 'scheduled' ? scheduledSessions
      : sessionScope.value === 'channel' ? channelSessions
      : sessions
    )
    if (!targetSessions.value.some((item) => item.id === session.id)) {
      targetSessions.value = [session, ...targetSessions.value]
    }
    switchingSessionId.value = null
    await restoreSessionRuntime(session.id)
  } catch (error) {
    if (generation === sessionsScratch.sessionSwitchGeneration) showNotice(errorMessage(error), 'error')
  } finally {
    if (generation === sessionsScratch.sessionSwitchGeneration) switchingSessionId.value = null
  }
}
export async function openScheduledSession(sessionId: string): Promise<void> {
  sessionScope.value = 'scheduled'
  await openSession(sessionId)
}
async function openChannelSession(sessionId: string): Promise<void> {
  sessionScope.value = 'channel'
  await openSession(sessionId)
}
export async function openArtifactSession(item: LibraryItem): Promise<void> {
  selectedLibraryItem.value = null
  libraryPdfLaunch.value = null
  await openSession(item.session_id)
}
export async function deleteSession(session: AgentSession): Promise<void> {
  const title = session.title || '新会话'
  const confirmed = await requestConfirmation(
    'Delete this conversation?',
    `“${title}” and all of its messages, draft artifacts, and session assets will be permanently removed.`,
    'Delete conversation',
  )
  if (!confirmed) return
  try {
    await aiClient.deleteAgentSession(session.id)
    sessions.value = sessions.value.filter((item) => item.id !== session.id)
    scheduledSessions.value = scheduledSessions.value.filter((item) => item.id !== session.id)
    channelSessions.value = channelSessions.value.filter((item) => item.id !== session.id)
    if (editingSessionId.value === session.id) cancelSessionTitleEdit()
    if (conversationId.value === session.id) {
      clearWorkspaceState()
      if (sessionScope.value === 'scheduled') await loadScheduledSessions(true)
      else if (sessionScope.value === 'channel') await loadChannelSessions(true)
      else await loadSessions(true)
    }
    showNotice('Conversation deleted')
  } catch (error) {
    showNotice(errorMessage(error), 'error')
  }
}
function clearWorkspaceState(): void {
  sessionsScratch.sessionSwitchGeneration += 1
  turnDetails.clear()
  switchingSessionId.value = null
  sessionDetailRequests.clear()
  raw.value = ''
  artifactContent.value = null
  conversation.value = []
  followUp.value = ''
  initialMessageParts.value = []
  pendingMessageImages.value = []
  slashCommands.value = []
  slashCommandsLoaded.value = false
  atCommands.value = []
  atCommandsLoaded.value = false
  clearSlashCommand()
  selectedSuggestions.value = []
  artifacts.value = []
  assets.value = []
  previewAsset.value = null
  selectedArtifactId.value = null
  artifactPreview.value = true
  artifactDiff.value = false
  conversationId.value = null
  workspaceView.value = 'workspace'
  traceMessages.value = []
  selectedTraceTurnId.value = null
  traceError.value = ''
  traceLoading.value = false
  clearTraceHash()
  currentContextUsage.value = null
  contextComposition.value = null
  shellApprovalMode.value = 'review'
  resetStreamState()
  streamingStatus.value = 'idle'
  window.localStorage.removeItem(activeSessionKey)
}
export async function resetWorkspace(): Promise<void> {
  clearWorkspaceState()
  try {
    const started = await aiClient.startAgent()
    conversationId.value = started.conversation_id
    window.localStorage.setItem(activeSessionKey, started.conversation_id)
    applyArtifacts(started.artifacts)
    assets.value = started.assets
    await loadSessions(true)
  } catch (error) {
    showNotice(errorMessage(error), 'error')
  }
}
export async function initializeWorkspace(): Promise<void> {
  const persistedId = window.localStorage.getItem(activeSessionKey)
  workspaceRestoring.value = Boolean(persistedId)
  try {
    await loadInitialData()
    if (persistedId) {
      try {
        const session = await aiClient.getAgentSession(persistedId)
        applySession(session)
        await restoreSessionRuntime(session.id)
      } catch {
        window.localStorage.removeItem(activeSessionKey)
      }
    }
  } finally {
    // Without this hold the panes render their empty state first and flip to real
    // content once the conversation arrives, which reads as a flash on reload.
    workspaceRestoring.value = false
  }
  await loadSessions(true)
}
