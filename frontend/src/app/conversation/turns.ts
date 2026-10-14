import { aiClient } from '../../api/client'
import type { AgentCompactionActivity, AgentCustomEvent, AgentModelUsage, AgentServerToolActivity, AgentTimelineEntry, AgentToolActivity, AnalysisMessage } from '../../api/types'
import { addAgentUsage } from '../../utils/agentUsage'
import { asContextComposition } from '../../utils/contextComposition'
import { buildMessageParts } from '../../utils/messageParts'
import { appendStreamedAssistantMessage } from '../../utils/streamedAssistant'
import { hasRunningTool, upsertToolActivity } from '../../utils/toolActivities'
import { todoFromTool } from '../../utils/toolPresentation'
import { agentResourceRefresh, applyArtifacts, refreshArtifactsAfterTurn, syncSelectedArtifactDraft } from '../artifacts/actions'
import { assets } from '../assets'
import { atCommandIdFor, clearSlashCommand, deleteReferenceToken, deleteSelectedSlashCommand, selectAtCommand, selectSlashCommand, slashCommandIdFor } from '../composer/actions'
import { atCommands, atCommandsLoaded, atCommandsLoading, atMenu, atMenuActiveIndex, atMenuCommands, followUp, initialMessageParts, pendingMessageImages, raw, slashCommands, slashCommandsLoaded, slashCommandsLoading, slashMenu, slashMenuActiveIndex, slashMenuCommands } from '../composer/state'
import { isAbortError } from '../format'
import { errorMessage, showNotice } from '../notice'
import { reasoningEffort, selectedProviderId, shellApprovalMode } from '../providers'
import { activeSessionKey, conversationId, loadSessions, scheduleSessionTitleRefresh } from '../sessions'
import { settingsSection } from '../settings'
import type { AskUserState, ComposerTarget, QueuedFollowUp } from '../types'
import { applySession, navigate, restoreSessionContextComposition, restoreSessionRuntime } from '../workspace'
import { handleSteeringStarted, markSteeringMessagesResponded, queueFollowUp, settleSteeringMessages } from './queue'
import { activeStreamController, activeTodos, askAnswer, askUserImages, contextComposition, conversation, conversationScratch, conversationStarted, currentContextUsage, loading, pendingQuestion, pendingShellApprovals, pendingSteeringEchoes, queuedFollowUps, queuedQuestions, selectedAskOptions, shellApprovalSubmittingIds, streamingActivities, streamingGenerationDurationMs, streamingMessage, streamingReasoning, streamingStatus, streamingTimeline, streamingUsage } from './state'
import { hasStreamedResponse, resetStreamState, startTurnClock, stopTurnClock } from './stream'
import { loadInteractionTrace, workspaceView } from './trace'

function commitStreamedResponse(
  messages: readonly AnalysisMessage[],
  options: { fallbackContent?: string; error?: string } = {},
): void {
  conversation.value = appendStreamedAssistantMessage(
    settleSteeringMessages(messages),
    {
      content: streamingMessage.value,
      reasoning: streamingReasoning.value || undefined,
      activities: streamingActivities.value,
      timeline: streamingTimeline.value,
      duration_ms: stopTurnClock(),
      generation_duration_ms: streamingGenerationDurationMs.value,
      usage: streamingUsage.value || undefined,
    },
    options,
  )
}
function updateToolActivity(activity: AgentToolActivity): void {
  streamingActivities.value = upsertToolActivity(streamingActivities.value, activity)

  const timelineIndex = streamingTimeline.value.findIndex(
    (item) => item.type === 'tool' && item.activity.id === activity.id,
  )
  if (timelineIndex < 0) {
    streamingTimeline.value.push({ id: `tool-${activity.id}`, type: 'tool', activity })
  } else {
    const current = streamingTimeline.value[timelineIndex]
    if (current.type === 'tool') {
      streamingTimeline.value.splice(timelineIndex, 1, {
        ...current,
        activity: { ...current.activity, ...activity },
      })
    }
  }
}
function updateServerToolActivity(activity: AgentServerToolActivity): void {
  const index = streamingTimeline.value.findIndex(
    (item) => item.type === 'server_tool' && item.activity.id === activity.id,
  )
  if (index < 0) {
    streamingTimeline.value.push({ id: `server-tool-${activity.id}`, type: 'server_tool', activity })
    return
  }
  const current = streamingTimeline.value[index]
  if (current.type !== 'server_tool') return
  streamingTimeline.value.splice(index, 1, {
    ...current,
    activity: {
      ...current.activity,
      ...activity,
      name: activity.name || current.activity.name,
      input: activity.input ?? current.activity.input,
      input_delta: `${current.activity.input_delta || ''}${activity.input_delta || ''}`,
    },
  })
}
function updateCompactionActivity(activity: AgentCompactionActivity): void {
  const index = streamingTimeline.value.findIndex((item) => item.type === 'compaction')
  const previous = index >= 0 ? streamingTimeline.value[index] : null
  const previousActivity = previous?.type === 'compaction' ? previous.activity : null
  const entry: AgentTimelineEntry = {
    id: 'context-compaction',
    type: 'compaction',
    activity: {
      ...previousActivity,
      ...activity,
      content: `${previousActivity?.content || ''}${activity.content}`,
      reasoning: `${previousActivity?.reasoning || ''}${activity.reasoning}`,
    },
  }
  if (index < 0) streamingTimeline.value.push(entry)
  else streamingTimeline.value.splice(index, 1, entry)
}
function updateStreamText(type: 'reasoning' | 'message', content: string): void {
  if (!content) return
  if (type === 'reasoning') streamingReasoning.value += content
  else streamingMessage.value += content

  const last = streamingTimeline.value.at(-1)
  if (last?.type === type) {
    last.content += content
    streamingTimeline.value = [...streamingTimeline.value]
    return
  }
  streamingTimeline.value.push({
    id: `${type}-${streamingTimeline.value.length}`,
    type,
    content,
  })
}
function streamCallbacks() {
  const sessionId = conversationId.value
  return {
    onStatus: (state: string) => { streamingStatus.value = state },
    onModelStarted: () => { conversationScratch.modelStartedAt = performance.now() },
    onUsage: (usage: AgentModelUsage) => {
      streamingUsage.value = addAgentUsage(streamingUsage.value, usage)
      currentContextUsage.value = usage
      if (conversationScratch.modelStartedAt) streamingGenerationDurationMs.value += performance.now() - conversationScratch.modelStartedAt
      conversationScratch.modelStartedAt = 0
    },
    onReasoning: (content: string) => {
      streamingStatus.value = 'reasoning'
      updateStreamText('reasoning', content)
    },
    onMessage: (content: string) => {
      if (conversationScratch.steeringResponseStarted) {
        markSteeringMessagesResponded()
        conversationScratch.steeringResponseStarted = false
      }
      streamingStatus.value = 'writing'
      updateStreamText('message', content)
    },
    onSteering: handleSteeringStarted,
    onTool: (activity: AgentToolActivity) => {
      if (conversationId.value !== sessionId) return
      updateToolActivity(activity)
      const toolsStillRunning = hasRunningTool(streamingActivities.value)
      streamingStatus.value = toolsStillRunning ? 'running_tool' : 'generating'
      const todos = todoFromTool(activity)
      if (todos) activeTodos.value = todos
      if (activity.state !== 'started' && !toolsStillRunning && sessionId) agentResourceRefresh.schedule(sessionId)
    },
    onServerTool: (activity: AgentServerToolActivity) => {
      if (conversationId.value !== sessionId) return
      updateServerToolActivity(activity)
      const hostedToolStillRunning = streamingTimeline.value.some(
        entry => entry.type === 'server_tool'
          && (entry.activity.state === 'started' || entry.activity.state === 'streaming'),
      )
      streamingStatus.value = hostedToolStillRunning ? 'running_tool' : 'generating'
    },
    onCompaction: (activity: AgentCompactionActivity) => {
      streamingStatus.value = activity.state === 'completed' ? 'generating' : 'compacting'
      updateCompactionActivity(activity)
    },
    onCustom: handleCustomAgentEvent,
  }
}
function handleCustomAgentEvent(event: AgentCustomEvent): void {
  if (event.name === 'context_composition') {
    contextComposition.value = asContextComposition(event.payload)
    return
  }
  if (event.name === 'shell_approval_requested') {
    const payload = event.payload
    if (typeof payload.tool_call_id !== 'string' || typeof payload.command !== 'string') return
    if (pendingShellApprovals.value.some(item => item.toolCallId === payload.tool_call_id)) return
    pendingShellApprovals.value.push({
      toolCallId: payload.tool_call_id,
      command: payload.command,
      timeoutSeconds: typeof payload.timeout_seconds === 'number' ? payload.timeout_seconds : 30,
      responseEvent: typeof payload.response_event === 'string' ? payload.response_event : 'shell_approval_response',
      rememberSupported: payload.remember_supported === true,
    })
    streamingStatus.value = 'waiting_for_user'
    return
  }
  if (event.name !== 'ask_user') return
  const payload = event.payload
  if (typeof payload.tool_call_id !== 'string' || typeof payload.question !== 'string') return
  const question: AskUserState = {
    toolCallId: payload.tool_call_id,
    question: payload.question,
    options: Array.isArray(payload.options) ? payload.options.filter((item): item is string => typeof item === 'string') : [],
    allowMultiple: payload.allow_multiple === true,
    responseEvent: typeof payload.response_event === 'string' ? payload.response_event : 'ask_user_response',
  }
  if (pendingQuestion.value?.toolCallId === question.toolCallId) return
  if (pendingQuestion.value) {
    queuedQuestions.value.push(question)
  } else {
    pendingQuestion.value = question
    askAnswer.value = ''
    askUserImages.value = []
    selectedAskOptions.value = []
  }
  streamingStatus.value = 'waiting_for_user'
}
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
