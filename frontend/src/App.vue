<script setup lang="ts">
import { computed, defineAsyncComponent, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ApiError, aiClient, assetClient, libraryClient, settingsClient, tagClient } from './api/client'
import type { AgentArtifact, AgentAtCommand, AgentCompactionActivity, AgentContextComposition, AgentCustomEvent, AgentModelUsage, AgentModelUsageActivitySeries, AgentPersistedMessage, AgentServerToolActivity, AgentSession, AgentSlashCommand, AgentSteeringMessage, AgentTimelineEntry, AgentTodoState, AgentToolActivity, AgentUsageActivityDay, AIProvider, AIProviderInput, AnalysisMessage, ArtifactContent, CardType, LibraryItem, LibraryItemUpdate, MessageImagePart, MessagePart, ReasoningEffort, RuntimeSettings, SessionAsset, SessionType, ShellApprovalMode, StaticAsset, Tag } from './api/types'
import AgentComposerControls from './components/AgentComposerControls.vue'
import ArtifactDiffView from './components/ArtifactDiffView.vue'
import ComposerCommandMenu from './components/ComposerCommandMenu.vue'
import CacheHitRate from './components/CacheHitRate.vue'
import ConfirmDialog from './components/ConfirmDialog.vue'
import TagManagerDialog from './components/TagManagerDialog.vue'
import AssetPreviewDialog from './components/AssetPreviewDialog.vue'
import AssetRename from './components/AssetRename.vue'
import AskUserPrompt from './components/AskUserPrompt.vue'
import ShellApprovalPrompt from './components/ShellApprovalPrompt.vue'
import ToolResult from './components/ToolResult.vue'
import UsageActivityGraph from './components/UsageActivityGraph.vue'
import { addAgentUsage, latestAgentUsage, summarizeAgentUsage } from './utils/agentUsage'
import { artifactContentFromLibraryUpdate, artifactEditableContent, hasPendingDraft, libraryItemFromArtifact } from './utils/artifactEditor'
import { artifactListsEquivalent, sameArtifactRevision, stabilizeArtifactReferences } from './utils/artifactStability'
import { diffArtifactContent } from './utils/artifactDiff'
import { addTagPath } from './utils/tagAssignment'
import { assetOpenAction, isPdfAsset } from './utils/assetOpen'
import { createAsyncRefreshScheduler } from './utils/asyncRefresh'
import { AtCommandInput, type AtCommandMatch } from './utils/atCommand'
import { SlashCommandInput, type SlashCommandMatch } from './utils/slashCommand'
import { buildConversationTurns, formatTurnDuration, splitTurnTimeline, type ConversationTurn } from './utils/conversationTurns'
import { jsonSnapshot } from './utils/jsonSnapshot'
import { buildMessageParts, rebaseImagePositions, type PositionedMessageImage } from './utils/messageParts'
import { restorePersistedConversation } from './utils/persistedConversation'
import { moveItemBeforeOrAfter } from './utils/reorder'
import { readPaneHidden, writePaneHidden } from './utils/paneVisibility'
import { artifactImageUrl, versionedPreviewUrl } from './utils/artifactPreview'
import { appendStreamedAssistantMessage, createStreamedAssistantMessage } from './utils/streamedAssistant'
import { defaultProviderBaseUrl, providerBaseUrlHelp } from './utils/providerDefaults'
import { todoFromTool } from './utils/toolPresentation'
import { hasRunningTool, upsertToolActivity } from './utils/toolActivities'
import { TurnDetailsVisibility } from './utils/turnDetails'
import { presentationSections } from './utils/slides'
import { libraryExcerptText } from './utils/libraryExcerpt'
import { asContextComposition } from './utils/contextComposition'
import { visibleTagRows } from './utils/tagTree'
import { useI18n, type Locale } from './i18n'

const MarkdownContent = defineAsyncComponent(() => import('./components/MarkdownContent.vue'))
const LibraryEditor = defineAsyncComponent(() => import('./components/LibraryEditor.vue'))
const PdfThumbnail = defineAsyncComponent(() => import('./components/PdfThumbnail.vue'))
const SlidesPreview = defineAsyncComponent(() => import('./components/SlidesPreview.vue'))
const PdfPreview = defineAsyncComponent(() => import('./components/PdfPreview.vue'))
const InteractionTrace = defineAsyncComponent(() => import('./components/InteractionTrace.vue'))
const ModelUsageTrend = defineAsyncComponent(() => import('./components/ModelUsageTrend.vue'))
const StaticAssetsView = defineAsyncComponent(() => import('./components/StaticAssetsView.vue'))
const StaticAssetImportDialog = defineAsyncComponent(() => import('./components/StaticAssetImportDialog.vue'))
const ScheduledTasksView = defineAsyncComponent(() => import('./components/ScheduledTasksView.vue'))
const ChannelsView = defineAsyncComponent(() => import('./components/ChannelsView.vue'))

type View = 'library' | 'search' | 'new' | 'assets' | 'scheduledTasks' | 'channels' | 'settings'
type SessionScope = Extract<SessionType, 'normal' | 'scheduled' | 'channel'>
type NoticeKind = 'success' | 'error'
type AssetEditorMode = 'closed' | 'text' | 'link'
type AssetFilter = 'all' | 'documents' | 'images' | 'links' | 'notes' | 'code'
type SettingsSection = 'usage' | 'providers'
type ComposerTarget = 'initial' | 'follow-up'
const DEFAULT_SESSION_TITLE = '新会话'
const { locale, setLocale, t } = useI18n()
type AgentMessageTimelineEntry = Extract<AgentTimelineEntry, { type: 'message' }>
interface ConfirmationState {
  open: boolean
  title: string
  message: string
  confirmLabel: string
}
interface AskUserState {
  toolCallId: string
  question: string
  options: string[]
  allowMultiple: boolean
  responseEvent: string
}
interface ShellApprovalState {
  toolCallId: string
  command: string
  timeoutSeconds: number
  responseEvent: string
  rememberSupported: boolean
}
interface QueuedFollowUp {
  id: number
  content: string
  parts: MessagePart[]
  shellApprovalMode: ShellApprovalMode
  slashCommandId: string | null
  atCommandId: string | null
}
interface PendingSteeringEcho {
  message: AgentSteeringMessage
  applied: boolean
}
interface ActiveSlashMenu {
  target: ComposerTarget
  match: SlashCommandMatch
  activeIndex: number
}
interface ActiveAtMenu {
  target: ComposerTarget
  match: AtCommandMatch
  activeIndex: number
}
interface ComposerHighlightSegment {
  text: string
  kind: 'slash' | 'reference' | null
}
const libraryItems = ref<LibraryItem[]>([])
const selectedLibraryItem = ref<LibraryItem | null>(null)
const fullscreenSlidesItem = ref<LibraryItem | null>(null)
const libraryPdfLaunch = ref<{ item: LibraryItem; mode: 'expanded' | 'presentation' } | null>(null)
const librarySlidesStage = ref<HTMLElement | null>(null)
let slidesPreviewTrigger: HTMLElement | null = null

async function openSlidesFullscreen(item: LibraryItem): Promise<void> {
  slidesPreviewTrigger = document.activeElement instanceof HTMLElement ? document.activeElement : null
  fullscreenSlidesItem.value = item
  await nextTick()
  librarySlidesStage.value?.focus()
  try {
    await librarySlidesStage.value?.requestFullscreen()
  } catch {
    // Keep the viewport-sized preview available if native fullscreen is unavailable.
  }
}

async function closeSlidesFullscreen(): Promise<void> {
  if (document.fullscreenElement === librarySlidesStage.value) await document.exitFullscreen()
  fullscreenSlidesItem.value = null
  slidesPreviewTrigger?.focus()
}

function openLibraryPdf(item: LibraryItem, mode: 'expanded' | 'presentation'): void {
  libraryPdfLaunch.value = { item, mode }
}

function handleSlidesFullscreenChange(): void {
  if (!document.fullscreenElement && fullscreenSlidesItem.value) {
    fullscreenSlidesItem.value = null
    slidesPreviewTrigger?.focus()
  }
}
const libraryEditorItem = ref<LibraryItem | null>(null)
const libraryEditorArtifactId = ref<string | null>(null)
const libraryEditorSaving = ref(false)
const libraryLoading = ref(false)
const deletingLibraryItemId = ref<string | null>(null)
const draggingLibraryItem = ref<LibraryItem | null>(null)
const draggingStaticAsset = ref<StaticAsset | null>(null)
const tagDropTargetId = ref<string | null>(null)
const tagAssignmentBusy = ref(false)
const tags = ref<Tag[]>([])
const collapsedTagIds = ref<Set<string>>(new Set())
const hoveredTagId = ref<string | null>(null)
const tagManagerOpen = ref(false)
const tagManagerBusy = ref(false)
const tagManagerFeedback = ref('')
const tagManagerFeedbackKind = ref<'success' | 'error'>('success')
const query = ref('')
const activeQuery = ref('')
const selectedTag = ref<string | null>(null)
const selectedLibraryType = ref<LibraryItem['item_type'] | null>(null)
const view = ref<View>('new')
const raw = ref('')
const artifactContent = ref<ArtifactContent | null>(null)
const conversation = ref<AnalysisMessage[]>([])
const queuedFollowUps = ref<QueuedFollowUp[]>([])
const draggingQueuedFollowUpId = ref<number | null>(null)
const steeringQueuedFollowUpId = ref<number | null>(null)
let nextQueuedFollowUpId = 0
let activeTurnHistory: AnalysisMessage[] | null = null
let steeringResponseStarted = false
const pendingSteeringEchoes: PendingSteeringEcho[] = []
const initialTraceLocation = traceLocationFromHash()
const workspaceView = ref<'workspace' | 'trace'>(initialTraceLocation ? 'trace' : 'workspace')
const selectedTraceTurnId = ref<string | null>(initialTraceLocation?.turnId || null)
const traceMessages = ref<AgentPersistedMessage[]>([])
const traceLoading = ref(false)
const traceError = ref('')
const followUp = ref('')
const slashCommands = ref<AgentSlashCommand[]>([])
const slashCommandsLoaded = ref(false)
const slashCommandsLoading = ref(false)
const slashMenu = ref<ActiveSlashMenu | null>(null)
const selectedSlashCommand = ref<AgentSlashCommand | null>(null)
const atCommands = ref<AgentAtCommand[]>([])
const atCommandsLoaded = ref(false)
const atCommandsLoading = ref(false)
const atMenu = ref<ActiveAtMenu | null>(null)
const initialComposerInput = ref<HTMLTextAreaElement | null>(null)
const followUpComposerInput = ref<HTMLTextAreaElement | null>(null)
const initialComposerHighlight = ref<HTMLElement | null>(null)
const followUpComposerHighlight = ref<HTMLElement | null>(null)
const composerComposing = ref(false)
const initialMessageParts = ref<MessagePart[]>([])
const pendingMessageImages = ref<PositionedMessageImage[]>([])
const streamingMessage = ref('')
const streamingReasoning = ref('')
const streamingActivities = ref<AgentToolActivity[]>([])
const streamingTimeline = ref<AgentTimelineEntry[]>([])
const streamingUsage = ref<AgentModelUsage | null>(null)
const currentContextUsage = ref<AgentModelUsage | null>(null)
const contextComposition = ref<AgentContextComposition | null>(null)
const streamingGenerationDurationMs = ref(0)
const pendingQuestion = ref<AskUserState | null>(null)
const pendingShellApprovals = ref<ShellApprovalState[]>([])
const shellApprovalSubmittingIds = ref<string[]>([])
const queuedQuestions = ref<AskUserState[]>([])
const askAnswer = ref('')
const askUserImages = ref<PositionedMessageImage[]>([])
const selectedAskOptions = ref<string[]>([])
const answeringQuestion = ref(false)
const activeTodos = ref<AgentTodoState | null>(null)
let agentScrollFrame: number | null = null
let followAgentOutput = true
const streamingStatus = ref('idle')
const turnElapsedMs = ref(0)
const activeStreamController = ref<AbortController | null>(null)
const artifactPreview = ref(true)
// Bumped on refresh so a recompiled PDF is fetched again instead of reusing cached bytes.
const artifactPreviewNonce = ref(0)
const artifactRefreshing = ref(false)
/** Show the draft-versus-published diff instead of the editor or preview. */
const artifactDiff = ref(false)
const conversationId = ref<string | null>(null)
const editingSessionId = ref<string | null>(null)
const sessionTitleDraft = ref('')
const artifacts = ref<AgentArtifact[]>([])
const assets = ref<SessionAsset[]>([])
const previewAsset = ref<SessionAsset | null>(null)
const assetEditorMode = ref<AssetEditorMode>('closed')
const assetName = ref('')
const assetValue = ref('')
const assetUploading = ref(false)
const assetQuery = ref('')
const assetFilter = ref<AssetFilter>('all')
const assetDragging = ref(false)
const assetsPaneKey = 'zett.assets-pane-hidden'
const assetsPaneHidden = ref(readPaneHidden(assetsPaneKey))
//: The artifact pane's preview, which refits its pages when this pane changes width.
const pdfPreviewRef = ref<{ refit: () => void } | null>(null)
const staticAssetImportOpen = ref(false)
const staticAssets = ref<StaticAsset[]>([])
const staticAssetsView = ref<{ reload: () => Promise<void> } | null>(null)
const staticAssetsLoading = ref(false)
const staticAssetImportingId = ref<string | null>(null)
const sessions = ref<AgentSession[]>([])
const scheduledSessions = ref<AgentSession[]>([])
const channelSessions = ref<AgentSession[]>([])
const sessionListRef = ref<HTMLElement | null>(null)
const sessionScope = ref<SessionScope>('normal')
const sessionsLoading = ref(false)
const scheduledSessionsLoading = ref(false)
const channelSessionsLoading = ref(false)
//: Scopes whose first list request has settled; until then the sidebar is loading,
//: not empty, so a startup or scope switch never flashes the empty state.
const loadedSessionScopes = ref<Set<SessionScope>>(new Set())
const switchingSessionId = ref<string | null>(null)
const sessionDetailRequests = new Map<string, Promise<AgentSession>>()
const sessionsHaveMore = ref(true)
const scheduledSessionsHaveMore = ref(true)
const channelSessionsHaveMore = ref(true)
const sessionPageSize = 20
const selectedArtifactId = ref<string | null>(null)
const loading = ref(false)
//: True until the persisted conversation, including its artifacts, has loaded.
const workspaceRestoring = ref(true)
const saving = ref(false)
const notice = ref('')
const noticeKind = ref<NoticeKind>('success')
const confirmation = ref<ConfirmationState>({ open: false, title: '', message: '', confirmLabel: 'Delete' })
let resolveConfirmation: ((confirmed: boolean) => void) | null = null
const selectedSuggestions = ref<string[]>([])
const providers = ref<AIProvider[]>([])
const selectedProviderId = ref<string | null>(null)
const reasoningEffort = ref<ReasoningEffort>('medium')
const shellApprovalMode = ref<ShellApprovalMode>('review')
const editingProviderId = ref<string | null>(null)
const providerLoading = ref(false)
const providerSaving = ref(false)
const apiKeyVisible = ref(true)
const ai = ref<AIProviderInput>({
  name: '',
  provider: 'openai_compatible',
  model: '',
  base_url: '',
  api_key: '',
  temperature: 0.2,
  response: false,
  enabled: true,
})
const runtimeSettings = ref<RuntimeSettings>({
  max_message_images: 32,
  max_turn_iterations: 256,
  max_asset_size_bytes: 250 * 1024 * 1024,
  compaction_max_tokens: 800_000,
  compaction_keep_recent_tokens: 64_000,
})
const maxAssetSizeMb = computed<number>({
  get: () => Math.round(runtimeSettings.value.max_asset_size_bytes / (1024 * 1024)),
  set: (value) => {
    const normalized = Number.isFinite(value) ? Math.max(1, Math.round(value)) : 1
    runtimeSettings.value.max_asset_size_bytes = normalized * 1024 * 1024
  },
})
const runtimeSettingsSaving = ref(false)
const usageActivity = ref<AgentUsageActivityDay[]>([])
const modelUsageActivity = ref<AgentModelUsageActivitySeries[]>([])
const usageActivityLoading = ref(false)
const settingsSection = ref<SettingsSection>('providers')
const searchInput = ref<HTMLInputElement | null>(null)
const agentThread = ref<HTMLElement | null>(null)
const agentTurnStack = ref<HTMLElement | null>(null)
const assetFileInput = ref<HTMLInputElement | null>(null)
let titleRefreshTimer: number | null = null
let turnStartedAt = 0
let providerSelectionGeneration = 0
let sessionSwitchGeneration = 0
let turnClock: number | null = null
let modelStartedAt = 0
let agentContentResizeObserver: ResizeObserver | null = null
const activeSessionKey = 'zett.active-session-id'
const cardTypes: CardType[] = ['note', 'idea', 'quote', 'todo', 'reference']
const assetFilters: Array<{ value: AssetFilter; label: string }> = [
  { value: 'all', label: 'All' },
  { value: 'documents', label: 'Documents' },
  { value: 'images', label: 'Images' },
  { value: 'links', label: 'Links' },
  { value: 'notes', label: 'Notes' },
  { value: 'code', label: 'Code' },
]
const libraryTypeFilters: Array<{ value: LibraryItem['item_type'] | null; label: string }> = [
  { value: null, label: 'All' },
  { value: 'card', label: 'Cards' },
  { value: 'article', label: 'Articles' },
  { value: 'slides', label: 'Slides' },
  { value: 'latex_pdf', label: 'PDFs' },
]

const flatTags = computed(() => visibleTagRows(tags.value, collapsedTagIds.value))
const selectedTagName = computed(() => flatTags.value.find((tag) => tag.id === selectedTag.value)?.path)
const pageTitle = computed(() => {
  if (view.value === 'search') {
    return activeQuery.value
      ? t('Results for “{query}”', { query: activeQuery.value })
      : t('Search library')
  }
  return selectedTagName.value || t('All knowledge')
})
const pageDescription = computed(() => {
  return view.value === 'search'
    ? t('{count} matching items', { count: libraryItems.value.length })
    : t('{count} items in your library', { count: libraryItems.value.length })
})
/**
 * Identity of the result set on screen. The grid is keyed by it, so a filter
 * that lands on a different set remounts its cards and replays the float-in,
 * while an unchanged set keeps the same nodes instead of animating again.
 */
const libraryGridKey = computed(() =>
  libraryItems.value.map((item) => `${item.item_type}-${item.id}`).join('|'),
)
const conversationStarted = computed(
  () => loading.value || conversation.value.length > 0 || artifacts.value.length > 0 || artifactContent.value !== null,
)
const conversationTurns = computed(() => buildConversationTurns(raw.value, conversation.value, initialMessageParts.value))
const canSubmitMessage = computed(() => (
  (conversationStarted.value ? followUp.value : raw.value).trim().length > 0 || pendingMessageImages.value.length > 0
))
const slashMenuCommands = computed(() => {
  const query = slashMenu.value?.match.query.trim().toLowerCase()
  if (!query) return slashCommands.value
  return slashCommands.value.filter((command) => (
    command.name.toLowerCase().includes(query)
    || command.description.toLowerCase().includes(query)
    || command.type.toLowerCase().includes(query)
  ))
})
const slashMenuActiveIndex = computed(() => {
  const menu = slashMenu.value
  if (!menu || !slashMenuCommands.value.length) return 0
  return Math.min(menu.activeIndex, slashMenuCommands.value.length - 1)
})
const slashMenuItems = computed(() => slashMenuCommands.value.map((command) => ({
  id: command.id,
  name: command.name,
  description: command.description,
  badge: command.type,
})))
const atMenuCommands = computed(() => {
  const query = atMenu.value?.match.query.trim().toLowerCase()
  if (!query) return atCommands.value
  return atCommands.value.filter((command) => (
    command.name.toLowerCase().includes(query)
    || command.label.toLowerCase().includes(query)
    || command.kind.toLowerCase().includes(query)
  ))
})
const atMenuActiveIndex = computed(() => {
  const menu = atMenu.value
  if (!menu || !atMenuCommands.value.length) return 0
  return Math.min(menu.activeIndex, atMenuCommands.value.length - 1)
})
const atMenuItems = computed(() => atMenuCommands.value.map((command) => ({
  id: command.id,
  name: command.name,
  description: `${command.label} · ${command.description}`,
  badge: command.kind,
})))
const initialTokenHighlight = computed(() => composerHighlightSegments('initial'))
const followUpTokenHighlight = computed(() => composerHighlightSegments('follow-up'))
const conversationUsage = computed(() => {
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
const selectedArtifact = computed(() => artifacts.value.find((artifact) => artifact.id === selectedArtifactId.value) || null)
/**
 * The artifact pane's preview source. The nonce makes every refresh a new URL,
 * because recompiling replaces the PDF bytes without changing the artifact row.
 */
const artifactPreviewAsset = computed(() => {
  const artifact = selectedArtifact.value
  if (!artifact) return artifact
  return { ...artifact, content_url: versionedPreviewUrl(artifact.content_url, artifactPreviewNonce.value) }
})
const selectedArtifactDiff = computed(() => diffArtifactContent(
  selectedArtifact.value?.content ?? null,
  selectedArtifact.value?.draft_content ?? null,
))
const selectedImageUrl = computed(() => {
  return artifactImageUrl(artifactContent.value, selectedArtifact.value)
})

function artifactTypeLabel(type: ArtifactContent['artifact_type']): string {
  return ({ card: 'Card', article: 'Article', image: 'Image', slides: 'Slides', latex_pdf: 'LaTeX PDF' })[type]
}

function artifactTitle(content: ArtifactContent | null): string {
  if (!content) return 'Untitled artifact'
  return content.artifact_type === 'latex_pdf' ? content.pdf_name.replace(/\.pdf$/, '') : content.title
}

function libraryExcerpt(item: LibraryItem): string {
  const source = item.summary || (item.item_type === 'slides' ? item.subtitle : '') || item.content
  return libraryExcerptText(source) || 'Open to explore this item.'
}
/** Stagger a freshly filtered grid so it blooms instead of snapping in at once. */
function cardFloatDelay(index: number): string {
  return `${Math.min(index, 8) * 40}ms`
}
const activeSessions = computed(() => (
  sessionScope.value === 'scheduled' ? scheduledSessions.value
  : sessionScope.value === 'channel' ? channelSessions.value
  : sessions.value
))
const activeSessionsLoading = computed(() => (
  sessionScope.value === 'scheduled' ? scheduledSessionsLoading.value
  : sessionScope.value === 'channel' ? channelSessionsLoading.value
  : sessionsLoading.value
))
const activeSessionsHaveMore = computed(() => (
  sessionScope.value === 'scheduled' ? scheduledSessionsHaveMore.value
  : sessionScope.value === 'channel' ? channelSessionsHaveMore.value
  : sessionsHaveMore.value
))
const activeSessionsPending = computed(() => (
  activeSessionsLoading.value || !loadedSessionScopes.value.has(sessionScope.value)
))
const visibleSessions = computed(() => activeSessions.value.filter((session) => (
  session.message_count > 0
  || session.id === conversationId.value
)))
const filteredAssets = computed(() => {
  const normalizedQuery = assetQuery.value.trim().toLowerCase()
  return [...assets.value]
    .filter((asset) => (
      (!normalizedQuery
        || asset.name.toLowerCase().includes(normalizedQuery)
        || asset.source_url?.toLowerCase().includes(normalizedQuery))
      && (assetFilter.value === 'all' || classifyAsset(asset) === assetFilter.value)
    ))
    .sort((left, right) => right.created_at.localeCompare(left.created_at))
})
const importedStaticAssetIds = computed(() => assets.value.flatMap((asset) => (
  typeof asset.metadata.static_asset_id === 'string' ? [asset.metadata.static_asset_id] : []
)))

function resetStreamState(): void {
  streamingMessage.value = ''
  streamingReasoning.value = ''
  streamingActivities.value = []
  streamingTimeline.value = []
  streamingUsage.value = null
  streamingGenerationDurationMs.value = 0
  modelStartedAt = 0
  pendingQuestion.value = null
  pendingShellApprovals.value = []
  shellApprovalSubmittingIds.value = []
  queuedQuestions.value = []
  askUserImages.value = []
  activeTodos.value = null
  steeringResponseStarted = false
  streamingStatus.value = 'starting'
}

function traceLocationFromHash(): { sessionId: string; turnId: string | null } | null {
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

function clearTraceHash(): void {
  if (!window.location.hash.startsWith('#trace')) return
  window.history.replaceState(null, '', `${window.location.pathname}${window.location.search}`)
}

function updateTraceTurn(turnId: string): void {
  selectedTraceTurnId.value = turnId
  if (workspaceView.value === 'trace') replaceTraceHash(turnId)
}

function setWorkspaceView(next: 'workspace' | 'trace'): void {
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

async function loadInteractionTrace(sessionId = conversationId.value): Promise<void> {
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

function settleSteeringMessages(messages: readonly AnalysisMessage[]): AnalysisMessage[] {
  return messages.map((message) => (
    message.steering_status === 'waiting'
      ? { ...message, steering_status: 'responded' as const }
      : message
  ))
}

function markSteeringMessagesResponded(): void {
  if (activeTurnHistory) {
    activeTurnHistory.splice(0, activeTurnHistory.length, ...settleSteeringMessages(activeTurnHistory))
    conversation.value = [...activeTurnHistory]
    return
  }
  conversation.value = settleSteeringMessages(conversation.value)
}

function hasStreamedResponse(): boolean {
  return Boolean(streamingMessage.value || streamingReasoning.value || streamingTimeline.value.length)
}

function startTurnClock(): void {
  if (turnClock !== null) window.clearInterval(turnClock)
  turnStartedAt = performance.now()
  turnElapsedMs.value = 0
  turnClock = window.setInterval(() => {
    turnElapsedMs.value = performance.now() - turnStartedAt
  }, 200)
}

function stopTurnClock(): number {
  const duration = turnStartedAt ? performance.now() - turnStartedAt : turnElapsedMs.value
  turnElapsedMs.value = duration
  turnStartedAt = 0
  if (turnClock !== null) window.clearInterval(turnClock)
  turnClock = null
  return duration
}

function currentTurnDurationMs(): number {
  return turnStartedAt ? performance.now() - turnStartedAt : turnElapsedMs.value
}

function isRunningTurn(index: number): boolean {
  return loading.value && index === conversationTurns.value.length - 1
}

function isSteeredTurn(index: number): boolean {
  return conversationTurns.value[index + 1]?.prompt.steering_status !== undefined
}

const turnDetails = new TurnDetailsVisibility()

function isTurnDetailsOpen(turn: ConversationTurn, index: number): boolean {
  return turnDetails.isOpen(turn.id, isRunningTurn(index))
}

function turnTimeline(turn: ConversationTurn, index: number): AgentTimelineEntry[] {
  if (isRunningTurn(index)) return streamingTimeline.value
  return turn.responses.flatMap((response) => historicalTimeline(response))
}

function turnExecutionTimeline(turn: ConversationTurn, index: number): AgentTimelineEntry[] {
  return splitTurnTimeline(turnTimeline(turn, index)).execution
}

function turnAnswerTimeline(turn: ConversationTurn, index: number): AgentMessageTimelineEntry[] {
  return splitTurnTimeline(turnTimeline(turn, index)).answer
}

function turnTask(index: number): string {
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

function turnDuration(turn: ConversationTurn, index: number): string {
  if (isRunningTurn(index)) return formatTurnDuration(turnElapsedMs.value)
  return formatTurnDuration(turn.response?.duration_ms || 0)
}

function turnCacheHitRate(turn: ConversationTurn, index: number): number | null {
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

const agentResourceRefresh = createAsyncRefreshScheduler(
  async (sessionId: string) => {
    const [currentArtifacts, currentAssets] = await Promise.all([
      aiClient.listAgentArtifacts(sessionId),
      aiClient.listSessionAssets(sessionId),
    ])
    if (conversationId.value === sessionId) {
      applyArtifacts(currentArtifacts)
      assets.value = currentAssets
    }
  },
  (error, sessionId) => {
    if (conversationId.value === sessionId) showNotice(errorMessage(error), 'error')
  },
)

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

function formatToolValue(value: unknown): string {
  if (value === undefined) return 'Waiting for result…'
  if (typeof value === 'string') return value
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
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
  if (activeTurnHistory) {
    activeTurnHistory.push(nextMessage)
    conversation.value = [...activeTurnHistory]
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
  if (!activeTurnHistory || !hasStreamedResponse()) return
  activeTurnHistory.push(createStreamedAssistantMessage({
    content: streamingMessage.value,
    reasoning: streamingReasoning.value || undefined,
    activities: streamingActivities.value,
    timeline: streamingTimeline.value,
    duration_ms: currentTurnDurationMs(),
    generation_duration_ms: streamingGenerationDurationMs.value,
    usage: streamingUsage.value || undefined,
  }))
  conversation.value = [...activeTurnHistory]
  streamingMessage.value = ''
  streamingReasoning.value = ''
  streamingActivities.value = []
  streamingTimeline.value = []
  streamingUsage.value = null
  streamingGenerationDurationMs.value = 0
  modelStartedAt = 0
}

function handleSteeringStarted(message: AgentSteeringMessage): void {
  checkpointStreamedResponseForSteering()
  applyStreamedSteeringEcho(message)
  steeringResponseStarted = true
}

function streamCallbacks() {
  const sessionId = conversationId.value
  return {
    onStatus: (state: string) => { streamingStatus.value = state },
    onModelStarted: () => { modelStartedAt = performance.now() },
    onUsage: (usage: AgentModelUsage) => {
      streamingUsage.value = addAgentUsage(streamingUsage.value, usage)
      currentContextUsage.value = usage
      if (modelStartedAt) streamingGenerationDurationMs.value += performance.now() - modelStartedAt
      modelStartedAt = 0
    },
    onReasoning: (content: string) => {
      streamingStatus.value = 'reasoning'
      updateStreamText('reasoning', content)
    },
    onMessage: (content: string) => {
      if (steeringResponseStarted) {
        markSteeringMessagesResponded()
        steeringResponseStarted = false
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

function showNextAskQuestion(): void {
  pendingQuestion.value = queuedQuestions.value.shift() || null
  askAnswer.value = ''
  askUserImages.value = []
  selectedAskOptions.value = []
  streamingStatus.value = pendingQuestion.value ? 'waiting_for_user' : 'resuming'
}

function toggleAskOption(option: string): void {
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

function updateAskAnswer(value: string): void {
  askAnswer.value = value
  if (value.trim() && !pendingQuestion.value?.allowMultiple) selectedAskOptions.value = []
}

async function answerAgentQuestion(): Promise<void> {
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

async function respondToShellApproval(
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

async function attachAskUserImages(files: File[]): Promise<void> {
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

function removeAskUserImage(id: string): void {
  askUserImages.value = askUserImages.value.filter((image) => image.id !== id)
}

function handleAgentThreadScroll(): void {
  const thread = agentThread.value
  if (!thread) return
  followAgentOutput = thread.scrollHeight - thread.scrollTop - thread.clientHeight < 96
  if (!followAgentOutput && agentScrollFrame !== null) {
    window.cancelAnimationFrame(agentScrollFrame)
    agentScrollFrame = null
  }
}

function handleAgentThreadWheel(event: WheelEvent): void {
  if (event.deltaY >= 0) return
  followAgentOutput = false
  if (agentScrollFrame !== null) {
    window.cancelAnimationFrame(agentScrollFrame)
    agentScrollFrame = null
  }
}

function scrollAgentThread(force = false): void {
  void nextTick(() => {
    const thread = agentThread.value
    if (!thread || (!force && !followAgentOutput)) return
    if (agentScrollFrame !== null) window.cancelAnimationFrame(agentScrollFrame)
    agentScrollFrame = window.requestAnimationFrame(() => {
      agentScrollFrame = null
      if (!force && !followAgentOutput) return
      const bottom = Math.max(0, thread.scrollHeight - thread.clientHeight)
      if (Math.abs(thread.scrollTop - bottom) > 1) thread.scrollTop = bottom
      followAgentOutput = true
    })
  })
}

function toggleTurnExecution(turn: ConversationTurn, event: MouseEvent): void {
  const details = (event.currentTarget as HTMLElement | null)?.closest('details')
  const thread = agentThread.value
  if (!(details instanceof HTMLDetailsElement) || !thread) return
  const summary = details.querySelector(':scope > summary')
  if (!(summary instanceof HTMLElement)) return

  event.preventDefault()
  const previousTop = summary.getBoundingClientRect().top
  followAgentOutput = false
  if (agentScrollFrame !== null) {
    window.cancelAnimationFrame(agentScrollFrame)
    agentScrollFrame = null
  }
  details.open = !details.open
  turnDetails.setOpen(turn.id, details.open)
  void nextTick(() => {
    if (!details.isConnected) return
    const offset = summary.getBoundingClientRect().top - previousTop
    if (Math.abs(offset) > 1) thread.scrollTop += offset
  })
}

function clearSessionTitleRefresh(): void {
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

function scheduleSessionTitleRefresh(sessionId: string): void {
  clearSessionTitleRefresh()
  const deadline = Date.now() + 30_000
  titleRefreshTimer = window.setTimeout(
    () => void refreshSessionTitleUntilResolved(sessionId, deadline),
    800,
  )
}

watch(
  [streamingMessage, streamingReasoning, () => streamingTimeline.value.length, pendingQuestion, activeTodos],
  () => scrollAgentThread(),
)
watch(
  () => conversation.value.length,
  () => scrollAgentThread(),
)
watch(loading, (isLoading) => {
  if (isLoading) scrollAgentThread(true)
})
watch(agentTurnStack, (current, previous) => {
  if (previous) agentContentResizeObserver?.unobserve(previous)
  if (current) agentContentResizeObserver?.observe(current)
})

function toggleTag(tagId: string): void {
  const next = new Set(collapsedTagIds.value)
  if (next.has(tagId)) next.delete(tagId)
  else next.add(tagId)
  collapsedTagIds.value = next
}

async function createTag(path: string): Promise<void> {
  if (tagManagerBusy.value) return
  tagManagerFeedback.value = ''
  tagManagerBusy.value = true
  try {
    const created = await tagClient.create({ path })
    tags.value = await tagClient.list()
    tagManagerFeedbackKind.value = 'success'
    tagManagerFeedback.value = `Created “${created.path}”.`
    showNotice(`Tag “${created.path}” added`)
  } catch (error) {
    const message = errorMessage(error)
    tagManagerFeedbackKind.value = 'error'
    tagManagerFeedback.value = message
    showNotice(message, 'error')
  } finally {
    tagManagerBusy.value = false
  }
}

function openTagManager(): void {
  tagManagerFeedback.value = ''
  tagManagerFeedbackKind.value = 'success'
  tagManagerOpen.value = true
}

function tagSubtreeContains(tag: Tag, tagId: string): boolean {
  return tag.id === tagId || tag.children.some((child) => tagSubtreeContains(child, tagId))
}

async function deleteTag(tag: Tag): Promise<void> {
  if (tagManagerBusy.value) return
  const childCount = visibleTagRows(tag.children).length
  const itemCount = tag.total_count
  const scope = childCount
    ? `This also deletes ${childCount} nested ${childCount === 1 ? 'tag' : 'tags'}`
    : 'This deletes the tag'
  const assignments = itemCount
    ? ` and removes it from ${itemCount} ${itemCount === 1 ? 'artifact' : 'artifacts'}.`
    : '.'
  const confirmed = await requestConfirmation(
    `Delete “${tag.path}”?`,
    `${scope}${assignments} The artifacts themselves will remain.`,
    childCount ? 'Delete tag tree' : 'Delete tag',
  )
  if (!confirmed) return

  tagManagerBusy.value = true
  try {
    await tagClient.delete(tag.id)
    if (selectedTag.value && tagSubtreeContains(tag, selectedTag.value)) selectedTag.value = null
    const [tagData] = await Promise.all([tagClient.list(), loadLibrary()])
    tags.value = tagData
    showNotice(`Tag “${tag.path}” deleted`)
  } catch (error) {
    showNotice(errorMessage(error), 'error')
  } finally {
    tagManagerBusy.value = false
  }
}

function showNotice(message: string, kind: NoticeKind = 'success'): void {
  notice.value = message
  noticeKind.value = kind
  window.setTimeout(() => {
    if (notice.value === message) notice.value = ''
  }, 3200)
}

function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message
  return error instanceof Error ? error.message : 'Something went wrong'
}

function requestConfirmation(title: string, message: string, confirmLabel: string): Promise<boolean> {
  resolveConfirmation?.(false)
  confirmation.value = { open: true, title, message, confirmLabel }
  return new Promise((resolve) => {
    resolveConfirmation = resolve
  })
}

function settleConfirmation(confirmed: boolean): void {
  confirmation.value = { ...confirmation.value, open: false }
  resolveConfirmation?.(confirmed)
  resolveConfirmation = null
}

async function loadLibrary(): Promise<void> {
  libraryLoading.value = true
  try {
    libraryItems.value = await libraryClient.list({
      query: view.value === 'search' ? activeQuery.value : '',
      tagId: selectedTag.value,
      artifactTypes: selectedLibraryType.value ? [selectedLibraryType.value] : undefined,
    })
  } catch (error) {
    showNotice(errorMessage(error), 'error')
  } finally {
    libraryLoading.value = false
  }
}

async function loadInitialData(): Promise<void> {
  usageActivityLoading.value = true
  try {
    const [
      tagData,
      libraryData,
      providerData,
      runtimeSettingsData,
      usageActivityData,
      modelUsageActivityData,
    ] = await Promise.all([
      tagClient.list(),
      libraryClient.list(),
      aiClient.listProviders(),
      settingsClient.get(),
      settingsClient.getUsageActivity().catch(() => []),
      settingsClient.getModelUsageActivity(30).catch(() => []),
    ])
    tags.value = tagData
    libraryItems.value = libraryData
    providers.value = providerData
    runtimeSettings.value = runtimeSettingsData
    usageActivity.value = usageActivityData
    modelUsageActivity.value = modelUsageActivityData
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

async function selectSettingsSection(section: SettingsSection): Promise<void> {
  if (settingsSection.value === section) return
  settingsSection.value = section
  if (section !== 'usage') return
  usageActivityLoading.value = true
  try {
    const [usageActivityData, modelUsageActivityData] = await Promise.all([
      settingsClient.getUsageActivity(),
      settingsClient.getModelUsageActivity(30),
    ])
    usageActivity.value = usageActivityData
    modelUsageActivity.value = modelUsageActivityData
  } catch (error) {
    showNotice(errorMessage(error), 'error')
  } finally {
    usageActivityLoading.value = false
  }
}

function navigate(nextView: View): void {
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

function openSearch(): void {
  view.value = 'search'
  void nextTick(() => searchInput.value?.focus())
}

function handleShortcut(event: KeyboardEvent): void {
  if (event.key === 'Escape' && fullscreenSlidesItem.value) {
    void closeSlidesFullscreen()
    return
  }
  if (event.key === 'Escape' && libraryEditorItem.value) return
  if (event.key === 'Escape' && selectedLibraryItem.value) {
    selectedLibraryItem.value = null
    return
  }
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
    event.preventDefault()
    openSearch()
  }
}

function changeLocale(event: Event): void {
  setLocale((event.target as HTMLSelectElement).value as Locale)
}

function openLibraryItem(item: LibraryItem): void {
  selectedLibraryItem.value = item
}

function openLibraryEditor(item: LibraryItem): void {
  if (item.item_type === 'latex_pdf') return
  selectedLibraryItem.value = null
  libraryEditorArtifactId.value = null
  libraryEditorItem.value = item
}

function openSelectedArtifactEditor(): void {
  const artifact = selectedArtifact.value
  if (!artifact) return
  const item = libraryItemFromArtifact(artifact)
  if (!item) return
  libraryEditorArtifactId.value = artifact.id
  libraryEditorItem.value = item
}

async function closeLibraryEditor(dirty: boolean): Promise<void> {
  if (libraryEditorSaving.value) return
  if (dirty) {
    const confirmed = await requestConfirmation(
      'Discard unsaved changes?',
      'Your edits have not been saved. Leaving the editor will discard them.',
      'Discard changes',
    )
    if (!confirmed) return
  }
  libraryEditorItem.value = null
  libraryEditorArtifactId.value = null
}

async function saveLibraryEditor(payload: LibraryItemUpdate): Promise<void> {
  const item = libraryEditorItem.value
  if (!item || libraryEditorSaving.value) return
  libraryEditorSaving.value = true
  try {
    const artifactId = libraryEditorArtifactId.value
    if (artifactId !== null) {
      const artifact = artifacts.value.find((candidate) => candidate.id === artifactId)
      if (!artifact) return
      const content = artifactEditableContent(artifact)
      if (!content) return
      artifactContent.value = artifactContentFromLibraryUpdate(content, payload)
      // The editor stages the draft; publishing stays a separate action.
      await syncSelectedArtifactDraft()
      const updated = artifacts.value.find((candidate) => candidate.id === artifactId)
      const updatedItem = updated ? libraryItemFromArtifact(updated) : null
      if (updatedItem) libraryEditorItem.value = updatedItem
      showNotice('Draft updated — review the diff and save to publish it')
      return
    }

    const updated = await libraryClient.update(item.item_type, item.id, payload)
    libraryItems.value = libraryItems.value.map((candidate) => (
      candidate.item_type === updated.item_type && candidate.id === updated.id ? updated : candidate
    ))
    libraryEditorItem.value = updated
    if (selectedLibraryItem.value?.item_type === updated.item_type && selectedLibraryItem.value.id === updated.id) {
      selectedLibraryItem.value = updated
    }
    tags.value = await tagClient.list()
    showNotice(`${artifactTypeLabel(updated.item_type)} saved`)
  } catch (error) {
    showNotice(errorMessage(error), 'error')
  } finally {
    libraryEditorSaving.value = false
  }
}

async function copyLibraryItemId(item: LibraryItem): Promise<void> {
  try {
    await navigator.clipboard.writeText(item.id)
    showNotice('Resource ID copied')
  } catch {
    showNotice('Could not copy the resource ID', 'error')
  }
}

function startLibraryItemDrag(item: LibraryItem, event: DragEvent): void {
  draggingLibraryItem.value = item
  tagDropTargetId.value = null
  if (!event.dataTransfer) return
  event.dataTransfer.effectAllowed = 'copy'
  event.dataTransfer.setData('application/x-zett-artifact-id', item.id)
  event.dataTransfer.setData('text/plain', item.id)
}

function endLibraryItemDrag(): void {
  draggingLibraryItem.value = null
  tagDropTargetId.value = null
}

/** What a drag carries: a library artifact, or a static asset from the asset view. */
type DraggedResource =
  | { kind: 'artifact'; item: LibraryItem }
  | { kind: 'asset'; asset: StaticAsset }

function startStaticAssetDrag(asset: StaticAsset): void {
  draggingStaticAsset.value = asset
  tagDropTargetId.value = null
}

function endStaticAssetDrag(): void {
  draggingStaticAsset.value = null
  tagDropTargetId.value = null
}

function draggedResource(event: DragEvent): DraggedResource | null {
  if (draggingLibraryItem.value) return { kind: 'artifact', item: draggingLibraryItem.value }
  if (draggingStaticAsset.value) return { kind: 'asset', asset: draggingStaticAsset.value }
  const artifactId = event.dataTransfer?.getData('application/x-zett-artifact-id')
    || event.dataTransfer?.getData('text/plain')
  const item = libraryItems.value.find((candidate) => candidate.id === artifactId)
  return item ? { kind: 'artifact', item } : null
}

function handleTagDragOver(tag: Tag, event: DragEvent): void {
  const dragged = draggedResource(event)
  if (!dragged || tagAssignmentBusy.value) return
  event.preventDefault()
  if (event.dataTransfer) event.dataTransfer.dropEffect = 'copy'
  tagDropTargetId.value = tag.id
}

function handleTagDragLeave(tag: Tag, event: DragEvent): void {
  const row = event.currentTarget
  if (row instanceof HTMLElement && event.relatedTarget instanceof Node && row.contains(event.relatedTarget)) return
  if (tagDropTargetId.value === tag.id) tagDropTargetId.value = null
}

function applyArtifactTags(artifact: AgentArtifact): void {
  const paths = artifact.tags.map((tag) => tag.path)
  const updateItem = (item: LibraryItem): LibraryItem => (
    item.id === artifact.id ? { ...item, tags: paths, updated_at: artifact.updated_at } : item
  )
  libraryItems.value = libraryItems.value.map(updateItem)
  if (selectedLibraryItem.value) selectedLibraryItem.value = updateItem(selectedLibraryItem.value)
}

async function dropResourceOnTag(tag: Tag, event: DragEvent): Promise<void> {
  const dragged = draggedResource(event)
  if (!dragged || tagAssignmentBusy.value) return
  event.preventDefault()
  const current = dragged.kind === 'artifact' ? dragged.item.tags : dragged.asset.tags.map((item) => item.path)
  const assignment = addTagPath(current, tag.path)
  const label = dragged.kind === 'artifact' ? dragged.item.title : dragged.asset.name
  if (!assignment.changed) {
    showNotice(`“${label}” is already in ${tag.path}`)
    endLibraryItemDrag()
    endStaticAssetDrag()
    return
  }

  tagAssignmentBusy.value = true
  try {
    if (dragged.kind === 'artifact') {
      applyArtifactTags(await tagClient.replaceArtifactTags(dragged.item.id, assignment.paths))
    } else {
      applyAssetTags(await tagClient.replaceAssetTags(dragged.asset.id, assignment.paths))
    }
    tags.value = await tagClient.list()
    showNotice(`Added “${label}” to ${tag.path}`)
  } catch (error) {
    showNotice(errorMessage(error), 'error')
  } finally {
    tagAssignmentBusy.value = false
    endLibraryItemDrag()
    endStaticAssetDrag()
  }
}

/** Keep both asset lists in step: this view's, and the one the asset view owns. */
function applyAssetTags(asset: StaticAsset): void {
  staticAssets.value = staticAssets.value.map((item) => (item.id === asset.id ? asset : item))
  void staticAssetsView.value?.reload()
}

async function deleteLibraryItem(item: LibraryItem): Promise<void> {
  if (deletingLibraryItemId.value !== null) return
  const confirmed = await requestConfirmation(
    `Delete this ${item.item_type}?`,
    `“${item.title}” will be permanently removed from artifacts. This action cannot be undone.`,
    `Delete ${item.item_type}`,
  )
  if (!confirmed) return
  deletingLibraryItemId.value = item.id
  try {
    await libraryClient.delete(item.item_type, item.id)
    libraryItems.value = libraryItems.value.filter((candidate) => candidate.id !== item.id)
    if (selectedLibraryItem.value?.id === item.id) selectedLibraryItem.value = null
    if (libraryEditorItem.value?.id === item.id) {
      libraryEditorItem.value = null
      libraryEditorArtifactId.value = null
    }
    tags.value = await tagClient.list()
    showNotice(`${item.item_type === 'article' ? 'Article' : 'Card'} deleted`)
  } catch (error) {
    showNotice(errorMessage(error), 'error')
  } finally {
    deletingLibraryItemId.value = null
  }
}

async function deleteSelectedLibraryItem(): Promise<void> {
  if (selectedLibraryItem.value) await deleteLibraryItem(selectedLibraryItem.value)
}

async function search(): Promise<void> {
  activeQuery.value = query.value.trim()
  selectedTag.value = null
  view.value = 'search'
  await loadLibrary()
}

async function filterByTag(tagId: string | null): Promise<void> {
  selectedTag.value = tagId
  activeQuery.value = ''
  query.value = ''
  view.value = 'library'
  await loadLibrary()
}

async function filterByArtifactType(artifactType: LibraryItem['item_type'] | null): Promise<void> {
  selectedLibraryType.value = artifactType
  await loadLibrary()
}

async function analyze(): Promise<void> {
  if (!raw.value.trim() && !pendingMessageImages.value.length) return
  if (selectedProviderId.value === null) {
    showNotice('Add and select an AI provider first', 'error')
    view.value = 'settings'
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
  activeTurnHistory = requestHistory
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
    if (activeTurnHistory === requestHistory) activeTurnHistory = null
    pendingSteeringEchoes.length = 0
    if (streamingStatus.value !== 'cancelled') streamingStatus.value = 'idle'
    await refreshArtifactsAfterTurn(activeConversationId)
    if (workspaceView.value === 'trace' && activeConversationId) void loadInteractionTrace(activeConversationId)
    drainQueuedFollowUps()
  }
}

async function refine(queued?: QueuedFollowUp): Promise<void> {
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
  activeTurnHistory = history
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
    if (activeTurnHistory === history) activeTurnHistory = null
    pendingSteeringEchoes.length = 0
    if (streamingStatus.value !== 'cancelled') streamingStatus.value = 'idle'
    await refreshArtifactsAfterTurn(activeConversationId)
    if (workspaceView.value === 'trace' && activeConversationId) void loadInteractionTrace(activeConversationId)
    drainQueuedFollowUps()
  }
}

function queueFollowUp(): void {
  const content = followUp.value
  if (!content.trim() && !pendingMessageImages.value.length) return
  const parts = buildMessageParts(content, pendingMessageImages.value)
  const slashCommandId = slashCommandIdFor(content)
  const atCommandId = atCommandIdFor(content)
  queuedFollowUps.value.push({
    id: nextQueuedFollowUpId++,
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

function drainQueuedFollowUps(): void {
  if (loading.value || !queuedFollowUps.value.length) return
  const [next, ...remaining] = queuedFollowUps.value
  queuedFollowUps.value = remaining
  if (next) void refine(next)
}

function queuedFollowUpText(item: QueuedFollowUp): string {
  const text = item.content.trim()
  if (text) return text
  const imageCount = item.parts.filter((part) => part.type === 'image').length
  return imageCount === 1 ? 'Image attachment' : `${imageCount} image attachments`
}

function removeQueuedFollowUp(item: QueuedFollowUp): void {
  queuedFollowUps.value = queuedFollowUps.value.filter((queued) => queued.id !== item.id)
}

function startQueuedFollowUpDrag(item: QueuedFollowUp, event: DragEvent): void {
  draggingQueuedFollowUpId.value = item.id
  if (event.dataTransfer) {
    event.dataTransfer.effectAllowed = 'move'
    event.dataTransfer.setData('text/plain', String(item.id))
  }
}

function dropQueuedFollowUp(target: QueuedFollowUp, event: DragEvent): void {
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

function endQueuedFollowUpDrag(): void {
  draggingQueuedFollowUpId.value = null
}

async function steerQueuedFollowUp(item: QueuedFollowUp): Promise<void> {
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

function submitConversation(): void {
  if (loading.value) {
    queueFollowUp()
    return
  }
  if (conversationStarted.value) void refine()
  else void analyze()
}

function stopGeneration(): void {
  pendingQuestion.value = null
  pendingShellApprovals.value = []
  shellApprovalSubmittingIds.value = []
  queuedQuestions.value = []
  queuedFollowUps.value = []
  activeTodos.value = null
  activeStreamController.value?.abort()
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError'
}

async function ensureConversation(): Promise<string> {
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

function applySession(session: AgentSession): void {
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
  followAgentOutput = true
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

async function restoreSessionContextComposition(sessionId: string): Promise<void> {
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

async function updateShellApprovalMode(mode: ShellApprovalMode): Promise<void> {
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

async function restoreSessionRuntime(sessionId: string): Promise<void> {
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

function prefetchSession(sessionId: string): void {
  if (sessionId === conversationId.value || loading.value || sessionDetailRequests.has(sessionId)) return
  void loadSessionDetail(sessionId).catch(() => undefined)
}

async function openSession(sessionId: string): Promise<void> {
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
  const generation = ++sessionSwitchGeneration
  switchingSessionId.value = sessionId
  view.value = 'new'
  try {
    const session = await loadSessionDetail(sessionId)
    if (generation !== sessionSwitchGeneration) return
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
    if (generation === sessionSwitchGeneration) showNotice(errorMessage(error), 'error')
  } finally {
    if (generation === sessionSwitchGeneration) switchingSessionId.value = null
  }
}

async function openScheduledSession(sessionId: string): Promise<void> {
  sessionScope.value = 'scheduled'
  await openSession(sessionId)
}

async function openChannelSession(sessionId: string): Promise<void> {
  sessionScope.value = 'channel'
  await openSession(sessionId)
}

async function openArtifactSession(item: LibraryItem): Promise<void> {
  selectedLibraryItem.value = null
  libraryPdfLaunch.value = null
  await openSession(item.session_id)
}

function startSessionTitleEdit(session: AgentSession): void {
  editingSessionId.value = session.id
  sessionTitleDraft.value = session.title || '新会话'
}

function cancelSessionTitleEdit(): void {
  editingSessionId.value = null
  sessionTitleDraft.value = ''
}

function handleSessionTitleFocusOut(event: FocusEvent): void {
  const editor = event.currentTarget
  const nextTarget = event.relatedTarget
  if (!(editor instanceof HTMLFormElement)) return
  if (nextTarget instanceof Node && editor.contains(nextTarget)) return
  cancelSessionTitleEdit()
}

async function saveSessionTitle(sessionId: string): Promise<void> {
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

async function deleteSession(session: AgentSession): Promise<void> {
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

async function loadSessions(reset = false): Promise<void> {
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

async function loadScheduledSessions(reset = false): Promise<void> {
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

async function loadChannelSessions(reset = false): Promise<void> {
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

function handleSessionListScroll(): void {
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

function selectArtifact(artifact: AgentArtifact): void {
  const artifactChanged = selectedArtifactId.value !== artifact.id
  const current = selectedArtifact.value
  if (!artifactChanged && current && artifactContent.value && sameArtifactRevision(current, artifact)) return
  const content = artifactEditableContent(artifact)
  if (!content) return
  selectedArtifactId.value = artifact.id
  artifactContent.value = jsonSnapshot(content)
  selectedSuggestions.value = content.artifact_type === 'latex_pdf' ? [] : content.suggested_tags.map((tag) => tag.path)
  if (artifactChanged) {
    artifactPreview.value = true
    artifactDiff.value = false
  }
}

function applyArtifacts(nextArtifacts: AgentArtifact[], preferLatest = true): void {
  const stableArtifacts = stabilizeArtifactReferences(artifacts.value, nextArtifacts)
  if (artifactListsEquivalent(artifacts.value, stableArtifacts)) return
  artifacts.value = stableArtifacts
  if (!stableArtifacts.length) {
    selectedArtifactId.value = null
    artifactContent.value = null
    return
  }
  const current = stableArtifacts.find((artifact) => artifact.id === selectedArtifactId.value)
  const target = preferLatest
    ? [...stableArtifacts].sort((left, right) => right.updated_at.localeCompare(left.updated_at))[0]
    : current || stableArtifacts[0]
  if (target) selectArtifact(target)
}

async function refreshArtifacts(preferLatest = false): Promise<void> {
  const activeConversationId = conversationId.value
  if (!activeConversationId) return
  const listed = await aiClient.listAgentArtifacts(activeConversationId)
  // A conversation switch while this request was open must not move another session's artifacts into view.
  if (conversationId.value !== activeConversationId) return
  applyArtifacts(listed, preferLatest)
}

/**
 * Re-read the conversation's artifacts and force the preview to load again, so a
 * PDF compiled after the pane opened replaces the bytes shown in the pane.
 */
async function refreshSelectedArtifact(): Promise<void> {
  const activeConversationId = conversationId.value
  if (!activeConversationId || artifactRefreshing.value) return
  artifactRefreshing.value = true
  try {
    const listed = await aiClient.listAgentArtifacts(activeConversationId)
    if (conversationId.value !== activeConversationId) return
    applyArtifacts(listed)
    artifactPreviewNonce.value += 1
  } catch (error) {
    showNotice(errorMessage(error), 'error')
  } finally {
    artifactRefreshing.value = false
  }
}

async function refreshArtifactsAfterTurn(sessionId: string | null): Promise<void> {
  if (!sessionId) return
  await agentResourceRefresh.whenIdle()
  if (conversationId.value !== sessionId) return
  try {
    await refreshArtifacts(true)
  } catch (error) {
    showNotice(errorMessage(error), 'error')
  }
}

/**
 * Persist the panel's edits as a draft. Editing never rewrites published
 * content; the save action is what publishes a draft.
 */
async function syncSelectedArtifactDraft(): Promise<void> {
  const current = selectedArtifact.value
  if (!conversationId.value || !selectedArtifactId.value || !artifactContent.value || !current) return
  const updated = await aiClient.updateAgentArtifactDraft(
    conversationId.value,
    selectedArtifactId.value,
    artifactContent.value,
  )
  const index = artifacts.value.findIndex((artifact) => artifact.id === updated.id)
  if (index >= 0) artifacts.value.splice(index, 1, updated)
}

function clearWorkspaceState(): void {
  sessionSwitchGeneration += 1
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

async function resetWorkspace(): Promise<void> {
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

function showAssetEditor(mode: Exclude<AssetEditorMode, 'closed'>): void {
  assetEditorMode.value = assetEditorMode.value === mode ? 'closed' : mode
  assetName.value = ''
  assetValue.value = ''
}

function toggleAssetsPane(hidden: boolean): void {
  assetsPaneHidden.value = hidden
  writePaneHidden(assetsPaneKey, hidden)
  // The preview must refit before this frame paints: a resize observer reports the new
  // stage width only after the wrong-scale frame is already on screen.
  void nextTick().then(() => pdfPreviewRef.value?.refit())
}

async function addInlineAsset(): Promise<void> {
  if (!assetName.value.trim() || !assetValue.value.trim()) return
  assetUploading.value = true
  try {
    const sessionId = await ensureConversation()
    const asset = assetEditorMode.value === 'link'
      ? await aiClient.createLinkAsset(sessionId, assetName.value.trim(), assetValue.value.trim())
      : await aiClient.createTextAsset(sessionId, assetName.value.trim(), assetValue.value)
    assets.value.push(asset)
    assetEditorMode.value = 'closed'
    assetName.value = ''
    assetValue.value = ''
  } catch (error) {
    showNotice(errorMessage(error), 'error')
  } finally {
    assetUploading.value = false
  }
}

async function openStaticAssetImport(): Promise<void> {
  staticAssetImportOpen.value = true
  staticAssetsLoading.value = true
  try {
    staticAssets.value = await assetClient.list()
  } catch (error) {
    showNotice(errorMessage(error), 'error')
  } finally {
    staticAssetsLoading.value = false
  }
}

async function importStaticAsset(asset: StaticAsset): Promise<void> {
  if (staticAssetImportingId.value !== null) return
  staticAssetImportingId.value = asset.id
  try {
    const sessionId = await ensureConversation()
    const imported = await aiClient.importStaticAsset(sessionId, asset.id)
    assets.value.push(imported)
    showNotice(t('Referenced “{name}” from Static Assets', { name: asset.name }))
  } catch (error) {
    showNotice(errorMessage(error), 'error')
  } finally {
    staticAssetImportingId.value = null
  }
}

async function uploadAssets(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const files = Array.from(input.files || [])
  await uploadAssetFiles(files)
  input.value = ''
}

async function uploadAssetFiles(files: File[]): Promise<void> {
  if (!files.length || assetUploading.value) return
  assetUploading.value = true
  try {
    const sessionId = await ensureConversation()
    for (const file of files) assets.value.push(await aiClient.uploadAsset(sessionId, file))
  } catch (error) {
    showNotice(errorMessage(error), 'error')
  } finally {
    assetUploading.value = false
  }
}

async function dropAssets(event: DragEvent): Promise<void> {
  assetDragging.value = false
  await uploadAssetFiles(Array.from(event.dataTransfer?.files || []))
}

function readMessageImage(file: File, position: number): Promise<PositionedMessageImage> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onerror = () => reject(reader.error || new Error(`Unable to read ${file.name}`))
    reader.onload = () => {
      const contentUrl = typeof reader.result === 'string' ? reader.result : ''
      const separator = contentUrl.indexOf(',')
      if (separator < 0) {
        reject(new Error(`Unable to encode ${file.name}`))
        return
      }
      resolve({
        id: crypto.randomUUID(),
        type: 'image',
        name: file.name || 'Pasted image',
        mime_type: file.type,
        content_url: contentUrl,
        position,
      })
    }
    reader.readAsDataURL(file)
  })
}

async function attachPastedImages(files: File[], position: number): Promise<void> {
  const available = Math.max(0, runtimeSettings.value.max_message_images - pendingMessageImages.value.length)
  const images = files.filter((file) => file.type.startsWith('image/')).slice(0, available)
  if (!images.length) return
  try {
    pendingMessageImages.value.push(...await Promise.all(images.map((file) => readMessageImage(file, position))))
    if (images.length < files.filter((file) => file.type.startsWith('image/')).length) {
      showNotice(`A message can contain up to ${runtimeSettings.value.max_message_images} images`, 'error')
    }
  } catch (error) {
    showNotice(errorMessage(error), 'error')
  }
}

function removeMessageImage(id: string): void {
  pendingMessageImages.value = pendingMessageImages.value.filter((image) => image.id !== id)
}

function rebaseMessageImagePositions(previous: string, next: string): void {
  pendingMessageImages.value = rebaseImagePositions(pendingMessageImages.value, previous, next)
}

function composerTextarea(target: ComposerTarget): HTMLTextAreaElement | null {
  return target === 'initial' ? initialComposerInput.value : followUpComposerInput.value
}

function composerTextValue(target: ComposerTarget): string {
  return target === 'initial' ? raw.value : followUp.value
}

function composerHighlight(target: ComposerTarget): HTMLElement | null {
  return target === 'initial' ? initialComposerHighlight.value : followUpComposerHighlight.value
}

/**
 * Highlight every composer token the backend can resolve for this text: the
 * selected slash command and any `@` reference that matches a listed resource.
 * The textarea stays transparent above this mirror so both kinds read as chips.
 */
function composerHighlightSegments(target: ComposerTarget): ComposerHighlightSegment[] | null {
  const value = composerTextValue(target)
  const marked: Array<{ start: number; end: number; kind: 'slash' | 'reference' }> = []
  const slash = detectedSlashCommand(value)
  if (slash) marked.push({ ...slash.range, kind: 'slash' })
  for (const token of AtCommandInput.tokens(value)) {
    const reference = atCommands.value.find(item => item.name === token.name)
    if (reference) marked.push({ start: token.start, end: token.end, kind: 'reference' })
  }
  if (!marked.length) return null
  marked.sort((left, right) => left.start - right.start)
  const segments: ComposerHighlightSegment[] = []
  let cursor = 0
  for (const span of marked) {
    if (span.start < cursor) continue
    if (span.start > cursor) segments.push({ text: value.slice(cursor, span.start), kind: null })
    segments.push({ text: value.slice(span.start, span.end), kind: span.kind })
    cursor = span.end
  }
  if (cursor < value.length) segments.push({ text: value.slice(cursor), kind: null })
  return segments
}

function detectedSlashCommand(value: string): { command: AgentSlashCommand; range: { start: number; end: number } } | null {
  const selected = selectedSlashCommand.value
  if (selected) {
    const range = SlashCommandInput.range(value, selected.name)
    if (range) return { command: selected, range }
  }
  for (const token of SlashCommandInput.tokens(value)) {
    const command = slashCommands.value.find(item => item.name === token.name)
    if (command) return { command, range: { start: token.start, end: token.end } }
  }
  return null
}

function slashCommandIdFor(value: string): string | null {
  return detectedSlashCommand(value)?.command.id ?? null
}

/**
 * Resolve the `@` tokens a message already contains. Like the slash command
 * lookup, the browser submits at most one reference: the first token that still
 * matches a listed resource owns the turn.
 */
function atCommandIdFor(value: string): string | null {
  for (const token of AtCommandInput.tokens(value)) {
    const reference = atCommands.value.find(item => item.name === token.name)
    if (reference) return reference.id
  }
  return null
}

function syncComposerHighlight(target: ComposerTarget): void {
  const textarea = composerTextarea(target)
  const highlight = composerHighlight(target)
  if (!textarea || !highlight) return
  highlight.scrollTop = textarea.scrollTop
  highlight.scrollLeft = textarea.scrollLeft
}

function finishComposerComposition(): void {
  window.requestAnimationFrame(() => {
    composerComposing.value = false
    syncComposerHighlight(conversationStarted.value ? 'follow-up' : 'initial')
  })
}

function setComposerTextValue(target: ComposerTarget, value: string): void {
  if (target === 'initial') raw.value = value
  else followUp.value = value
}

function clearSlashCommand(): void {
  selectedSlashCommand.value = null
  slashMenu.value = null
  atMenu.value = null
  composerComposing.value = false
}

async function loadAtCommands(force = false): Promise<void> {
  const sessionId = conversationId.value
  if (!sessionId) {
    atCommands.value = []
    atCommandsLoaded.value = true
    return
  }
  if (atCommandsLoaded.value && !force) return
  atCommandsLoading.value = true
  try {
    const commands = await aiClient.listAtCommands(sessionId)
    if (conversationId.value === sessionId) {
      atCommands.value = commands
      atCommandsLoaded.value = true
    }
  } catch (error) {
    showNotice(errorMessage(error), 'error')
  } finally {
    if (conversationId.value === sessionId) atCommandsLoading.value = false
  }
}

function refreshAtMenu(target: ComposerTarget, value: string, caret: number): void {
  if (!atCommandsLoaded.value && !atCommandsLoading.value && AtCommandInput.tokenNames(value).length) {
    void loadAtCommands()
  }
  const match = AtCommandInput.match(value, caret)
  if (!match) {
    if (atMenu.value?.target === target) atMenu.value = null
    return
  }
  const current = atMenu.value
  const sameRange = current?.target === target
    && current.match.start === match.start
  atMenu.value = {
    target,
    match,
    activeIndex: sameRange ? current.activeIndex : 0,
  }
  // References are created and deleted during the session, so every new token
  // refreshes the list while repeated keystrokes reuse the loaded one.
  if (!atCommandsLoading.value) void loadAtCommands(!sameRange)
}

function selectAtCommand(index: number): void {
  const menu = atMenu.value
  const command = atMenuCommands.value[index]
  if (!menu || !command) return
  const textarea = composerTextarea(menu.target)
  const insertion = AtCommandInput.insert(composerTextValue(menu.target), menu.match, command.name)
  setComposerTextValue(menu.target, insertion.value)
  atMenu.value = null
  composerComposing.value = false
  void nextTick(() => {
    textarea?.focus()
    textarea?.setSelectionRange(insertion.caret, insertion.caret)
    syncComposerHighlight(menu.target)
  })
}

function deleteReferenceToken(event: KeyboardEvent, target: ComposerTarget): boolean {
  if (event.key !== 'Backspace' && event.key !== 'Delete') return false
  const textarea = composerTextarea(target)
  if (!textarea) return false
  const value = textarea.value
  const selectionStart = textarea.selectionStart ?? 0
  const selectionEnd = textarea.selectionEnd ?? 0
  const token = AtCommandInput.tokens(value).find((candidate) => (
    event.key === 'Backspace'
      ? selectionStart >= candidate.start && selectionStart <= candidate.end + 1
      : selectionStart >= candidate.start - 1 && selectionStart <= candidate.end
  ))
  if (!token || !atCommands.value.some(item => item.name === token.name)) return false
  const deletion = AtCommandInput.deleteAtomically(
    value,
    token.name,
    selectionStart,
    selectionEnd,
    event.key,
  )
  if (!deletion) return false
  event.preventDefault()
  setComposerTextValue(target, deletion.value)
  atMenu.value = null
  void nextTick(() => {
    textarea.focus()
    textarea.setSelectionRange(deletion.caret, deletion.caret)
    syncComposerHighlight(target)
  })
  return true
}

async function loadSlashCommands(force = false): Promise<void> {
  const sessionId = conversationId.value
  if (!sessionId) {
    slashCommands.value = []
    slashCommandsLoaded.value = true
    return
  }
  if (slashCommandsLoaded.value && !force) return
  slashCommandsLoading.value = true
  try {
    const commands = await aiClient.listSlashCommands(sessionId)
    if (conversationId.value === sessionId) {
      slashCommands.value = commands
      slashCommandsLoaded.value = true
    }
  } catch (error) {
    showNotice(errorMessage(error), 'error')
  } finally {
    if (conversationId.value === sessionId) slashCommandsLoading.value = false
  }
}

function refreshSlashMenu(target: ComposerTarget, value: string, caret: number): void {
  if (!slashCommandsLoaded.value && !slashCommandsLoading.value && SlashCommandInput.tokenNames(value).length) {
    void loadSlashCommands()
  }
  if (selectedSlashCommand.value) {
    if (SlashCommandInput.contains(value, selectedSlashCommand.value.name)) {
      slashMenu.value = null
      return
    }
    selectedSlashCommand.value = null
  }
  const match = SlashCommandInput.match(value, caret)
  if (!match) {
    if (slashMenu.value?.target === target) slashMenu.value = null
    return
  }
  const current = slashMenu.value
  const sameRange = current?.target === target
    && current.match.start === match.start
  slashMenu.value = {
    target,
    match,
    activeIndex: sameRange ? current.activeIndex : 0,
  }
  if (!slashCommandsLoading.value) void loadSlashCommands(!sameRange)
}

function selectSlashCommand(index: number): void {
  const menu = slashMenu.value
  const command = slashMenuCommands.value[index]
  if (!menu || !command) return
  const textarea = composerTextarea(menu.target)
  const insertion = SlashCommandInput.insert(composerTextValue(menu.target), menu.match, command.name)
  setComposerTextValue(menu.target, insertion.value)
  selectedSlashCommand.value = command
  slashMenu.value = null
  composerComposing.value = false
  void nextTick(() => {
    textarea?.focus()
    textarea?.setSelectionRange(insertion.caret, insertion.caret)
    syncComposerHighlight(menu.target)
  })
}

function deleteSelectedSlashCommand(event: KeyboardEvent, target: ComposerTarget): boolean {
  if (event.key !== 'Backspace' && event.key !== 'Delete') return false
  const command = selectedSlashCommand.value
  const textarea = composerTextarea(target)
  if (!command || !textarea) return false
  const deletion = SlashCommandInput.deleteAtomically(
    textarea.value,
    command.name,
    textarea.selectionStart ?? 0,
    textarea.selectionEnd ?? 0,
    event.key,
  )
  if (!deletion) return false
  event.preventDefault()
  setComposerTextValue(target, deletion.value)
  clearSlashCommand()
  void nextTick(() => {
    textarea.focus()
    textarea.setSelectionRange(deletion.caret, deletion.caret)
    syncComposerHighlight(target)
  })
  return true
}

function handleComposerKeydown(event: KeyboardEvent, target: ComposerTarget): void {
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

function handleComposerSelection(target: ComposerTarget, event: MouseEvent): void {
  const textarea = event.currentTarget
  if (!(textarea instanceof HTMLTextAreaElement)) return
  refreshSlashMenu(target, textarea.value, textarea.selectionStart ?? textarea.value.length)
  refreshAtMenu(target, textarea.value, textarea.selectionStart ?? textarea.value.length)
}

function updateComposerText(event: Event, target: 'initial' | 'follow-up'): void {
  const textarea = event.target as HTMLTextAreaElement
  const next = textarea.value
  const previous = target === 'initial' ? raw.value : followUp.value
  rebaseMessageImagePositions(previous, next)
  setComposerTextValue(target, next)
  refreshSlashMenu(target, next, textarea.selectionStart ?? next.length)
  refreshAtMenu(target, next, textarea.selectionStart ?? next.length)
  void nextTick(() => syncComposerHighlight(target))
}

async function pasteAssets(event: ClipboardEvent): Promise<void> {
  const clipboard = event.clipboardData
  if (!clipboard) return
  const itemFiles = Array.from(clipboard.items)
    .filter((item) => item.kind === 'file')
    .map((item) => item.getAsFile())
    .filter((file): file is File => file !== null)
  const files = itemFiles.length ? itemFiles : Array.from(clipboard.files)
  const target = event.target
  const insideComposer = target instanceof Element && target.closest('.agent-input textarea') !== null
  const editableTarget = target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement
  if (insideComposer && files.some((file) => file.type.startsWith('image/'))) {
    event.preventDefault()
    const position = target instanceof HTMLTextAreaElement ? target.selectionStart ?? target.value.length : 0
    await attachPastedImages(files, position)
    return
  }
  if (editableTarget && files.length) return
  if (files.length) {
    if (assetUploading.value) return
    event.preventDefault()
    await uploadAssetFiles(files)
    showNotice(`${files.length} pasted ${files.length === 1 ? 'asset' : 'assets'} added`)
    return
  }

  const insideAssetPane = target instanceof Element && target.closest('.assets-pane') !== null
  if (!insideAssetPane || editableTarget) return
  const content = clipboard.getData('text/plain').trim()
  if (!content) return
  event.preventDefault()
  assetUploading.value = true
  try {
    const sessionId = await ensureConversation()
    let asset: SessionAsset
    try {
      const url = new URL(content)
      asset = await aiClient.createLinkAsset(sessionId, url.hostname || 'Pasted link', url.toString())
    } catch {
      const timestamp = new Date().toISOString().slice(0, 19).replaceAll(':', '-')
      asset = await aiClient.createTextAsset(sessionId, `Pasted note ${timestamp}`, content)
    }
    assets.value.push(asset)
    showNotice('Pasted asset added')
  } catch (error) {
    showNotice(errorMessage(error), 'error')
  } finally {
    assetUploading.value = false
  }
}

async function renameAsset(asset: SessionAsset, name: string): Promise<void> {
  const updated = await aiClient.renameSessionAsset(asset.session_id, asset.id, name)
  // A late response from a previous session must not change the visible list.
  if (conversationId.value !== asset.session_id) return
  assets.value = assets.value.map(item => item.id === asset.id ? updated : item)
  if (previewAsset.value?.id === asset.id) previewAsset.value = updated
}

function openAsset(asset: SessionAsset): void {
  const action = assetOpenAction(asset)
  if (!action) return
  if (action.kind === 'preview') {
    previewAsset.value = asset
    return
  }
  window.open(action.url, '_blank', 'noopener,noreferrer')
}

function openImagePreview(image: { name: string; url: string }): void {
  previewAsset.value = {
    id: `message-image-${image.name}`,
    session_id: conversationId.value || '',
    asset_type: 'image',
    name: image.name,
    mime_type: null,
    size_bytes: 0,
    sha256: null,
    text_content: null,
    source_url: null,
    storage_path: null,
    source_path: null,
    content_url: image.url,
    metadata: {},
    created_at: '',
    updated_at: '',
  }
}

function openMessageImage(part: MessageImagePart): void {
  openImagePreview({ name: part.name, url: part.content_url })
}

async function removeAsset(asset: SessionAsset): Promise<void> {
  if (!conversationId.value) return
  const message = asset.metadata.import_mode === 'object'
    ? `“${asset.name}” will be removed from this conversation. The Static Asset itself will remain available.`
    : `“${asset.name}” will be removed from this conversation and its local file will be deleted.`
  const confirmed = await requestConfirmation(
    'Delete this asset?',
    message,
    'Delete asset',
  )
  if (!confirmed) return
  try {
    await aiClient.deleteSessionAsset(conversationId.value, asset.id)
    assets.value = assets.value.filter((item) => item.id !== asset.id)
    if (previewAsset.value?.id === asset.id) previewAsset.value = null
  } catch (error) {
    showNotice(errorMessage(error), 'error')
  }
}

function formatBytes(value: number): string {
  if (value < 1024) return `${value} B`
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`
  return `${(value / (1024 * 1024)).toFixed(1)} MB`
}

function assetExtension(asset: SessionAsset): string {
  const extension = asset.name.split('.').pop()
  if (extension && extension !== asset.name && extension.length <= 5) return extension.toUpperCase()
  if (asset.asset_type === 'image') return 'IMG'
  if (asset.asset_type === 'link') return 'URL'
  if (asset.asset_type === 'text') return 'TXT'
  return 'FILE'
}

function classifyAsset(asset: SessionAsset): Exclude<AssetFilter, 'all'> {
  if (asset.asset_type === 'image' || asset.mime_type?.startsWith('image/')) return 'images'
  if (asset.metadata.import_mode === 'object' && isPdfAsset(asset)) return 'documents'
  if (asset.asset_type === 'link') return 'links'
  const extension = asset.name.split('.').pop()?.toLowerCase() || ''
  const codeExtensions = new Set(['py', 'js', 'ts', 'tsx', 'jsx', 'vue', 'json', 'yaml', 'yml', 'toml', 'sh', 'sql', 'html', 'css'])
  if (codeExtensions.has(extension) || /javascript|typescript|json|python|shell|yaml|xml/.test(asset.mime_type || '')) return 'code'
  if (asset.asset_type === 'text' || extension === 'md' || asset.mime_type === 'text/markdown') return 'notes'
  return 'documents'
}

function assetTypeLabel(asset: SessionAsset): string {
  const category = classifyAsset(asset)
  if (category === 'images') return 'Image'
  if (category === 'links') return 'Link'
  if (category === 'notes') return 'Note'
  if (category === 'code') return 'Code'
  return 'Document'
}

function assetSourceLabel(asset: SessionAsset): string | null {
  if (asset.metadata.import_mode === 'object') return t('Static asset')
  if (!asset.source_url) return null
  try {
    return new URL(asset.source_url).hostname
  } catch {
    return asset.source_url
  }
}

function formatAssetDate(value: string): string {
  return new Intl.DateTimeFormat(undefined, {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(parseUtcTimestamp(value))
}

async function saveSelectedArtifact(): Promise<boolean> {
  const artifactId = selectedArtifactId.value
  const activeConversationId = conversationId.value
  const content = artifactContent.value
  if (!content || !activeConversationId || !artifactId) return false
  saving.value = true
  try {
    if (content.artifact_type !== 'latex_pdf') {
      content.suggested_tags = content.suggested_tags.filter((tag) => selectedSuggestions.value.includes(tag.path))
    }
    await syncSelectedArtifactDraft()
    const saved = await aiClient.saveAgentArtifact(activeConversationId, artifactId)
    const index = artifacts.value.findIndex((artifact) => artifact.id === saved.id)
    if (index >= 0) artifacts.value.splice(index, 1, saved)
    if (selectedArtifactId.value === artifactId) {
      artifactContent.value = jsonSnapshot(saved.content)
      // The published draft is gone, so leave the comparison view.
      artifactDiff.value = false
    }
    if (content.artifact_type !== 'image') {
      await loadLibrary()
      tags.value = await tagClient.list()
    }
    showNotice(
      content.artifact_type === 'image'
        ? 'Image changes saved'
        : `${artifactTypeLabel(content.artifact_type)} saved to artifacts`,
    )
    return true
  } catch (error) {
    showNotice(errorMessage(error), 'error')
    return false
  } finally {
    saving.value = false
  }
}

async function deleteSelectedArtifact(): Promise<void> {
  if (!conversationId.value || !selectedArtifactId.value) return
  const artifactTitle = artifactContent.value?.artifact_type === 'latex_pdf'
    ? artifactContent.value.pdf_name
    : artifactContent.value?.title || 'Untitled artifact'
  const confirmed = await requestConfirmation(
    'Delete this artifact?',
    `“${artifactTitle}” will be permanently removed from this conversation. A linked artifact will also be deleted.`,
    'Delete artifact',
  )
  if (!confirmed) return
  try {
    await aiClient.deleteAgentArtifact(conversationId.value, selectedArtifactId.value)
    await refreshArtifacts(false)
    showNotice('Artifact deleted')
  } catch (error) {
    showNotice(errorMessage(error), 'error')
  }
}

async function saveAI(): Promise<void> {
  if (providerLoading.value || providerSaving.value) return
  providerSaving.value = true
  try {
    const providerId = editingProviderId.value
    const isNew = providerId === null
    const saved = isNew
      ? await aiClient.createProvider(ai.value)
      : await aiClient.updateProvider(providerId, ai.value)
    providers.value = await aiClient.listProviders()
    selectedProviderId.value = saved.id
    await selectProvider(saved)
    showNotice(isNew ? 'Provider verified and added' : 'Provider verified and saved')
  } catch (error) {
    showNotice(errorMessage(error), 'error')
  } finally {
    providerSaving.value = false
  }
}

async function saveRuntimeSettings(): Promise<void> {
  if (runtimeSettingsSaving.value) return
  runtimeSettingsSaving.value = true
  try {
    runtimeSettings.value = await settingsClient.update(runtimeSettings.value)
    showNotice('Runtime settings saved')
  } catch (error) {
    showNotice(errorMessage(error), 'error')
  } finally {
    runtimeSettingsSaving.value = false
  }
}

async function selectProvider(provider: AIProvider): Promise<void> {
  const generation = ++providerSelectionGeneration
  providerLoading.value = true
  try {
    const detail = await aiClient.getProvider(provider.id)
    if (generation !== providerSelectionGeneration) return
    editingProviderId.value = detail.id
    selectedProviderId.value = detail.id
    apiKeyVisible.value = true
    ai.value = {
      name: detail.name,
      provider: detail.provider,
      model: detail.model,
      base_url: detail.base_url || '',
      api_key: detail.api_key || '',
      temperature: detail.temperature,
      response: detail.response,
      enabled: detail.enabled,
    }
  } catch (error) {
    if (generation === providerSelectionGeneration) showNotice(errorMessage(error), 'error')
  } finally {
    if (generation === providerSelectionGeneration) providerLoading.value = false
  }
}

function newProvider(): void {
  providerSelectionGeneration += 1
  providerLoading.value = false
  editingProviderId.value = null
  apiKeyVisible.value = true
  ai.value = { name: '', provider: 'openai_compatible', model: '', base_url: '', api_key: '', temperature: 0.2, response: false, enabled: true }
}

function selectProviderKind(): void {
  if (ai.value.provider === 'responses_compatible') ai.value.response = true
  ai.value.base_url = defaultProviderBaseUrl(ai.value.provider, ai.value.response)
}

function setResponseMode(enabled: boolean): void {
  ai.value.response = enabled
  ai.value.base_url = defaultProviderBaseUrl(ai.value.provider, ai.value.response)
}

async function removeProvider(): Promise<void> {
  if (editingProviderId.value === null) return
  const confirmed = await requestConfirmation(
    'Delete this provider?',
    `“${ai.value.name || ai.value.model}” and its locally stored credentials will be permanently removed.`,
    'Delete provider',
  )
  if (!confirmed) return
  await aiClient.deleteProvider(editingProviderId.value)
  providers.value = await aiClient.listProviders()
  const next = providers.value[0]
  selectedProviderId.value = next?.id ?? null
  if (next) await selectProvider(next)
  else newProvider()
  showNotice('Provider removed')
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat(locale.value === 'zh' ? 'zh-CN' : 'en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  }).format(parseUtcTimestamp(value))
}

function formatDateTime(value: string): string {
  return new Intl.DateTimeFormat(locale.value === 'zh' ? 'zh-CN' : 'en-US', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(parseUtcTimestamp(value))
}

function parseUtcTimestamp(value: string): Date {
  const normalized = value.includes('T') ? value : value.replace(' ', 'T')
  const includesTimezone = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(normalized)
  return new Date(includesTimezone ? normalized : `${normalized}Z`)
}

async function initializeWorkspace(): Promise<void> {
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

onMounted(() => {
  document.addEventListener('fullscreenchange', handleSlidesFullscreenChange)
  window.addEventListener('keydown', handleShortcut)
  agentContentResizeObserver = new ResizeObserver(() => scrollAgentThread())
  if (agentTurnStack.value) agentContentResizeObserver.observe(agentTurnStack.value)
  void initializeWorkspace()
})
onBeforeUnmount(() => {
  document.removeEventListener('fullscreenchange', handleSlidesFullscreenChange)
  resolveConfirmation?.(false)
  activeStreamController.value?.abort()
  if (agentScrollFrame !== null) window.cancelAnimationFrame(agentScrollFrame)
  if (turnClock !== null) window.clearInterval(turnClock)
  agentContentResizeObserver?.disconnect()
  agentContentResizeObserver = null
  window.removeEventListener('keydown', handleShortcut)
  clearSessionTitleRefresh()
})
</script>

<template>
  <div class="app-shell">
    <svg class="icon-library" aria-hidden="true">
      <symbol id="icon-cards" viewBox="0 0 24 24"><rect x="4" y="4" width="16" height="16" rx="3"/><path d="M8 9h8M8 13h5"/></symbol>
      <symbol id="icon-search" viewBox="0 0 24 24"><circle cx="11" cy="11" r="6.5"/><path d="m16 16 4 4"/></symbol>
      <symbol id="icon-add" viewBox="0 0 24 24"><path d="M12 5v14M5 12h14"/></symbol>
      <symbol id="icon-settings" viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path d="M19 13.5v-3l-2.1-.5a7 7 0 0 0-.7-1.7l1.1-1.8-2.1-2.1-1.8 1.1a7 7 0 0 0-1.7-.7L11.2 3h-3l-.5 2.1a7 7 0 0 0-1.7.7L4.2 4.7 2.1 6.8l1.1 1.8a7 7 0 0 0-.7 1.7L.5 10.8v3l2.1.5a7 7 0 0 0 .7 1.7l-1.1 1.8 2.1 2.1 1.8-1.1a7 7 0 0 0 1.7.7l.5 2.1h3l.5-2.1a7 7 0 0 0 1.7-.7l1.8 1.1 2.1-2.1-1.1-1.8a7 7 0 0 0 .7-1.7z" transform="translate(1.5 -0.25) scale(.88)"/></symbol>
      <symbol id="icon-schedule" viewBox="0 0 24 24"><circle cx="12" cy="13" r="8"/><path d="M12 9v4l3 2M8 3h8M5 6l-2 2m16-2 2 2"/></symbol>
      <symbol id="icon-channels" viewBox="0 0 24 24"><circle cx="12" cy="12" r="1.5"/><path d="M5.6 5.6a9 9 0 0 0 0 12.8M18.4 5.6a9 9 0 0 1 0 12.8M8.5 8.5a5 5 0 0 0 0 7M15.5 8.5a5 5 0 0 1 0 7"/></symbol>
      <symbol id="icon-spark" viewBox="0 0 24 24"><path d="m12 2 1.3 5.1L18 9l-4.7 1.9L12 16l-1.3-5.1L6 9l4.7-1.9zM19 15l.7 2.3L22 18l-2.3.7L19 21l-.7-2.3L16 18l2.3-.7z"/></symbol>
      <symbol id="icon-arrow" viewBox="0 0 24 24"><path d="M5 12h14m-5-5 5 5-5 5"/></symbol>
      <symbol id="icon-stop" viewBox="0 0 24 24"><rect x="7" y="7" width="10" height="10" rx="1.5"/></symbol>
      <symbol id="icon-check" viewBox="0 0 24 24"><path d="m5 12 4 4L19 6"/></symbol>
      <symbol id="icon-user" viewBox="0 0 24 24"><circle cx="12" cy="8" r="3.5"/><path d="M5.5 20c.6-4 2.8-6 6.5-6s5.9 2 6.5 6"/></symbol>
      <symbol id="icon-attachment" viewBox="0 0 24 24"><path d="m8.5 12.5 6.2-6.2a3 3 0 0 1 4.2 4.2l-8.1 8.1a5 5 0 0 1-7.1-7.1l8-8"/></symbol>
      <symbol id="icon-link" viewBox="0 0 24 24"><path d="M10 13a5 5 0 0 0 7.5.5l2-2a5 5 0 0 0-7-7l-1.1 1.1M14 11a5 5 0 0 0-7.5-.5l-2 2a5 5 0 0 0 7 7l1.1-1.1"/></symbol>
      <symbol id="icon-text" viewBox="0 0 24 24"><path d="M5 6h14M12 6v13M8 19h8"/></symbol>
      <symbol id="icon-library-import" viewBox="0 0 24 24"><path d="M4 4h5v16H4zM11 4h5v16h-5zM18.5 8v8M22.5 12h-8"/></symbol>
      <symbol id="icon-trash" viewBox="0 0 24 24"><path d="M4 7h16M9 7V4h6v3m3 0-1 13H7L6 7m4 4v5m4-5v5"/></symbol>
      <symbol id="icon-edit" viewBox="0 0 24 24"><path d="m4 20 4.2-1 10.7-10.7a2.1 2.1 0 0 0-3-3L5.2 16zM14.7 6.5l3 3"/></symbol>
      <symbol id="icon-copy" viewBox="0 0 24 24"><rect x="8" y="8" width="11" height="11" rx="2"/><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/></symbol>
      <symbol id="icon-conversation" viewBox="0 0 24 24"><path d="M5 5.5h14a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H10l-5 3v-3H5a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2Z"/><path d="M8 10h8M8 13h5"/></symbol>
      <symbol id="icon-eye" viewBox="0 0 24 24"><path d="M2.5 12s3.5-6 9.5-6 9.5 6 9.5 6-3.5 6-9.5 6-9.5-6-9.5-6Z"/><circle cx="12" cy="12" r="2.5"/></symbol>
      <symbol id="icon-eye-off" viewBox="0 0 24 24"><path d="M3 3l18 18M10.6 6.1A9.8 9.8 0 0 1 12 6c6 0 9.5 6 9.5 6a16.4 16.4 0 0 1-2.1 3M6.2 6.2C3.8 7.8 2.5 12 2.5 12s3.5 6 9.5 6c1.2 0 2.3-.3 3.3-.7M10.2 10.2a2.5 2.5 0 0 0 3.6 3.6"/></symbol>
      <symbol id="icon-refresh" viewBox="0 0 24 24"><path d="M20 12a8 8 0 1 1-2.3-5.7M20 4v5h-5"/></symbol>
    </svg>

    <aside class="sidebar">
      <button class="brand" type="button" aria-label="Open artifacts" @click="navigate('library')">
        <span class="brand-mark"><img src="/logo.png" alt="" /></span>
        <span><strong>Commonplace</strong><small>{{ $t('brand.subtitle') }}</small></span>
      </button>

      <nav class="primary-nav" aria-label="Main navigation">
        <button :class="{ active: view === 'new' && sessionScope === 'normal' }" type="button" @click="navigate('new')">
          <svg><use href="#icon-spark" /></svg><span>{{ $t('nav.workspace') }}</span>
        </button>
        <button :class="{ active: view === 'scheduledTasks' || (view === 'new' && sessionScope === 'scheduled') }" type="button" @click="navigate('scheduledTasks')">
          <svg><use href="#icon-schedule" /></svg><span>{{ $t('nav.scheduledTasks') }}</span>
        </button>
        <button :class="{ active: view === 'search' || (view === 'library' && selectedTag === null) }" type="button" @click="navigate('library')">
          <svg><use href="#icon-cards" /></svg><span>{{ $t('nav.artifacts') }}</span><small>{{ libraryItems.length }}</small>
        </button>
        <button :class="{ active: view === 'assets' }" type="button" @click="navigate('assets')">
          <svg><use href="#icon-attachment" /></svg><span>{{ $t('nav.assets') }}</span>
        </button>
      </nav>

      <div v-if="view === 'new' || view === 'scheduledTasks' || view === 'channels'" class="sidebar-section session-section">
        <div class="sidebar-heading"><span>{{ sessionScope === 'channel' ? $t('nav.channelConversations') : $t('nav.conversations') }}</span><button v-if="sessionScope === 'normal'" type="button" :aria-label="$t('nav.newConversation')" @click="resetWorkspace"><svg><use href="#icon-add" /></svg></button></div>
        <div ref="sessionListRef" class="session-history-list" @scroll.passive="handleSessionListScroll">
          <div
            v-for="session in visibleSessions"
            :key="session.id"
            class="session-history-item"
            :class="{ active: conversationId === session.id || switchingSessionId === session.id, switching: switchingSessionId === session.id }"
            :aria-current="conversationId === session.id ? 'page' : undefined"
          >
            <form v-if="editingSessionId === session.id" class="session-title-editor" @submit.prevent="saveSessionTitle(session.id)" @focusout="handleSessionTitleFocusOut">
              <input v-model="sessionTitleDraft" maxlength="100" aria-label="Conversation title" autofocus @keydown.esc.prevent="cancelSessionTitleEdit" />
              <button type="submit" aria-label="Save title">Save</button>
              <button type="button" aria-label="Cancel title edit" @click="cancelSessionTitleEdit">Cancel</button>
            </form>
            <button v-else class="session-open-button" type="button" @mouseenter="prefetchSession(session.id)" @focus="prefetchSession(session.id)" @click="openSession(session.id)">
              <span><strong title="Click to rename" @click.stop="startSessionTitleEdit(session)">{{ session.title || '新会话' }}</strong><small>{{ formatDateTime(session.created_at) }}</small></span>
              <small>{{ session.message_count }}</small>
            </button>
            <button v-if="editingSessionId !== session.id" class="session-delete-button" type="button" :aria-label="`Delete ${session.title || 'conversation'}`" title="Delete conversation" @click.stop="deleteSession(session)"><svg><use href="#icon-trash" /></svg></button>
          </div>
          <template v-if="!visibleSessions.length && activeSessionsPending">
            <div v-for="index in 3" :key="`session-skeleton-${index}`" class="session-history-skeleton" aria-hidden="true" />
          </template>
          <p v-else-if="!visibleSessions.length" class="sidebar-empty">{{ $t('nav.noConversations') }}</p>
          <div v-if="visibleSessions.length && activeSessionsLoading" class="session-list-loading" role="status" aria-live="polite">
            <span class="session-switch-spinner" aria-hidden="true" />
            <small>{{ $t('nav.loading') }}</small>
          </div>
        </div>
      </div>

      <div v-else class="sidebar-section">
        <div class="sidebar-heading"><span>{{ $t('nav.collections') }}</span><button type="button" :aria-label="$t('nav.manageTags')" @click="openTagManager"><svg><use href="#icon-add" /></svg></button></div>
        <div class="tag-list">
          <div
            v-for="tag in flatTags"
            :key="tag.id"
            class="tag-row"
            :class="{ 'drop-target': tagDropTargetId === tag.id, 'drop-busy': tagAssignmentBusy }"
            :style="{ '--tag-depth': tag.depth }"
            @mouseenter="hoveredTagId = tag.id"
            @mouseleave="hoveredTagId = null"
            @dragenter="handleTagDragOver(tag, $event)"
            @dragover="handleTagDragOver(tag, $event)"
            @dragleave="handleTagDragLeave(tag, $event)"
            @drop="dropResourceOnTag(tag, $event)"
          >
            <button
              v-if="tag.hasChildren"
              class="tag-toggle"
              :class="{ collapsed: collapsedTagIds.has(tag.id) }"
              type="button"
              :aria-label="`${collapsedTagIds.has(tag.id) ? $t('nav.expand') : $t('nav.collapse')} ${tag.name}`"
              @click="toggleTag(tag.id)"
            ><span>⌄</span></button>
            <span v-else class="tag-toggle-placeholder" />
            <button
              class="tag-select"
              :class="{ active: selectedTag === tag.id && view === 'library' }"
              :title="tag.path"
              type="button"
              @click="filterByTag(tag.id)"
            >
              <span class="tag-dot" :style="tag.color ? { background: tag.color } : undefined" />
              <span class="tag-label">{{ tag.name }}</span><small v-if="hoveredTagId !== tag.id">{{ tag.total_count }}</small>
            </button>
            <button
              v-if="hoveredTagId === tag.id"
              class="tag-delete"
              type="button"
              :disabled="tagManagerBusy"
              :aria-label="$t('nav.deleteTag', { path: tag.path })"
              :title="$t('nav.deleteTag', { path: tag.path })"
              @click.stop="deleteTag(tag)"
            ><svg><use href="#icon-trash" /></svg></button>
          </div>
          <p v-if="!flatTags.length" class="sidebar-empty">{{ $t('nav.tagsEmpty') }}</p>
        </div>
      </div>

      <div class="sidebar-footer">
        <button class="channels-nav-button" :class="{ active: view === 'channels' || (view === 'new' && sessionScope === 'channel') }" type="button" @click="navigate('channels')">
          <svg><use href="#icon-channels" /></svg><span>{{ $t('nav.channels') }}</span>
        </button>
        <label class="locale-control">
          <span>{{ $t('settings.language') }}</span>
          <select :value="locale" @change="changeLocale">
            <option value="en">{{ $t('settings.english') }}</option>
            <option value="zh">{{ $t('settings.chinese') }}</option>
          </select>
        </label>
        <button :class="{ active: view === 'settings' }" type="button" @click="navigate('settings')">
          <svg><use href="#icon-settings" /></svg><span>{{ $t('nav.settings') }}</span>
          <span class="status-dot" :class="{ online: providers.some((provider) => provider.enabled) }" />
        </button>
      </div>
    </aside>

    <main class="workspace">
      <Transition name="toast">
        <div v-if="notice" class="toast" :class="noticeKind" role="status">
          <svg v-if="noticeKind === 'success'"><use href="#icon-check" /></svg>
          <span>{{ notice }}</span>
        </div>
      </Transition>

      <ConfirmDialog :open="confirmation.open" :title="confirmation.title" :message="confirmation.message" :confirm-label="confirmation.confirmLabel" @cancel="settleConfirmation(false)" @confirm="settleConfirmation(true)" />
      <TagManagerDialog v-if="tagManagerOpen" :tags="tags" :busy="tagManagerBusy" :feedback="tagManagerFeedback" :feedback-kind="tagManagerFeedbackKind" @close="tagManagerOpen = false" @create="createTag" @delete="deleteTag" />
      <AssetPreviewDialog :asset="previewAsset" @close="previewAsset = null" />
      <StaticAssetImportDialog
        v-if="staticAssetImportOpen"
        :assets="staticAssets"
        :loading="staticAssetsLoading"
        :importing-id="staticAssetImportingId"
        :imported-ids="importedStaticAssetIds"
        @close="staticAssetImportOpen = false"
        @import="importStaticAsset"
      />
      <LibraryEditor
        v-if="libraryEditorItem"
        :item="libraryEditorItem"
        :saving="libraryEditorSaving"
        :save-label="libraryEditorArtifactId !== null ? $t('Save draft') : $t('Save')"
        @close="closeLibraryEditor"
        @save="saveLibraryEditor"
      />

      <template v-if="view === 'library' || view === 'search'">
        <header class="topbar">
          <form class="search-field" role="search" @submit.prevent="search">
            <svg><use href="#icon-search" /></svg>
            <input ref="searchInput" v-model="query" :aria-label="$t('search.placeholder')" :placeholder="$t('search.placeholder')" />
            <button v-if="query" type="button" :aria-label="$t('search.clear')" @click="query = ''; search()">×</button>
            <kbd v-else>⌘ K</kbd>
          </form>
          <button class="primary-action" type="button" @click="navigate('new')"><svg><use href="#icon-add" /></svg>{{ $t('search.newCard') }}</button>
        </header>

        <section class="content library-view">
          <div class="page-heading">
            <div><p class="eyebrow">{{ $t('Your knowledge') }}</p><h1>{{ pageTitle }}</h1><p>{{ pageDescription }}</p></div>
            <button v-if="selectedTag !== null" class="text-button" type="button" @click="filterByTag(null)">Clear filter</button>
          </div>

          <div class="library-type-filters" aria-label="Artifact type filters">
            <span>{{ $t('Type') }}</span>
            <button
              v-for="filter in libraryTypeFilters"
              :key="filter.label"
              :class="{ active: selectedLibraryType === filter.value }"
              type="button"
              @click="filterByArtifactType(filter.value)"
            >{{ $t(filter.label) }}</button>
          </div>

          <!--
            Skeleton cards only stand in for a library that has nothing to show yet.
            Replacing an already loaded grid with placeholders made every filter
            click flash: with two results the other four shimmering slots appeared
            and vanished, which reads as the grid itself flickering.
          -->
          <div v-if="libraryLoading && !libraryItems.length" class="card-grid" aria-label="Loading artifacts">
            <div v-for="index in 6" :key="index" class="card skeleton" />
          </div>
          <div v-else-if="libraryItems.length" :key="libraryGridKey" class="card-grid" :aria-busy="libraryLoading">
            <article
              v-for="(item, index) in libraryItems"
              :key="`${item.item_type}-${item.id}`"
              class="card"
              :class="[`library-${item.item_type}`, { dragging: draggingLibraryItem?.id === item.id }]"
              :style="{ animationDelay: cardFloatDelay(index) }"
              role="button"
              tabindex="0"
              draggable="true"
              :aria-label="`Open ${item.title}`"
              @click="openLibraryItem(item)"
              @keydown.enter="openLibraryItem(item)"
              @keydown.space.prevent="openLibraryItem(item)"
              @dragstart="startLibraryItemDrag(item, $event)"
              @dragend="endLibraryItemDrag"
            >
              <div class="card-topline">
                <span class="card-type">{{ item.item_type === 'card' ? $t(item.card_type || 'card') : $t(item.item_type) }}</span>
                <div class="card-topline-actions">
                  <button class="card-action-button" type="button" :aria-label="`Open conversation for ${item.title}`" title="Open source conversation" @click.stop="openArtifactSession(item)" @keydown.stop>
                    <svg><use href="#icon-conversation" /></svg>
                  </button>
                  <button v-if="item.item_type === 'slides'" class="card-action-button" type="button" :aria-label="`Preview ${item.title} fullscreen`" title="Fullscreen preview" @click.stop="openSlidesFullscreen(item)" @keydown.stop>
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M9 3H3v6m12-6h6v6M3 15v6h6m12-6v6h-6" /></svg>
                  </button>
                  <button v-if="item.item_type === 'latex_pdf'" class="card-action-button" type="button" :aria-label="`Preview ${item.title}`" title="Preview PDF" @click.stop="openLibraryPdf(item, 'expanded')" @keydown.stop>
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M9 3H3v6m12-6h6v6M3 15v6h6m12-6v6h-6" /></svg>
                  </button>
                  <button v-if="item.item_type === 'latex_pdf'" class="card-action-button" type="button" :aria-label="`Present ${item.title}`" title="Present PDF" @click.stop="openLibraryPdf(item, 'presentation')" @keydown.stop>
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="13" rx="2" /><path d="M12 17v4m-4 0h8M10 8l5 2.5-5 2.5Z" /></svg>
                  </button>
                  <button v-if="item.item_type !== 'latex_pdf'" class="card-action-button" type="button" :aria-label="`Edit ${item.title}`" title="Edit and preview" @click.stop="openLibraryEditor(item)" @keydown.stop>
                    <svg><use href="#icon-edit" /></svg>
                  </button>
                  <button class="card-action-button card-copy-action" type="button" :aria-label="`Copy ID for ${item.title}`" title="Copy artifact ID" @click.stop="copyLibraryItemId(item)" @keydown.stop>
                    <svg><use href="#icon-copy" /></svg>
                  </button>
                  <button class="card-action-button danger" :disabled="deletingLibraryItemId !== null" type="button" :aria-label="`Delete ${item.title}`" :title="deletingLibraryItemId === item.id ? 'Deleting…' : `Delete ${item.item_type}`" @click.stop="deleteLibraryItem(item)" @keydown.stop>
                    <svg><use href="#icon-trash" /></svg>
                  </button>
                </div>
              </div>
              <h2 :title="item.title">{{ item.title }}</h2>
              <div v-if="item.item_type === 'latex_pdf'" class="library-pdf-thumbnail">
                <PdfThumbnail :asset="libraryClient.documentReference(item.id)" artifact fit="contain" />
              </div>
              <div v-if="item.item_type === 'slides'" class="library-deck-summary">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="4" width="18" height="13" rx="2" /><path d="M12 17v4m-4 0h8M8 9h8m-8 4h5" /></svg>
                <span>{{ $t('Presentation · {count} slides', { count: presentationSections(item.content).flat().length }) }}</span>
              </div>
              <p v-if="item.item_type !== 'latex_pdf'" class="card-excerpt">{{ libraryExcerpt(item) }}</p>
              <div class="card-footer">
                <div class="card-footer-info">
                  <div v-if="item.tags.length" class="card-tags"><span v-for="path in item.tags.slice(0, 2)" :key="path" :title="path">{{ path }}</span></div>
                  <time>{{ formatDate(item.updated_at) }}</time>
                </div>
                <svg><use href="#icon-arrow" /></svg>
              </div>
            </article>
          </div>
          <div v-else class="empty-state">
            <span class="empty-icon"><svg><use :href="view === 'search' ? '#icon-search' : '#icon-cards'" /></svg></span>
            <h2>{{ view === 'search' ? $t('Nothing found') : $t('Your library is ready') }}</h2>
            <p>{{ view === 'search' ? $t('Try a different phrase or browse your collections.') : $t('Capture a thought and let AI shape it into a useful card, article, or slide deck.') }}</p>
            <button class="primary-action" type="button" @click="view === 'search' ? navigate('library') : navigate('new')">
              {{ view === 'search' ? $t('Browse library') : $t('Create your first card') }}
            </button>
          </div>
        </section>
      </template>

      <template v-else-if="view === 'new'">
        <header class="topbar compact chat-topbar">
          <div class="chat-topbar-title"><span class="status-dot online" /><span>{{ sessionScope === 'scheduled' ? $t('nav.scheduledConversation') : sessionScope === 'channel' ? $t('nav.channelConversation') : $t('nav.workspace') }}</span></div>
          <div class="workspace-view-switch" role="group" aria-label="AI workspace view">
            <button :class="{ active: workspaceView === 'workspace' }" type="button" @click="setWorkspaceView('workspace')">{{ $t('Workspace') }}</button>
            <button :class="{ active: workspaceView === 'trace' }" type="button" @click="setWorkspaceView('trace')">{{ $t('Trace') }}</button>
          </div>
          <button class="close-button" type="button" aria-label="Close" @click="navigate('library')">×</button>
        </header>
        <section class="content create-view">
          <div v-if="workspaceView === 'trace'" class="trace-workspace">
            <InteractionTrace
              :messages="traceMessages"
              :loading="traceLoading"
              :error="traceError"
              :selected-turn-id="selectedTraceTurnId"
              @refresh="loadInteractionTrace()"
              @preview-image="openImagePreview"
              @update:selected-turn-id="updateTraceTurn"
            />
          </div>
          <div v-else class="agent-workspace" :class="{ 'session-switching': switchingSessionId !== null, 'assets-hidden': assetsPaneHidden }" @paste="pasteAssets">
            <aside v-if="!assetsPaneHidden" class="assets-pane" aria-label="Session assets" tabindex="0">
              <header class="assets-header">
                <div><strong>{{ $t('Assets') }}</strong><small>{{ $t('Session resources') }}</small></div>
                <div class="assets-header-actions">
                  <button type="button" :title="$t('Add text note')" :aria-label="$t('Add text note')" @click="showAssetEditor('text')"><svg><use href="#icon-text" /></svg></button>
                  <button type="button" :title="$t('Add link')" :aria-label="$t('Add link')" @click="showAssetEditor('link')"><svg><use href="#icon-link" /></svg></button>
                  <button type="button" :title="$t('Upload files')" :aria-label="$t('Upload files')" @click="assetFileInput?.click()"><svg><use href="#icon-attachment" /></svg></button>
                  <button class="asset-import-action" type="button" :title="$t('Import static asset')" :aria-label="$t('Import static asset')" @click="openStaticAssetImport">
                    <svg><use href="#icon-library-import" /></svg>
                    <span>{{ $t('Import') }}</span>
                  </button>
                  <button class="asset-hide-action" type="button" :title="$t('Hide assets')" :aria-label="$t('Hide assets')" @click="toggleAssetsPane(true)">
                    <svg><use href="#icon-eye-off" /></svg>
                  </button>
                </div>
              </header>

              <div class="assets-search">
                <svg><use href="#icon-search" /></svg>
                <input v-model="assetQuery" type="search" :placeholder="$t('Search assets')" :aria-label="$t('Search assets')" />
              </div>

              <div class="asset-filter-list" :aria-label="$t('Asset type')">
                <button v-for="filter in assetFilters" :key="filter.value" :class="{ active: assetFilter === filter.value }" type="button" @click="assetFilter = filter.value">{{ $t(filter.label) }}</button>
              </div>

              <div class="asset-list-heading">
                <span>{{ filteredAssets.length === 1 ? $t('{count} asset', { count: filteredAssets.length }) : $t('{count} assets', { count: filteredAssets.length }) }}</span>
                <small>{{ $t('Newest') }}</small>
              </div>

              <form v-if="assetEditorMode !== 'closed'" class="asset-editor" @submit.prevent="addInlineAsset">
                <strong>{{ assetEditorMode === 'link' ? $t('Add a link') : $t('Add a note') }}</strong>
                <input v-model="assetName" :placeholder="assetEditorMode === 'link' ? $t('Link name') : $t('Note name')" />
                <textarea v-model="assetValue" :placeholder="assetEditorMode === 'link' ? 'https://…' : $t('Text content')" rows="3" />
                <div><button :disabled="assetUploading || !assetName.trim() || !assetValue.trim()" type="submit">{{ $t('Add asset') }}</button><button type="button" @click="assetEditorMode = 'closed'">{{ $t('Cancel') }}</button></div>
              </form>

              <div class="asset-browser">
                <div class="asset-browser-list">
                  <article v-for="asset in filteredAssets" :key="asset.id" class="asset-row">
                    <button class="asset-row-main" type="button" @click="openAsset(asset)">
                      <span class="asset-thumbnail" :class="classifyAsset(asset)">
                        <img v-if="asset.mime_type?.startsWith('image/') && (asset.source_url || asset.content_url)" :src="asset.source_url || asset.content_url || ''" alt="" />
                        <PdfThumbnail v-else-if="isPdfAsset(asset)" :asset="asset" />
                        <svg v-else><use :href="asset.asset_type === 'link' ? '#icon-link' : asset.asset_type === 'text' ? '#icon-text' : '#icon-attachment'" /></svg>
                        <small>{{ assetExtension(asset) }}</small>
                      </span>
                      <span class="asset-row-copy">
                        <strong>{{ asset.name }}</strong>
                        <small>{{ assetTypeLabel(asset) }} · {{ assetSourceLabel(asset) || formatBytes(asset.size_bytes) }}</small>
                        <time>{{ formatAssetDate(asset.created_at) }}</time>
                      </span>
                    </button>
                    <button class="asset-delete" type="button" :aria-label="`Delete ${asset.name}`" @click="removeAsset(asset)"><svg><use href="#icon-trash" /></svg></button>
                    <AssetRename :name="asset.name" :save="name => renameAsset(asset, name)" />
                  </article>
                  <div v-if="!filteredAssets.length" class="asset-empty">
                    <svg><use :href="assets.length ? '#icon-search' : '#icon-attachment'" /></svg>
                    <strong>{{ assets.length ? $t('No matching assets') : $t('No assets yet') }}</strong>
                    <small>{{ assets.length ? $t('Try another search or filter.') : $t('Add reference material for this conversation.') }}</small>
                  </div>
                </div>

                <button class="asset-drop-zone" :class="{ dragging: assetDragging }" type="button" @click="assetFileInput?.click()" @dragenter.prevent="assetDragging = true" @dragover.prevent="assetDragging = true" @dragleave.prevent="assetDragging = false" @drop.prevent="dropAssets">
                  <svg><use href="#icon-attachment" /></svg>
                  <strong>{{ assetUploading ? 'Uploading…' : $t('Drop or paste assets here') }}</strong>
                  <small>{{ $t('Click this area, then press Ctrl/⌘ + V') }}</small>
                </button>
              </div>
              <input ref="assetFileInput" type="file" multiple hidden @change="uploadAssets" />
            </aside>

            <section class="agent-chat" :class="{ 'session-switching': switchingSessionId !== null }" aria-label="Knowledge card conversation" :aria-busy="switchingSessionId !== null">
              <div class="agent-chat-header">
                <div class="agent-identity"><img src="/logo.png" alt="" /><div><strong>{{ $t('Zettelkasten Agent') }}</strong><small>{{ $t('Turn a conversation into knowledge') }}</small></div></div>
                <button v-if="assetsPaneHidden" class="asset-show-action" type="button" :title="$t('Show assets')" :aria-label="$t('Show assets')" @click="toggleAssetsPane(false)">
                  <svg><use href="#icon-eye" /></svg>
                  <span>{{ $t('Assets') }}</span>
                </button>
                <span class="streaming-status"><i />{{ $t('Zettelkasten Agent online') }}</span>
              </div>

              <div ref="agentThread" class="agent-thread" :class="{ empty: !conversationStarted && switchingSessionId === null }" aria-live="polite" @scroll.passive="handleAgentThreadScroll" @wheel.passive="handleAgentThreadWheel">
                <Transition name="session-content" mode="out-in">
                  <div v-if="switchingSessionId || workspaceRestoring" key="switching" class="session-switch-state" aria-live="polite">
                    <span class="session-switch-spinner" aria-hidden="true" />
                    <strong>{{ workspaceRestoring ? 'Restoring conversation' : 'Switching conversation' }}</strong>
                    <small>Loading messages and workspace…</small>
                  </div>
                  <div v-else-if="!conversationStarted" key="welcome" class="agent-welcome">
                    <span class="feature-icon"><svg><use href="#icon-spark" /></svg></span>
                    <h2>{{ $t('What should we remember?') }}</h2>
                    <p>{{ $t('Share a rough thought, excerpt, or question. You can refine the result through conversation before saving it.') }}</p>
                    <div class="prompt-hints"><button type="button" @click="raw = 'I have an idea: '">{{ $t('Capture an idea') }}</button><button type="button" @click="raw = 'Key point from what I just read: '">{{ $t('Summarize a note') }}</button></div>
                  </div>
                  <div v-else ref="agentTurnStack" :key="conversationId || 'conversation'" class="turn-stack">
                  <article
                    v-for="(turn, index) in conversationTurns"
                    :key="turn.id"
                    class="conversation-turn"
                    :class="{ running: isRunningTurn(index) }"
                  >
                    <section class="turn-prompt" aria-label="User message">
                      <div class="turn-prompt-content">
                        <div v-if="turn.prompt.steering_status === 'waiting'" class="turn-steering-status">
                          <i aria-hidden="true" />
                          <span>Will respond immediately after the current tool call or turn finishes.</span>
                        </div>
                        <template v-if="turn.prompt.parts?.length">
                          <template v-for="(part, partIndex) in turn.prompt.parts" :key="`${turn.id}-part-${partIndex}`">
                            <div
                              v-if="part.type === 'text' && part.text"
                              class="message-content"
                            >
                              <MarkdownContent :content="part.text" />
                            </div>
                            <button
                              v-else-if="part.type === 'image'"
                              class="turn-prompt-image-button"
                              type="button"
                              :aria-label="`Preview ${part.name}`"
                              @click="openMessageImage(part)"
                            >
                              <img class="turn-prompt-image" :src="part.content_url" :alt="part.name" />
                            </button>
                          </template>
                        </template>
                        <div v-else-if="turn.prompt.content" class="message-content">
                          <MarkdownContent :content="turn.prompt.content" />
                        </div>
                      </div>
                    </section>

                    <div class="turn-content">
                      <details class="turn-execution" :open="isTurnDetailsOpen(turn, index)">
                        <summary @click="toggleTurnExecution(turn, $event)">
                          <span class="turn-state-icon" aria-hidden="true"><i /></span>
                          <span class="turn-execution-copy">
                            <strong>{{ isRunningTurn(index) ? turnTask(index) : `Processed in ${turnDuration(turn, index)}` }}</strong>
                            <small>{{ isRunningTurn(index) ? `Running · ${turnDuration(turn, index)}` : 'Show thinking, tools, and task details' }}</small>
                          </span>
                          <span class="turn-execution-metrics">
                            <CacheHitRate class="turn-execution-cache" label="Cache" :rate="turnCacheHitRate(turn, index)" />
                          </span>
                          <span class="turn-chevron" aria-hidden="true">›</span>
                        </summary>
                        <div class="turn-execution-details">
                          <div v-if="isRunningTurn(index) && activeTodos?.todos.length" class="turn-task-list">
                            <div><strong>Task progress</strong><small>{{ activeTodos.completed ? 'Completed' : `${(activeTodos.processing_index ?? 0) + 1} of ${activeTodos.todos.length}` }}</small></div>
                            <ol>
                              <li v-for="todo in activeTodos.todos" :key="todo.content" :class="todo.status">
                                <i aria-hidden="true">{{ todo.status === 'completed' ? '✓' : todo.status === 'processing' ? '•' : '' }}</i>
                                <span>{{ todo.content }}</span>
                              </li>
                            </ol>
                          </div>
                          <div v-if="turnExecutionTimeline(turn, index).length" class="agent-event-timeline">
                            <template v-for="entry in turnExecutionTimeline(turn, index)" :key="entry.id">
                            <details v-if="entry.type === 'reasoning'" class="reasoning-panel" :class="{ 'streaming-reasoning': isRunningTurn(index) }">
                              <summary><i aria-hidden="true" /><span>Thinking</span><small>{{ isRunningTurn(index) ? 'Live' : 'Completed' }}</small></summary>
                              <MarkdownContent class="reasoning-content" :content="entry.content" />
                            </details>
                            <MarkdownContent v-else-if="entry.type === 'message'" class="intermediate-response" :content="entry.content" />
                            <details v-else-if="entry.type === 'compaction'" class="reasoning-panel compaction-panel">
                              <summary><span>Context compaction</span><small>{{ entry.activity.state }}</small></summary>
                              <div class="compaction-content">
                                <MarkdownContent v-if="entry.activity.reasoning" class="reasoning-content" :content="entry.activity.reasoning" />
                                <MarkdownContent v-if="entry.activity.content" class="reasoning-content" :content="entry.activity.content" />
                                <small v-if="entry.activity.compressed_from">Compressed {{ entry.activity.compressed_from }}–{{ entry.activity.compressed_to }} · kept {{ entry.activity.kept_from }}–{{ entry.activity.kept_to }}</small>
                              </div>
                            </details>
                            <details v-else-if="entry.type === 'tool'" class="tool-activity" :class="entry.activity.state">
                              <summary><i /><span>{{ entry.activity.name.replaceAll('_', ' ') }}</span><small v-if="entry.activity.duration_ms">{{ Math.round(entry.activity.duration_ms) }} ms</small></summary>
                              <div class="tool-activity-details">
                                <div><strong>Arguments</strong><pre>{{ formatToolValue(entry.activity.arguments || {}) }}</pre></div>
                                <div><strong>{{ entry.activity.error_message ? 'Error' : 'Result' }}</strong><ToolResult :output="entry.activity.output" :error="entry.activity.error_message" @preview-image="openImagePreview" /></div>
                              </div>
                            </details>
                            <details v-else-if="entry.type === 'server_tool'" class="tool-activity server-tool-activity" :class="entry.activity.state">
                              <summary><i /><span>{{ entry.activity.name.replaceAll('_', ' ') }}</span><small>Provider tool · {{ entry.activity.state }}</small></summary>
                              <div class="tool-activity-details">
                                <div><strong>Input</strong><pre>{{ entry.activity.input_delta || (entry.activity.input === null ? 'Waiting for streamed input…' : formatToolValue(entry.activity.input)) }}</pre></div>
                                <div v-if="entry.activity.output !== undefined || entry.activity.error_code"><strong>{{ entry.activity.error_code ? 'Error' : 'Result' }}</strong><pre :class="{ error: entry.activity.error_code }">{{ entry.activity.error_code || formatToolValue(entry.activity.output) }}</pre></div>
                              </div>
                            </details>
                            </template>
                          </div>
                          <p v-else-if="isRunningTurn(index)" class="turn-empty-detail">Waiting for execution details…</p>
                        </div>
                      </details>

                      <section class="turn-response" aria-label="Agent response">
                        <div class="agent-response-content">
                          <template v-for="entry in turnAnswerTimeline(turn, index)" :key="entry.id">
                            <MarkdownContent class="final-response" :content="entry.content" />
                          </template>
                          <span v-if="isRunningTurn(index)" class="streaming-dots compact" aria-label="Generating"><i /><i /><i /></span>
                          <p v-else-if="isSteeredTurn(index)" class="turn-steered-note">This turn was steered by a follow-up message.</p>
                          <p v-else-if="!turnAnswerTimeline(turn, index).length && !turn.response?.error" class="turn-empty-response">No response was recorded for this turn.</p>
                          <div v-if="turn.response?.error" class="turn-error" role="alert">
                            <strong>Request failed</strong>
                            <span>{{ turn.response.error }}</span>
                          </div>
                        </div>
                      </section>
                    </div>
                  </article>
                  </div>
                </Transition>
              </div>

              <AskUserPrompt
                v-if="pendingQuestion"
                :question="pendingQuestion.question"
                :options="pendingQuestion.options"
                :allow-multiple="pendingQuestion.allowMultiple"
                :selected-options="selectedAskOptions"
                :answer="askAnswer"
                :images="askUserImages"
                :queued-count="queuedQuestions.length"
                :submitting="answeringQuestion"
                @toggle="toggleAskOption"
                @update:answer="updateAskAnswer"
                @add-images="attachAskUserImages"
                @preview-image="openImagePreview"
                @remove-image="removeAskUserImage"
                @submit="answerAgentQuestion"
              />

              <ShellApprovalPrompt
                v-for="approval in pendingShellApprovals"
                :key="approval.toolCallId"
                :command="approval.command"
                :timeout-seconds="approval.timeoutSeconds"
                :remember-supported="approval.rememberSupported"
                :submitting="shellApprovalSubmittingIds.includes(approval.toolCallId)"
                @execute="remember => respondToShellApproval(approval.toolCallId, 'execute', remember)"
                @abort="respondToShellApproval(approval.toolCallId, 'abort')"
              />

              <div class="agent-composer-stack">
                <div v-if="queuedFollowUps.length" class="queued-followup-list" aria-label="Queued follow-up messages" aria-live="polite">
                  <article
                    v-for="item in queuedFollowUps"
                    :key="item.id"
                    class="queued-followup"
                    :class="{ dragging: draggingQueuedFollowUpId === item.id }"
                    @dragover.prevent
                    @drop.prevent="dropQueuedFollowUp(item, $event)"
                  >
                    <button
                      class="queued-followup-drag"
                      type="button"
                      draggable="true"
                      title="Drag to reorder"
                      aria-label="Drag to reorder"
                      @dragstart.stop="startQueuedFollowUpDrag(item, $event)"
                      @dragend.stop="endQueuedFollowUpDrag"
                    >
                      <svg viewBox="0 0 20 20" aria-hidden="true"><circle cx="7" cy="5" r="1" /><circle cx="13" cy="5" r="1" /><circle cx="7" cy="10" r="1" /><circle cx="13" cy="10" r="1" /><circle cx="7" cy="15" r="1" /><circle cx="13" cy="15" r="1" /></svg>
                    </button>
                    <span class="queued-followup-icon" aria-hidden="true"><svg><use href="#icon-conversation" /></svg></span>
                    <div class="queued-followup-copy">
                      <p>{{ queuedFollowUpText(item) }}</p>
                      <div v-if="item.parts.some((part) => part.type === 'image')" class="queued-followup-images">
                        <template v-for="(part, partIndex) in item.parts" :key="`${item.id}-${partIndex}`">
                          <button
                            v-if="part.type === 'image'"
                            class="queued-followup-image-preview"
                            type="button"
                            :aria-label="`Preview ${part.name}`"
                            @click="openImagePreview({ name: part.name, url: part.content_url })"
                          >
                            <img :src="part.content_url" :alt="part.name" />
                          </button>
                        </template>
                      </div>
                    </div>
                    <button
                      class="queued-followup-steer"
                      type="button"
                      :disabled="steeringQueuedFollowUpId === item.id || item.slashCommandId !== null || item.atCommandId !== null"
                      :aria-label="`Steer with ${queuedFollowUpText(item)}`"
                      title="Apply this follow-up to the active run now"
                      @click="steerQueuedFollowUp(item)"
                    >
                      <svg aria-hidden="true" viewBox="0 0 24 24"><path d="m9 7-5 5 5 5M5 12h8a6 6 0 0 1 6 6" /></svg>
                      <span>{{ steeringQueuedFollowUpId === item.id ? 'Sending…' : 'Steer' }}</span>
                    </button>
                    <button
                      class="queued-followup-remove"
                      type="button"
                      :aria-label="`Remove ${queuedFollowUpText(item)}`"
                      @click="removeQueuedFollowUp(item)"
                    >
                      <svg aria-hidden="true"><use href="#icon-trash" /></svg>
                    </button>
                  </article>
                </div>
                <form class="agent-input" @submit.prevent="submitConversation">
                  <ComposerCommandMenu
                    v-if="slashMenu"
                    :items="slashMenuItems"
                    :active-index="slashMenuActiveIndex"
                    :loading="slashCommandsLoading && !slashCommandsLoaded"
                    :heading="$t('composer.slashCommands')"
                    :hint="$t('composer.selectOneCommand')"
                    :empty-label="$t('composer.noSlashCommands')"
                    @select="selectSlashCommand"
                    @hover="slashMenu = slashMenu ? { ...slashMenu, activeIndex: $event } : null"
                  />
                  <ComposerCommandMenu
                    v-if="atMenu"
                    trigger="@"
                    :items="atMenuItems"
                    :active-index="atMenuActiveIndex"
                    :loading="atCommandsLoading && !atCommandsLoaded"
                    :heading="$t('composer.references')"
                    :hint="$t('composer.selectOneReference')"
                    :empty-label="$t('composer.noReferences')"
                    @select="selectAtCommand"
                    @hover="atMenu = atMenu ? { ...atMenu, activeIndex: $event } : null"
                  />
                  <div v-if="pendingMessageImages.length" class="message-image-drafts" aria-label="Images attached to this message">
                    <figure v-for="image in pendingMessageImages" :key="image.id">
                      <button
                        class="message-image-preview"
                        type="button"
                        :aria-label="`Preview ${image.name}`"
                        @click="openImagePreview({ name: image.name, url: image.content_url })"
                      >
                        <img :src="image.content_url" :alt="image.name" />
                      </button>
                      <button class="message-image-remove" type="button" :aria-label="`Remove ${image.name}`" @click="removeMessageImage(image.id)">×</button>
                    </figure>
                  </div>
                  <div v-if="!conversationStarted" class="composer-textarea-wrap" :class="{ 'token-selected': initialTokenHighlight, composing: composerComposing }">
                    <div ref="initialComposerHighlight" class="composer-input-mirror" aria-hidden="true"><template v-if="initialTokenHighlight"><template v-for="(segment, index) in initialTokenHighlight" :key="index"><mark v-if="segment.kind" :class="segment.kind === 'reference' ? 'reference' : ''">{{ segment.text }}</mark><span v-else>{{ segment.text }}</span></template></template><template v-else>{{ raw }}</template></div>
                    <textarea
                      ref="initialComposerInput"
                      :value="raw"
                      rows="3"
                      autofocus
                      :placeholder="$t('composer.messagePlaceholder')"
                      @input="updateComposerText($event, 'initial')"
                      @scroll.passive="syncComposerHighlight('initial')"
                      @compositionstart="composerComposing = true"
                      @compositionend="finishComposerComposition"
                      @click="handleComposerSelection('initial', $event)"
                      @keydown="handleComposerKeydown($event, 'initial')"
                    />
                  </div>
                  <div v-else class="composer-textarea-wrap" :class="{ 'token-selected': followUpTokenHighlight, composing: composerComposing }">
                    <div ref="followUpComposerHighlight" class="composer-input-mirror" aria-hidden="true"><template v-if="followUpTokenHighlight"><template v-for="(segment, index) in followUpTokenHighlight" :key="index"><mark v-if="segment.kind" :class="segment.kind === 'reference' ? 'reference' : ''">{{ segment.text }}</mark><span v-else>{{ segment.text }}</span></template></template><template v-else>{{ followUp }}</template></div>
                    <textarea
                      ref="followUpComposerInput"
                      :value="followUp"
                      rows="3"
                      :placeholder="$t('composer.continuePlaceholder')"
                      @input="updateComposerText($event, 'follow-up')"
                      @scroll.passive="syncComposerHighlight('follow-up')"
                      @compositionstart="composerComposing = true"
                      @compositionend="finishComposerComposition"
                      @click="handleComposerSelection('follow-up', $event)"
                      @keydown="handleComposerKeydown($event, 'follow-up')"
                    />
                  </div>
                  <div class="agent-input-footer">
                    <div class="composer-leading">
                      <AgentComposerControls
                        :providers="providers"
                        :selected-provider-id="selectedProviderId"
                        :effort="reasoningEffort"
                        :shell-approval="shellApprovalMode"
                        :disabled="loading"
                        :usage="conversationUsage"
                        :current-usage="currentContextUsage"
                        :context-composition="contextComposition"
                        :compaction-max-tokens="runtimeSettings.compaction_max_tokens"
                        @update:selected-provider-id="selectedProviderId = $event"
                        @update:effort="reasoningEffort = $event"
                        @update:shell-approval="updateShellApprovalMode"
                        @add-provider="navigate('settings')"
                      />
                    </div>
                    <div class="composer-submit">
                      <small>{{ loading ? $t('composer.enterToQueue') : $t('composer.enterToSend') }}</small>
                      <button
                        class="send-button"
                        :class="{ stop: loading }"
                        :disabled="!loading && !canSubmitMessage"
                        type="button"
                        :aria-label="loading ? 'Stop generating' : 'Send message'"
                        @click="loading ? stopGeneration() : submitConversation()"
                      >
                        <svg v-if="loading"><use href="#icon-stop" /></svg>
                        <svg v-else><use href="#icon-arrow" /></svg>
                      </button>
                    </div>
                  </div>
                </form>
              </div>
            </section>

            <aside class="artifact-pane artifact-workspace">
              <header class="artifact-collection-header">
                <div><strong>{{ $t('Artifacts') }}</strong><small>{{ $t('{count} in this conversation', { count: artifacts.length }) }}</small></div>
                <div class="artifact-collection-actions">
                  <span v-if="loading" class="artifact-syncing"><i />{{ $t('Updating') }}</span>
                  <button class="artifact-refresh" type="button" :title="$t('Refresh artifacts')" :aria-label="$t('Refresh artifacts')" :disabled="artifactRefreshing" @click="refreshSelectedArtifact">
                    <svg :class="{ spinning: artifactRefreshing }"><use href="#icon-refresh" /></svg>
                  </button>
                </div>
              </header>
              <div v-if="artifacts.length" class="artifact-list" aria-label="Conversation artifacts">
                <button v-for="artifact in artifacts" :key="artifact.id" :class="{ active: artifact.id === selectedArtifactId }" type="button" @click="selectArtifact(artifact)">
                  <span class="artifact-kind-icon">{{ artifact.artifact_type === 'card' ? '◇' : artifact.artifact_type === 'article' ? '¶' : artifact.artifact_type === 'slides' ? '▤' : '▧' }}</span>
                  <span><strong>{{ artifactTitle(artifactEditableContent(artifact)) }}</strong><small>{{ artifact.artifact_type }} · v{{ artifact.version }} · {{ artifact.status }}{{ hasPendingDraft(artifact) ? ' · unsaved draft' : '' }}</small></span>
                </button>
              </div>
              <div v-if="workspaceRestoring" class="artifact-placeholder">
                <span><svg><use href="#icon-cards" /></svg></span>
                <h2>{{ $t('Restoring conversation') }}</h2>
                <p>{{ $t('Artifacts appear once this conversation has loaded.') }}</p>
              </div>
              <div v-else-if="!artifactContent" class="artifact-placeholder">
                <span><svg><use href="#icon-cards" /></svg></span>
                <h2>{{ $t('No artifacts yet') }}</h2>
                <p>{{ $t('Keep talking with Zett Agent. Cards, articles, slides, and images will appear here when the conversation produces them.') }}</p>
              </div>
              <div v-else class="artifact-panel artifact-editor">
                <div class="artifact-editor-accent" />
                <header class="artifact-editor-header">
                  <div class="artifact-state"><i :class="{ saved: selectedArtifact?.status === 'saved' }" /><span><strong>{{ selectedArtifact?.artifact_type }} artifact</strong><small>{{ selectedArtifact?.status }} · version {{ selectedArtifact?.version }}{{ selectedArtifact && hasPendingDraft(selectedArtifact) ? ' · unsaved draft' : '' }}</small></span></div>
                  <div class="artifact-mode-switch" :aria-label="$t('Artifact display mode')"><button v-if="selectedArtifactDiff?.changed" type="button" :class="{ active: artifactDiff }" @click="artifactDiff = true; artifactPreview = false">{{ $t('Diff') }}</button><button v-if="['card', 'article', 'slides'].includes(artifactContent.artifact_type)" type="button" @click="openSelectedArtifactEditor">{{ $t('Edit') }}</button><button v-else type="button" :class="{ active: !artifactPreview && !artifactDiff }" @click="artifactPreview = false; artifactDiff = false">{{ $t('Edit') }}</button><button type="button" :class="{ active: artifactPreview && !artifactDiff }" @click="artifactPreview = true; artifactDiff = false">{{ $t('Preview') }}</button></div>
                </header>
                <div class="artifact-editor-body">
                  <ArtifactDiffView v-if="artifactDiff && selectedArtifactDiff" :diff="selectedArtifactDiff" />
                  <template v-else>
                  <div v-if="artifactContent.artifact_type === 'card'" class="card-meta-row">
                    <div class="card-type-control">
                      <span>{{ $t('Card type') }}</span>
                      <div class="card-type-options" role="group" :aria-label="$t('Card type')">
                        <button v-for="cardType in cardTypes" :key="cardType" :class="{ active: artifactContent.card_type === cardType }" type="button" @click="artifactContent.card_type = cardType">{{ $t(cardType) }}</button>
                      </div>
                    </div>
                  </div>
                  <template v-if="artifactContent.artifact_type === 'latex_pdf'">
                    <template v-if="!artifactPreview">
                      <label class="card-summary-control"><span>{{ $t('Project directory') }}</span><textarea v-model="artifactContent.project_path" rows="3" /></label>
                      <label class="card-title-control"><span>{{ $t('PDF filename') }}</span><textarea v-model="artifactContent.pdf_name" rows="1" /></label>
                      <p>{{ $t('Source files stay in the project directory. Compile the PDF before saving this reference.') }}</p>
                    </template>
                    <PdfPreview v-else-if="artifactPreviewAsset" ref="pdfPreviewRef" :asset="artifactPreviewAsset" artifact />
                  </template>
                  <template v-else-if="!artifactPreview">
                    <label class="card-title-control"><span>Title</span><textarea v-model="artifactContent.title" rows="2" /></label>
                    <label v-if="artifactContent.artifact_type === 'article' || artifactContent.artifact_type === 'slides'" class="card-summary-control"><span>Subtitle</span><textarea v-model="artifactContent.subtitle" rows="2" placeholder="Optional subtitle" /></label>
                    <label class="card-summary-control"><span>{{ artifactContent.artifact_type === 'image' ? 'Caption' : 'Summary' }}</span><textarea v-model="artifactContent.summary" rows="3" /></label>
                    <label v-if="artifactContent.artifact_type === 'image'" class="card-content-control"><span>Image prompt</span><textarea v-model="artifactContent.prompt" placeholder="Creative direction or generation prompt" /></label>
                    <label v-if="artifactContent.artifact_type === 'image'" class="card-summary-control"><span>Alt text</span><textarea v-model="artifactContent.alt_text" rows="3" /></label>
                    <template v-if="artifactContent.artifact_type === 'image'">
                      <label class="card-summary-control"><span>Source URL</span><textarea v-model="artifactContent.source_url" rows="2" placeholder="https://…" /></label>
                      <!-- The local key belongs to an uploaded session file, not to this edit: the assistant sets it through upload_asset, so it is shown read-only instead of being typed here. -->
                      <label v-if="artifactContent.asset_path" class="card-summary-control"><span>Local file</span><textarea :value="artifactContent.asset_path" rows="1" readonly /></label>
                    </template>
                    <label v-else class="card-content-control"><span>{{ artifactContent.artifact_type === 'article' ? 'Article' : artifactContent.artifact_type === 'slides' ? 'Slides' : 'Knowledge' }} · Markdown</span><textarea v-model="artifactContent.content" /></label>
                  </template>
                  <article v-else class="artifact-preview" :class="`artifact-preview-${artifactContent.artifact_type}`">
                    <SlidesPreview v-if="artifactContent.artifact_type === 'slides'" compact :title="artifactContent.title" :content="artifactContent.content" />
                    <template v-else>
                    <span class="artifact-preview-label">{{ artifactContent.artifact_type }}</span>
                    <h1>{{ artifactContent.title }}</h1>
                    <p v-if="artifactContent.artifact_type === 'article' && artifactContent.subtitle" class="article-subtitle">{{ artifactContent.subtitle }}</p>
                    <img v-if="artifactContent.artifact_type === 'image' && selectedImageUrl" :src="selectedImageUrl" :alt="artifactContent.alt_text" />
                    <div v-else-if="artifactContent.artifact_type === 'image'" class="image-brief-placeholder"><span>Image brief</span><p>{{ artifactContent.prompt || 'Waiting for an image source or generation step.' }}</p></div>
                    <MarkdownContent v-if="artifactContent.summary" class="preview-summary" :content="artifactContent.summary" />
                    <div v-if="artifactContent.artifact_type !== 'image'" class="preview-divider" />
                    <MarkdownContent v-if="artifactContent.artifact_type !== 'image'" class="preview-content" :content="artifactContent.content" />
                    </template>
                  </article>
                  <div v-if="artifactContent.artifact_type !== 'latex_pdf' && artifactContent.suggested_tags.length" class="suggestions card-tags-editor"><span>Classification</span><div class="suggestion-list"><label v-for="tag in artifactContent.suggested_tags" :key="tag.path" :class="{ selected: selectedSuggestions.includes(tag.path) }"><input v-model="selectedSuggestions" type="checkbox" :value="tag.path" /><span>{{ tag.path }}</span><small>{{ Math.round(tag.confidence * 100) }}%</small></label></div></div>
                  </template>
                </div>
                <footer class="panel-actions artifact-editor-actions"><button class="danger-button" type="button" @click="deleteSelectedArtifact">Delete</button><button class="primary-action" :disabled="saving || !artifactTitle(artifactContent).trim()" type="button" @click="saveSelectedArtifact">{{ saving ? 'Saving…' : artifactDiff && selectedArtifact?.draft_content ? 'Save draft' : artifactContent.artifact_type === 'image' ? 'Save changes' : selectedArtifact?.status === 'saved' ? `Update artifact ${artifactTypeLabel(artifactContent.artifact_type).toLowerCase()}` : 'Save artifact' }}<svg><use href="#icon-arrow" /></svg></button></footer>
              </div>
            </aside>
          </div>
        </section>
      </template>

      <template v-else-if="view === 'assets'">
        <StaticAssetsView
          ref="staticAssetsView"
          @drag-start="startStaticAssetDrag"
          @drag-end="endStaticAssetDrag"
        />
      </template>

      <template v-else-if="view === 'scheduledTasks'">
        <ScheduledTasksView @open-session="openScheduledSession" />
      </template>

      <template v-else-if="view === 'channels'">
        <ChannelsView />
      </template>

      <template v-else>
        <header class="topbar compact"><div><p class="eyebrow">{{ $t('Preferences') }}</p><h1>{{ $t('Settings') }}</h1></div></header>
        <section class="content settings-view">
          <nav class="settings-tabs" role="tablist" aria-label="Settings sections">
            <button :class="{ active: settingsSection === 'usage' }" type="button" role="tab" :aria-selected="settingsSection === 'usage'" @click="selectSettingsSection('usage')">{{ $t('settings.usage') }}</button>
            <button :class="{ active: settingsSection === 'providers' }" type="button" role="tab" :aria-selected="settingsSection === 'providers'" @click="selectSettingsSection('providers')">{{ $t('settings.providersLimits') }}</button>
          </nav>
          <div v-if="settingsSection === 'providers'" class="settings-section">
          <div class="settings-intro"><div><h2>{{ $t('AI providers') }}</h2><p>{{ $t('Keep multiple model connections and choose one for each conversation.') }}</p></div></div>
          <div class="provider-toolbar">
            <div v-if="providers.length" class="provider-list">
              <button v-for="provider in providers" :key="provider.id" :class="{ active: editingProviderId === provider.id }" type="button" @click="selectProvider(provider)"><span class="status-dot" :class="{ online: provider.enabled }" /><span><strong>{{ provider.name }}</strong><small>{{ provider.provider }} · {{ provider.model }}</small></span></button>
            </div>
            <button class="secondary-action" type="button" @click="newProvider"><svg><use href="#icon-add" /></svg>{{ $t('New provider') }}</button>
          </div>
          <form class="settings-card" @submit.prevent="saveAI">
            <div class="form-grid">
              <label class="field"><span>{{ $t('Connection name') }}</span><input v-model="ai.name" placeholder="e.g. Fast OpenAI" /><small>Shown in the conversation provider picker.</small></label>
              <label class="field"><span>{{ $t('Provider') }}</span><select v-model="ai.provider" @change="selectProviderKind"><option value="openai_compatible">OpenAI compatible</option><option value="responses_compatible">Responses compatible</option><option value="openai">OpenAI</option><option value="deepseek">DeepSeek</option><option value="anthropic">Anthropic</option><option value="google">Google Gemini</option><option value="ollama">Ollama</option></select><small>The API format used for model requests.</small></label>
              <label class="field"><span>{{ $t('Model') }}</span><input v-model="ai.model" placeholder="e.g. gpt-4.1-mini" /><small>Use the exact model identifier from your provider.</small></label>
              <label class="field full"><span>{{ $t('Base URL') }} <em>{{ ['openai_compatible', 'responses_compatible'].includes(ai.provider) ? 'Custom' : 'Auto-filled' }}</em></span><input v-model="ai.base_url" :placeholder="ai.provider === 'responses_compatible' ? 'https://api.example.com' : 'https://api.example.com/v1'" /><small>{{ providerBaseUrlHelp(ai.provider) }}</small></label>
              <label class="field full"><span>{{ $t('API key') }} <em>{{ providerLoading ? 'Loading…' : editingProviderId === null ? 'New' : ai.api_key ? 'Loaded' : 'Not set' }}</em></span><div class="secret-input"><input v-model="ai.api_key" :type="apiKeyVisible ? 'text' : 'password'" autocomplete="off" placeholder="Leave blank to keep the saved key" /><button type="button" :aria-label="apiKeyVisible ? 'Hide API key' : 'Show API key'" :title="apiKeyVisible ? 'Hide API key' : 'Show API key'" @click="apiKeyVisible = !apiKeyVisible"><svg aria-hidden="true"><use :href="apiKeyVisible ? '#icon-eye-off' : '#icon-eye'" /></svg></button></div><small>Stored encrypted locally. Saving a blank value keeps the existing key.</small></label>
              <label class="field temperature-field"><span>{{ $t('Temperature') }} <output>{{ ai.temperature.toFixed(1) }}</output></span><input v-model.number="ai.temperature" type="range" min="0" max="2" step="0.1" /></label>
              <div v-if="ai.provider === 'responses_compatible'" class="field"><span>{{ $t('API mode') }}</span><strong>Responses API</strong><small>This compatible connection always uses the Responses protocol.</small></div>
              <div v-else-if="['openai', 'openai_compatible', 'deepseek'].includes(ai.provider)" class="field"><span>{{ $t('API mode') }}</span><div class="mode-options" role="group" :aria-label="$t('API mode')"><button type="button" :class="{ active: !ai.response }" @click="setResponseMode(false)">Chat Completions</button><button type="button" :class="{ active: ai.response }" @click="setResponseMode(true)">Responses API</button></div><small>Responses mode enables provider-hosted tools such as web search.</small></div>
            </div>
            <div class="settings-actions"><button v-if="editingProviderId !== null" class="danger-button" type="button" @click="removeProvider">Delete provider</button><span v-else>Credentials are encrypted in your local database.</span><div><label class="switch"><input v-model="ai.enabled" type="checkbox" /><span /><small>{{ ai.enabled ? 'Enabled' : 'Disabled' }}</small></label><button class="primary-action" :disabled="providerSaving || providerLoading || !ai.name || !ai.model" :aria-busy="providerSaving" type="submit"><span v-if="providerSaving" class="button-spinner" aria-hidden="true" /><span>{{ providerSaving ? 'Testing…' : editingProviderId === null ? 'Add provider' : 'Save provider' }}</span></button></div></div>
          </form>

          <div class="settings-intro runtime-settings-heading">
            <div><h2>{{ $t('Conversation limits') }}</h2><p>{{ $t('Control local limits applied to new Agent requests.') }}</p></div>
          </div>
          <form class="settings-card" @submit.prevent="saveRuntimeSettings">
            <div class="form-grid">
              <label class="field">
                <span>{{ $t('Images per message') }}</span>
                <input v-model.number="runtimeSettings.max_message_images" type="number" min="1" max="256" step="1" />
                <small>Maximum number of images that can be pasted into one user message.</small>
              </label>
              <label class="field">
                <span>{{ $t('Model steps per turn') }}</span>
                <input v-model.number="runtimeSettings.max_turn_iterations" type="number" min="1" max="512" step="1" />
                <small>Maximum model calls, including tool-loop continuations, allowed in one turn.</small>
              </label>
              <label class="field">
                <span>{{ $t('Max asset file size') }} <em>MB</em></span>
                <input v-model.number="maxAssetSizeMb" type="number" min="1" max="2048" step="1" />
                <small>{{ $t('Maximum size for an uploaded image or file in this conversation.') }}</small>
              </label>
              <label class="field">
                <span>{{ $t('Compact context at') }}</span>
                <input v-model.number="runtimeSettings.compaction_max_tokens" type="number" min="128000" max="800000" step="1000" />
                <small>Estimated active-context tokens that trigger a compact snapshot.</small>
              </label>
              <label class="field">
                <span>{{ $t('Keep recent context') }}</span>
                <input v-model.number="runtimeSettings.compaction_keep_recent_tokens" type="number" min="32000" max="256000" step="1000" />
                <small>Recent estimated tokens retained verbatim after compaction.</small>
              </label>
            </div>
            <div class="settings-actions">
              <span>Stored locally and applied without restarting Zett.</span>
              <div><button class="primary-action" :disabled="runtimeSettingsSaving" type="submit">{{ runtimeSettingsSaving ? 'Saving…' : $t('Save limits') }}</button></div>
            </div>
          </form>
          </div>
          <div v-else class="settings-section">
          <div class="settings-intro runtime-settings-heading">
            <div><h2>{{ $t('Model activity') }}</h2><p>{{ $t('Daily token requests recorded from completed LLM calls.') }}</p></div>
          </div>
          <div class="settings-card">
            <div v-if="usageActivityLoading" class="settings-activity-state">Loading activity…</div>
            <UsageActivityGraph v-else :days="usageActivity" />
          </div>

          <div class="settings-intro runtime-settings-heading">
            <div><h2>{{ $t('By model') }}</h2><p>{{ $t('Request volume and token usage for every provider model.') }}</p></div>
          </div>
          <div v-if="usageActivityLoading" class="settings-activity-state">Loading model activity…</div>
          <div v-else-if="!modelUsageActivity.length" class="settings-card settings-activity-state">No model activity recorded yet.</div>
          <div v-else class="model-usage-list">
            <ModelUsageTrend
              v-for="series in modelUsageActivity"
              :key="`${series.provider || 'unknown'}:${series.model || 'unknown'}`"
              :provider="series.provider"
              :model="series.model"
              :days="series.days"
            />
          </div>
          </div>
        </section>
      </template>

      <Teleport to="body">
        <section v-if="fullscreenSlidesItem" ref="librarySlidesStage" class="library-slides-fullscreen" role="dialog" aria-modal="true" :aria-label="fullscreenSlidesItem.title" tabindex="-1">
          <button class="library-slides-close" type="button" aria-label="Close fullscreen preview" @click="closeSlidesFullscreen">×</button>
          <SlidesPreview :title="fullscreenSlidesItem.title" :content="fullscreenSlidesItem.content" :show-fullscreen-button="false" auto-focus />
        </section>
      </Teleport>
      <div v-if="libraryPdfLaunch" class="library-pdf-launch">
        <PdfPreview
          :asset="libraryClient.documentReference(libraryPdfLaunch.item.id)"
          artifact
          :initial-mode="libraryPdfLaunch.mode"
          @close="libraryPdfLaunch = null"
        />
      </div>
      <Transition name="sheet">
        <div v-if="selectedLibraryItem" class="detail-backdrop" @click.self="selectedLibraryItem = null">
          <aside class="detail-sheet" role="dialog" aria-modal="true" :aria-label="selectedLibraryItem.title">
            <header class="detail-header">
              <div><span class="card-type">{{ selectedLibraryItem.item_type === 'card' ? selectedLibraryItem.card_type : selectedLibraryItem.item_type }}</span></div>
              <div class="detail-header-actions">
                <button class="detail-header-button" type="button" @click="openArtifactSession(selectedLibraryItem)"><svg><use href="#icon-conversation" /></svg>Conversation</button>
                <button class="detail-header-button" type="button" @click="copyLibraryItemId(selectedLibraryItem)"><svg><use href="#icon-copy" /></svg>Copy ID</button>
                <button v-if="selectedLibraryItem.item_type !== 'latex_pdf'" class="detail-header-button" type="button" @click="openLibraryEditor(selectedLibraryItem)"><svg><use href="#icon-edit" /></svg>Edit</button>
                <button class="detail-delete-button" :disabled="deletingLibraryItemId !== null" type="button" @click="deleteSelectedLibraryItem"><svg><use href="#icon-trash" /></svg>Delete</button>
                <button class="close-button" type="button" aria-label="Close resource details" @click="selectedLibraryItem = null">×</button>
              </div>
            </header>
            <div class="detail-content">
              <h1>{{ selectedLibraryItem.title }}</h1>
              <p v-if="selectedLibraryItem.item_type !== 'card' && selectedLibraryItem.subtitle" class="detail-subtitle">{{ selectedLibraryItem.subtitle }}</p>
              <MarkdownContent v-if="selectedLibraryItem.summary" class="detail-summary" :content="selectedLibraryItem.summary" />
              <div v-if="selectedLibraryItem.tags.length" class="detail-tags"><span v-for="path in selectedLibraryItem.tags" :key="path">{{ path }}</span></div>

              <section class="detail-section"><h2>{{ selectedLibraryItem.item_type === 'article' ? 'Article' : selectedLibraryItem.item_type === 'slides' ? 'Slide deck' : 'Content' }}</h2><PdfPreview v-if="selectedLibraryItem.item_type === 'latex_pdf'" :asset="libraryClient.documentReference(selectedLibraryItem.id)" artifact /><SlidesPreview v-else-if="selectedLibraryItem.item_type === 'slides'" :title="selectedLibraryItem.title" :content="selectedLibraryItem.content" /><MarkdownContent v-else class="detail-body" :content="selectedLibraryItem.content" /></section>
              <section v-if="selectedLibraryItem.raw_content" class="detail-section raw-section"><h2>Original input</h2><div class="detail-body">{{ selectedLibraryItem.raw_content }}</div></section>

              <dl class="detail-metadata">
                <div><dt>Type</dt><dd>{{ selectedLibraryItem.item_type }}</dd></div>
                <div><dt>Status</dt><dd>{{ selectedLibraryItem.status }}</dd></div>
                <div><dt>Created</dt><dd>{{ formatDateTime(selectedLibraryItem.created_at) }}</dd></div>
                <div><dt>Updated</dt><dd>{{ formatDateTime(selectedLibraryItem.updated_at) }}</dd></div>
                <div><dt>Artifact ID</dt><dd>{{ selectedLibraryItem.id }}</dd></div>
              </dl>
            </div>
          </aside>
        </div>
      </Transition>
    </main>
  </div>
</template>
<style>
:root {
  font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Helvetica Neue", sans-serif;
  color: #1d1d1f;
  background: #f5f5f7;
  font-synthesis: none;
  text-rendering: optimizeLegibility;
  --accent: #476957;
  --accent-dark: #345243;
  --accent-soft: #e5eee9;
  --text: #1d1d1f;
  --secondary: #6e6e73;
  --tertiary: #929298;
  --line: rgba(29, 29, 31, 0.1);
  --surface: rgba(255, 255, 255, 0.82);
  --sidebar: rgba(232, 232, 235, 0.78);
  --shadow: 0 18px 54px rgba(24, 28, 26, 0.08), 0 2px 10px rgba(24, 28, 26, 0.04);
}

* { box-sizing: border-box; }
html, body, #app { min-height: 100%; }
body { margin: 0; min-width: 320px; background: radial-gradient(circle at 78% 0%, #edf3ef 0, transparent 34rem), #f5f5f7; }
button, input, textarea, select { font: inherit; }
button { -webkit-tap-highlight-color: transparent; }
button:focus-visible, input:focus-visible, textarea:focus-visible, select:focus-visible { outline: 3px solid rgba(0, 122, 255, 0.22); outline-offset: 2px; }
button:active { transform: scale(0.97); transition: transform 100ms ease-out; }
svg { width: 1.25rem; height: 1.25rem; fill: none; stroke: currentColor; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; }
.icon-library { position: absolute; width: 0; height: 0; overflow: hidden; }

.app-shell { min-height: 100vh; display: grid; grid-template-columns: 16.5rem minmax(0, 1fr); }
.sidebar { position: fixed; inset: 0 auto 0 0; width: 16.5rem; display: flex; flex-direction: column; padding: 1.25rem 0.85rem 0; overflow: hidden; background: var(--sidebar); border-right: 1px solid rgba(255, 255, 255, 0.62); box-shadow: inset -1px 0 rgba(29, 29, 31, 0.06); backdrop-filter: blur(28px) saturate(150%); -webkit-backdrop-filter: blur(28px) saturate(150%); z-index: 10; }
.brand { display: flex; align-items: center; gap: 0.72rem; width: 100%; padding: 0.35rem 0.55rem 1.35rem; border: 0; background: transparent; color: var(--text); text-align: left; cursor: pointer; }
.brand-mark { display: grid; place-items: center; width: 2.15rem; height: 2.15rem; flex: 0 0 auto; }
.brand-mark img { display: block; width: 100%; height: 100%; object-fit: contain; filter: drop-shadow(0 4px 5px rgba(53, 83, 67, 0.18)); }
.brand strong, .brand small { display: block; }
.brand strong { font-size: 0.94rem; line-height: 1.2; letter-spacing: -0.012em; }
.brand small { margin-top: 0.12rem; color: var(--secondary); font-size: 0.69rem; letter-spacing: 0.01em; }
.primary-nav { display: grid; gap: 0.18rem; }
.primary-nav button, .sidebar-footer button, .tag-select { position: relative; display: flex; align-items: center; width: 100%; border: 0; color: #3b3b3e; background: transparent; cursor: pointer; text-align: left; }
.primary-nav button, .sidebar-footer button { gap: 0.7rem; min-height: 2.35rem; padding: 0 0.7rem; border-radius: 0.62rem; font-size: 0.83rem; font-weight: 530; }
.primary-nav button:hover, .sidebar-footer button:hover, .tag-select:hover { background: rgba(255, 255, 255, 0.48); }
.primary-nav button.active, .sidebar-footer button.active { background: rgba(255, 255, 255, 0.82); color: var(--text); box-shadow: 0 1px 4px rgba(0,0,0,.05), inset 0 0 0 1px rgba(255,255,255,.5); }
.primary-nav button svg, .sidebar-footer button svg { width: 1rem; height: 1rem; color: #646468; }
.primary-nav button small { margin-left: auto; color: var(--tertiary); font-size: 0.68rem; font-variant-numeric: tabular-nums; }
kbd { margin-left: auto; padding: 0.12rem 0.34rem; border: 1px solid rgba(29,29,31,.1); border-radius: 0.28rem; color: #8a8a8f; background: rgba(255,255,255,.5); box-shadow: 0 1px rgba(255,255,255,.7); font-family: inherit; font-size: 0.62rem; }
.sidebar-section { min-height: 0; display: flex; flex: 1; flex-direction: column; margin-top: 1.55rem; }
.sidebar-heading { display: flex; align-items: center; justify-content: space-between; padding: 0 0.55rem 0.4rem; color: #818186; font-size: 0.66rem; font-weight: 650; letter-spacing: .045em; text-transform: uppercase; }
.sidebar-heading button { display: grid; place-items: center; width: 1.5rem; height: 1.5rem; padding: 0; border: 0; border-radius: 50%; background: transparent; color: #747479; cursor: pointer; }
.sidebar-heading button:hover { background: rgba(255,255,255,.6); }
.sidebar-heading svg { width: .85rem; height: .85rem; }
.tag-list { min-height: 0; overflow: auto; scrollbar-width: thin; scrollbar-color: rgba(29,29,31,.16) transparent; }
.tag-row { position: relative; display: flex; align-items: center; min-width: 0; height: 2rem; padding-left: calc(var(--tag-depth) * .72rem); }
.tag-row::before { position: absolute; top: 0; bottom: 0; left: calc(.62rem + (var(--tag-depth) - 1) * .72rem); width: 1px; background: rgba(76,96,84,.12); content: ''; opacity: min(1, var(--tag-depth)); }
.tag-row.drop-target { border-radius: .58rem; background: rgba(225,237,230,.82); box-shadow: inset 0 0 0 1px rgba(80,122,96,.2); }
.tag-row.drop-target .tag-select { color: #315641; background: transparent; font-weight: 660; }
.tag-row.drop-target .tag-dot { background: #5f8a70 !important; transform: scale(1.22); }
.tag-row.drop-busy .tag-select { cursor: progress; }
.tag-select { min-width: 0; height: 1.85rem; gap: .58rem; padding: 0 .55rem 0 .2rem; border-radius: .5rem; font-size: .77rem; }
.tag-select.active { color: var(--accent-dark); background: rgba(255,255,255,.64); font-weight: 600; }
.tag-toggle, .tag-toggle-placeholder { display: grid; width: 1.25rem; height: 1.85rem; flex: 0 0 1.25rem; place-items: center; }
.tag-toggle { padding: 0; border: 0; border-radius: .35rem; color: #8a948e; background: transparent; cursor: pointer; }
.tag-toggle:hover { color: #486453; background: rgba(255,255,255,.55); }
.tag-toggle span { display: block; font-size: .78rem; line-height: 1; transform: translateY(-1px); transition: transform 140ms ease; }
.tag-toggle.collapsed span { transform: rotate(-90deg); }
.tag-dot { width: .42rem; height: .42rem; flex: 0 0 auto; border-radius: 50%; background: #91a89b; box-shadow: inset 0 0 0 1px rgba(0,0,0,.06); }
.tag-label { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.tag-select small { margin-left: auto; color: #98989d; font-size: .66rem; }
.tag-delete { position: absolute; right: .2rem; z-index: 2; display: grid; place-items: center; width: 1.55rem; height: 1.55rem; padding: 0; border: 0; border-radius: .42rem; color: #a35e5e; background: rgba(250, 243, 242, .96); cursor: pointer; transition: color 120ms ease, background 120ms ease; }
.tag-delete svg { width: .82rem; height: .82rem; }
.tag-delete:hover { color: #963f3f; background: #f7e7e5; }
.tag-delete:disabled { cursor: default; opacity: .35; }
.session-section { overflow: hidden; }
.session-history-list { min-height: 0; display: grid; flex: 1; align-content: start; gap: .18rem; overflow-y: auto; padding-bottom: .7rem; scrollbar-width: thin; }
.session-history-item { position: relative; min-width: 0; border-radius: .58rem; transition: background 180ms ease, box-shadow 180ms ease, opacity 180ms ease; animation: session-item-in 200ms cubic-bezier(.2,.8,.2,1) both; }
@keyframes session-item-in { from { opacity: 0; transform: translateY(4px); } }
.session-history-item:hover { background: rgba(255,255,255,.5); }
.session-history-item.active { background: rgba(255,255,255,.86); box-shadow: 0 1px 5px rgba(0,0,0,.05); }
.session-history-item.switching { background: rgba(255,255,255,.72); }
.session-history-item.switching .session-open-button { opacity: .72; }
.session-open-button { min-width: 0; width: 100%; display: flex; align-items: center; justify-content: space-between; gap: .5rem; padding: .55rem 2.15rem .55rem .6rem; border: 0; border-radius: inherit; color: var(--text); background: transparent; cursor: pointer; text-align: left; }
.session-open-button > span { min-width: 0; }
.session-history-list strong, .session-history-list small { display: block; }
.session-history-list strong { overflow: hidden; font-size: .72rem; font-weight: 610; text-overflow: ellipsis; white-space: nowrap; }
.session-history-list strong:hover { color: var(--accent); text-decoration: underline; text-underline-offset: .16rem; }
.session-history-list small { margin-top: .15rem; color: var(--tertiary); font-size: .57rem; white-space: nowrap; }
.session-open-button > small { flex: 0 0 auto; margin: 0; padding: .15rem .35rem; border-radius: 1rem; background: rgba(71,105,87,.08); }
.session-title-editor { display: grid; grid-template-columns: minmax(0, 1fr) auto auto; gap: .2rem; padding: .35rem; }
.session-title-editor input { min-width: 0; height: 1.9rem; padding: 0 .45rem; border: 1px solid rgba(71,105,87,.35); border-radius: .42rem; outline: 0; background: #fff; font: inherit; font-size: .67rem; }
.session-title-editor input:focus { border-color: var(--accent); box-shadow: 0 0 0 2px rgba(71,105,87,.1); }
.session-title-editor button { padding: 0 .38rem; border: 0; border-radius: .38rem; color: var(--accent); background: rgba(71,105,87,.08); cursor: pointer; font-size: .55rem; }
.session-delete-button { position: absolute; top: 50%; right: .38rem; display: grid; place-items: center; width: 1.45rem; height: 1.45rem; padding: 0; opacity: 0; transform: translateY(-50%); border: 0; border-radius: .4rem; color: #9a7777; background: rgba(255,255,255,.82); cursor: pointer; transition: opacity 120ms ease, color 120ms ease, background 120ms ease; }
.session-delete-button svg { width: .72rem; height: .72rem; }
.session-history-item:hover .session-delete-button, .session-delete-button:focus-visible { opacity: 1; }
.session-delete-button:hover { color: #a63f3f; background: #f8eaea; }
.session-history-skeleton { height: 2.3rem; margin: .05rem .45rem .25rem; border: 0; border-radius: .6rem; background: linear-gradient(100deg, rgba(255,255,255,.32) 28%, rgba(255,255,255,.95) 44%, rgba(255,255,255,.32) 60%); background-size: 220% 100%; box-shadow: inset 0 0 0 1px rgba(29,29,31,.05); animation: shimmer 1.35s linear infinite; }
.session-list-loading { display: flex; align-items: center; justify-content: center; gap: .45rem; padding: .6rem 0 .35rem; color: var(--tertiary); }
.session-list-loading .session-switch-spinner { width: 1rem; height: 1rem; border-width: 1.5px; }
.sidebar-empty { padding: .55rem; color: var(--tertiary); font-size: .72rem; }
.sidebar-footer { padding: .65rem 0 .15rem; border-top: 1px solid rgba(29,29,31,.07); }
.sidebar-footer .channels-nav-button { margin-bottom: .65rem; }
.locale-control { display: flex; align-items: center; justify-content: space-between; gap: .45rem; margin-bottom: .3rem; padding: 0 .55rem; color: #77777c; font-size: .64rem; }
.locale-control select { min-width: 5.4rem; height: 1.8rem; padding: 0 1.65rem 0 .55rem; border: 1px solid rgba(29,29,31,.1); border-radius: .5rem; color: #4e5651; background: rgba(255,255,255,.65); cursor: pointer; font-size: .65rem; }
.status-dot { margin-left: auto; width: .43rem; height: .43rem; border-radius: 50%; background: #aaa; box-shadow: 0 0 0 3px rgba(0,0,0,.03); }
.status-dot.online { background: #49a369; box-shadow: 0 0 0 3px rgba(73,163,105,.12); }

.workspace { min-width: 0; min-height: 100vh; grid-column: 2; }
.topbar { position: sticky; top: 0; z-index: 8; min-height: 5rem; display: flex; align-items: center; gap: 1rem; padding: 1rem clamp(1.5rem, 4vw, 4rem); background: rgba(245,245,247,.97); backdrop-filter: blur(22px) saturate(160%); -webkit-backdrop-filter: blur(22px) saturate(160%); }
.topbar::after { content: ""; position: absolute; left: 0; right: 0; bottom: -0.8rem; height: .8rem; background: linear-gradient(rgba(245,245,247,.55), transparent); pointer-events: none; }
.topbar.compact { justify-content: space-between; }
.topbar.compact h1 { margin: .1rem 0 0; font-size: 1.45rem; }
.chat-topbar { min-height: 4.5rem; }
.chat-topbar-title { display: flex; align-items: center; gap: .55rem; color: var(--secondary); font-size: .75rem; font-weight: 620; }
.chat-topbar-title .status-dot { margin-left: 0; }
.workspace-view-switch { display: flex; gap: .16rem; padding: .17rem; border: 1px solid rgba(60,78,67,.1); border-radius: .62rem; background: rgba(235,239,236,.82); }
.workspace-view-switch button { min-height: 1.8rem; padding: 0 .68rem; border: 0; border-radius: .46rem; color: #68736c; background: transparent; cursor: pointer; font-size: .62rem; font-weight: 650; }
.workspace-view-switch button:hover { color: #355442; }
.workspace-view-switch button.active { color: #31523f; background: #fff; box-shadow: 0 1px 4px rgba(38,57,46,.1); }
.search-field { flex: 1; max-width: 38rem; height: 2.65rem; display: flex; align-items: center; gap: .65rem; padding: 0 .85rem; border: 1px solid rgba(29,29,31,.08); border-radius: .78rem; background: rgba(255,255,255,.72); box-shadow: 0 1px 4px rgba(0,0,0,.035), inset 0 1px rgba(255,255,255,.8); transition: box-shadow 180ms ease, background 180ms ease; }
.search-field:focus-within { background: white; box-shadow: 0 0 0 3px rgba(71,105,87,.12), 0 8px 24px rgba(0,0,0,.05); }
.search-field svg { width: 1rem; height: 1rem; color: #85858a; }
.search-field input { flex: 1; min-width: 0; border: 0; outline: 0; color: var(--text); background: transparent; font-size: .84rem; }
.search-field input::placeholder { color: #9c9ca1; }
.search-field button { width: 1.5rem; height: 1.5rem; padding: 0; border: 0; border-radius: 50%; background: #e8e8eb; color: #77777c; cursor: pointer; }
.search-field kbd { margin-left: 0; }
.primary-action, .secondary-action, .text-button, .close-button { border: 0; cursor: pointer; }
.primary-action { min-height: 2.55rem; display: inline-flex; align-items: center; justify-content: center; gap: .42rem; padding: 0 1rem; border-radius: .72rem; color: white; background: linear-gradient(180deg, #537764, #3d604e); box-shadow: 0 4px 12px rgba(52,82,67,.18), inset 0 1px rgba(255,255,255,.18); font-size: .8rem; font-weight: 620; }
.primary-action:hover { filter: brightness(1.04); }
.primary-action:disabled { opacity: .45; cursor: not-allowed; transform: none; }
.primary-action svg { width: .95rem; height: .95rem; }
.button-spinner { width: .86rem; height: .86rem; flex: 0 0 auto; border: 1.5px solid rgba(255,255,255,.38); border-top-color: #fff; border-radius: 50%; animation: session-spin 720ms linear infinite; }
.secondary-action { min-height: 2.55rem; padding: 0 1rem; border-radius: .72rem; color: #55555a; background: #efeff1; font-size: .8rem; font-weight: 560; }
.text-button { color: var(--accent-dark); background: transparent; font-size: .8rem; font-weight: 560; }
.close-button { width: 2rem; height: 2rem; border-radius: 50%; color: #606065; background: rgba(224,224,227,.78); font-size: 1.2rem; line-height: 1; }

.content { width: min(100%, 76rem); margin: 0 auto; padding: 2.15rem clamp(1.5rem, 4vw, 4rem) 5rem; }
.library-view { width: min(100%, 84rem); }
.page-heading { display: flex; align-items: end; justify-content: space-between; gap: 1rem; margin-bottom: 1.75rem; }
.eyebrow { margin: 0; color: var(--accent); font-size: .67rem; font-weight: 700; letter-spacing: .075em; text-transform: uppercase; }
.page-heading h1 { margin: .35rem 0 .3rem; font-size: clamp(1.85rem, 3vw, 2.45rem); line-height: 1.06; letter-spacing: -.032em; }
.page-heading p:last-child, .settings-intro p, .editor-intro p { margin: 0; color: var(--secondary); font-size: .82rem; line-height: 1.55; }
.library-type-filters { display: flex; align-items: center; gap: .3rem; margin: -1rem 0 1.15rem; }
.library-type-filters > span { margin-right: .25rem; color: #8c938f; font-size: .66rem; font-weight: 680; letter-spacing: .045em; text-transform: uppercase; }
.library-type-filters button { min-height: 1.85rem; padding: 0 .7rem; border: 1px solid transparent; border-radius: .58rem; color: #727975; background: transparent; cursor: pointer; font-size: .7rem; font-weight: 610; }
.library-type-filters button:hover { color: #435449; background: rgba(255,255,255,.6); }
.library-type-filters button.active { border-color: rgba(78,111,91,.12); color: #3f604c; background: #edf3ef; box-shadow: inset 0 0 0 1px rgba(255,255,255,.55); }
.card-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 17rem), 1fr)); gap: 1rem; }
/* A filtered grid is remounted, so its cards rise the last few pixels into place.
   `backwards` fill keeps the start state during the stagger delay and hands the
   transform back to the hover lift once the animation ends. */
.card-grid > article.card { animation: card-float-in 420ms cubic-bezier(.22,.72,.24,1) backwards; }
@keyframes card-float-in { from { opacity: 0; transform: translateY(14px); } }
.card { container-type: inline-size; container-name: artifact-card; min-width: 0; height: 18rem; box-sizing: border-box; display: flex; flex-direction: column; padding: 1.1rem 1.2rem; overflow: hidden; border: 1px solid rgba(29,29,31,.075); border-radius: 1rem; background: var(--surface); box-shadow: 0 1px 2px rgba(0,0,0,.025); backdrop-filter: blur(14px); transition: transform 260ms cubic-bezier(.2,.8,.2,1), box-shadow 260ms cubic-bezier(.2,.8,.2,1), background 180ms ease; }
.card[role="button"] { cursor: pointer; }
.card[draggable="true"] { cursor: grab; }
.card[draggable="true"]:active { cursor: grabbing; }
.card.dragging { opacity: .52; transform: scale(.985); }
.card:hover { transform: translateY(-3px); background: rgba(255,255,255,.96); box-shadow: var(--shadow); }
.card:active { transform: scale(.985); transition-duration: 100ms; }
.card-topline { min-width: 0; display: flex; align-items: center; justify-content: space-between; gap: .45rem; }
.card-topline .card-type { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.card-topline-actions { display: flex; align-items: center; gap: .16rem; }
.card-action-button { display: grid; place-items: center; width: 1.75rem; height: 1.75rem; padding: 0; border: 0; border-radius: .5rem; color: #8b918d; background: transparent; cursor: pointer; transition: color 160ms ease, background 160ms ease, transform 160ms ease; }
.card-action-button:hover, .card-action-button:focus-visible { color: #365845; background: #e9f0ec; outline: none; transform: scale(1.04); }
.card-action-button.danger:hover, .card-action-button.danger:focus-visible { color: #a33e3e; background: #f8eded; }
.card-action-button:disabled { opacity: .4; cursor: wait; transform: none; }
.card-action-button svg { width: .86rem; height: .86rem; }
@container artifact-card (max-width: 15rem) {
  .card-topline-actions { gap: .05rem; }
  .card-action-button { width: 1.55rem; height: 1.55rem; }
  .card-copy-action { display: none; }
}
.card-type { padding: .25rem .5rem; border-radius: 2rem; color: var(--accent-dark); background: var(--accent-soft); font-size: .62rem; font-weight: 680; letter-spacing: .04em; text-transform: uppercase; }
.card time { color: var(--tertiary); font-size: .65rem; }
.card h2 { display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2; flex-shrink: 0; max-height: 2.8em; margin: 1rem 0 .65rem; overflow: hidden; overflow-wrap: anywhere; font-size: 1.05rem; line-height: 1.4; letter-spacing: -.017em; }
.library-article .card-type { color: #665139; background: #f4ede3; }
.library-slides .card-type { color: #385d49; background: #e7f0ea; }
.library-latex_pdf h2 { margin-bottom: .5rem; }
.library-pdf-thumbnail { flex: 1 1 0; min-width: 0; min-height: 0; margin: 0 0 .25rem; overflow: hidden; border: 1px solid rgba(42,55,47,.09); border-radius: .55rem; background: #e7eae8; }
.library-deck-summary { display: flex; align-items: center; gap: .45rem; flex-shrink: 0; margin-bottom: .65rem; color: #607c6c; font-size: .68rem; }
.library-deck-summary svg { width: 1.1rem; height: 1.1rem; flex-shrink: 0; }
.card > .card-excerpt { display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 3; flex-shrink: 0; max-height: 4.8em; margin: 0; overflow: hidden; overflow-wrap: anywhere; color: var(--secondary); font-size: .78rem; line-height: 1.6; }
.card-footer-info { display: grid; min-width: 0; gap: .6rem; }
.card-footer { display: flex; align-items: end; justify-content: space-between; gap: .5rem; margin-top: auto; padding-top: 1rem; }
.card-tags { display: flex; min-width: 0; overflow: hidden; gap: .3rem; }
.card-tags span { max-width: 8rem; padding: .23rem .45rem; overflow: hidden; border-radius: .35rem; color: #737378; background: #f0f0f2; font-size: .62rem; text-overflow: ellipsis; white-space: nowrap; }
.card-footer > svg { width: .95rem; height: .95rem; flex: 0 0 auto; color: #a0a0a5; transition: transform 180ms ease; }
.card:hover .card-footer > svg { transform: translateX(3px); color: var(--accent); }
.skeleton { border: 0; background: linear-gradient(100deg, rgba(255,255,255,.55) 30%, rgba(255,255,255,.92) 45%, rgba(255,255,255,.55) 60%); background-size: 220% 100%; animation: shimmer 1.4s infinite linear; }
@keyframes shimmer { to { background-position-x: -220%; } }
.empty-state { min-height: 28rem; display: grid; place-items: center; align-content: center; text-align: center; }
.empty-icon, .feature-icon { display: grid; place-items: center; width: 3rem; height: 3rem; border-radius: 1rem; color: var(--accent); background: var(--accent-soft); box-shadow: inset 0 0 0 1px rgba(71,105,87,.06); }
.empty-icon svg, .feature-icon svg { width: 1.35rem; height: 1.35rem; }
.empty-state h2 { margin: 1rem 0 .35rem; font-size: 1.1rem; letter-spacing: -.015em; }
.empty-state p { max-width: 24rem; margin: 0 0 1.25rem; color: var(--secondary); font-size: .8rem; line-height: 1.55; }

.create-view { width: min(100%, 124rem); max-width: 124rem; padding-right: clamp(.55rem, 1vw, 1rem); padding-left: clamp(.55rem, 1vw, 1rem); }
.agent-workspace { height: calc(100vh - 8.2rem); min-height: 39rem; display: grid; grid-template-columns: minmax(0, 2fr) minmax(0, 5fr) minmax(0, 3fr); gap: .72rem; }
@media (min-width: 1181px) { .agent-workspace.assets-hidden { grid-template-columns: minmax(0, 5fr) minmax(0, 3fr); } }
.trace-workspace { height: calc(100vh - 8.2rem); min-height: 39rem; }
@media (min-width: 1181px) {
  /* The workspace owns its scrolling on a wide screen: it fills the viewport below the
     bar, so the page itself never scrolls and no pane slides under the sticky topbar. */
  .create-view { height: calc(100vh - 4.5rem); min-height: 0; display: flex; flex-direction: column; overflow: hidden; padding-top: .9rem; padding-bottom: 1rem; }
  .create-view > .agent-workspace, .create-view > .trace-workspace { flex: 1 1 auto; height: auto; min-height: 0; }
}
.assets-pane, .agent-chat, .artifact-pane { min-width: 0; min-height: 0; overflow: hidden; border: 1px solid rgba(29,29,31,.08); border-radius: 1.15rem; background: rgba(255,255,255,.97); box-shadow: var(--shadow); backdrop-filter: blur(18px); transition: opacity 180ms ease, transform 240ms cubic-bezier(.2,.8,.2,1); }
.agent-workspace.session-switching .assets-pane, .agent-workspace.session-switching .artifact-pane { opacity: .48; transform: translateY(4px); pointer-events: none; }
.agent-chat { display: grid; grid-template-rows: auto minmax(0, 1fr) auto; }
.agent-chat-header { min-height: 4.4rem; display: flex; align-items: center; gap: 1rem; padding: .75rem 1rem; border-bottom: 1px solid var(--line); }
.agent-identity { display: flex; align-items: center; gap: .65rem; }
.agent-identity img { width: 2rem; height: 2rem; object-fit: contain; filter: drop-shadow(0 3px 4px rgba(53,83,67,.14)); }
.agent-identity strong, .agent-identity small { display: block; }
.agent-identity strong { font-size: .78rem; letter-spacing: -.01em; }
.agent-identity small { margin-top: .15rem; color: var(--tertiary); font-size: .58rem; }
.agent-chat-header .provider-picker { margin-left: auto; }
.streaming-status { display: inline-flex; align-items: center; gap: .4rem; margin-left: auto; color: var(--tertiary); font-size: .6rem; }
.streaming-status i { width: .4rem; height: .4rem; border-radius: 50%; background: #49a369; box-shadow: 0 0 0 3px rgba(73,163,105,.12); }
.asset-show-action { display: inline-flex; align-items: center; gap: .35rem; padding: .3rem .55rem; border: 1px solid var(--line); border-radius: .55rem; color: #4a544e; background: #fff; font: inherit; font-size: .62rem; cursor: pointer; }
.asset-show-action:hover { color: #345442; background: #eef2ef; }
.asset-show-action svg { width: .8rem; height: .8rem; }
.assets-pane { display: flex; flex-direction: column; background: rgba(249,250,249,.98); }
.assets-pane:focus { outline: none; }
.assets-pane:focus-visible { border-color: rgba(71,105,87,.4); box-shadow: 0 0 0 3px rgba(71,105,87,.1), var(--shadow); }
.assets-header { min-height: 4.4rem; display: flex; align-items: center; justify-content: space-between; gap: .5rem; padding: .8rem .85rem; border-bottom: 1px solid var(--line); }
.assets-header > div:first-child { min-width: 0; }
.assets-header strong, .assets-header small { display: block; }
.assets-header strong { color: #303632; font-size: .86rem; }
.assets-header small { margin-top: .12rem; color: var(--tertiary); font-size: .58rem; }
.assets-header-actions { display: flex; gap: .1rem; }
.assets-header-actions button, .asset-delete { display: grid; place-items: center; width: 1.72rem; height: 1.72rem; padding: 0; border: 0; border-radius: .48rem; color: #67716b; background: transparent; cursor: pointer; }
.assets-header-actions button:hover, .asset-delete:hover { color: #345442; background: #e5ebe7; }
.assets-header-actions svg, .asset-delete svg { width: .82rem; height: .82rem; }
.assets-header-actions .asset-import-action { width: auto; min-width: 1.72rem; display: flex; align-items: center; gap: .3rem; padding: 0 .48rem; color: #3f6850; background: #f2f7f4; font-size: .62rem; font-weight: 680; }
.asset-import-action span { white-space: nowrap; }
.assets-search { height: 2.45rem; display: flex; align-items: center; gap: .45rem; margin: .75rem .75rem .55rem; padding: 0 .65rem; border: 1px solid #dfe4e1; border-radius: .65rem; background: white; box-shadow: 0 1px 3px rgba(27,39,32,.03); }
.assets-search:focus-within { border-color: rgba(71,105,87,.45); box-shadow: 0 0 0 3px rgba(71,105,87,.08); }
.assets-search svg { width: .83rem; height: .83rem; flex: 0 0 auto; color: #8a928d; }
.assets-search input { min-width: 0; width: 100%; border: 0; outline: 0; color: #343a36; background: transparent; font-size: .7rem; }
.asset-filter-list { display: flex; flex-wrap: wrap; gap: .25rem; padding: 0 .75rem .62rem; }
.asset-filter-list button { flex: 0 0 auto; min-height: 1.7rem; padding: 0 .52rem; border: 0; border-radius: .5rem; color: #747a76; background: #e9ecea; cursor: pointer; font-size: .58rem; font-weight: 620; }
.asset-filter-list button.active { color: white; background: #64806e; box-shadow: 0 2px 5px rgba(57,85,69,.16); }
.asset-list-heading { display: flex; justify-content: space-between; padding: .35rem .8rem .5rem; color: #777e79; font-size: .61rem; font-weight: 630; }
.asset-list-heading small { color: #909691; font-size: .57rem; font-weight: 500; }
.asset-editor { display: grid; gap: .42rem; margin: 0 .7rem .6rem; padding: .65rem; border: 1px solid #dfe5e1; border-radius: .7rem; background: #fff; }
.asset-editor > strong { color: #47514b; font-size: .67rem; }
.asset-editor input, .asset-editor textarea { min-width: 0; width: 100%; padding: .48rem .55rem; resize: vertical; border: 1px solid var(--line); border-radius: .5rem; outline: 0; background: #fafbfa; font: inherit; font-size: .66rem; }
.asset-editor input:focus, .asset-editor textarea:focus { border-color: rgba(71,105,87,.45); box-shadow: 0 0 0 2px rgba(71,105,87,.08); }
.asset-editor > div { display: flex; justify-content: flex-end; gap: .3rem; }
.asset-editor button { min-height: 1.75rem; padding: 0 .55rem; border: 0; border-radius: .48rem; color: #fff; background: var(--accent); cursor: pointer; font-size: .6rem; font-weight: 620; }
.asset-editor button:last-child { color: #676b68; background: #eceeed; }
.asset-editor button:disabled { opacity: .45; cursor: not-allowed; }
.asset-browser { min-height: 0; flex: 1; display: flex; flex-direction: column; }
.asset-browser-list { min-height: 0; flex: 1; padding: 0 .65rem; overflow-y: auto; scrollbar-width: thin; }
.asset-row { position: relative; display: flex; align-items: center; margin-bottom: .38rem; overflow: hidden; border: 1px solid #e1e5e2; border-radius: .7rem; background: rgba(255,255,255,.88); transition: border-color 150ms ease, box-shadow 150ms ease, transform 150ms ease; }
.asset-row:hover { border-color: #cdd8d1; box-shadow: 0 4px 12px rgba(32,49,39,.06); transform: translateY(-1px); }
.asset-row-main { min-width: 0; flex: 1; display: flex; align-items: center; gap: .58rem; padding: .48rem .42rem; border: 0; color: inherit; background: transparent; cursor: pointer; text-align: left; }
.asset-thumbnail { position: relative; width: 3.65rem; height: 3rem; flex: 0 0 auto; display: grid; place-items: center; overflow: hidden; border: 1px solid #e2e5e3; border-radius: .52rem; color: #65776d; background: linear-gradient(145deg, #f7f9f7, #eaeeeb); }
.asset-thumbnail img { width: 100%; height: 100%; object-fit: cover; }
.asset-thumbnail > svg { width: 1.15rem; height: 1.15rem; }
.asset-thumbnail > small { position: absolute; left: .22rem; bottom: .2rem; padding: .1rem .22rem; border-radius: .22rem; color: white; background: #65796c; font-size: .43rem; font-weight: 750; letter-spacing: .025em; }
.asset-thumbnail.images > small { background: #507b66; }
.asset-thumbnail.links > small { background: #47749a; }
.asset-thumbnail.code > small { background: #626f82; }
.asset-thumbnail.notes > small { background: #9a794b; }
.asset-row-copy { min-width: 0; display: block; padding-right: 3rem; }
.asset-row-copy strong, .asset-row-copy small, .asset-row-copy time { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.asset-row-copy strong { color: #343a36; font-size: .65rem; font-weight: 650; }
.asset-row-copy small { margin-top: .16rem; color: #7f8681; font-size: .53rem; }
.asset-row-copy time { margin-top: .14rem; color: #a0a5a1; font-size: .49rem; }
.asset-delete { position: absolute; top: .25rem; right: .22rem; width: 1.45rem; height: 1.45rem; opacity: 0; color: #949a96; background: rgba(247,248,247,.92); }
.asset-row:hover .asset-delete, .asset-delete:focus-visible { opacity: 1; }
.asset-empty { height: 100%; min-height: 9rem; display: grid; place-items: center; align-content: center; gap: .35rem; padding: 1rem; color: #858c87; text-align: center; }
.asset-empty svg { width: 1.2rem; height: 1.2rem; }
.asset-empty strong { color: #666f69; font-size: .68rem; }
.asset-empty small { max-width: 11rem; font-size: .56rem; line-height: 1.45; }
.asset-drop-zone { min-height: 5.2rem; flex: 0 0 auto; display: grid; place-items: center; align-content: center; gap: .24rem; margin: .65rem; border: 1px dashed #bfcac3; border-radius: .75rem; color: #718078; background: rgba(255,255,255,.58); cursor: pointer; }
.asset-drop-zone:hover, .asset-drop-zone.dragging { border-color: #668873; color: #42604f; background: #edf4ef; }
.asset-drop-zone svg { width: 1rem; height: 1rem; }
.asset-drop-zone strong { font-size: .62rem; }
.asset-drop-zone small { color: #989e9a; font-size: .48rem; }
.agent-thread { position: relative; min-width: 0; min-height: 0; padding: 1.2rem; overflow-x: hidden; overflow-y: auto; overscroll-behavior: contain; scroll-behavior: auto; scrollbar-width: thin; scrollbar-gutter: stable; overflow-anchor: none; }
.agent-thread.empty { display: grid; place-items: center; }
.session-switch-state { min-height: 100%; display: grid; place-items: center; align-content: center; gap: .52rem; color: #66736b; text-align: center; }
.session-switch-state strong { color: #405247; font-size: .82rem; }
.session-switch-state small { color: #8b958f; font-size: .62rem; }
.session-switch-spinner { width: 1.35rem; height: 1.35rem; border: 2px solid rgba(91,124,104,.18); border-top-color: #5b7c68; border-radius: 50%; animation: session-spin 720ms linear infinite; }
@keyframes session-spin { to { transform: rotate(360deg); } }
.session-content-enter-active, .session-content-leave-active { transition: opacity 160ms ease, transform 220ms cubic-bezier(.2,.8,.2,1), filter 180ms ease; }
.session-content-enter-from { opacity: 0; transform: translateY(8px); filter: blur(4px); }
.session-content-leave-to { opacity: 0; transform: translateY(-6px); filter: blur(4px); }
.turn-stack { --conversation-font-size: .94rem; width: min(100%, 46rem); min-width: 0; max-width: 100%; margin: 0 auto; }
.conversation-turn { min-width: 0; max-width: 100%; display: grid; gap: .5rem; margin-bottom: .72rem; }
.turn-content { min-width: 0; max-width: 100%; display: grid; gap: .68rem; padding: .12rem 0 .68rem; }
.turn-prompt { display: flex; justify-content: flex-end; padding-left: 18%; }
/* Keep bubble spacing on its DOM container: MarkdownContent has multiple roots. */
.turn-prompt-content { box-sizing: border-box; display: grid; gap: .5rem; width: fit-content; min-width: 0; max-width: 100%; padding: .68rem 1rem; overflow: hidden; border-radius: 1rem 1rem .3rem 1rem; color: #34483d; background: #eef1ef; }
.turn-steering-status { display: inline-flex; align-items: center; gap: .38rem; width: fit-content; padding: .24rem .45rem; border-radius: .4rem; color: #4c6857; background: #e3eee7; font-size: .56rem; font-weight: 570; line-height: 1.35; }
.turn-steering-status i { width: .38rem; height: .38rem; flex: 0 0 auto; border-radius: 50%; background: #6f927b; animation: activity-pulse 1.1s ease-in-out infinite; }
.turn-prompt .message-content { width: auto; min-width: 0; max-width: 100%; padding: 0; border: 0; border-radius: 0; color: inherit; background: transparent; box-shadow: none; }
.turn-prompt-image-button { width: fit-content; max-width: 100%; display: block; padding: 0; border: 0; border-radius: .75rem; background: transparent; cursor: zoom-in; }
.turn-prompt-image-button:hover .turn-prompt-image { box-shadow: 0 0 0 2px rgba(71,105,87,.22); }
.turn-prompt-image-button:focus-visible { outline: 3px solid rgba(71,105,87,.24); outline-offset: 2px; }
.turn-prompt-image { display: block; width: min(100%, 22rem); max-height: 18rem; margin: 0; border-radius: .75rem; object-fit: contain; background: #e2e7e4; }
.turn-execution { margin-right: 7%; }
.turn-execution > summary { min-height: 3.1rem; display: grid; grid-template-columns: auto minmax(0,1fr) auto auto; align-items: center; gap: .62rem; padding: .55rem .1rem; border-bottom: 1px solid #e7ebe8; cursor: pointer; list-style: none; user-select: none; }
.turn-execution > summary::-webkit-details-marker { display: none; }
.turn-state-icon { width: 1.55rem; height: 1.55rem; display: grid; place-items: center; border: 1px solid #d9e1dc; border-radius: 50%; background: #f5f8f6; }
.turn-state-icon i { width: .43rem; height: .43rem; border-radius: 50%; background: #72907d; }
.conversation-turn.running .turn-state-icon { border-color: #b8ccbf; background: #edf4ef; box-shadow: 0 0 0 .22rem rgba(96,139,112,.07); }
.conversation-turn.running .turn-state-icon i { animation: activity-pulse 1.15s ease-in-out infinite; }
.turn-execution-copy { min-width: 0; display: grid; gap: .16rem; }
.turn-execution-copy strong { overflow: hidden; color: #59635d; font-size: .68rem; font-weight: 620; text-overflow: ellipsis; white-space: nowrap; }
.conversation-turn.running .turn-execution-copy strong { color: #355b45; }
.turn-execution-copy small { color: #929995; font-size: .56rem; font-variant-numeric: tabular-nums; }
.turn-execution-metrics { min-width: 0; display: flex; align-items: center; justify-content: flex-end; }
.turn-execution-cache { opacity: .72; font-size: .58rem; }
.turn-chevron { color: #8e9892; font-size: 1.05rem; line-height: 1; transition: transform 160ms ease; }
.turn-execution[open] > summary .turn-chevron { transform: rotate(90deg); }
.turn-execution-details { display: grid; gap: .28rem; padding: .48rem 0 .2rem; animation: turn-reveal 160ms ease-out; }
.turn-empty-detail { margin: 0; color: #979e99; font-size: .62rem; }
.turn-response { min-width: 0; max-width: 100%; padding-right: 7%; }
.agent-response-content { min-width: 0; max-width: 100%; padding-top: .1rem; }
.turn-prompt .message-content, .agent-response-content { font-size: var(--conversation-font-size); line-height: 1.65; }
.agent-response-content .final-response { margin: 0; padding: 0; border: 0; border-radius: 0; color: #303632; background: transparent; box-shadow: none; }
.turn-task-list { margin: .1rem 0 .55rem; padding: .25rem 0 .45rem; border-bottom: 1px solid #e8ebe9; }
.turn-task-list > div { display: flex; align-items: center; justify-content: space-between; gap: .5rem; color: #53645a; }
.turn-task-list > div strong { font-size: .62rem; }
.turn-task-list > div small { color: #89928c; font-size: .56rem; }
.turn-task-list ol { display: grid; gap: .3rem; margin: .42rem 0 0; padding: 0; list-style: none; }
.turn-task-list li { display: grid; grid-template-columns: 1rem minmax(0,1fr); color: #838b86; font-size: .63rem; line-height: 1.4; }
.turn-task-list li i { width: .82rem; height: .82rem; display: grid; place-items: center; border: 1px solid #d3ddd6; border-radius: 50%; font-size: .52rem; font-style: normal; }
.turn-task-list li.processing { color: #355442; font-weight: 620; }
.turn-task-list li.processing i { border-color: #76927f; color: #476957; background: #e7f0ea; }
.turn-task-list li.completed { color: #969d98; text-decoration: line-through; }
.turn-task-list li.completed i { border-color: #789383; color: white; background: #789383; }
.turn-empty-response { margin: 0; padding: .55rem .7rem; color: #949b97; font-size: .66rem; font-style: italic; }
.turn-steered-note { margin: 0; padding: .55rem .7rem; color: #718078; font-size: .66rem; font-style: italic; }
.turn-error { display: grid; gap: .2rem; margin-top: .7rem; padding: .58rem .72rem; border-left: 2px solid #c46c66; border-radius: 0 .55rem .55rem 0; color: #774541; background: #fbf3f2; font-size: .64rem; line-height: 1.45; }
.turn-error strong { font-size: .66rem; font-weight: 650; }
.turn-error span { overflow-wrap: anywhere; color: #8a5752; }
@keyframes turn-reveal { from { opacity: 0; transform: translateY(-3px); } }
.agent-welcome { max-width: 25rem; text-align: center; }
.agent-welcome .feature-icon { margin: 0 auto; }
.agent-welcome h2 { margin: 1rem 0 .4rem; font-size: 1.25rem; letter-spacing: -.025em; }
.agent-welcome > p { margin: 0 auto; color: var(--secondary); font-size: .76rem; line-height: 1.6; }
.prompt-hints { display: flex; justify-content: center; gap: .45rem; margin-top: 1.1rem; }
.prompt-hints button { padding: .48rem .65rem; border: 1px solid var(--line); border-radius: .58rem; color: #606065; background: rgba(247,247,248,.8); cursor: pointer; font-size: .64rem; }
.agent-composer-stack { min-width: 0; transition: opacity 180ms ease; }
.agent-chat.session-switching .agent-composer-stack { opacity: .48; pointer-events: none; }
.queued-followup-list { max-height: 10rem; display: grid; margin: .8rem .8rem .35rem; padding: .25rem .35rem; overflow-y: auto; border: 1px solid rgba(29,29,31,.11); border-radius: .82rem; background: #f3f6f4; box-shadow: 0 2px 9px rgba(33,48,39,.045); scrollbar-width: thin; }
.queued-followup-list + .agent-input { margin-top: 0; }
.queued-followup { min-width: 0; min-height: 2.6rem; display: flex; align-items: center; gap: .52rem; padding: .34rem .25rem; border-radius: .55rem; }
.queued-followup + .queued-followup { border-top: 1px solid rgba(54,73,61,.1); border-radius: 0; }
.queued-followup.dragging { opacity: .52; background: #e5ece7; }
.queued-followup-drag { width: 1.2rem; height: 1.7rem; flex: 0 0 auto; display: grid; place-items: center; padding: 0; border: 0; border-radius: .35rem; color: #9aa29d; background: transparent; cursor: grab; }
.queued-followup-drag:active { cursor: grabbing; }
.queued-followup-drag:hover, .queued-followup-drag:focus-visible { color: #53675b; background: #e4ebe6; outline: none; }
.queued-followup-drag svg { width: .78rem; height: .78rem; fill: currentColor; }
.queued-followup-icon { width: 1.42rem; height: 1.42rem; flex: 0 0 auto; display: grid; place-items: center; color: #67776c; }
.queued-followup-icon svg { width: .82rem; height: .82rem; fill: none; stroke: currentColor; stroke-width: 1.7; stroke-linecap: round; stroke-linejoin: round; }
.queued-followup-copy { min-width: 0; flex: 1; }
.queued-followup-copy p { margin: 0; overflow: hidden; color: #48534d; font-size: .65rem; line-height: 1.4; text-overflow: ellipsis; white-space: nowrap; }
.queued-followup-images { display: flex; gap: .28rem; margin-top: .32rem; }
.queued-followup-image-preview { width: 1.7rem; height: 1.7rem; display: block; padding: 0; border: 0; border-radius: .36rem; background: transparent; cursor: zoom-in; }
.queued-followup-image-preview:hover img, .queued-followup-image-preview:focus-visible img { box-shadow: 0 0 0 2px rgba(71,105,87,.22); }
.queued-followup-image-preview:focus-visible { outline: 2px solid rgba(71,105,87,.2); outline-offset: 2px; }
.queued-followup-images img { width: 1.7rem; height: 1.7rem; border: 1px solid #d8e0da; border-radius: .36rem; object-fit: cover; background: #eef2ef; }
.queued-followup-steer { flex: 0 0 auto; min-height: 1.72rem; display: inline-flex; align-items: center; gap: .28rem; padding: 0 .42rem; border: 0; border-radius: .42rem; color: #54655b; background: transparent; cursor: pointer; font-size: .59rem; font-weight: 620; }
.queued-followup-steer svg { width: .76rem; height: .76rem; fill: none; stroke: currentColor; stroke-width: 1.75; stroke-linecap: round; stroke-linejoin: round; }
.queued-followup-steer:hover, .queued-followup-steer:focus-visible { color: #355b44; background: #e3ebe6; outline: none; }
.queued-followup-steer:disabled { opacity: .55; cursor: wait; }
.queued-followup-remove { flex: 0 0 auto; width: 1.45rem; height: 1.45rem; display: grid; place-items: center; padding: 0; border: 0; border-radius: .4rem; color: #8b958e; background: transparent; cursor: pointer; }
.queued-followup-remove svg { width: .78rem; height: .78rem; fill: none; stroke: currentColor; stroke-width: 1.7; stroke-linecap: round; stroke-linejoin: round; }
.queued-followup-remove:hover, .queued-followup-remove:focus-visible { color: #6d453f; background: #f5eae8; outline: none; }
.agent-input { position: relative; container-type: inline-size; container-name: composer-footer; margin: .8rem; padding: .25rem; border: 1px solid rgba(29,29,31,.11); border-radius: .9rem; background: white; box-shadow: 0 3px 16px rgba(0,0,0,.055); }
.message-image-drafts { display: flex; gap: .42rem; padding: .55rem .58rem .1rem; overflow-x: auto; }
.message-image-drafts figure { position: relative; width: 3.5rem; height: 3.5rem; flex: 0 0 auto; margin: 0; }
.message-image-preview { display: block; width: 100%; height: 100%; padding: 0; border: 0; border-radius: .66rem; background: transparent; cursor: zoom-in; }
.message-image-preview:hover img, .message-image-preview:focus-visible img { box-shadow: 0 0 0 2px rgba(71,105,87,.22); }
.message-image-preview:focus-visible { outline: 2px solid rgba(71,105,87,.2); outline-offset: 2px; }
.message-image-drafts img { display: block; width: 100%; height: 100%; border: 1px solid #dce3de; border-radius: .66rem; object-fit: cover; background: #f2f4f2; }
.message-image-drafts .message-image-remove { position: absolute; top: -.28rem; right: -.28rem; width: 1rem; height: 1rem; display: grid; place-items: center; padding: 0; border: 2px solid #fff; border-radius: 50%; color: #fff; background: #59645d; box-shadow: 0 1px 4px rgba(31,39,34,.18); cursor: pointer; font-size: .67rem; line-height: 1; }
.agent-input:focus-within { border-color: rgba(71,105,87,.4); box-shadow: 0 0 0 3px rgba(71,105,87,.1), 0 5px 20px rgba(0,0,0,.06); }
.composer-textarea-wrap { position: relative; min-height: 4rem; overflow: hidden; }
.composer-input-mirror { position: absolute; inset: 0; z-index: 0; box-sizing: border-box; padding: .7rem .8rem .25rem; overflow: hidden; color: transparent; font: inherit; font-size: .78rem; line-height: 1.5; pointer-events: none; white-space: pre-wrap; overflow-wrap: break-word; }
.composer-input-mirror mark { padding: 0; border-radius: .36rem; color: transparent; background: transparent; }
.agent-input textarea { display: block; width: 100%; min-height: 4rem; padding: .7rem .8rem .25rem; resize: none; border: 0; outline: 0; color: var(--text); caret-color: var(--text); background: transparent; font-family: inherit; font-size: .78rem; line-height: 1.5; }
.composer-textarea-wrap textarea { position: relative; z-index: 1; }
.composer-textarea-wrap.token-selected .composer-input-mirror { color: var(--text); }
.composer-textarea-wrap.token-selected textarea { color: transparent; }
.composer-textarea-wrap.token-selected .composer-input-mirror mark { margin: -.1rem -.34rem; padding: .1rem .34rem; border-radius: .34rem; color: #2f674a; background: #e7eee9; }
.composer-textarea-wrap.token-selected .composer-input-mirror mark.reference { color: #31537a; background: #e6edf6; }
.composer-textarea-wrap.token-selected.composing .composer-input-mirror { color: transparent; }
.composer-textarea-wrap.token-selected.composing .composer-input-mirror mark { color: transparent; }
.composer-textarea-wrap.token-selected.composing textarea { color: var(--text); }
.agent-input-footer { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: .5rem; min-height: 2.45rem; padding: 0 .3rem .1rem .45rem; }
.agent-input-footer small { color: var(--tertiary); font-size: .55rem; }
.agent-input .send-button { position: static; }
.agent-input-footer > :first-child { min-width: 0; flex: 1 1 auto; }
.composer-leading { min-width: 0; flex: 1 1 auto; display: flex; align-items: center; gap: .35rem; }
.composer-submit { min-width: 0; flex: 0 0 auto; display: flex; align-items: center; gap: .35rem; }
@container composer-footer (max-width: 420px) {
  .agent-input-footer { align-items: flex-start; }
  .composer-leading { flex-basis: 100%; }
  .composer-submit { width: 100%; justify-content: flex-end; margin-top: .15rem; }
}
@container composer-footer (max-width: 760px) {
  .composer-submit > small { display: none; }
}
.artifact-pane { container-type: inline-size; container-name: artifact-pane; overflow: hidden; background: #f3f4f1; }
.artifact-workspace { display: flex; flex-direction: column; }
.artifact-collection-header { display: flex; align-items: center; justify-content: space-between; gap: .7rem; padding: .85rem 1rem .72rem; border-bottom: 1px solid #e4e8e5; background: rgba(255,255,255,.92); }
.artifact-collection-header strong, .artifact-collection-header small { display: block; }
.artifact-collection-header strong { color: #303632; font-size: .78rem; }
.artifact-collection-header small { margin-top: .1rem; color: var(--tertiary); font-size: .58rem; }
.artifact-collection-actions { display: flex; align-items: center; gap: .45rem; }
.artifact-refresh { display: grid; place-items: center; width: 1.7rem; height: 1.7rem; padding: 0; border: 1px solid #e0e5e1; border-radius: .5rem; color: #5b6560; background: #fff; cursor: pointer; }
.artifact-refresh:hover:not(:disabled) { color: #345442; background: #eef2ef; }
.artifact-refresh:disabled { opacity: .55; cursor: default; }
.artifact-refresh svg { width: .85rem; height: .85rem; }
.artifact-refresh svg.spinning { animation: artifact-refresh-spin 900ms linear infinite; }
@keyframes artifact-refresh-spin { to { transform: rotate(360deg); } }
.artifact-syncing { display: inline-flex; align-items: center; gap: .35rem; color: #758179; font-size: .58rem; }
.artifact-syncing i { width: .36rem; height: .36rem; border-radius: 50%; background: #619071; animation: activity-pulse 1s ease-in-out infinite; }
.artifact-list { flex: 0 0 auto; display: flex; gap: .45rem; padding: .65rem; overflow-x: auto; border-bottom: 1px solid #e5e9e6; background: #f7f9f7; scrollbar-width: thin; }
.artifact-list button { min-width: 10.5rem; max-width: 14rem; display: flex; align-items: center; gap: .52rem; padding: .55rem .62rem; border: 1px solid #e0e5e1; border-radius: .68rem; color: #566059; background: #fff; text-align: left; cursor: pointer; }
.artifact-list button.active { border-color: #88a694; color: #294b39; background: #edf4ef; box-shadow: 0 0 0 2px rgba(89,132,106,.09); }
.artifact-list button > span:last-child { min-width: 0; }
.artifact-list strong, .artifact-list small { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.artifact-list strong { font-size: .64rem; }
.artifact-list small { margin-top: .14rem; color: #8a928d; font-size: .53rem; text-transform: capitalize; }
.artifact-kind-icon { width: 1.65rem; height: 1.65rem; flex: 0 0 auto; display: grid; place-items: center; border-radius: .5rem; color: #42634f; background: #e5eee8; font-size: .82rem; font-weight: 700; }
.artifact-placeholder { height: 100%; display: grid; place-items: center; align-content: center; padding: 2rem; text-align: center; }
.artifact-placeholder > span { display: grid; place-items: center; width: 3rem; height: 3rem; border-radius: 1rem; color: var(--accent); background: var(--accent-soft); }
.artifact-placeholder h2 { margin: 1rem 0 .35rem; font-size: 1rem; }
.artifact-placeholder p { max-width: 18rem; margin: 0; color: var(--tertiary); font-size: .7rem; line-height: 1.55; }
.artifact-pane .artifact-panel { min-height: 0; flex: 1 1 auto; border: 0; border-radius: 0; box-shadow: none; }
.editor-intro { display: flex; gap: 1rem; align-items: center; margin: .5rem 0 1.5rem; }
.editor-intro h2, .settings-intro h2 { margin: 0 0 .28rem; font-size: 1.05rem; letter-spacing: -.015em; }
.editor-intro p { max-width: 39rem; }
.provider-picker { display: grid; gap: .25rem; margin-left: auto; color: var(--tertiary); font-size: .6rem; font-weight: 650; text-transform: uppercase; }
.provider-picker select, .conversation-heading select { max-width: 14rem; height: 2.2rem; padding: 0 1.8rem 0 .65rem; border: 1px solid var(--line); border-radius: .62rem; color: #4b4b50; background: rgba(255,255,255,.76); font-size: .7rem; text-transform: none; }
.initial-agent-layout { display: grid; grid-template-columns: 1fr; gap: 1rem; align-items: start; }
.initial-agent-layout.streaming { grid-template-columns: minmax(28rem, 1.35fr) minmax(17rem, .65fr); }
.composer { overflow: hidden; border: 1px solid rgba(29,29,31,.09); border-radius: 1.1rem; background: rgba(255,255,255,.84); box-shadow: 0 2px 12px rgba(0,0,0,.025); transition: box-shadow 200ms ease; }
.composer:focus-within { box-shadow: 0 0 0 3px rgba(71,105,87,.11), var(--shadow); }
.composer textarea { display: block; width: 100%; min-height: 16rem; padding: 1.35rem; resize: vertical; border: 0; outline: 0; color: var(--text); background: transparent; font-size: 1rem; line-height: 1.65; }
.composer textarea::placeholder { color: #aaaab0; }
.composer-footer { min-height: 4.1rem; display: flex; align-items: center; justify-content: space-between; gap: 1rem; padding: .65rem .75rem .65rem 1.25rem; border-top: 1px solid rgba(29,29,31,.065); background: rgba(247,247,248,.68); }
.composer-footer > span { color: var(--tertiary); font-size: .68rem; }
.refinement-workspace { display: grid; grid-template-columns: minmax(17rem, .72fr) minmax(30rem, 1.45fr); gap: 1rem; align-items: start; }
.conversation-panel { position: sticky; top: 6rem; overflow: hidden; border: 1px solid rgba(29,29,31,.08); border-radius: 1.1rem; background: rgba(255,255,255,.88); box-shadow: var(--shadow); backdrop-filter: blur(18px); }
.conversation-panel.initial-stream { position: static; min-height: 20rem; }
.conversation-heading { display: flex; align-items: center; justify-content: space-between; padding: 1.1rem 1.15rem .9rem; border-bottom: 1px solid var(--line); }
.conversation-heading h2 { margin: .2rem 0 0; font-size: 1rem; letter-spacing: -.015em; }
.conversation-heading > span { color: var(--tertiary); font-size: .62rem; }
.message-list { max-height: 28rem; min-height: 15rem; padding: 1rem; overflow: auto; scrollbar-width: thin; }
.message-content { margin: 0; padding: .78rem .9rem; border: 1px solid rgba(29,29,31,.035); border-radius: .88rem; color: #303431; background: #f0f1f2; font-size: .76rem; line-height: 1.58; overflow-wrap: anywhere; }
.live-agent-state { display: inline-flex; align-items: center; gap: .3rem; text-transform: capitalize; }
.live-agent-state i { width: .36rem; height: .36rem; border-radius: 50%; background: #4b9867; box-shadow: 0 0 0 .18rem rgba(75,152,103,.12); animation: activity-pulse 1.1s ease-in-out infinite; }
.agent-event-timeline { width: 100%; display: grid; gap: .12rem; }
.agent-event-timeline > .reasoning-panel, .agent-event-timeline > .tool-activity { margin: 0; }
.intermediate-response { margin: .18rem 0 .3rem; padding: .12rem 0; color: #4f5b54; font-size: .68rem; line-height: 1.58; }
.tool-activity-list { display: grid; gap: .32rem; margin: 0 0 .48rem; }
.tool-activity { min-width: 0; color: #657068; font-size: .64rem; }
.tool-activity summary { display: flex; align-items: center; gap: .42rem; min-height: 1.7rem; padding: .12rem .08rem; cursor: pointer; list-style: none; text-transform: capitalize; user-select: none; }
.tool-activity summary::-webkit-details-marker { display: none; }
.tool-activity summary::after { content: '›'; margin-left: .12rem; color: #8b948f; font-size: .82rem; transition: transform 150ms ease; }
.tool-activity[open] summary::after { transform: rotate(90deg); }
.tool-activity summary i { width: .38rem; height: .38rem; flex: 0 0 auto; border-radius: 50%; background: #d59b45; animation: activity-pulse 1.1s ease-in-out infinite; }
.tool-activity.succeeded summary i { background: #4b9867; animation: none; }
.tool-activity.failed { color: #914d4d; }
.tool-activity.failed summary i { background: #bd5656; animation: none; }
.tool-activity summary small { margin-left: auto; color: var(--tertiary); font-size: .58rem; text-transform: none; }
.tool-activity-details { display: grid; gap: .55rem; margin: .08rem 0 .55rem; padding: .2rem 0 .12rem; }
.tool-activity-details strong { display: block; margin-bottom: .28rem; color: #78827c; font-size: .56rem; letter-spacing: .055em; text-transform: uppercase; }
.tool-activity-details pre { max-height: 11rem; margin: 0; padding: .32rem 0; overflow: auto; border: 0; color: #465049; background: transparent; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; font-size: .62rem; line-height: 1.48; text-transform: none; white-space: pre-wrap; overflow-wrap: anywhere; }
.tool-activity-details pre.error { color: #8d4040; }
.reasoning-panel { width: 100%; margin: 0; color: #5d6961; background: transparent; }
.reasoning-panel summary { display: flex; align-items: center; gap: .42rem; min-height: 1.7rem; padding: .12rem .08rem; cursor: pointer; list-style: none; font-size: .68rem; font-weight: 630; user-select: none; }
.reasoning-panel summary::-webkit-details-marker { display: none; }
.reasoning-panel summary::after { content: '›'; margin-left: .12rem; color: #8b948f; font-size: .82rem; transition: transform 150ms ease; }
.reasoning-panel[open] summary::after { transform: rotate(90deg); }
.reasoning-panel summary > i { width: .38rem; height: .38rem; flex: 0 0 auto; border-radius: 50%; background: #789383; }
.reasoning-panel summary small { margin-left: auto; color: var(--tertiary); font-size: .58rem; font-weight: 500; }
.reasoning-content { max-height: 14rem; margin: .08rem 0 .55rem; padding: .25rem 0; overflow: auto; color: #657068; font-size: .68rem; line-height: 1.58; }
.compaction-panel { color: #6d658b; }
.compaction-content { margin-left: 0; padding-left: 0; }
.compaction-content .reasoning-content { margin-left: 0; padding-left: 0; border-left: 0; }
.compaction-content > small { display: block; padding: .32rem 0 .45rem; color: var(--tertiary); font-size: .61rem; }
.streaming-reasoning > summary { color: #466554; }
.streaming-reasoning > summary > i { animation: activity-pulse 1.1s ease-in-out infinite; }
.stream-waiting { display: flex; gap: .25rem; padding: .8rem 1rem !important; }
.stream-waiting i { width: .32rem; height: .32rem; border-radius: 50%; background: #929298; animation: typing-pulse 1s ease-in-out infinite; }
.stream-waiting i:nth-child(2) { animation-delay: 140ms; }
.stream-waiting i:nth-child(3) { animation-delay: 280ms; }
.streaming-dots { display: inline-flex; align-items: center; gap: .2rem; }
.streaming-dots.compact { margin: .3rem .18rem .05rem; vertical-align: middle; }
.streaming-dots i { width: .27rem; height: .27rem; border-radius: 50%; background: #78877e; animation: typing-pulse 1s ease-in-out infinite; }
.streaming-dots i:nth-child(2) { animation-delay: 140ms; }
.streaming-dots i:nth-child(3) { animation-delay: 280ms; }
@keyframes activity-pulse { 50% { opacity: .35; } }
.typing-message p { display: flex; gap: .25rem; padding: .8rem 1rem; }
.typing-message i { width: .32rem; height: .32rem; border-radius: 50%; background: #929298; animation: typing-pulse 1s ease-in-out infinite; }
.typing-message i:nth-child(2) { animation-delay: 140ms; }
.typing-message i:nth-child(3) { animation-delay: 280ms; }
@keyframes typing-pulse { 0%, 60%, 100% { opacity: .35; transform: translateY(0); } 30% { opacity: 1; transform: translateY(-2px); } }
.chat-composer { position: relative; padding: .75rem .75rem 1.6rem; border-top: 1px solid var(--line); background: rgba(247,247,248,.72); }
.chat-composer textarea { display: block; width: 100%; min-height: 4.5rem; padding: .7rem 2.8rem .7rem .75rem; resize: none; border: 1px solid rgba(29,29,31,.11); border-radius: .75rem; outline: 0; color: var(--text); background: white; font-size: .72rem; line-height: 1.45; }
.chat-composer textarea:focus { border-color: rgba(71,105,87,.48); box-shadow: 0 0 0 3px rgba(71,105,87,.1); }
.chat-composer > small { position: absolute; left: 1rem; bottom: .48rem; color: var(--tertiary); font-size: .55rem; }
.send-button { position: absolute; right: 1.05rem; top: 1.15rem; display: grid; place-items: center; width: 2.75rem; height: 2.75rem; padding: 0; border: 0; border-radius: .8rem; color: white; background: var(--accent); cursor: pointer; }
.send-button:disabled { opacity: .35; cursor: not-allowed; transform: none; }
.send-button svg { width: 1.3rem; height: 1.3rem; transform: rotate(-90deg); }
.send-button.stop { background: #59635d; }
.send-button.stop svg { width: 1.08rem; height: 1.08rem; transform: none; fill: currentColor; }
.artifact-panel { padding: 1.5rem; border: 1px solid rgba(29,29,31,.08); border-radius: 1.1rem; background: rgba(255,255,255,.88); box-shadow: var(--shadow); backdrop-filter: blur(18px); transform-origin: 50% 0; }
.artifact-panel.artifact-editor { position: relative; display: flex; flex-direction: column; padding: 0; overflow: hidden; color: #252a27; background: #fff; }
.artifact-editor-accent { height: .26rem; flex: 0 0 auto; background: linear-gradient(90deg, #385d49, #77a087 70%, #b5cabb); }
.artifact-editor-header { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: .55rem 1rem; padding: .9rem 1.15rem; border-bottom: 1px solid #e9ece9; }
.artifact-state { flex: 1 1 12rem; min-width: 0; display: flex; align-items: center; gap: .62rem; }
.artifact-state > i { width: .58rem; height: .58rem; flex: 0 0 auto; border-radius: 50%; background: #7a9d87; box-shadow: 0 0 0 .28rem #edf4ef; }
.artifact-state > i.saved { background: #347b51; }
.artifact-state strong, .artifact-state small { display: block; }
.artifact-state strong { font-size: .78rem; letter-spacing: .025em; text-transform: uppercase; }
.artifact-state small { margin-top: .13rem; color: var(--tertiary); font-size: .65rem; }
.artifact-editor-body { min-height: 0; flex: 1; padding: 1.1rem 1.2rem 1.4rem; overflow-y: auto; overscroll-behavior: contain; scrollbar-width: thin; scrollbar-gutter: stable; }
.card-meta-row { display: flex; align-items: end; justify-content: space-between; gap: 1rem; margin-bottom: 1rem; }
.card-type-control { display: grid; gap: .35rem; }
.card-type-control > span, .card-title-control > span, .card-summary-control > span, .card-content-control > span, .card-tags-editor > span { color: #7c837e; font-size: .64rem; font-weight: 700; letter-spacing: .07em; text-transform: uppercase; }
.card-type-options { display: flex; flex-wrap: wrap; gap: .28rem; padding: .2rem; border: 1px solid #dfe5e1; border-radius: .68rem; background: #f3f5f3; }
.card-type-options button { min-height: 1.8rem; padding: 0 .68rem; border: 0; border-radius: .5rem; color: #747b77; background: transparent; cursor: pointer; font-size: .68rem; font-weight: 620; text-transform: capitalize; }
.card-type-options button:hover { color: #405548; background: rgba(255,255,255,.72); }
.card-type-options button.active { color: #2f5541; background: #fff; box-shadow: 0 1px 4px rgba(30,50,39,.1), inset 0 0 0 1px rgba(71,105,87,.1); }
.artifact-mode-switch { flex: 0 0 auto; margin-left: auto; display: flex; align-items: center; gap: .18rem; padding: .16rem; border: 1px solid #e1e5e2; border-radius: .62rem; background: #f2f4f2; }
.artifact-mode-switch button { min-width: 0; min-height: 1.6rem; padding: 0 .7rem; border: 0; border-radius: .45rem; color: #7a807c; background: transparent; cursor: pointer; font-size: .65rem; font-weight: 620; white-space: nowrap; }
.artifact-mode-switch button.active { color: #365744; background: #fff; box-shadow: 0 1px 4px rgba(24,38,30,.09); }
.card-title-control, .card-summary-control, .card-content-control { display: grid; gap: .42rem; margin-top: 1rem; }
.card-title-control textarea, .card-summary-control textarea, .card-content-control textarea { width: 100%; resize: vertical; border: 0; outline: 0; color: #222724; font-family: inherit; }
.card-title-control textarea { min-height: 4.25rem; padding: .15rem 0 .7rem; border-bottom: 1px solid #e1e5e2; border-radius: 0; background: transparent; font-size: clamp(1.25rem, 2vw, 1.65rem); font-weight: 720; line-height: 1.22; letter-spacing: -.025em; }
.card-title-control textarea:focus { border-bottom-color: #789887; }
.card-summary-control { padding: .85rem .9rem .75rem; border: 1px solid #e4ebe6; border-radius: .82rem; background: #f5f8f6; }
.card-summary-control textarea { min-height: 4rem; padding: 0; background: transparent; color: #4d5b53; font-size: .82rem; line-height: 1.55; }
.card-content-control { margin-top: 1.15rem; }
.card-content-control textarea { min-height: 15rem; padding: .9rem; border: 1px solid #e2e5e3; border-radius: .82rem; background: #fbfcfb; font-size: .84rem; line-height: 1.68; }
.card-content-control textarea:focus, .card-summary-control:focus-within { border-color: rgba(71,105,87,.42); box-shadow: 0 0 0 3px rgba(71,105,87,.08); }
.artifact-preview { min-height: 23rem; margin-top: .7rem; padding: .35rem .1rem 1rem; }
.artifact-preview-label { display: inline-flex; margin-bottom: .65rem; padding: .25rem .48rem; border-radius: 2rem; color: #4e6a59; background: #edf3ef; font-size: .56rem; font-weight: 700; letter-spacing: .07em; text-transform: uppercase; }
.article-subtitle { margin: -.35rem 0 1rem; color: #778079; font-size: .9rem; line-height: 1.5; }
.artifact-preview-image img { width: 100%; max-height: 25rem; margin: .25rem 0 1rem; object-fit: contain; border: 1px solid #e2e7e3; border-radius: .8rem; background: #f6f8f6; }
.image-brief-placeholder { min-height: 13rem; display: grid; place-items: center; align-content: center; gap: .5rem; margin: .35rem 0 1rem; padding: 1.2rem; border: 1px dashed #bdc9c1; border-radius: .85rem; color: #657169; background: #f6f8f6; text-align: center; }
.image-brief-placeholder span { font-size: .62rem; font-weight: 700; letter-spacing: .07em; text-transform: uppercase; }
.image-brief-placeholder p { max-width: 18rem; margin: 0; font-size: .72rem; line-height: 1.55; }
.artifact-preview h1 { margin: .2rem 0 .75rem; color: #202622; font-size: clamp(1.45rem, 2.2vw, 1.9rem); line-height: 1.2; letter-spacing: -.032em; }
.preview-summary { color: #68726c; font-size: .86rem; line-height: 1.65; }
.preview-divider { width: 2.5rem; height: .18rem; margin: 1.25rem 0; border-radius: 1rem; background: #9db5a6; }
.preview-content { color: #343a36; font-size: .88rem; line-height: 1.72; }
.card-tags-editor { margin-top: 1.2rem; }
.card-tags-editor .suggestion-list label { border-radius: 2rem; background: #f5f5f3; }
.artifact-editor-actions { position: relative; flex: 0 0 auto; margin-top: auto; padding: .85rem 1.15rem; border-top: 1px solid #e5e8e5; background: rgba(255,255,255,.94); backdrop-filter: blur(16px); }
.panel-heading, .settings-intro { display: flex; align-items: center; justify-content: space-between; gap: 1rem; }
.panel-heading h2 { margin: .22rem 0 0; font-size: 1.2rem; letter-spacing: -.02em; }
.ai-badge { display: inline-flex; align-items: center; gap: .35rem; padding: .35rem .55rem; border-radius: 2rem; color: var(--accent-dark); background: var(--accent-soft); font-size: .65rem; font-weight: 650; }
.ai-badge svg { width: .75rem; height: .75rem; }
.form-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 1.05rem; margin-top: 1.35rem; }
.field { display: grid; gap: .42rem; color: #4c4c51; font-size: .72rem; font-weight: 620; }
.field.full { grid-column: 1 / -1; }
.field > span { display: flex; justify-content: space-between; align-items: center; }
.field em { color: var(--tertiary); font-style: normal; font-weight: 450; }
.field input, .field select, .field textarea { width: 100%; border: 1px solid rgba(29,29,31,.11); border-radius: .68rem; outline: 0; color: var(--text); background: #fafafa; box-shadow: inset 0 1px 2px rgba(0,0,0,.02); font-size: .8rem; font-weight: 430; transition: border-color 150ms ease, box-shadow 150ms ease, background 150ms ease; }
.field input, .field select { height: 2.65rem; padding: 0 .75rem; }
.field textarea { min-height: 9rem; padding: .75rem; resize: vertical; line-height: 1.55; }
.field input:focus, .field select:focus, .field textarea:focus { border-color: rgba(71,105,87,.48); background: white; box-shadow: 0 0 0 3px rgba(71,105,87,.1); }
.field > small { color: var(--tertiary); font-size: .65rem; font-weight: 430; line-height: 1.45; }
.secret-input { position: relative; }
.secret-input input { padding-right: 2.75rem; }
.secret-input button { position: absolute; top: 50%; right: .35rem; display: grid; place-items: center; width: 2rem; height: 2rem; padding: 0; border: 0; border-radius: .5rem; color: #7d8781; background: transparent; cursor: pointer; transform: translateY(-50%); }
.secret-input button:hover { color: var(--accent-dark); background: var(--accent-soft); }
.secret-input button svg { width: 1rem; height: 1rem; }
.mode-options { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: .28rem; padding: .2rem; border: 1px solid rgba(29,29,31,.1); border-radius: .68rem; background: #f3f4f3; }
.mode-options button { min-height: 2.2rem; padding: 0 .6rem; border: 0; border-radius: .52rem; color: #6f7772; background: transparent; cursor: pointer; font-size: .7rem; font-weight: 580; transition: color 150ms ease, background 150ms ease, box-shadow 150ms ease; }
.mode-options button:hover { color: #455d50; }
.mode-options button.active { color: #2f5a43; background: #fff; box-shadow: 0 1px 4px rgba(42,65,52,.1); }
.suggestions { margin-top: 1.25rem; }
.suggestions > span { color: #4c4c51; font-size: .72rem; font-weight: 620; }
.suggestion-list { display: flex; flex-wrap: wrap; gap: .45rem; margin-top: .55rem; }
.suggestion-list label { display: flex; align-items: center; gap: .35rem; padding: .45rem .58rem; border: 1px solid var(--line); border-radius: .55rem; color: #69696e; background: #f4f4f5; cursor: pointer; font-size: .67rem; transition: background 150ms ease, transform 100ms ease; }
.suggestion-list label:active { transform: scale(.97); }
.suggestion-list label.selected { border-color: rgba(71,105,87,.16); color: var(--accent-dark); background: var(--accent-soft); }
.suggestion-list input { position: absolute; opacity: 0; pointer-events: none; }
.suggestion-list small { opacity: .65; font-size: .58rem; }
.panel-actions { display: flex; justify-content: flex-end; gap: .6rem; margin-top: 1.5rem; padding-top: 1rem; border-top: 1px solid var(--line); }

.settings-view { max-width: 64rem; }
.settings-tabs { width: fit-content; display: flex; gap: .18rem; margin: .25rem 0 1.15rem; padding: .2rem; border: 1px solid rgba(60,78,67,.1); border-radius: .72rem; background: rgba(235,239,236,.82); }
.settings-tabs button { min-height: 2rem; padding: 0 .78rem; border: 0; border-radius: .54rem; color: #69746d; background: transparent; cursor: pointer; font-size: .68rem; font-weight: 650; }
.settings-tabs button:hover { color: #355442; }
.settings-tabs button.active { color: #31523f; background: #fff; box-shadow: 0 1px 4px rgba(38,57,46,.1); }
.settings-section { animation: settings-section-in 180ms ease-out both; }
@keyframes settings-section-in { from { opacity: 0; transform: translateY(5px); } }
.model-usage-list { display: grid; gap: 1.15rem; }
.model-usage-list .model-usage-trend + .model-usage-trend { padding-top: 1.15rem; border-top: 1px solid rgba(29,29,31,.08); }
.settings-intro { margin: .5rem 0 1rem; }
.runtime-settings-heading { margin-top: 1.8rem; }
.settings-card { padding: 1.5rem; border: 1px solid rgba(29,29,31,.075); border-radius: 1rem; background: rgba(255,255,255,.84); box-shadow: 0 2px 12px rgba(0,0,0,.025); }
.provider-toolbar { display: flex; align-items: flex-start; gap: .8rem; margin: 0 0 .8rem; }
.provider-toolbar > .secondary-action { flex: 0 0 auto; margin-left: auto; }
.provider-list { min-width: 0; flex: 1; display: flex; gap: .55rem; margin: 0; padding: 0; overflow-x: auto; }
.provider-list > button { min-width: 11rem; display: flex; align-items: center; gap: .6rem; padding: .68rem .75rem; border: 1px solid var(--line); border-radius: .72rem; color: var(--text); background: rgba(255,255,255,.48); cursor: pointer; text-align: left; }
.provider-list > button.active { border-color: rgba(71,105,87,.28); background: var(--accent-soft); box-shadow: 0 2px 8px rgba(52,82,67,.08); }
.provider-list strong, .provider-list small { display: block; }
.provider-list strong { max-width: 9rem; overflow: hidden; font-size: .72rem; text-overflow: ellipsis; white-space: nowrap; }
.provider-list small { margin-top: .18rem; color: var(--secondary); font-size: .58rem; }
.settings-card .form-grid { margin-top: 0; }
.settings-activity-state { min-height: 8rem; display: grid; place-items: center; color: var(--tertiary); font-size: .68rem; }
.settings-actions { display: flex; align-items: center; justify-content: space-between; gap: 1rem; margin-top: 1.4rem; padding-top: 1rem; border-top: 1px solid var(--line); }
.settings-actions > span { color: var(--tertiary); font-size: .68rem; }
.settings-actions > div { display: flex; align-items: center; gap: 1rem; margin-left: auto; }
.danger-button { border: 0; color: #a33e3e; background: transparent; cursor: pointer; font-size: .7rem; font-weight: 600; }
.switch { display: flex; align-items: center; gap: .55rem; cursor: pointer; }
.switch input { position: absolute; opacity: 0; }
.switch > span { position: relative; width: 2.25rem; height: 1.3rem; border-radius: 1rem; background: #c7c7cc; transition: background 180ms ease; }
.switch > span::after { content: ""; position: absolute; top: .13rem; left: .13rem; width: 1.04rem; height: 1.04rem; border-radius: 50%; background: white; box-shadow: 0 1px 4px rgba(0,0,0,.24); transition: transform 260ms cubic-bezier(.2,.8,.2,1); }
.switch input:checked + span { background: #5f856f; }
.switch input:checked + span::after { transform: translateX(.94rem); }
.switch small { min-width: 3.2rem; color: var(--secondary); font-size: .68rem; }
.temperature-field input { accent-color: var(--accent); }
.temperature-field output { color: var(--accent); font-variant-numeric: tabular-nums; }
.taxonomy-heading { margin-top: 2.2rem; }
.taxonomy-form { display: grid; grid-template-columns: 1fr 1.35fr auto; gap: 1rem; align-items: end; }

.detail-backdrop { position: fixed; inset: 0; z-index: 40; display: flex; justify-content: flex-end; background: rgba(24,26,25,.24); backdrop-filter: blur(3px); }
.detail-sheet { width: min(100%, 42rem); height: 100%; overflow-y: auto; border-left: 1px solid rgba(255,255,255,.72); background: rgba(250,250,251,.94); box-shadow: -24px 0 70px rgba(20,24,22,.16); backdrop-filter: blur(28px) saturate(150%); }
.detail-header { position: sticky; top: 0; z-index: 2; min-height: 4.5rem; display: flex; align-items: center; justify-content: space-between; padding: 0 1.5rem; background: rgba(250,250,251,.82); backdrop-filter: blur(22px); }
.detail-header > div { display: flex; align-items: center; gap: .65rem; }
.detail-header-actions { margin-left: auto; }
.detail-header-button { display: inline-flex; align-items: center; gap: .35rem; min-height: 2rem; padding: 0 .62rem; border: 0; border-radius: .5rem; color: #4f6257; background: transparent; cursor: pointer; font-size: .66rem; font-weight: 620; }
.detail-header-button:hover { color: #345442; background: #e9f0ec; }
.detail-header-button svg { width: .78rem; height: .78rem; }
.detail-delete-button { display: inline-flex; align-items: center; gap: .35rem; min-height: 2rem; padding: 0 .62rem; border: 0; border-radius: .5rem; color: #9a4b4b; background: transparent; cursor: pointer; font-size: .66rem; font-weight: 620; }
.detail-delete-button:hover { color: #a43030; background: #f8eaea; }
.detail-delete-button:disabled { opacity: .45; cursor: wait; }
.detail-delete-button svg { width: .78rem; height: .78rem; }
.detail-loading { color: var(--tertiary); font-size: .62rem; }
.detail-content { padding: 1.2rem 2rem 4rem; }
.detail-content > h1 { margin: .4rem 0 .75rem; font-size: clamp(1.7rem, 3vw, 2.25rem); line-height: 1.12; letter-spacing: -.035em; }
.detail-summary { margin: 0 0 1rem; color: var(--secondary); font-size: .88rem; line-height: 1.65; }
.detail-tags { display: flex; flex-wrap: wrap; gap: .4rem; margin: 1rem 0 1.6rem; }
.detail-tags span { padding: .32rem .55rem; border-radius: .5rem; color: var(--accent-dark); background: var(--accent-soft); font-size: .65rem; }
.detail-section { margin-top: 1.8rem; }
.detail-section h2 { margin: 0 0 .65rem; color: var(--tertiary); font-size: .64rem; font-weight: 700; letter-spacing: .065em; text-transform: uppercase; }
.detail-section > p, .detail-body { margin: 0; color: #36363a; font-size: .84rem; line-height: 1.75; overflow-wrap: anywhere; }
.detail-section > p { white-space: pre-wrap; }
.raw-section { padding: 1rem; border: 1px solid var(--line); border-radius: .8rem; background: rgba(238,238,240,.6); }
.raw-section .detail-body { color: var(--secondary); font-size: .75rem; }
.detail-metadata { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 1rem; margin: 2rem 0 0; padding-top: 1.3rem; border-top: 1px solid var(--line); }
.detail-metadata div { min-width: 0; }
.detail-metadata dt { margin-bottom: .25rem; color: var(--tertiary); font-size: .58rem; font-weight: 650; letter-spacing: .04em; text-transform: uppercase; }
.detail-metadata dd { margin: 0; overflow: hidden; color: #55555a; font-size: .68rem; text-overflow: ellipsis; white-space: nowrap; }
.sheet-enter-active, .sheet-leave-active { transition: background 240ms ease, backdrop-filter 240ms ease; }
.sheet-enter-active .detail-sheet, .sheet-leave-active .detail-sheet { transition: transform 360ms cubic-bezier(.2,.8,.2,1), opacity 220ms ease; }
.sheet-enter-from, .sheet-leave-to { background: transparent; backdrop-filter: blur(0); }
.sheet-enter-from .detail-sheet, .sheet-leave-to .detail-sheet { opacity: .75; transform: translateX(100%); }

.toast { position: fixed; top: 1rem; left: calc(50% + 8.25rem); z-index: 30; display: flex; align-items: center; gap: .5rem; padding: .65rem .85rem; transform: translateX(-50%); border: 1px solid rgba(29,29,31,.08); border-radius: .72rem; color: #3d594a; background: rgba(247,252,249,.9); box-shadow: 0 10px 32px rgba(0,0,0,.12); backdrop-filter: blur(18px); font-size: .74rem; font-weight: 580; }
.toast.error { color: #8a3838; background: rgba(255,247,247,.94); }
.toast svg { width: .9rem; height: .9rem; }
.toast-enter-active, .toast-leave-active { transition: opacity 180ms ease, transform 280ms cubic-bezier(.2,.8,.2,1); }
.toast-enter-from, .toast-leave-to { opacity: 0; transform: translate(-50%, -10px) scale(.96); }
.material-enter-active, .material-leave-active { transition: opacity 220ms ease, transform 380ms cubic-bezier(.2,.8,.2,1), filter 260ms ease; }
.material-enter-from, .material-leave-to { opacity: 0; transform: translateY(-10px) scale(.985); filter: blur(8px); }

.library-slides-fullscreen { position: fixed; inset: 0; z-index: 1200; display: grid; width: 100vw; height: 100dvh; background: white; }
.library-slides-fullscreen :deep(.slides-stage) { width: 100%; height: 100%; aspect-ratio: auto; border: 0; border-radius: 0; }
.library-slides-close { position: absolute; top: .6rem; right: .6rem; z-index: 30; width: 2rem; height: 2rem; border: 1px solid #d9e2dc; border-radius: .4rem; background: white; color: #426b53; font-size: 1.5rem; cursor: pointer; }
.library-pdf-launch { position: fixed; width: 1px; height: 1px; overflow: hidden; }

/* Typography scale */
.brand strong { font-size: 1rem; }
.brand small { font-size: .76rem; }
.primary-nav button, .sidebar-footer button { font-size: .9rem; }
.primary-nav button small, .tag-list small { font-size: .73rem; }
kbd, .card-type, .card-tags span { font-size: .69rem; }
.sidebar-heading { font-size: .72rem; }
.tag-list button { font-size: .84rem; }
.sidebar-empty { font-size: .79rem; line-height: 1.45; }
.chat-topbar-title { font-size: .82rem; }
.search-field input { font-size: .91rem; }
.primary-action, .secondary-action, .text-button { font-size: .87rem; }
.eyebrow { font-size: .72rem; }
.page-heading p:last-child, .settings-intro p, .editor-intro p { font-size: .89rem; }
.card time { font-size: .71rem; }
.card h2 { font-size: 1.14rem; }
.card > .card-excerpt, .empty-state p { font-size: .86rem; }
.agent-identity strong { font-size: .86rem; }
.agent-identity small, .streaming-status { font-size: .66rem; }
.agent-welcome > p { font-size: .84rem; }
.prompt-hints button { font-size: .72rem; }
.agent-input textarea, .composer-input-mirror { font-size: .88rem; }
.agent-input-footer small { font-size: .63rem; }
.artifact-placeholder p { font-size: .78rem; }
.provider-picker { font-size: .68rem; }
.provider-picker select, .conversation-heading select { font-size: .78rem; }
.composer-footer > span, .conversation-heading > span { font-size: .74rem; }
.message-content, .message-body > p { font-size: .82rem; }
.chat-composer textarea { font-size: .82rem; }
.chat-composer > small { font-size: .63rem; }
.ai-badge { font-size: .72rem; }
.field, .suggestions > span { font-size: .8rem; }
.field input, .field select, .field textarea { font-size: .88rem; }
.field > small { font-size: .72rem; }
.suggestion-list label { font-size: .74rem; }
.suggestion-list small, .provider-list small { font-size: .65rem; }
.provider-list strong { font-size: .8rem; }
.settings-actions > span, .switch small { font-size: .75rem; }
.danger-button { font-size: .77rem; }
.detail-loading, .detail-tags span { font-size: .7rem; }
.detail-summary { font-size: .94rem; }
.detail-subtitle { margin: -.55rem 0 1rem; color: var(--secondary); font-size: .9rem; line-height: 1.5; }
.detail-section h2 { font-size: .71rem; }
.detail-section p, .detail-body { font-size: .92rem; }
.raw-section .detail-body { font-size: .83rem; }
.detail-metadata dt { font-size: .65rem; }
.detail-metadata dd { font-size: .76rem; }
.toast { font-size: .82rem; }

@media (max-width: 760px) {
  .app-shell { display: block; padding-bottom: 4.6rem; }
  .sidebar { position: fixed; top: auto; bottom: 0; width: 100%; height: 4.25rem; display: block; padding: .45rem max(.65rem, env(safe-area-inset-right)) max(.45rem, env(safe-area-inset-bottom)) max(.65rem, env(safe-area-inset-left)); border: 0; border-top: 1px solid rgba(255,255,255,.7); box-shadow: 0 -1px rgba(29,29,31,.07); }
  .brand, .sidebar-section { display: none; }
  .primary-nav { display: grid; grid-template-columns: repeat(4, 1fr); width: 67%; }
  .primary-nav button, .sidebar-footer button { height: 3.25rem; flex-direction: column; justify-content: center; gap: .2rem; padding: 0; font-size: .68rem; }
  .primary-nav button small, .primary-nav kbd, .status-dot { display: none; }
  .primary-nav button svg, .sidebar-footer button svg { width: 1.15rem; height: 1.15rem; }
  .sidebar-footer { position: absolute; right: .65rem; bottom: max(.45rem, env(safe-area-inset-bottom)); width: calc((100% - 1.3rem) / 3); display: grid; grid-template-columns: repeat(2, 1fr); padding: 0; border: 0; }
  .sidebar-footer .channels-nav-button { margin-bottom: 0; }
  .locale-control { display: none; }
  .topbar { min-height: 4.5rem; padding: .8rem 1rem; }
  .topbar .primary-action { width: 2.65rem; padding: 0; font-size: 0; }
  .topbar .primary-action svg { width: 1rem; height: 1rem; }
  .content { padding: 1.3rem 1rem 3rem; }
  .card-grid { grid-template-columns: 1fr; }
  .card { min-height: 13rem; }
  .form-grid, .taxonomy-form { grid-template-columns: 1fr; }
  .artifact-pane .form-grid { grid-template-columns: 1fr; }
  .assets-header-actions .asset-import-action { width: 1.72rem; padding: 0; }
  .asset-import-action span { display: none; }
  .refinement-workspace { grid-template-columns: 1fr; }
  .initial-agent-layout.streaming { grid-template-columns: 1fr; }
  .agent-workspace { height: auto; min-height: 0; grid-template-columns: 1fr; }
  .assets-pane { min-height: 28rem; max-height: 70vh; }
  .agent-chat { min-height: 70vh; }
  .artifact-pane { min-height: 30rem; }
  .composer-submit small { display: none; }
  .conversation-panel { position: static; }
  .field.full { grid-column: auto; }
  .settings-actions, .panel-heading { align-items: flex-start; }
  .settings-actions { flex-direction: column; }
  .settings-actions .primary-action, .taxonomy-form .primary-action { width: 100%; }
  .toast { left: 50%; width: max-content; max-width: calc(100% - 2rem); }
  .detail-sheet { width: 100%; }
  .detail-content { padding: 1rem 1.2rem 5rem; }
  .detail-metadata { grid-template-columns: 1fr; }
}

@media (min-width: 761px) and (max-width: 1180px) {
  .refinement-workspace { grid-template-columns: 1fr; }
  .initial-agent-layout.streaming { grid-template-columns: 1fr; }
  .agent-workspace { height: auto; grid-template-columns: 1fr; }
  .assets-pane { min-height: 32rem; max-height: 75vh; }
  .agent-chat { min-height: 42rem; }
  .artifact-pane { min-height: 36rem; }
  .conversation-panel { position: static; }
}

@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { scroll-behavior: auto !important; animation-duration: 1ms !important; animation-iteration-count: 1 !important; transition-duration: 120ms !important; }
  .card:hover { transform: none; }
  .material-enter-from, .material-leave-to { transform: none; filter: none; }
}

@media (prefers-reduced-transparency: reduce) {
  .sidebar, .topbar, .card, .artifact-panel, .toast { background: #f6f6f8; backdrop-filter: none; -webkit-backdrop-filter: none; }
  .settings-card, .composer { background: #fff; }
}

@media (prefers-contrast: more) {
  :root { --line: rgba(0,0,0,.35); }
  .sidebar, .topbar, .card, .settings-card, .composer, .artifact-panel { border-color: rgba(0,0,0,.35); background: #fff; }
}
</style>
