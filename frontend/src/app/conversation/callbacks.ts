import type { AgentCompactionActivity, AgentCustomEvent, AgentModelUsage, AgentServerToolActivity, AgentTimelineEntry, AgentToolActivity, AnalysisMessage } from '../../api/types'
import { addAgentUsage } from '../../utils/agentUsage'
import { asContextComposition } from '../../utils/contextComposition'
import { appendStreamedAssistantMessage } from '../../utils/streamedAssistant'
import { hasRunningTool, upsertToolActivity } from '../../utils/toolActivities'
import { todoFromTool } from '../../utils/toolPresentation'
import { agentResourceRefresh } from '../artifacts/actions'
import { conversationId } from '../sessions'
import type { AskUserState } from '../types'
import { handleSteeringStarted, markSteeringMessagesResponded, settleSteeringMessages } from './queue'
import { activeTodos, askAnswer, askUserImages, contextComposition, conversation, conversationScratch, currentContextUsage, pendingQuestion, pendingShellApprovals, queuedQuestions, selectedAskOptions, streamingActivities, streamingGenerationDurationMs, streamingMessage, streamingReasoning, streamingStatus, streamingTimeline, streamingUsage } from './state'
import { stopTurnClock } from './stream'

export function commitStreamedResponse(
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
export function streamCallbacks() {
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
