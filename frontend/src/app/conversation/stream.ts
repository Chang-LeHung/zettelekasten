import { nextTick } from 'vue'
import type { AgentTimelineEntry, AnalysisMessage } from '../../api/types'
import { summarizeAgentUsage } from '../../utils/agentUsage'
import { formatTurnDuration, splitTurnTimeline } from '../../utils/conversationTurns'
import type { ConversationTurn } from '../../utils/conversationTurns'
import type { AgentMessageTimelineEntry } from '../types'
import { activeTodos, agentThread, askUserImages, conversationScratch, conversationTurns, loading, pendingQuestion, pendingShellApprovals, queuedQuestions, shellApprovalSubmittingIds, streamingActivities, streamingGenerationDurationMs, streamingMessage, streamingReasoning, streamingStatus, streamingTimeline, streamingUsage, turnDetails, turnElapsedMs } from './state'

export function resetStreamState(): void {
  streamingMessage.value = ''
  streamingReasoning.value = ''
  streamingActivities.value = []
  streamingTimeline.value = []
  streamingUsage.value = null
  streamingGenerationDurationMs.value = 0
  conversationScratch.modelStartedAt = 0
  pendingQuestion.value = null
  pendingShellApprovals.value = []
  shellApprovalSubmittingIds.value = []
  queuedQuestions.value = []
  askUserImages.value = []
  activeTodos.value = null
  conversationScratch.steeringResponseStarted = false
  streamingStatus.value = 'starting'
}
export function hasStreamedResponse(): boolean {
  return Boolean(streamingMessage.value || streamingReasoning.value || streamingTimeline.value.length)
}
export function startTurnClock(): void {
  if (conversationScratch.turnClock !== null) window.clearInterval(conversationScratch.turnClock)
  conversationScratch.turnStartedAt = performance.now()
  turnElapsedMs.value = 0
  conversationScratch.turnClock = window.setInterval(() => {
    turnElapsedMs.value = performance.now() - conversationScratch.turnStartedAt
  }, 200)
}
export function stopTurnClock(): number {
  const duration = conversationScratch.turnStartedAt ? performance.now() - conversationScratch.turnStartedAt : turnElapsedMs.value
  turnElapsedMs.value = duration
  conversationScratch.turnStartedAt = 0
  if (conversationScratch.turnClock !== null) window.clearInterval(conversationScratch.turnClock)
  conversationScratch.turnClock = null
  return duration
}
export function currentTurnDurationMs(): number {
  return conversationScratch.turnStartedAt ? performance.now() - conversationScratch.turnStartedAt : turnElapsedMs.value
}
export function isRunningTurn(index: number): boolean {
  return loading.value && index === conversationTurns.value.length - 1
}
export function isSteeredTurn(index: number): boolean {
  return conversationTurns.value[index + 1]?.prompt.steering_status !== undefined
}
export function isTurnDetailsOpen(turn: ConversationTurn, index: number): boolean {
  return turnDetails.isOpen(turn.id, isRunningTurn(index))
}
function turnTimeline(turn: ConversationTurn, index: number): AgentTimelineEntry[] {
  if (isRunningTurn(index)) return streamingTimeline.value
  return turn.responses.flatMap((response) => historicalTimeline(response))
}
export function turnExecutionTimeline(turn: ConversationTurn, index: number): AgentTimelineEntry[] {
  return splitTurnTimeline(turnTimeline(turn, index)).execution
}
export function turnAnswerTimeline(turn: ConversationTurn, index: number): AgentMessageTimelineEntry[] {
  return splitTurnTimeline(turnTimeline(turn, index)).answer
}
export function turnTask(index: number): string {
  if (!isRunningTurn(index)) return 'Completed'
  const processing = activeTodos.value?.processing?.content
  if (processing) return processing
  const activeTool = [...streamingActivities.value].reverse().find((activity) => activity.state === 'started')
  if (activeTool) return `Using ${activeTool.name.replaceAll('_', ' ')}`
  const labels: Record<string, string> = {
    starting: 'Preparing your request',
    compacting: 'Organizing conversation context',
    generating: 'Thinking through your request',
    reasoning: 'Thinking through your request',
    writing: 'Writing the response',
    waiting_for_user: 'Waiting for your answer',
    resuming: 'Resuming the task',
  }
  return labels[streamingStatus.value] || 'Working on your request'
}
export function turnDuration(turn: ConversationTurn, index: number): string {
  if (isRunningTurn(index)) return formatTurnDuration(turnElapsedMs.value)
  return formatTurnDuration(turn.response?.duration_ms || 0)
}
export function turnCacheHitRate(turn: ConversationTurn, index: number): number | null {
  const messages = [...turn.responses]
  if (isRunningTurn(index) && streamingUsage.value) {
    messages.push({
      role: 'assistant',
      content: streamingMessage.value,
      usage: streamingUsage.value,
    })
  }
  return summarizeAgentUsage(messages)?.cache_hit_rate ?? null
}
function historicalTimeline(message: AnalysisMessage): AgentTimelineEntry[] {
  if (message.timeline?.length) {
    return message.timeline.some((entry) => entry.type === 'message') || !message.content
      ? message.timeline
      : [...message.timeline, { id: 'message', type: 'message', content: message.content }]
  }
  const entries: AgentTimelineEntry[] = []
  if (message.reasoning) {
    entries.push({ id: 'reasoning', type: 'reasoning', content: message.reasoning })
  }
  for (const activity of message.activities || []) {
    entries.push({ id: `tool-${activity.id}`, type: 'tool', activity })
  }
  if (message.content) entries.push({ id: 'message', type: 'message', content: message.content })
  return entries
}
export function handleAgentThreadScroll(): void {
  const thread = agentThread.value
  if (!thread) return
  conversationScratch.followAgentOutput = thread.scrollHeight - thread.scrollTop - thread.clientHeight < 96
  if (!conversationScratch.followAgentOutput && conversationScratch.agentScrollFrame !== null) {
    window.cancelAnimationFrame(conversationScratch.agentScrollFrame)
    conversationScratch.agentScrollFrame = null
  }
}
export function handleAgentThreadWheel(event: WheelEvent): void {
  if (event.deltaY >= 0) return
  conversationScratch.followAgentOutput = false
  if (conversationScratch.agentScrollFrame !== null) {
    window.cancelAnimationFrame(conversationScratch.agentScrollFrame)
    conversationScratch.agentScrollFrame = null
  }
}
export function scrollAgentThread(force = false): void {
  void nextTick(() => {
    const thread = agentThread.value
    if (!thread || (!force && !conversationScratch.followAgentOutput)) return
    if (conversationScratch.agentScrollFrame !== null) window.cancelAnimationFrame(conversationScratch.agentScrollFrame)
    conversationScratch.agentScrollFrame = window.requestAnimationFrame(() => {
      conversationScratch.agentScrollFrame = null
      if (!force && !conversationScratch.followAgentOutput) return
      const bottom = Math.max(0, thread.scrollHeight - thread.clientHeight)
      if (Math.abs(thread.scrollTop - bottom) > 1) thread.scrollTop = bottom
      conversationScratch.followAgentOutput = true
    })
  })
}
export function toggleTurnExecution(turn: ConversationTurn, event: MouseEvent): void {
  const details = (event.currentTarget as HTMLElement | null)?.closest('details')
  const thread = agentThread.value
  if (!(details instanceof HTMLDetailsElement) || !thread) return
  const summary = details.querySelector(':scope > summary')
  if (!(summary instanceof HTMLElement)) return

  event.preventDefault()
  const previousTop = summary.getBoundingClientRect().top
  conversationScratch.followAgentOutput = false
  if (conversationScratch.agentScrollFrame !== null) {
    window.cancelAnimationFrame(conversationScratch.agentScrollFrame)
    conversationScratch.agentScrollFrame = null
  }
  details.open = !details.open
  turnDetails.setOpen(turn.id, details.open)
  void nextTick(() => {
    if (!details.isConnected) return
    const offset = summary.getBoundingClientRect().top - previousTop
    if (Math.abs(offset) > 1) thread.scrollTop += offset
  })
}
