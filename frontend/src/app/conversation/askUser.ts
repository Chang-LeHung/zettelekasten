import { aiClient } from '../../api/client'
import type { ShellApprovalMode } from '../../api/types'
import { buildMessageParts, readMessageImage } from '../../utils/messageParts'
import { errorMessage, showNotice } from '../notice'
import { shellApprovalMode } from '../providers'
import { conversationId } from '../sessions'
import { runtimeSettings } from '../settings'
import { answeringQuestion, askAnswer, askUserImages, pendingQuestion, pendingShellApprovals, queuedQuestions, selectedAskOptions, shellApprovalSubmittingIds, streamingStatus } from './state'

function showNextAskQuestion(): void {
  pendingQuestion.value = queuedQuestions.value.shift() || null
  askAnswer.value = ''
  askUserImages.value = []
  selectedAskOptions.value = []
  streamingStatus.value = pendingQuestion.value ? 'waiting_for_user' : 'resuming'
}
export function toggleAskOption(option: string): void {
  const question = pendingQuestion.value
  if (!question) return
  if (!question.allowMultiple) {
    selectedAskOptions.value = [option]
    askAnswer.value = ''
    return
  }
  selectedAskOptions.value = selectedAskOptions.value.includes(option)
    ? selectedAskOptions.value.filter((item) => item !== option)
    : [...selectedAskOptions.value, option]
}
export function updateAskAnswer(value: string): void {
  askAnswer.value = value
  if (value.trim() && !pendingQuestion.value?.allowMultiple) selectedAskOptions.value = []
}
export async function answerAgentQuestion(): Promise<void> {
  const question = pendingQuestion.value
  const activeConversationId = conversationId.value
  if (!question || !activeConversationId || answeringQuestion.value) return
  const typedAnswer = askAnswer.value.trim()
  const answer = question.allowMultiple
    ? [...selectedAskOptions.value, ...(typedAnswer ? [typedAnswer] : [])]
    : typedAnswer || selectedAskOptions.value[0]
  if ((!answer || (Array.isArray(answer) && !answer.length)) && !askUserImages.value.length) return
  const answerText = Array.isArray(answer) ? answer.join('\n') : answer || ''
  const parts = askUserImages.value.length ? buildMessageParts(answerText, askUserImages.value) : []
  answeringQuestion.value = true
  try {
    await aiClient.emitAgentEvent(activeConversationId, question.responseEvent, {
      session_id: activeConversationId,
      tool_call_id: question.toolCallId,
      answer,
      parts,
    })
    askUserImages.value = []
    showNextAskQuestion()
  } catch (error) {
    showNotice(errorMessage(error), 'error')
  } finally {
    answeringQuestion.value = false
  }
}
export async function respondToShellApproval(
  toolCallId: string,
  decision: 'execute' | 'abort',
  remember = false,
): Promise<void> {
  const approval = pendingShellApprovals.value.find(item => item.toolCallId === toolCallId)
  const activeConversationId = conversationId.value
  if (!approval || !activeConversationId) return
  shellApprovalSubmittingIds.value = [...shellApprovalSubmittingIds.value, approval.toolCallId]
  try {
    const response = await aiClient.emitAgentEvent(activeConversationId, approval.responseEvent, {
      session_id: activeConversationId,
      tool_call_id: approval.toolCallId,
      decision,
      remember: decision === 'execute' && remember,
    })
    if (!response.accepted) {
      showNotice('The shell approval request is no longer active', 'error')
      return
    }
    pendingShellApprovals.value = pendingShellApprovals.value.filter(item => item.toolCallId !== approval.toolCallId)
    streamingStatus.value = pendingShellApprovals.value.length ? 'waiting_for_user' : 'resuming'
  } catch (error) {
    showNotice(errorMessage(error), 'error')
  } finally {
    shellApprovalSubmittingIds.value = shellApprovalSubmittingIds.value.filter(id => id !== approval.toolCallId)
  }
}
export async function attachAskUserImages(files: File[]): Promise<void> {
  const available = Math.max(0, runtimeSettings.value.max_message_images - askUserImages.value.length)
  const images = files.filter((file) => file.type.startsWith('image/')).slice(0, available)
  if (!images.length) return
  try {
    askUserImages.value.push(...await Promise.all(images.map((file) => readMessageImage(file, askAnswer.value.length))))
    if (images.length < files.filter((file) => file.type.startsWith('image/')).length) {
      showNotice(`An answer can contain up to ${runtimeSettings.value.max_message_images} images`, 'error')
    }
  } catch (error) {
    showNotice(errorMessage(error), 'error')
  }
}
export function removeAskUserImage(id: string): void {
  askUserImages.value = askUserImages.value.filter((image) => image.id !== id)
}
export async function updateShellApprovalMode(mode: ShellApprovalMode): Promise<void> {
  const previous = shellApprovalMode.value
  shellApprovalMode.value = mode
  const activeConversationId = conversationId.value
  if (!activeConversationId) return
  try {
    await aiClient.updateAgentSessionShellApproval(activeConversationId, mode)
    if (mode === 'allow_all' && pendingShellApprovals.value.length) {
      await Promise.all(
        pendingShellApprovals.value.map(item => respondToShellApproval(item.toolCallId, 'execute')),
      )
    }
  } catch (error) {
    shellApprovalMode.value = previous
    showNotice(errorMessage(error), 'error')
  }
}
