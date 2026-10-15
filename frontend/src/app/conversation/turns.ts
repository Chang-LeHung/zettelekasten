import { aiClient } from '../../api/client'
import type { AnalysisMessage } from '../../api/types'
import { buildMessageParts } from '../../utils/messageParts'
import { applyArtifacts, refreshArtifactsAfterTurn, syncSelectedArtifactDraft } from '../artifacts/actions'
import { assets } from '../assets'
import { atCommandIdFor, clearSlashCommand, deleteReferenceToken, deleteSelectedSlashCommand, selectAtCommand, selectSlashCommand, slashCommandIdFor } from '../composer/actions'
import { atCommands, atCommandsLoaded, atCommandsLoading, atMenu, atMenuActiveIndex, atMenuCommands, followUp, initialMessageParts, pendingMessageImages, raw, slashCommands, slashCommandsLoaded, slashCommandsLoading, slashMenu, slashMenuActiveIndex, slashMenuCommands } from '../composer/state'
import { isAbortError } from '../format'
import { errorMessage, showNotice } from '../notice'
import { reasoningEffort, selectedProviderId, shellApprovalMode } from '../providers'
import { activeSessionKey, conversationId, loadSessions, scheduleSessionTitleRefresh } from '../sessions'
import { settingsSection } from '../settings'
import type { ComposerTarget, QueuedFollowUp } from '../types'
import { applySession, navigate, restoreSessionContextComposition, restoreSessionRuntime } from '../workspace'
import { commitStreamedResponse, streamCallbacks } from './callbacks'
import { queueFollowUp } from './queue'
import { activeStreamController, activeTodos, conversation, conversationScratch, conversationStarted, loading, pendingQuestion, pendingShellApprovals, pendingSteeringEchoes, queuedFollowUps, queuedQuestions, shellApprovalSubmittingIds, streamingStatus } from './state'
import { hasStreamedResponse, resetStreamState, startTurnClock, stopTurnClock } from './stream'
import { loadInteractionTrace, workspaceView } from './trace'

async function analyze(): Promise<void> {
  if (!raw.value.trim() && !pendingMessageImages.value.length) return
  if (selectedProviderId.value === null) {
    showNotice('Add and select an AI provider first', 'error')
    navigate('settings')
    settingsSection.value = 'providers'
    return
  }
  loading.value = true
  const controller = new AbortController()
  activeStreamController.value = controller
  resetStreamState()
  startTurnClock()
  const messageText = raw.value
  const slashCommandId = slashCommandIdFor(messageText)
  const atCommandId = atCommandIdFor(messageText)
  const requestParts = buildMessageParts(messageText, pendingMessageImages.value)
  initialMessageParts.value = requestParts
  pendingMessageImages.value = []
  clearSlashCommand()
  const requestHistory: AnalysisMessage[] = []
  conversationScratch.activeTurnHistory = requestHistory
  const callbacks = streamCallbacks()
  let activeConversationId: string | null = null
  try {
    activeConversationId = await ensureConversation()
    // A slash command owns the turn; a bare `@` reference runs through the
    // at-command stream, which injects that resource before the Agent runs.
    const result = slashCommandId
      ? await aiClient.slashCommandStream(
          activeConversationId,
          slashCommandId,
          messageText,
          selectedProviderId.value,
          reasoningEffort.value,
          [],
          callbacks,
          controller.signal,
          requestParts,
          shellApprovalMode.value,
        )
      : atCommandId
        ? await aiClient.atCommandStream(
            activeConversationId,
            atCommandId,
            messageText,
            selectedProviderId.value,
            reasoningEffort.value,
            [],
            callbacks,
            controller.signal,
            requestParts,
            shellApprovalMode.value,
          )
      : await aiClient.analyzeStream(
          activeConversationId,
          messageText,
          selectedProviderId.value,
          reasoningEffort.value,
          [],
          callbacks,
          controller.signal,
          requestParts,
          shellApprovalMode.value,
        )
    commitStreamedResponse(requestHistory, {
      fallbackContent: result ? 'The artifact is ready.' : 'How would you like to continue?',
    })
    await restoreSessionContextComposition(activeConversationId)
    await loadSessions(true)
    scheduleSessionTitleRefresh(activeConversationId)
  } catch (error) {
    if (controller.signal.aborted || isAbortError(error)) {
      if (hasStreamedResponse()) commitStreamedResponse(requestHistory)
      streamingStatus.value = 'cancelled'
      await loadSessions(true)
    } else {
      commitStreamedResponse(requestHistory, { error: errorMessage(error) })
    }
  } finally {
    stopTurnClock()
    if (activeStreamController.value === controller) activeStreamController.value = null
    loading.value = false
    if (conversationScratch.activeTurnHistory === requestHistory) conversationScratch.activeTurnHistory = null
    pendingSteeringEchoes.length = 0
    if (streamingStatus.value !== 'cancelled') streamingStatus.value = 'idle'
    await refreshArtifactsAfterTurn(activeConversationId)
    if (workspaceView.value === 'trace' && activeConversationId) void loadInteractionTrace(activeConversationId)
    drainQueuedFollowUps()
  }
}
export async function refine(queued?: QueuedFollowUp): Promise<void> {
  const content = queued?.content ?? followUp.value
  if (!content.trim() && !(queued?.parts.length || pendingMessageImages.value.length)) return
  if (selectedProviderId.value === null) {
    showNotice('Select an AI provider first', 'error')
    return
  }
  const requestParts = queued?.parts ?? buildMessageParts(content, pendingMessageImages.value)
  const slashCommandId = queued?.slashCommandId ?? slashCommandIdFor(content)
  const atCommandId = queued?.atCommandId ?? atCommandIdFor(content)
  const history: AnalysisMessage[] = [...conversation.value, { role: 'user', content, parts: requestParts }]
  conversation.value = history
  if (!queued) {
    followUp.value = ''
    pendingMessageImages.value = []
    clearSlashCommand()
  }
  loading.value = true
  const controller = new AbortController()
  activeStreamController.value = controller
  resetStreamState()
  startTurnClock()
  conversationScratch.activeTurnHistory = history
  const callbacks = streamCallbacks()
  let activeConversationId: string | null = null
  try {
    activeConversationId = await ensureConversation()
    await syncSelectedArtifactDraft()
    const result = slashCommandId
      ? await aiClient.slashCommandStream(
          activeConversationId,
          slashCommandId,
          content,
          selectedProviderId.value,
          reasoningEffort.value,
          history,
          callbacks,
          controller.signal,
          requestParts,
          queued?.shellApprovalMode ?? shellApprovalMode.value,
        )
      : atCommandId
        ? await aiClient.atCommandStream(
            activeConversationId,
            atCommandId,
            content,
            selectedProviderId.value,
            reasoningEffort.value,
            history,
            callbacks,
            controller.signal,
            requestParts,
            queued?.shellApprovalMode ?? shellApprovalMode.value,
          )
      : await aiClient.analyzeStream(
          activeConversationId,
          content,
          selectedProviderId.value,
          reasoningEffort.value,
          history,
          callbacks,
          controller.signal,
          requestParts,
          queued?.shellApprovalMode ?? shellApprovalMode.value,
        )
    commitStreamedResponse(history, {
      fallbackContent: result ? 'The artifact is ready.' : 'How would you like to continue?',
    })
    await restoreSessionContextComposition(activeConversationId)
    await loadSessions(true)
    scheduleSessionTitleRefresh(activeConversationId)
  } catch (error) {
    if (controller.signal.aborted || isAbortError(error)) {
      if (hasStreamedResponse()) commitStreamedResponse(history)
      streamingStatus.value = 'cancelled'
      await loadSessions(true)
    } else {
      commitStreamedResponse(history, { error: errorMessage(error) })
    }
  } finally {
    stopTurnClock()
    if (activeStreamController.value === controller) activeStreamController.value = null
    loading.value = false
    if (conversationScratch.activeTurnHistory === history) conversationScratch.activeTurnHistory = null
    pendingSteeringEchoes.length = 0
    if (streamingStatus.value !== 'cancelled') streamingStatus.value = 'idle'
    await refreshArtifactsAfterTurn(activeConversationId)
    if (workspaceView.value === 'trace' && activeConversationId) void loadInteractionTrace(activeConversationId)
    drainQueuedFollowUps()
  }
}
function drainQueuedFollowUps(): void {
  if (loading.value || !queuedFollowUps.value.length) return
  const [next, ...remaining] = queuedFollowUps.value
  queuedFollowUps.value = remaining
  if (next) void refine(next)
}
export function submitConversation(): void {
  if (loading.value) {
    queueFollowUp()
    return
  }
  if (conversationStarted.value) void refine()
  else void analyze()
}
export function stopGeneration(): void {
  pendingQuestion.value = null
  pendingShellApprovals.value = []
  shellApprovalSubmittingIds.value = []
  queuedQuestions.value = []
  queuedFollowUps.value = []
  activeTodos.value = null
  activeStreamController.value?.abort()
}
export async function ensureConversation(): Promise<string> {
  if (conversationId.value) return conversationId.value
  const persistedId = window.localStorage.getItem(activeSessionKey)
  if (persistedId) {
    try {
      const persisted = await aiClient.getAgentSession(persistedId)
      applySession(persisted)
      await restoreSessionRuntime(persisted.id)
      return persisted.id
    } catch {
      window.localStorage.removeItem(activeSessionKey)
    }
  }
  const started = await aiClient.startAgent()
  conversationId.value = started.conversation_id
  window.localStorage.setItem(activeSessionKey, started.conversation_id)
  applyArtifacts(started.artifacts)
  assets.value = started.assets
  slashCommands.value = []
  slashCommandsLoaded.value = false
  atCommands.value = []
  atCommandsLoaded.value = false
  clearSlashCommand()
  return started.conversation_id
}
export function handleComposerKeydown(event: KeyboardEvent, target: ComposerTarget): void {
  if (event.isComposing) return
  if (deleteSelectedSlashCommand(event, target)) return
  if (deleteReferenceToken(event, target)) return
  const menu = slashMenu.value
  if (menu?.target === target) {
    if (slashCommandsLoading.value && (event.key === 'Enter' || event.key === 'Tab')) {
      event.preventDefault()
      return
    }
  }
  const references = atMenu.value
  if (references?.target === target) {
    if (atCommandsLoading.value && (event.key === 'Enter' || event.key === 'Tab')) {
      event.preventDefault()
      return
    }
  }
  if (menu?.target === target && slashMenuCommands.value.length) {
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault()
      const delta = event.key === 'ArrowDown' ? 1 : -1
      const count = slashMenuCommands.value.length
      slashMenu.value = {
        ...menu,
        activeIndex: (slashMenuActiveIndex.value + delta + count) % count,
      }
      return
    }
    if (event.key === 'Enter' || event.key === 'Tab') {
      event.preventDefault()
      selectSlashCommand(slashMenuActiveIndex.value)
      return
    }
  }
  if (references?.target === target && atMenuCommands.value.length) {
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault()
      const delta = event.key === 'ArrowDown' ? 1 : -1
      const count = atMenuCommands.value.length
      atMenu.value = {
        ...references,
        activeIndex: (atMenuActiveIndex.value + delta + count) % count,
      }
      return
    }
    if (event.key === 'Enter' || event.key === 'Tab') {
      event.preventDefault()
      selectAtCommand(atMenuActiveIndex.value)
      return
    }
  }
  if (event.key === 'Escape') {
    slashMenu.value = null
    atMenu.value = null
    return
  }
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    submitConversation()
  }
}
