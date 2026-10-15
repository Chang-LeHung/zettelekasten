import { aiClient } from '../../api/client'
import type { AgentSteeringMessage, AnalysisMessage } from '../../api/types'
import { buildMessageParts } from '../../utils/messageParts'
import { moveItemBeforeOrAfter } from '../../utils/reorder'
import { createStreamedAssistantMessage } from '../../utils/streamedAssistant'
import { atCommandIdFor, clearSlashCommand, slashCommandIdFor } from '../composer/actions'
import { followUp, pendingMessageImages } from '../composer/state'
import { errorMessage, showNotice } from '../notice'
import { shellApprovalMode } from '../providers'
import { conversationId } from '../sessions'
import type { PendingSteeringEcho, QueuedFollowUp } from '../types'
import { conversation, conversationScratch, draggingQueuedFollowUpId, loading, pendingSteeringEchoes, queuedFollowUps, steeringQueuedFollowUpId, streamingActivities, streamingGenerationDurationMs, streamingMessage, streamingReasoning, streamingStatus, streamingTimeline, streamingUsage } from './state'
import { currentTurnDurationMs, hasStreamedResponse } from './stream'

export function settleSteeringMessages(messages: readonly AnalysisMessage[]): AnalysisMessage[] {
  return messages.map((message) => (
    message.steering_status === 'waiting'
      ? { ...message, steering_status: 'responded' as const }
      : message
  ))
}
export function markSteeringMessagesResponded(): void {
  if (conversationScratch.activeTurnHistory) {
    conversationScratch.activeTurnHistory.splice(0, conversationScratch.activeTurnHistory.length, ...settleSteeringMessages(conversationScratch.activeTurnHistory))
    conversation.value = [...conversationScratch.activeTurnHistory]
    return
  }
  conversation.value = settleSteeringMessages(conversation.value)
}
function sameSteeringMessage(left: AgentSteeringMessage, right: AgentSteeringMessage): boolean {
  return left.content === right.content && JSON.stringify(left.parts) === JSON.stringify(right.parts)
}
function appendSteeringMessage(message: AgentSteeringMessage): void {
  const nextMessage: AnalysisMessage = {
    role: 'user',
    content: message.content,
    parts: message.parts,
    steering_status: 'waiting',
  }
  if (conversationScratch.activeTurnHistory) {
    conversationScratch.activeTurnHistory.push(nextMessage)
    conversation.value = [...conversationScratch.activeTurnHistory]
  } else {
    conversation.value = [...conversation.value, nextMessage]
  }
}
function applyPendingSteeringEcho(pending: PendingSteeringEcho): void {
  if (pending.applied) return
  pending.applied = true
  appendSteeringMessage(pending.message)
}
function applyStreamedSteeringEcho(message: AgentSteeringMessage): void {
  const pending = (
    pendingSteeringEchoes.find((candidate) => !candidate.applied && sameSteeringMessage(candidate.message, message))
    || pendingSteeringEchoes.find((candidate) => sameSteeringMessage(candidate.message, message))
  )
  if (pending) {
    applyPendingSteeringEcho(pending)
    return
  }
  const applied: PendingSteeringEcho = { message, applied: true }
  pendingSteeringEchoes.push(applied)
  appendSteeringMessage(message)
}
function checkpointStreamedResponseForSteering(): void {
  if (!conversationScratch.activeTurnHistory || !hasStreamedResponse()) return
  conversationScratch.activeTurnHistory.push(createStreamedAssistantMessage({
    content: streamingMessage.value,
    reasoning: streamingReasoning.value || undefined,
    activities: streamingActivities.value,
    timeline: streamingTimeline.value,
    duration_ms: currentTurnDurationMs(),
    generation_duration_ms: streamingGenerationDurationMs.value,
    usage: streamingUsage.value || undefined,
  }))
  conversation.value = [...conversationScratch.activeTurnHistory]
  streamingMessage.value = ''
  streamingReasoning.value = ''
  streamingActivities.value = []
  streamingTimeline.value = []
  streamingUsage.value = null
  streamingGenerationDurationMs.value = 0
  conversationScratch.modelStartedAt = 0
}
export function handleSteeringStarted(message: AgentSteeringMessage): void {
  checkpointStreamedResponseForSteering()
  applyStreamedSteeringEcho(message)
  conversationScratch.steeringResponseStarted = true
}
export function queueFollowUp(): void {
  const content = followUp.value
  if (!content.trim() && !pendingMessageImages.value.length) return
  const parts = buildMessageParts(content, pendingMessageImages.value)
  const slashCommandId = slashCommandIdFor(content)
  const atCommandId = atCommandIdFor(content)
  queuedFollowUps.value.push({
    id: conversationScratch.nextQueuedFollowUpId++,
    content,
    parts,
    shellApprovalMode: shellApprovalMode.value,
    slashCommandId,
    atCommandId,
  })
  followUp.value = ''
  pendingMessageImages.value = []
  clearSlashCommand()
}
export function queuedFollowUpText(item: QueuedFollowUp): string {
  const text = item.content.trim()
  if (text) return text
  const imageCount = item.parts.filter((part) => part.type === 'image').length
  return imageCount === 1 ? 'Image attachment' : `${imageCount} image attachments`
}
export function removeQueuedFollowUp(item: QueuedFollowUp): void {
  queuedFollowUps.value = queuedFollowUps.value.filter((queued) => queued.id !== item.id)
}
export function startQueuedFollowUpDrag(item: QueuedFollowUp, event: DragEvent): void {
  draggingQueuedFollowUpId.value = item.id
  if (event.dataTransfer) {
    event.dataTransfer.effectAllowed = 'move'
    event.dataTransfer.setData('text/plain', String(item.id))
  }
}
export function dropQueuedFollowUp(target: QueuedFollowUp, event: DragEvent): void {
  event.preventDefault()
  const sourceId = draggingQueuedFollowUpId.value
    ?? Number(event.dataTransfer?.getData('text/plain') || Number.NaN)
  if (!Number.isFinite(sourceId)) return
  const rect = (event.currentTarget as HTMLElement).getBoundingClientRect()
  const placeAfter = event.clientY > rect.top + rect.height / 2
  queuedFollowUps.value = moveItemBeforeOrAfter(
    queuedFollowUps.value,
    sourceId,
    target.id,
    placeAfter,
    item => item.id,
  )
  draggingQueuedFollowUpId.value = null
}
export function endQueuedFollowUpDrag(): void {
  draggingQueuedFollowUpId.value = null
}
export async function steerQueuedFollowUp(item: QueuedFollowUp): Promise<void> {
  const activeConversationId = conversationId.value
  if (!activeConversationId || !loading.value) return
  if (item.slashCommandId) {
    showNotice('Slash commands cannot be used as steering messages', 'error')
    return
  }
  if (item.atCommandId) {
    showNotice('Referenced resources cannot be used as steering messages', 'error')
    return
  }
  const steeringMessage: AgentSteeringMessage = {
    content: item.content,
    parts: item.parts,
  }
  const pendingEcho: PendingSteeringEcho = { message: steeringMessage, applied: false }
  pendingSteeringEchoes.push(pendingEcho)
  steeringQueuedFollowUpId.value = item.id
  try {
    const result = await aiClient.steerAgent(activeConversationId, item.content, item.parts)
    if (!result.accepted) {
      pendingSteeringEchoes.splice(pendingSteeringEchoes.indexOf(pendingEcho), 1)
      showNotice('The agent is not accepting steering right now', 'error')
      return
    }
    checkpointStreamedResponseForSteering()
    applyPendingSteeringEcho(pendingEcho)
    queuedFollowUps.value = queuedFollowUps.value.filter((queued) => queued.id !== item.id)
    streamingStatus.value = 'generating'
  } catch (error) {
    const index = pendingSteeringEchoes.indexOf(pendingEcho)
    if (index >= 0) pendingSteeringEchoes.splice(index, 1)
    showNotice(errorMessage(error), 'error')
  } finally {
    if (steeringQueuedFollowUpId.value === item.id) steeringQueuedFollowUpId.value = null
  }
}
