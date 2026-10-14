import { computed, ref } from 'vue'
import type { AgentContextComposition, AgentModelUsage, AgentTimelineEntry, AgentTodoState, AgentToolActivity, AnalysisMessage } from '../../api/types'
import { summarizeAgentUsage } from '../../utils/agentUsage'
import { buildConversationTurns } from '../../utils/conversationTurns'
import type { PositionedMessageImage } from '../../utils/messageParts'
import { TurnDetailsVisibility } from '../../utils/turnDetails'
import { artifactContent, artifacts } from '../artifacts/state'
import { followUp, initialMessageParts, pendingMessageImages, raw } from '../composer/state'
import type { AskUserState, PendingSteeringEcho, QueuedFollowUp, ShellApprovalState } from '../types'

export const conversation = ref<AnalysisMessage[]>([])
export const queuedFollowUps = ref<QueuedFollowUp[]>([])
export const draggingQueuedFollowUpId = ref<number | null>(null)
export const steeringQueuedFollowUpId = ref<number | null>(null)
export const conversationScratch = {
  nextQueuedFollowUpId: 0,
  activeTurnHistory: null as AnalysisMessage[] | null,
  steeringResponseStarted: false,
  agentScrollFrame: null as number | null,
  followAgentOutput: true,
  turnStartedAt: 0,
  turnClock: null as number | null,
  modelStartedAt: 0,
  agentContentResizeObserver: null as ResizeObserver | null,
}
export const pendingSteeringEchoes: PendingSteeringEcho[] = []
export const streamingMessage = ref('')
export const streamingReasoning = ref('')
export const streamingActivities = ref<AgentToolActivity[]>([])
export const streamingTimeline = ref<AgentTimelineEntry[]>([])
export const streamingUsage = ref<AgentModelUsage | null>(null)
export const currentContextUsage = ref<AgentModelUsage | null>(null)
export const contextComposition = ref<AgentContextComposition | null>(null)
export const streamingGenerationDurationMs = ref(0)
export const pendingQuestion = ref<AskUserState | null>(null)
export const pendingShellApprovals = ref<ShellApprovalState[]>([])
export const shellApprovalSubmittingIds = ref<string[]>([])
export const queuedQuestions = ref<AskUserState[]>([])
export const askAnswer = ref('')
export const askUserImages = ref<PositionedMessageImage[]>([])
export const selectedAskOptions = ref<string[]>([])
export const answeringQuestion = ref(false)
export const activeTodos = ref<AgentTodoState | null>(null)
export const streamingStatus = ref('idle')
export const turnElapsedMs = ref(0)
export const activeStreamController = ref<AbortController | null>(null)
export const loading = ref(false)
export const agentThread = ref<HTMLElement | null>(null)
export const agentTurnStack = ref<HTMLElement | null>(null)
export const conversationStarted = computed(
  () => loading.value || conversation.value.length > 0 || artifacts.value.length > 0 || artifactContent.value !== null,
)
export const conversationTurns = computed(() => buildConversationTurns(raw.value, conversation.value, initialMessageParts.value))
export const canSubmitMessage = computed(() => (
  (conversationStarted.value ? followUp.value : raw.value).trim().length > 0 || pendingMessageImages.value.length > 0
))
export const conversationUsage = computed(() => {
  const messages = conversationTurns.value.flatMap((turn) => turn.responses)
  const activeTurn = conversationTurns.value.at(-1)
  if (loading.value && activeTurn && !activeTurn.response && streamingUsage.value) {
    messages.push({
      role: 'assistant',
      content: streamingMessage.value,
      usage: streamingUsage.value,
      generation_duration_ms: streamingGenerationDurationMs.value,
    })
  }
  return summarizeAgentUsage(messages)
})
export const turnDetails = new TurnDetailsVisibility()
