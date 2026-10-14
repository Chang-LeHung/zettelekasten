<script setup lang="ts">
import { computed, defineAsyncComponent, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ApiError, aiClient, assetClient, libraryClient, settingsClient, tagClient, updateClient } from './api/client'
import type { AgentArtifact, AgentAtCommand, AgentCompactionActivity, AgentContextComposition, AgentCustomEvent, AgentModelUsage, AgentModelUsageActivitySeries, AgentPersistedMessage, AgentServerToolActivity, AgentSession, AgentSlashCommand, AgentSteeringMessage, AgentTimelineEntry, AgentTodoState, AgentToolActivity, AgentUsageActivityDay, AIProvider, AIProviderInput, AnalysisMessage, ArtifactContent, CardType, LibraryItem, LibraryItemUpdate, MessageImagePart, MessagePart, ReasoningEffort, RuntimeSettings, SessionAsset, SessionType, ShellApprovalMode, StaticAsset, Tag, CardStatus, UpdateStatus } from './api/types'
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
import BlockEditor from './components/BlockEditor.vue'
import LibraryStatusFilter from './components/LibraryStatusFilter.vue'
import CardStatusMark from './components/CardStatusMark.vue'
import CardStatusMenu from './components/CardStatusMenu.vue'
import AgentExecution from './components/AgentExecution.vue'
import UsageActivityGraph from './components/UsageActivityGraph.vue'
import { addAgentUsage, latestAgentUsage, summarizeAgentUsage } from './utils/agentUsage'
import { parseUtcTimestamp } from './utils/timestamps'
import { artifactContentFromLibraryUpdate, artifactEditableContent, hasPendingDraft, libraryItemFromArtifact } from './utils/artifactEditor'
import { artifactListsEquivalent, sameArtifactRevision, stabilizeArtifactReferences } from './utils/artifactStability'
import { diffArtifactContent } from './utils/artifactDiff'
import { artifactLifecycle, lifecycleClass, lifecycleHint, lifecycleLabel } from './utils/artifactLifecycle'
import { cardStatusLabel, cardStatusType, isStruck, statusTone } from './utils/cardStatus'
import { addTagPath } from './utils/tagAssignment'
import { waitForRestart } from './utils/serverRestart'
import { assetOpenAction, isPdfAsset } from './utils/assetOpen'
import { createAsyncRefreshScheduler } from './utils/asyncRefresh'
import { AtCommandInput, type AtCommandMatch } from './utils/atCommand'
import { SlashCommandInput, type SlashCommandMatch } from './utils/slashCommand'
import { buildConversationTurns, formatTurnDuration, splitTurnTimeline, type ConversationTurn } from './utils/conversationTurns'
import { jsonSnapshot } from './utils/jsonSnapshot'
import { buildMessageParts, readMessageImage, rebaseImagePositions, type PositionedMessageImage } from './utils/messageParts'
import { restorePersistedConversation } from './utils/persistedConversation'
import { moveItemBeforeOrAfter } from './utils/reorder'
import { readPaneHidden, writePaneHidden } from './utils/paneVisibility'
import { artifactImageUrl, versionedPreviewUrl } from './utils/artifactPreview'
import { appendStreamedAssistantMessage, createStreamedAssistantMessage } from './utils/streamedAssistant'
import { defaultProviderBaseUrl, providerBaseUrlHelp, providerIgnoresTemperature } from './utils/providerDefaults'
import { todoFromTool } from './utils/toolPresentation'
import { hasRunningTool, upsertToolActivity } from './utils/toolActivities'
import { TurnDetailsVisibility } from './utils/turnDetails'
import { presentationSections } from './utils/slides'
import { libraryExcerptText } from './utils/libraryExcerpt'
import { artifactListExcerpt, artifactListImage } from './utils/artifactListPresentation'
import { pendingArtifactSaves } from './utils/artifactSaveAll'
import { artifactTone } from './utils/artifactTone'
import { clampArtifactListHeight, MIN_ARTIFACT_LIST_HEIGHT } from './utils/artifactSplit'
import { asContextComposition } from './utils/contextComposition'
import { visibleTagRows } from './utils/tagTree'
import { boxFromPoints, exceedsThreshold, idsInBox, pruned, rangeBetween, settleLimited, toggled, type Box } from './utils/multiSelect'
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
type SettingsSection = 'general' | 'usage' | 'providers' | 'limits'
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
/**
 * Cards fetched per request. The sentinel under the grid turns this into the
 * step size of one scroll, not a ceiling on what the library shows.
 */
const LIBRARY_PAGE_SIZE = 60
const libraryLoading = ref(false)
const libraryLoadingMore = ref(false)
const libraryHasMore = ref(false)
const libraryTotal = ref<number | null>(null)
const librarySentinel = ref<HTMLElement | null>(null)
let libraryRequestId = 0
let libraryObserver: IntersectionObserver | null = null
const deletingLibraryItemId = ref<string | null>(null)
/** Cards picked with the mouse; any selection turns a click on a card into a toggle. */
const selectedLibraryIds = ref<Set<string>>(new Set())
const libraryMarquee = ref<Box | null>(null)
const bulkDeleting = ref(false)
let selectionAnchorId: string | null = null
const selectingLibrary = computed(() => selectedLibraryIds.value.size > 0)
const selectedLibraryItems = computed(() => libraryItems.value.filter((item) => selectedLibraryIds.value.has(item.id)))
const draggingLibraryItem = ref<LibraryItem | null>(null)
const draggingStaticAsset = ref<StaticAsset | null>(null)
const tagDropTargetId = ref<string | null>(null)
const tagAssignmentBusy = ref(false)
/**
 * The collection tree of the library being browsed, and the only one this app
 * ever shows: the sidebar, the manager, and every count read from it belong to
 * the library on screen, because the artifact library and the static asset
 * library keep separate trees.
 */
const collectionTags = ref<Tag[]>([])
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
//: Card statuses the library keeps; empty means every card regardless of status.
const selectedCardStatuses = ref<CardStatus[]>([])
//: Artifact ids whose status change is in flight, so one click cannot double-send.
const cardStatusUpdatingIds = ref<ReadonlySet<string>>(new Set())
const view = ref<View>('new')
const collectionTarget = computed<'artifact' | 'asset'>(() => (view.value === 'assets' ? 'asset' : 'artifact'))
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
const artifactPaneRef = ref<HTMLElement | null>(null)
const artifactHeaderRef = ref<HTMLElement | null>(null)
const artifactListHeight = ref<number | null>(null)
let artifactSplitPointer: number | null = null
let artifactSplitStartY = 0
let artifactSplitStartHeight = 0
let artifactPaneResizeObserver: ResizeObserver | null = null
const loading = ref(false)
//: True until the persisted conversation, including its artifacts, has loaded.
const workspaceRestoring = ref(true)
const saving = ref(false)
const savingAllArtifacts = ref(false)
//: The editor holds edits nothing has stored yet, so the saved look would overstate it.
const selectedArtifactDirty = computed(() => {
  const selected = selectedArtifact.value
  return Boolean(selected && artifactContent.value
    && JSON.stringify(artifactContent.value) !== JSON.stringify(artifactEditableContent(selected)))
})
const artifactsNeedingSave = computed(() => {
  const pending = pendingArtifactSaves(artifacts.value)
  const selected = selectedArtifact.value
  if (selected && artifactContent.value && !pending.some(item => item.id === selected.id)
    && JSON.stringify(artifactContent.value) !== JSON.stringify(artifactEditableContent(selected))) {
    pending.push(selected)
  }
  return pending
})
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
  agent_may_delete_artifacts: false,
  agent_may_delete_tags: false,
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
const agentPermissions = [
  {
    key: 'agent_may_delete_artifacts',
    title: 'Delete artifacts',
    description: 'Lets the Agent delete this conversation’s artifacts when you ask. Off, it has no delete tool at all.',
  },
  {
    key: 'agent_may_delete_tags',
    title: 'Delete tags',
    description: 'Lets the Agent delete tags from your library when you ask. Off, it has no delete tool at all.',
  },
] as const
/** What the server last confirmed, so a permission switch never saves half-edited limits with it. */
let persistedRuntimeSettings: RuntimeSettings | null = null
const agentPermissionSaving = ref<'agent_may_delete_artifacts' | 'agent_may_delete_tags' | null>(null)
/** What PyPI offers for this copy, and how it would install it. */
const updateStatus = ref<UpdateStatus | null>(null)
const updateChecking = ref(false)
const updateInstalling = ref(false)
const updateRestarting = ref(false)
const usageActivity = ref<AgentUsageActivityDay[]>([])
const modelUsageActivity = ref<AgentModelUsageActivitySeries[]>([])
const usageActivityLoading = ref(false)
const settingsSection = ref<SettingsSection>('providers')
const settingsOpen = ref(false)
const settingsDialog = ref<HTMLElement | null>(null)
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

const flatTags = computed(() => visibleTagRows(collectionTags.value, collapsedTagIds.value))
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
  // The header names the whole library, so a paged grid still counts every match.
  const count = libraryTotal.value ?? libraryItems.value.length
  return view.value === 'search'
    ? t('{count} matching items', { count })
    : t('{count} items in your library', { count })
})
/**
 * Identity of the query on screen. The grid is keyed by it, so a filter that
 * lands on a different set remounts its cards and replays the float-in, while
 * the next page of the same query keeps the loaded nodes instead of animating
 * the whole grid again.
 */
const libraryGridKey = computed(() => [
  view.value,
  view.value === 'search' ? activeQuery.value : '',
  selectedTag.value ?? '',
  selectedLibraryType.value ?? '',
].join('|'))
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

function setArtifactListHeight(height: number): void {
  const pane = artifactPaneRef.value
  const header = artifactHeaderRef.value
  if (!pane || !header) return
  const bounded = clampArtifactListHeight(height, pane.clientHeight, header.offsetHeight)
  if (artifactListHeight.value !== bounded) artifactListHeight.value = bounded
}

function startArtifactSplit(event: PointerEvent): void {
  if (event.button !== 0) return
  const pane = artifactPaneRef.value
  if (!pane) return
  event.preventDefault()
  artifactSplitPointer = event.pointerId
  artifactSplitStartY = event.clientY
  artifactSplitStartHeight = pane.querySelector('.artifact-list')?.getBoundingClientRect().height ?? MIN_ARTIFACT_LIST_HEIGHT
  ;(event.currentTarget as HTMLElement).setPointerCapture(event.pointerId)
}

function moveArtifactSplit(event: PointerEvent): void {
  if (artifactSplitPointer !== event.pointerId) return
  setArtifactListHeight(artifactSplitStartHeight + event.clientY - artifactSplitStartY)
}

function endArtifactSplit(event: PointerEvent): void {
  if (artifactSplitPointer !== event.pointerId) return
  artifactSplitPointer = null
}

function keyArtifactSplit(event: KeyboardEvent): void {
  const list = artifactPaneRef.value?.querySelector('.artifact-list')
  if (!list || !['ArrowUp', 'ArrowDown', 'Home', 'End'].includes(event.key)) return
  event.preventDefault()
  const current = list.getBoundingClientRect().height
  const desired = event.key === 'Home' ? 0 : event.key === 'End' ? Number.MAX_SAFE_INTEGER
    : current + (event.key === 'ArrowDown' ? 32 : -32)
  setArtifactListHeight(desired)
}

watch(artifactPaneRef, (pane) => {
  artifactPaneResizeObserver?.disconnect()
  artifactPaneResizeObserver = null
  if (!pane) return
  artifactPaneResizeObserver = new ResizeObserver(() => {
    if (artifactListHeight.value !== null) setArtifactListHeight(artifactListHeight.value)
  })
  artifactPaneResizeObserver.observe(pane)
})

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
    const created = await tagClient.create({ path, target: collectionTarget.value })
    await refreshTags()
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
    await Promise.all([refreshTags(), loadLibrary()])
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

/** The filters the grid is showing; the count and every page share them. */
function libraryListFilters() {
  return {
    query: view.value === 'search' ? activeQuery.value : '',
    tagId: selectedTag.value,
    artifactTypes: selectedLibraryType.value ? [selectedLibraryType.value] : undefined,
    cardStatuses: selectedCardStatuses.value.length ? selectedCardStatuses.value : undefined,
  }
}

/**
 * Load one page of the library. A plain call replaces the grid and asks how
 * many matches exist; `append` adds the next page when the sentinel below the
 * grid scrolls into view. Each request fetches one card past the page size, so
 * "is there more" costs no second round trip, and a stale page loses to the
 * filter change that replaced it.
 */
async function loadLibrary({ append = false }: { append?: boolean } = {}): Promise<void> {
  if (append && (libraryLoading.value || libraryLoadingMore.value || !libraryHasMore.value)) return
  const requestId = ++libraryRequestId
  const offset = append ? libraryItems.value.length : 0
  const filters = libraryListFilters()
  if (append) {
    libraryLoadingMore.value = true
  } else {
    libraryLoading.value = true
    // A reset supersedes any page still in flight, so its settle must not
    // leave the "loading more" state behind.
    libraryLoadingMore.value = false
  }
  try {
    const [page, total] = await Promise.all([
      libraryClient.list({ ...filters, limit: LIBRARY_PAGE_SIZE + 1, offset }),
      append ? Promise.resolve(libraryTotal.value) : libraryClient.count(filters),
    ])
    if (requestId !== libraryRequestId) return
    libraryHasMore.value = page.length > LIBRARY_PAGE_SIZE
    const visible = libraryHasMore.value ? page.slice(0, LIBRARY_PAGE_SIZE) : page
    libraryItems.value = append ? [...libraryItems.value, ...visible] : visible
    if (total !== null) libraryTotal.value = total
  } catch (error) {
    if (requestId === libraryRequestId) showNotice(errorMessage(error), 'error')
  } finally {
    if (requestId === libraryRequestId) {
      libraryLoading.value = false
      libraryLoadingMore.value = false
    }
  }
}

/** Reload the collection tree of the library being browsed. */
async function loadCollectionTags(): Promise<void> {
  collectionTags.value = await tagClient.list(collectionTarget.value)
}

/** Refresh that tree after an assignment or a collection changes. */
async function refreshTags(): Promise<void> {
  collectionTags.value = await tagClient.list(collectionTarget.value)
}

// Each library browses its own tree, so switching libraries drops a selection
// that belongs to the other one instead of filtering a list it cannot show.
// A card that was deleted, filtered away, or paged out cannot stay selected, and
// leaving the library drops the selection so it never resurfaces on return.
watch(libraryItems, (items) => {
  if (!selectedLibraryIds.value.size) return
  const remaining = pruned(selectedLibraryIds.value, items.map((item) => item.id))
  if (remaining.size !== selectedLibraryIds.value.size) selectedLibraryIds.value = remaining
})
watch(view, (next) => {
  if (next !== 'library') clearLibrarySelection()
})

watch(collectionTarget, () => {
  selectedTag.value = null
  loadCollectionTags().catch((error: unknown) => showNotice(errorMessage(error), 'error'))
})

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
    persistedRuntimeSettings = { ...runtimeSettingsData }
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

function closeSettings(): void {
  settingsOpen.value = false
}

function openSearch(): void {
  view.value = 'search'
  void nextTick(() => searchInput.value?.focus())
}

function handleShortcut(event: KeyboardEvent): void {
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

function editArtifactFromList(artifact: AgentArtifact): void {
  selectArtifact(artifact)
  if (['card', 'article', 'slides'].includes(artifact.artifact_type)) {
    openSelectedArtifactEditor()
    return
  }
  artifactPreview.value = false
  artifactDiff.value = false
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
    await refreshTags()
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
    await refreshTags()
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

/**
 * Stop an inner control's key from also activating the card, without swallowing
 * Escape: the global handler owns it, and a focused card button must not hide it.
 */
function stopCardKey(event: KeyboardEvent): void {
  if (event.key !== 'Escape') event.stopPropagation()
}

function isEditableTarget(target: EventTarget | null): boolean {
  return target instanceof HTMLElement && Boolean(target.closest('input, textarea, select, [contenteditable="true"]'))
}

function clearLibrarySelection(): void {
  selectedLibraryIds.value = new Set()
  selectionAnchorId = null
}

function selectAllLibraryItems(): void {
  selectedLibraryIds.value = new Set(libraryItems.value.map((item) => item.id))
  selectionAnchorId = libraryItems.value[0]?.id ?? null
}

function toggleLibrarySelection(item: LibraryItem): void {
  selectedLibraryIds.value = toggled(selectedLibraryIds.value, item.id)
  selectionAnchorId = item.id
}

/** Shift extends from the last card picked; the earlier picks stay. */
function extendLibrarySelection(item: LibraryItem): void {
  const span = rangeBetween(libraryItems.value.map((candidate) => candidate.id), selectionAnchorId, item.id)
  selectedLibraryIds.value = new Set([...selectedLibraryIds.value, ...span])
  selectionAnchorId ??= item.id
}

/** Click opens a card, unless the user is picking cards: then it picks, as in Finder and Photos. */
function onLibraryCardActivate(item: LibraryItem, event: MouseEvent | KeyboardEvent): void {
  if (event.shiftKey) extendLibrarySelection(item)
  else if (event.metaKey || event.ctrlKey || selectingLibrary.value) toggleLibrarySelection(item)
  else openLibraryItem(item)
}

const MARQUEE_EDGE = 64
const NOT_A_MARQUEE_START = '.card, button, a, input, select, textarea, label, summary, [role="button"], [role="dialog"], .library-bulk-bar'

/**
 * Drag a rectangle over empty space to pick every card it covers. Shift or
 * Cmd/Ctrl adds to the current picks; a plain drag replaces them, and a plain
 * click on empty space clears them. The rectangle is anchored to the page, not
 * the window, so it keeps covering what it started on while the page scrolls.
 */
function startLibraryMarquee(event: PointerEvent): void {
  if (event.button !== 0 || bulkDeleting.value || !libraryItems.value.length) return
  if (event.target instanceof Element && event.target.closest(NOT_A_MARQUEE_START)) return
  const additive = event.shiftKey || event.metaKey || event.ctrlKey
  const base = additive ? new Set(selectedLibraryIds.value) : new Set<string>()
  const originX = event.clientX + window.scrollX
  const originY = event.clientY + window.scrollY
  let pointerX = event.clientX
  let pointerY = event.clientY
  let dragging = false
  let frame = 0

  const update = (): void => {
    const box = boxFromPoints(originX - window.scrollX, originY - window.scrollY, pointerX, pointerY)
    libraryMarquee.value = box
    const targets = [...document.querySelectorAll<HTMLElement>('[data-library-id]')].map((element) => {
      const rect = element.getBoundingClientRect()
      return { id: element.dataset.libraryId!, box: { left: rect.left, top: rect.top, right: rect.right, bottom: rect.bottom } }
    })
    selectedLibraryIds.value = new Set([...base, ...idsInBox(box, targets)])
  }
  const tick = (): void => {
    if (pointerY < MARQUEE_EDGE) window.scrollBy(0, -Math.ceil((MARQUEE_EDGE - pointerY) / 3))
    else if (pointerY > window.innerHeight - MARQUEE_EDGE) window.scrollBy(0, Math.ceil((pointerY - (window.innerHeight - MARQUEE_EDGE)) / 3))
    update()
    frame = requestAnimationFrame(tick)
  }
  const move = (next: PointerEvent): void => {
    pointerX = next.clientX
    pointerY = next.clientY
    if (!dragging) {
      if (!exceedsThreshold(pointerX - (originX - window.scrollX), pointerY - (originY - window.scrollY))) return
      dragging = true
      document.body.classList.add('marquee-selecting')
      frame = requestAnimationFrame(tick)
    }
  }
  const finish = (): void => {
    cancelAnimationFrame(frame)
    window.removeEventListener('pointermove', move)
    window.removeEventListener('pointerup', finish)
    window.removeEventListener('pointercancel', finish)
    document.body.classList.remove('marquee-selecting')
    libraryMarquee.value = null
    // A plain click on empty space is "select nothing".
    if (!dragging && !additive) clearLibrarySelection()
    else selectionAnchorId = [...selectedLibraryIds.value].at(-1) ?? null
  }
  window.addEventListener('pointermove', move)
  window.addEventListener('pointerup', finish)
  window.addEventListener('pointercancel', finish)
}

async function deleteSelectedLibraryItems(): Promise<void> {
  const items = selectedLibraryItems.value
  if (!items.length || bulkDeleting.value || deletingLibraryItemId.value !== null) return
  const count = items.length
  const names = items.slice(0, 3).map((item) => `“${item.title}”`).join(', ')
  const confirmed = await requestConfirmation(
    count === 1 ? 'Delete this artifact?' : `Delete ${count} artifacts?`,
    `${names}${count > 3 ? ` and ${count - 3} more` : ''} will be permanently removed from artifacts. This action cannot be undone.`,
    count === 1 ? 'Delete artifact' : `Delete ${count} artifacts`,
  )
  if (!confirmed) return
  bulkDeleting.value = true
  try {
    // A few at a time: each is its own request, and a failure must not stop the rest.
    const results = await settleLimited(items, 4, (item) => libraryClient.delete(item.item_type, item.id))
    const removed = new Set(items.filter((_, index) => {
      const result = results[index]
      return result.status === 'fulfilled' && result.value.ok
    }).map((item) => item.id))
    const failed = items.filter((item) => !removed.has(item.id))
    if (removed.size) {
      libraryItems.value = libraryItems.value.filter((candidate) => !removed.has(candidate.id))
      if (libraryTotal.value !== null) libraryTotal.value = Math.max(0, libraryTotal.value - removed.size)
      if (selectedLibraryItem.value && removed.has(selectedLibraryItem.value.id)) selectedLibraryItem.value = null
      if (libraryEditorItem.value && removed.has(libraryEditorItem.value.id)) {
        libraryEditorItem.value = null
        libraryEditorArtifactId.value = null
      }
      await refreshTags()
    }
    // What could not be deleted stays selected, so one more press retries exactly those.
    selectedLibraryIds.value = new Set(failed.map((item) => item.id))
    if (!failed.length) {
      showNotice(removed.size === 1 ? 'Artifact deleted' : `${removed.size} artifacts deleted`)
    } else {
      const firstFailure = results.find((result): result is PromiseRejectedResult => result.status === 'rejected')
      showNotice(
        `${removed.size ? `${removed.size} deleted, ` : ''}${failed.length} could not be deleted${firstFailure ? `: ${errorMessage(firstFailure.reason)}` : ''}`,
        'error',
      )
    }
  } finally {
    bulkDeleting.value = false
  }
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
    if (libraryTotal.value !== null) libraryTotal.value = Math.max(0, libraryTotal.value - 1)
    if (selectedLibraryItem.value?.id === item.id) selectedLibraryItem.value = null
    if (libraryEditorItem.value?.id === item.id) {
      libraryEditorItem.value = null
      libraryEditorArtifactId.value = null
    }
    await refreshTags()
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
  if (view.value === 'assets') {
    // The collection tree belongs to the library on screen: filter the files
    // instead of leaving the view the user is browsing.
    return
  }
  view.value = 'library'
  await loadLibrary()
}

async function filterByArtifactType(artifactType: LibraryItem['item_type'] | null): Promise<void> {
  selectedLibraryType.value = artifactType
  // A status belongs to cards, so another type cannot keep a status filter.
  if (artifactType !== null && artifactType !== 'card') selectedCardStatuses.value = []
  await loadLibrary()
}

/** Replace the library's status filter and reload what it shows. */
async function setCardStatuses(next: CardStatus[]): Promise<void> {
  selectedCardStatuses.value = next
  await loadLibrary()
}

function markCardStatusUpdating(id: string, updating: boolean): void {
  const next = new Set(cardStatusUpdatingIds.value)
  if (updating) next.add(id)
  else next.delete(id)
  cardStatusUpdatingIds.value = next
}

function announceCardStatus(title: string, status: CardStatus): void {
  showNotice(t('cardStatus.updated', { title, status: t(cardStatusLabel(status)) }))
}

/** Move a library card to a new status. It takes effect at once: no draft, no save. */
async function setLibraryCardStatus(item: LibraryItem, status: CardStatus): Promise<void> {
  if (cardStatusUpdatingIds.value.has(item.id)) return
  markCardStatusUpdating(item.id, true)
  try {
    const updated = await libraryClient.setCardStatus(item.id, status)
    if (selectedLibraryItem.value?.id === item.id) selectedLibraryItem.value = updated
    if (selectedCardStatuses.value.length && !selectedCardStatuses.value.includes(status)) {
      // The card no longer matches the filter, so the grid and its count must be reread.
      await loadLibrary()
    } else {
      libraryItems.value = libraryItems.value.map((candidate) => (candidate.id === item.id ? updated : candidate))
    }
    announceCardStatus(item.title, status)
  } catch (error) {
    showNotice(errorMessage(error), 'error')
  } finally {
    markCardStatusUpdating(item.id, false)
  }
}

/** Move a conversation's card to a new status, without touching its draft. */
async function setConversationCardStatus(artifact: AgentArtifact, status: CardStatus): Promise<void> {
  const activeConversationId = conversationId.value
  if (!activeConversationId || cardStatusUpdatingIds.value.has(artifact.id)) return
  markCardStatusUpdating(artifact.id, true)
  try {
    const updated = await aiClient.setAgentCardStatus(activeConversationId, artifact.id, status)
    if (conversationId.value !== activeConversationId) return
    const index = artifacts.value.findIndex((candidate) => candidate.id === updated.id)
    // Replace only the status: a refresh built from this response would also
    // reset the draft the editor is showing if the model changed it meanwhile.
    if (index >= 0) artifacts.value.splice(index, 1, { ...artifacts.value[index]!, card_status: updated.card_status, updated_at: updated.updated_at })
    announceCardStatus(artifactTitle(artifactEditableContent(updated)), status)
    void loadLibrary()
  } catch (error) {
    showNotice(errorMessage(error), 'error')
  } finally {
    markCardStatusUpdating(artifact.id, false)
  }
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

async function saveSelectedArtifact(artifact: AgentArtifact | null = selectedArtifact.value): Promise<boolean> {
  if (savingAllArtifacts.value || saving.value) return false
  const artifactId = artifact?.id
  const activeConversationId = conversationId.value
  const isSelected = artifactId === selectedArtifactId.value
  const currentContent = isSelected ? artifactContent.value : artifact ? artifactEditableContent(artifact) : null
  const editorSnapshot = currentContent ? JSON.stringify(currentContent) : null
  const content = currentContent ? jsonSnapshot(currentContent) : null
  if (!content || !activeConversationId || !artifactId) return false
  saving.value = true
  try {
    if (isSelected && content.artifact_type !== 'latex_pdf') {
      content.suggested_tags = content.suggested_tags.filter((tag) => selectedSuggestions.value.includes(tag.path))
    }
    if (isSelected) {
      const updated = await aiClient.updateAgentArtifactDraft(activeConversationId, artifactId, content)
      if (conversationId.value !== activeConversationId) return false
      const draftIndex = artifacts.value.findIndex(item => item.id === updated.id)
      if (draftIndex >= 0) artifacts.value.splice(draftIndex, 1, updated)
    }
    const saved = await aiClient.saveAgentArtifact(activeConversationId, artifactId)
    if (conversationId.value !== activeConversationId) return false
    const index = artifacts.value.findIndex((artifact) => artifact.id === saved.id)
    if (index >= 0) artifacts.value.splice(index, 1, saved)
    if (isSelected && selectedArtifactId.value === artifactId
      && JSON.stringify(artifactContent.value) === editorSnapshot) {
      artifactContent.value = jsonSnapshot(saved.content)
      // The published draft is gone, so leave the comparison view.
      artifactDiff.value = false
    }
    if (content.artifact_type !== 'image') {
      await loadLibrary()
      await refreshTags()
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

async function saveAllArtifacts(): Promise<void> {
  const sessionId = conversationId.value
  if (!sessionId || saving.value || savingAllArtifacts.value) return
  const pending = [...artifactsNeedingSave.value]
  if (!pending.length) {
    showNotice('All artifacts are already saved')
    return
  }
  savingAllArtifacts.value = true
  const selectedId = selectedArtifactId.value
  const selectedDraft = selectedId && artifactContent.value ? jsonSnapshot(artifactContent.value) : null
  let savedCount = 0
  const failed: string[] = []
  try {
    for (const artifact of pending) {
      if (conversationId.value !== sessionId) break
      try {
        // Save All must include an edit still open in the selected editor.
        if (artifact.id === selectedId && selectedDraft) {
          const updated = await aiClient.updateAgentArtifactDraft(sessionId, artifact.id, selectedDraft)
          if (conversationId.value !== sessionId) break
          const draftIndex = artifacts.value.findIndex(item => item.id === updated.id)
          if (draftIndex >= 0) artifacts.value.splice(draftIndex, 1, updated)
        }
        if (conversationId.value !== sessionId) break
        const saved = await aiClient.saveAgentArtifact(sessionId, artifact.id)
        if (conversationId.value !== sessionId) break
        const index = artifacts.value.findIndex(item => item.id === saved.id)
        if (index >= 0) artifacts.value.splice(index, 1, saved)
        // An edit typed during the request must remain in the editor for a later save.
        if (selectedArtifactId.value === saved.id && selectedDraft
          && JSON.stringify(artifactContent.value) === JSON.stringify(selectedDraft)) {
          artifactContent.value = jsonSnapshot(saved.content)
          artifactDiff.value = false
        }
        savedCount += 1
      } catch (error) {
        failed.push(`${artifactTitle(artifactEditableContent(artifact))}: ${errorMessage(error)}`)
      }
    }
    if (savedCount && conversationId.value === sessionId) {
      await loadLibrary()
      await refreshTags()
    }
    if (conversationId.value !== sessionId) return
    showNotice(
      failed.length
        ? `Saved ${savedCount} of ${pending.length}. Failed: ${failed.join('; ')}`
        : `Saved ${savedCount} artifact${savedCount === 1 ? '' : 's'}`,
      failed.length ? 'error' : 'success',
    )
  } finally {
    savingAllArtifacts.value = false
  }
}

async function deleteSelectedArtifact(artifact: AgentArtifact | null = selectedArtifact.value): Promise<void> {
  const sessionId = conversationId.value
  if (!sessionId || !artifact || saving || savingAllArtifacts.value) return
  const title = artifactEditableContent(artifact)
  const name = title?.artifact_type === 'latex_pdf' ? title.pdf_name : title?.title || 'Untitled artifact'
  const confirmed = await requestConfirmation(
    'Delete this artifact?',
    `“${name}” will be permanently removed from this conversation. A linked artifact will also be deleted.`,
    'Delete artifact',
  )
  if (!confirmed || conversationId.value !== sessionId || saving || savingAllArtifacts.value) return
  try {
    await aiClient.deleteAgentArtifact(sessionId, artifact.id)
    if (conversationId.value !== sessionId) return
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
    persistedRuntimeSettings = { ...runtimeSettings.value }
    showNotice('Runtime settings saved')
  } catch (error) {
    showNotice(errorMessage(error), 'error')
  } finally {
    runtimeSettingsSaving.value = false
  }
}

/**
 * Apply one Agent permission the moment its switch moves. It saves the last
 * confirmed settings plus this one change, so limits still being typed in the
 * form above are neither saved nor lost.
 */
async function setAgentPermission(key: 'agent_may_delete_artifacts' | 'agent_may_delete_tags', enabled: boolean): Promise<void> {
  if (agentPermissionSaving.value) return
  agentPermissionSaving.value = key
  const base = persistedRuntimeSettings ?? runtimeSettings.value
  try {
    const saved = await settingsClient.update({ ...base, [key]: enabled })
    persistedRuntimeSettings = { ...saved }
    runtimeSettings.value = { ...runtimeSettings.value, [key]: saved[key] }
    showNotice(enabled ? 'The Agent can now delete here when you ask it to' : 'The Agent can no longer delete here')
  } catch (error) {
    showNotice(errorMessage(error), 'error')
  } finally {
    agentPermissionSaving.value = null
  }
}

/**
 * Ask PyPI, through the backend's cache, whether a newer release exists. The
 * backend reuses an answer for hours, so this is cheap to call on every start.
 */
async function refreshUpdateStatus(refresh = false): Promise<void> {
  if (updateChecking.value || updateInstalling.value) return
  updateChecking.value = true
  try {
    updateStatus.value = await updateClient.get(refresh)
  } catch (error) {
    showNotice(errorMessage(error), 'error')
  } finally {
    updateChecking.value = false
  }
}

/**
 * Download the release and let the installer that owns this copy replace it.
 * The running process keeps the old code, so the answer asks for a restart.
 */
async function installAvailableUpdate(): Promise<void> {
  const version = updateStatus.value?.latest
  if (!version || updateInstalling.value) return
  updateInstalling.value = true
  try {
    const result = await updateClient.install(version)
    if (!result.ok) {
      showNotice(result.detail || t('The installer failed'), 'error')
      return
    }
    showNotice(t('Installed {version} — restart Zett to use it', { version: result.version }))
    // Asked directly: refreshUpdateStatus() refuses while an install is running, and this one
    // still is until the `finally` below, so going through it left the button offering the
    // update that had just been installed. The cached answer is enough: what changed is the disk.
    updateStatus.value = await updateClient.get()
  } catch (error) {
    showNotice(errorMessage(error), 'error')
  } finally {
    updateInstalling.value = false
  }
}

/**
 * Restart this server so the release that was just installed is the one running.
 * A helper stops the process that answers, so the page waits until a server that no
 * longer asks for a restart answers, and then reloads to pick up its interface.
 */
async function restartZett(): Promise<void> {
  if (updateRestarting.value) return
  updateRestarting.value = true
  try {
    const result = await updateClient.restart()
    if (!result.ok) {
      showNotice(result.detail || t('Zett could not restart itself'), 'error')
      return
    }
    const back = await waitForRestart({
      now: () => Date.now(),
      sleep: (milliseconds) => new Promise((resolve) => window.setTimeout(resolve, milliseconds)),
      stillNeedsRestart: async () => (await updateClient.get()).restart_required,
    })
    if (back) {
      window.location.reload()
      return
    }
    showNotice(t('Zett did not come back; run `zett start` in a terminal'), 'error')
  } catch (error) {
    showNotice(errorMessage(error), 'error')
  } finally {
    updateRestarting.value = false
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
/**
 * Infinite scroll for the library grid: the sentinel sits after the last card,
 * so the next page is requested while the reader is still one screen above the
 * fold. A page shorter than the size ends the run by clearing `libraryHasMore`.
 */
watch(librarySentinel, (element) => {
  libraryObserver?.disconnect()
  libraryObserver = null
  if (!element || typeof IntersectionObserver === 'undefined') return
  libraryObserver = new IntersectionObserver((entries) => {
    if (entries.some((entry) => entry.isIntersecting)) void loadLibrary({ append: true })
  }, { rootMargin: '600px 0px' })
  libraryObserver.observe(element)
}, { flush: 'post' })
onBeforeUnmount(() => {
  document.removeEventListener('fullscreenchange', handleSlidesFullscreenChange)
  resolveConfirmation?.(false)
  activeStreamController.value?.abort()
  if (agentScrollFrame !== null) window.cancelAnimationFrame(agentScrollFrame)
  if (turnClock !== null) window.clearInterval(turnClock)
  libraryObserver?.disconnect()
  libraryObserver = null
  agentContentResizeObserver?.disconnect()
  agentContentResizeObserver = null
  artifactPaneResizeObserver?.disconnect()
  artifactPaneResizeObserver = null
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
      <symbol id="icon-download" viewBox="0 0 24 24"><path d="M12 4v9m0 0 3.5-3.5M12 13 8.5 9.5M5 19h14"/></symbol>
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
          <svg><use href="#icon-cards" /></svg><span>{{ $t('nav.artifacts') }}</span><small>{{ libraryTotal ?? libraryItems.length }}</small>
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
        <!--
          The update lives where the reader already looks for the running copy:
          one line above Settings, absent until PyPI has something newer that this copy
          can install (a source checkout never shows it), and a click installs it. Once
          installed, the same spot becomes the button that restarts Zett into it.
        -->
        <button
          v-if="updateStatus?.restart_required"
          class="update-callout restart"
          type="button"
          :disabled="updateRestarting"
          :aria-busy="updateRestarting"
          :title="$t('Installed {version} — restart Zett to use it', { version: updateStatus.installed })"
          @click="restartZett"
        >
          <svg><use href="#icon-refresh" /></svg>
          <span>{{ updateRestarting ? $t('Restarting…') : $t('Restart Zett to use {version}', { version: updateStatus.installed }) }}</span>
          <span v-if="updateRestarting" class="button-spinner" aria-hidden="true" />
        </button>
        <button
          v-else-if="updateStatus?.can_install"
          class="update-callout"
          type="button"
          :disabled="updateInstalling"
          :aria-busy="updateInstalling"
          :title="updateStatus.detail"
          @click="installAvailableUpdate"
        >
          <svg><use href="#icon-download" /></svg>
          <span>{{ updateInstalling ? $t('Installing…') : $t('Update to {version}', { version: updateStatus.latest ?? '' }) }}</span>
          <span v-if="updateInstalling" class="button-spinner" aria-hidden="true" />
        </button>
        <button :class="{ active: settingsOpen }" type="button" @click="navigate('settings')">
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
      <TagManagerDialog v-if="tagManagerOpen" :tags="collectionTags" :busy="tagManagerBusy" :feedback="tagManagerFeedback" :feedback-kind="tagManagerFeedbackKind" @close="tagManagerOpen = false" @create="createTag" @delete="deleteTag" />
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
        <header class="topbar library-topbar">
          <form class="search-field" role="search" @submit.prevent="search">
            <svg><use href="#icon-search" /></svg>
            <input ref="searchInput" v-model="query" :aria-label="$t('search.placeholder')" :placeholder="$t('search.placeholder')" />
            <button v-if="query" type="button" :aria-label="$t('search.clear')" @click="query = ''; search()">×</button>
            <kbd v-else>⌘ K</kbd>
          </form>
          <button class="primary-action" type="button" @click="navigate('new')"><svg><use href="#icon-add" /></svg>{{ $t('search.newCard') }}</button>
        </header>

        <section class="content library-view" :class="{ selecting: selectingLibrary }" @pointerdown="startLibraryMarquee">
          <div class="page-heading">
            <div><p class="eyebrow">{{ $t('Your knowledge') }}</p><h1>{{ pageTitle }}</h1><p>{{ pageDescription }}</p></div>
            <button v-if="selectedTag !== null" class="text-button" type="button" @click="filterByTag(null)">Clear filter</button>
          </div>

          <div class="library-filter-bar">
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
            <LibraryStatusFilter
              v-if="selectedLibraryType === null || selectedLibraryType === 'card'"
              :model-value="selectedCardStatuses"
              @update:model-value="setCardStatuses"
            />
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
              :class="[`library-${item.item_type}`, item.card_status ? statusTone(item.card_status) : '', { dragging: draggingLibraryItem?.id === item.id, picked: selectedLibraryIds.has(item.id), picking: selectingLibrary }]"
              :style="{ animationDelay: cardFloatDelay(index) }"
              :data-library-id="item.id"
              role="button"
              tabindex="0"
              draggable="true"
              :aria-label="`Open ${item.title}`"
              :aria-selected="selectingLibrary ? selectedLibraryIds.has(item.id) : undefined"
              @click="onLibraryCardActivate(item, $event)"
              @keydown.enter="onLibraryCardActivate(item, $event)"
              @keydown.space.prevent="onLibraryCardActivate(item, $event)"
              @dragstart="startLibraryItemDrag(item, $event)"
              @dragend="endLibraryItemDrag"
            >
              <div class="card-topline">
                <button
                  class="card-select"
                  type="button"
                  role="checkbox"
                  :aria-checked="selectedLibraryIds.has(item.id)"
                  :aria-label="`Select ${item.title}`"
                  @click.stop="toggleLibrarySelection(item)"
                  @keydown="stopCardKey"
                >
                  <svg viewBox="0 0 20 20" aria-hidden="true"><path d="m5 10.5 3.2 3.2L15 7" /></svg>
                </button>
                <span class="card-type">{{ item.item_type === 'card' ? $t(item.card_type || 'card') : $t(item.item_type) }}</span>
                <div class="card-topline-actions">
                  <button class="card-action-button" type="button" :aria-label="`Open conversation for ${item.title}`" title="Open source conversation" @click.stop="openArtifactSession(item)" @keydown="stopCardKey">
                    <svg><use href="#icon-conversation" /></svg>
                  </button>
                  <button v-if="item.item_type === 'slides'" class="card-action-button" type="button" :aria-label="`Preview ${item.title} fullscreen`" title="Fullscreen preview" @click.stop="openSlidesFullscreen(item)" @keydown="stopCardKey">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M9 3H3v6m12-6h6v6M3 15v6h6m12-6v6h-6" /></svg>
                  </button>
                  <button v-if="item.item_type === 'latex_pdf'" class="card-action-button" type="button" :aria-label="`Preview ${item.title}`" title="Preview PDF" @click.stop="openLibraryPdf(item, 'expanded')" @keydown="stopCardKey">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M9 3H3v6m12-6h6v6M3 15v6h6m12-6v6h-6" /></svg>
                  </button>
                  <button v-if="item.item_type === 'latex_pdf'" class="card-action-button" type="button" :aria-label="`Present ${item.title}`" title="Present PDF" @click.stop="openLibraryPdf(item, 'presentation')" @keydown="stopCardKey">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="13" rx="2" /><path d="M12 17v4m-4 0h8M10 8l5 2.5-5 2.5Z" /></svg>
                  </button>
                  <button v-if="item.item_type !== 'latex_pdf'" class="card-action-button" type="button" :aria-label="`Edit ${item.title}`" title="Edit and preview" @click.stop="openLibraryEditor(item)" @keydown="stopCardKey">
                    <svg><use href="#icon-edit" /></svg>
                  </button>
                  <button class="card-action-button card-copy-action" type="button" :aria-label="`Copy ID for ${item.title}`" title="Copy artifact ID" @click.stop="copyLibraryItemId(item)" @keydown="stopCardKey">
                    <svg><use href="#icon-copy" /></svg>
                  </button>
                  <button class="card-action-button danger" :disabled="deletingLibraryItemId !== null || bulkDeleting" type="button" :aria-label="`Delete ${item.title}`" :title="deletingLibraryItemId === item.id ? 'Deleting…' : `Delete ${item.item_type}`" @click.stop="deleteLibraryItem(item)" @keydown="stopCardKey">
                    <svg><use href="#icon-trash" /></svg>
                  </button>
                </div>
              </div>
              <div v-if="item.card_status" class="card-title-row">
                <CardStatusMark :status="item.card_status" :busy="cardStatusUpdatingIds.has(item.id)" @select="setLibraryCardStatus(item, $event)" />
                <h2 :title="item.title">{{ item.title }}</h2>
              </div>
              <h2 v-else :title="item.title">{{ item.title }}</h2>
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
                  <CardStatusMenu v-if="item.card_status" :status="item.card_status" :busy="cardStatusUpdatingIds.has(item.id)" @select="setLibraryCardStatus(item, $event)" />
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
          <!--
            Observer anchor for the grid's next page. It stays outside the
            v-if/v-else chain above so the empty state keeps its place in it.
          -->
          <div v-if="libraryItems.length && libraryHasMore" ref="librarySentinel" class="library-more" role="status" aria-live="polite">
            <span v-if="libraryLoadingMore">{{ $t('Loading more…') }}</span>
          </div>

          <div v-if="libraryMarquee" class="library-marquee" aria-hidden="true" :style="{ left: `${libraryMarquee.left}px`, top: `${libraryMarquee.top}px`, width: `${libraryMarquee.right - libraryMarquee.left}px`, height: `${libraryMarquee.bottom - libraryMarquee.top}px` }" />

          <Transition name="bulk-bar">
            <div v-if="selectingLibrary" class="library-bulk-bar" role="toolbar" :aria-label="$t('Selected artifacts')">
              <strong class="bulk-count" aria-live="polite">{{ $t('{count} selected', { count: selectedLibraryIds.size }) }}</strong>
              <button type="button" class="bulk-secondary" :disabled="bulkDeleting || selectedLibraryIds.size === libraryItems.length" @click="selectAllLibraryItems">
                {{ libraryHasMore ? $t('Select all loaded') : $t('Select all') }}
              </button>
              <button type="button" class="bulk-secondary" :disabled="bulkDeleting" @click="clearLibrarySelection">{{ $t('Clear') }}</button>
              <button type="button" class="bulk-delete" :disabled="bulkDeleting" :aria-busy="bulkDeleting" @click="deleteSelectedLibraryItems">
                <span v-if="bulkDeleting" class="button-spinner" aria-hidden="true" />
                <svg v-else aria-hidden="true"><use href="#icon-trash" /></svg>
                {{ bulkDeleting ? $t('Deleting…') : $t('Delete') }}
              </button>
            </div>
          </Transition>
        </section>
      </template>

      <template v-else-if="view === 'new'">
        <header class="topbar compact chat-topbar">
          <div class="chat-topbar-title"><span class="status-dot online" /><span>{{ sessionScope === 'scheduled' ? $t('nav.scheduledConversation') : sessionScope === 'channel' ? $t('nav.channelConversation') : $t('nav.workspace') }}</span></div>
          <button class="workspace-view-toggle" type="button" :aria-label="workspaceView === 'workspace' ? 'Show trace' : 'Show workspace'" :title="workspaceView === 'workspace' ? 'Show trace' : 'Show workspace'" @click="setWorkspaceView(workspaceView === 'workspace' ? 'trace' : 'workspace')">
            <svg v-if="workspaceView === 'workspace'" viewBox="0 0 24 24" aria-hidden="true"><path d="M4 6h4v4H4zM10 8h10M4 15h4v4H4zM10 17h10" /></svg>
            <svg v-else viewBox="0 0 24 24" aria-hidden="true"><path d="M4 4h7v16H4zM14 4h6v16h-6z" /></svg>
          </button>
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
                      <AgentExecution
                        :timeline="turnExecutionTimeline(turn, index)"
                        :running="isRunningTurn(index)"
                        :open="isTurnDetailsOpen(turn, index)"
                        :task="turnTask(index)"
                        :duration="turnDuration(turn, index)"
                        @toggle="toggleTurnExecution(turn, $event)"
                        @preview-image="openImagePreview"
                      >
                        <template #metrics>
                          <CacheHitRate class="turn-execution-cache" label="Cache" :rate="turnCacheHitRate(turn, index)" />
                        </template>
                        <template #tasks>
                          <div v-if="isRunningTurn(index) && activeTodos?.todos.length" class="turn-task-list">
                            <div><strong>Task progress</strong><small>{{ activeTodos.completed ? 'Completed' : `${(activeTodos.processing_index ?? 0) + 1} of ${activeTodos.todos.length}` }}</small></div>
                            <ol>
                              <li v-for="todo in activeTodos.todos" :key="todo.content" :class="todo.status">
                                <i aria-hidden="true">{{ todo.status === 'completed' ? '✓' : todo.status === 'processing' ? '•' : '' }}</i>
                                <span>{{ todo.content }}</span>
                              </li>
                            </ol>
                          </div>
                        </template>
                        <template #markdown="{ content }"><MarkdownContent :content="content" /></template>
                      </AgentExecution>

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

            <aside ref="artifactPaneRef" class="artifact-pane artifact-workspace">
              <header ref="artifactHeaderRef" class="artifact-collection-header">
                <div><strong>{{ $t('Artifacts') }}</strong><small>{{ $t('{count} in this conversation', { count: artifacts.length }) }}</small></div>
                <div class="artifact-collection-actions">
                  <span v-if="loading" class="artifact-syncing"><i />{{ $t('Updating') }}</span>
                  <button class="artifact-save-all" type="button" :disabled="savingAllArtifacts || saving || !artifactsNeedingSave.length" @click="saveAllArtifacts">{{ savingAllArtifacts ? 'Saving…' : 'Save all' }}</button>
                  <button class="artifact-refresh" type="button" :title="$t('Refresh artifacts')" :aria-label="$t('Refresh artifacts')" :disabled="artifactRefreshing" @click="refreshSelectedArtifact">
                    <svg :class="{ spinning: artifactRefreshing }"><use href="#icon-refresh" /></svg>
                  </button>
                </div>
              </header>
              <div v-if="artifacts.length" class="artifact-list" :style="artifactListHeight === null ? undefined : { height: `${artifactListHeight}px` }" aria-label="Conversation artifacts">
                <div v-for="artifact in artifacts" :key="artifact.id" class="artifact-list-item" :class="[artifactTone(artifact.artifact_type), lifecycleClass(artifactLifecycle(artifact)), artifact.card_status ? statusTone(artifact.card_status) : '', { active: artifact.id === selectedArtifactId }]" :data-lifecycle="artifactLifecycle(artifact)">
                  <CardStatusMark v-if="artifact.card_status" class="artifact-list-check" :status="artifact.card_status" :busy="cardStatusUpdatingIds.has(artifact.id)" @select="setConversationCardStatus(artifact, $event)" />
                  <button class="artifact-list-select" type="button" :disabled="saving || savingAllArtifacts" @click="selectArtifact(artifact)">
                    <img v-if="artifactListImage(artifact)" class="artifact-list-image" :src="artifactListImage(artifact) || undefined" alt="" />
                    <span v-else-if="artifact.card_status" class="artifact-kind-icon status-slot" aria-hidden="true" />
                    <span v-else class="artifact-kind-icon">{{ artifact.artifact_type === 'card' ? '◇' : artifact.artifact_type === 'article' ? '¶' : artifact.artifact_type === 'slides' ? '▤' : '▧' }}</span>
                    <span class="artifact-list-copy">
                      <small class="artifact-list-meta">
                        <span>{{ artifact.card_status ? $t(cardStatusType(artifact.card_status)) : artifact.artifact_type }}</span>
                        <em class="artifact-life-badge" :title="t(lifecycleHint(artifactLifecycle(artifact)))">{{ t(lifecycleLabel(artifactLifecycle(artifact))) }}</em>
                        <em v-if="artifact.card_status" class="artifact-status-tag">{{ t(cardStatusLabel(artifact.card_status)) }}</em>
                      </small>
                      <strong :class="{ 'status-struck': artifact.card_status && isStruck(artifact.card_status) }">{{ artifactTitle(artifactEditableContent(artifact)) }}</strong>
                      <span class="artifact-list-excerpt">{{ artifactListExcerpt(artifactEditableContent(artifact)) }}</span>
                    </span>
                  </button>
                  <div class="artifact-list-actions">
                    <button class="artifact-list-action" type="button" :disabled="saving || savingAllArtifacts || !artifactTitle(artifactEditableContent(artifact)).trim()" :aria-label="`${artifact.status === 'saved' ? 'Update' : 'Save'} ${artifactTitle(artifactEditableContent(artifact))}`" :title="artifact.status === 'saved' ? 'Update artifact' : 'Save artifact'" @click="saveSelectedArtifact(artifact)"><svg aria-hidden="true"><use href="#icon-check" /></svg></button>
                    <button class="artifact-list-action" type="button" :disabled="savingAllArtifacts" :aria-label="`Edit ${artifactTitle(artifactEditableContent(artifact))}`" title="Edit artifact" @click="editArtifactFromList(artifact)"><svg aria-hidden="true"><use href="#icon-edit" /></svg></button>
                    <button class="artifact-list-action danger" type="button" :disabled="saving || savingAllArtifacts" :aria-label="`Delete ${artifactTitle(artifactEditableContent(artifact))}`" title="Delete artifact" @click="deleteSelectedArtifact(artifact)"><svg aria-hidden="true"><use href="#icon-trash" /></svg></button>
                  </div>
                </div>
              </div>
              <div
                v-if="artifacts.length && artifactContent"
                class="artifact-splitter"
                role="separator"
                aria-label="Resize artifact list and preview"
                aria-orientation="horizontal"
                tabindex="0"
                :aria-valuenow="Math.round(artifactListHeight ?? MIN_ARTIFACT_LIST_HEIGHT)"
                @pointerdown="startArtifactSplit"
                @pointermove="moveArtifactSplit"
                @pointerup="endArtifactSplit"
                @pointercancel="endArtifactSplit"
                @keydown="keyArtifactSplit"
              ><span /></div>
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
              <div v-else :key="selectedArtifactId ?? 'artifact-preview'" class="artifact-panel artifact-editor" :class="[artifactTone(artifactContent.artifact_type), selectedArtifact ? lifecycleClass(artifactLifecycle(selectedArtifact)) : '', { editing: selectedArtifactDirty }]">
                <div class="artifact-editor-accent" />
                <header class="artifact-editor-header">
                  <div class="artifact-state"><i /><span><strong>{{ selectedArtifact?.card_status ? $t(cardStatusType(selectedArtifact.card_status)) : selectedArtifact?.artifact_type }} artifact</strong><small v-if="selectedArtifact" :title="t(lifecycleHint(artifactLifecycle(selectedArtifact)))"><span class="artifact-life-note">{{ t(lifecycleLabel(artifactLifecycle(selectedArtifact))) }}</span> · version {{ selectedArtifact.version }}<em v-if="selectedArtifactDirty" class="artifact-dirty-badge">{{ t('artifact.editing') }}</em></small></span></div>
                  <CardStatusMenu v-if="selectedArtifact?.card_status" :status="selectedArtifact.card_status" :busy="cardStatusUpdatingIds.has(selectedArtifact.id)" @select="setConversationCardStatus(selectedArtifact, $event)" />
                  <div v-if="selectedArtifactDiff?.changed || !artifactPreview" class="artifact-mode-switch" :aria-label="$t('Artifact display mode')"><button v-if="selectedArtifactDiff?.changed" type="button" :class="{ active: artifactDiff }" @click="artifactDiff = true; artifactPreview = false">{{ $t('Diff') }}</button><button v-if="!artifactPreview || artifactDiff" type="button" @click="artifactPreview = true; artifactDiff = false">{{ $t('Preview') }}</button></div>
                </header>
                <div class="artifact-editor-body">
                  <ArtifactDiffView v-if="artifactDiff && selectedArtifactDiff" :diff="selectedArtifactDiff" />
                  <template v-else>
                  <div v-if="artifactContent.artifact_type === 'card' && !artifactPreview" class="card-meta-row">
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
                    <div v-else class="card-body-editor"><span>{{ artifactContent.artifact_type === 'article' ? 'Article' : artifactContent.artifact_type === 'slides' ? 'Slides' : 'Knowledge' }} · Markdown</span><BlockEditor v-model="artifactContent.content" compact :slides="artifactContent.artifact_type === 'slides'" /></div>
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
              </div>
            </aside>
          </div>
        </section>
      </template>

      <template v-else-if="view === 'assets'">
        <StaticAssetsView
          ref="staticAssetsView"
          :tag-id="selectedTag"
          :tag-path="selectedTagName ?? null"
          @drag-start="startStaticAssetDrag"
          @drag-end="endStaticAssetDrag"
          @clear-tag="filterByTag(null)"
        />
      </template>

      <template v-else-if="view === 'scheduledTasks'">
        <ScheduledTasksView @open-session="openScheduledSession" />
      </template>

      <template v-else-if="view === 'channels'">
        <ChannelsView />
      </template>

      <Teleport to="body">
        <div v-if="settingsOpen" class="settings-backdrop" @click.self="closeSettings">
        <section ref="settingsDialog" class="settings-dialog" role="dialog" aria-modal="true" :aria-label="$t('Settings')" tabindex="-1">
          <header class="settings-dialog-header">
            <h1>{{ $t('Settings') }}</h1>
            <button class="close-button" type="button" :aria-label="$t('Close')" @click="closeSettings">×</button>
          </header>
          <div class="settings-dialog-body">
          <nav class="settings-tabs" role="tablist" aria-label="Settings sections">
            <button :class="{ active: settingsSection === 'general' }" type="button" role="tab" :aria-selected="settingsSection === 'general'" @click="selectSettingsSection('general')">{{ $t('settings.general') }}</button>
            <button :class="{ active: settingsSection === 'usage' }" type="button" role="tab" :aria-selected="settingsSection === 'usage'" @click="selectSettingsSection('usage')">{{ $t('settings.usage') }}</button>
            <button :class="{ active: settingsSection === 'providers' }" type="button" role="tab" :aria-selected="settingsSection === 'providers'" @click="selectSettingsSection('providers')">{{ $t('settings.providers') }}</button>
            <button :class="{ active: settingsSection === 'limits' }" type="button" role="tab" :aria-selected="settingsSection === 'limits'" @click="selectSettingsSection('limits')">{{ $t('settings.limits') }}</button>
          </nav>
          <section class="content settings-view">
          <div v-if="settingsSection === 'general'" class="settings-section">
          <div class="settings-intro">
            <div><h2>{{ $t('Preferences') }}</h2><p>{{ $t('Choose how Zett reads on this computer.') }}</p></div>
          </div>
          <div class="settings-card">
            <div class="form-grid">
              <label class="field">
                <span>{{ $t('settings.language') }}</span>
                <select :value="locale" @change="changeLocale">
                  <option value="en">{{ $t('settings.english') }}</option>
                  <option value="zh">{{ $t('settings.chinese') }}</option>
                </select>
                <small>{{ $t('Applied right away, and remembered in this browser.') }}</small>
              </label>
            </div>
          </div>
          </div>
          <div v-else-if="settingsSection === 'providers'" class="settings-section">
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
              <label class="field"><span>{{ $t('Provider') }}</span><select v-model="ai.provider" @change="selectProviderKind"><option value="openai_compatible">OpenAI compatible</option><option value="responses_compatible">Responses compatible</option><option value="openai">OpenAI</option><option value="deepseek">DeepSeek</option><option value="anthropic">Anthropic</option><option value="anthropic_compatible">Anthropic compatible</option><option value="google">Google Gemini</option><option value="ollama">Ollama</option></select><small>The API format used for model requests.</small></label>
              <label class="field"><span>{{ $t('Model') }}</span><input v-model="ai.model" placeholder="e.g. gpt-4.1-mini" /><small>Use the exact model identifier from your provider.</small></label>
              <label class="field full"><span>{{ $t('Base URL') }} <em>{{ ['openai_compatible', 'responses_compatible', 'anthropic_compatible'].includes(ai.provider) ? 'Custom' : 'Auto-filled' }}</em></span><input v-model="ai.base_url" :placeholder="ai.provider === 'responses_compatible' ? 'https://api.example.com' : 'https://api.example.com/v1'" /><small>{{ providerBaseUrlHelp(ai.provider) }}</small></label>
              <label class="field full"><span>{{ $t('API key') }} <em>{{ providerLoading ? 'Loading…' : editingProviderId === null ? 'New' : ai.api_key ? 'Loaded' : 'Not set' }}</em></span><div class="secret-input"><input v-model="ai.api_key" :type="apiKeyVisible ? 'text' : 'password'" autocomplete="off" placeholder="Leave blank to keep the saved key" /><button type="button" :aria-label="apiKeyVisible ? 'Hide API key' : 'Show API key'" :title="apiKeyVisible ? 'Hide API key' : 'Show API key'" @click="apiKeyVisible = !apiKeyVisible"><svg aria-hidden="true"><use :href="apiKeyVisible ? '#icon-eye-off' : '#icon-eye'" /></svg></button></div><small>Stored encrypted locally. Saving a blank value keeps the existing key.</small></label>
              <label v-if="!providerIgnoresTemperature(ai.provider)" class="field temperature-field"><span>{{ $t('Temperature') }} <output>{{ ai.temperature.toFixed(1) }}</output></span><input v-model.number="ai.temperature" type="range" min="0" max="2" step="0.1" /></label>
              <div v-if="ai.provider === 'responses_compatible'" class="field"><span>{{ $t('API mode') }}</span><strong>Responses API</strong><small>This compatible connection always uses the Responses protocol.</small></div>
              <div v-else-if="['openai', 'openai_compatible', 'deepseek'].includes(ai.provider)" class="field"><span>{{ $t('API mode') }}</span><div class="mode-options" role="group" :aria-label="$t('API mode')"><button type="button" :class="{ active: !ai.response }" @click="setResponseMode(false)">Chat Completions</button><button type="button" :class="{ active: ai.response }" @click="setResponseMode(true)">Responses API</button></div><small>Responses mode enables provider-hosted tools such as web search.</small></div>
            </div>
            <div class="settings-actions"><button v-if="editingProviderId !== null" class="danger-button" type="button" @click="removeProvider">Delete provider</button><span v-else>Credentials are encrypted in your local database.</span><div><label class="switch"><input v-model="ai.enabled" type="checkbox" /><span /><small>{{ ai.enabled ? 'Enabled' : 'Disabled' }}</small></label><button class="primary-action" :disabled="providerSaving || providerLoading || !ai.name || !ai.model" :aria-busy="providerSaving" type="submit"><span v-if="providerSaving" class="button-spinner" aria-hidden="true" /><span>{{ providerSaving ? 'Testing…' : editingProviderId === null ? 'Add provider' : 'Save provider' }}</span></button></div></div>
          </form>
          </div>
          <div v-else-if="settingsSection === 'limits'" class="settings-section">
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
          <div class="settings-intro runtime-settings-heading">
            <div><h2>{{ $t('Agent permissions') }}</h2><p>{{ $t('Things the Agent may do in a conversation only when you allow them.') }}</p></div>
          </div>
          <div class="settings-card permission-card">
            <label v-for="permission in agentPermissions" :key="permission.key" class="permission-row">
              <span class="permission-copy">
                <strong>{{ $t(permission.title) }}</strong>
                <small>{{ $t(permission.description) }}</small>
              </span>
              <span class="switch">
                <input
                  type="checkbox"
                  role="switch"
                  :checked="runtimeSettings[permission.key]"
                  :disabled="agentPermissionSaving !== null"
                  @change="setAgentPermission(permission.key, ($event.target as HTMLInputElement).checked)"
                />
                <span />
              </span>
            </label>
          </div>
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
          </div>
        </section>
        </div>
      </Teleport>

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
              <div><span class="card-type">{{ selectedLibraryItem.item_type === 'card' ? selectedLibraryItem.card_type : selectedLibraryItem.item_type }}</span><CardStatusMenu v-if="selectedLibraryItem.card_status" :status="selectedLibraryItem.card_status" :busy="cardStatusUpdatingIds.has(selectedLibraryItem.id)" @select="setLibraryCardStatus(selectedLibraryItem, $event)" /></div>
              <div class="detail-header-actions">
                <button class="detail-header-button" type="button" @click="openArtifactSession(selectedLibraryItem)"><svg><use href="#icon-conversation" /></svg>Conversation</button>
                <button class="detail-header-button" type="button" @click="copyLibraryItemId(selectedLibraryItem)"><svg><use href="#icon-copy" /></svg>Copy ID</button>
                <button v-if="selectedLibraryItem.item_type !== 'latex_pdf'" class="detail-header-button" type="button" @click="openLibraryEditor(selectedLibraryItem)"><svg><use href="#icon-edit" /></svg>Edit</button>
                <button class="detail-delete-button" :disabled="deletingLibraryItemId !== null" type="button" @click="deleteSelectedLibraryItem"><svg><use href="#icon-trash" /></svg>Delete</button>
                <button class="close-button" type="button" aria-label="Close resource details" @click="selectedLibraryItem = null">×</button>
              </div>
            </header>
            <div class="detail-content">
              <h1 :class="selectedLibraryItem.card_status ? [statusTone(selectedLibraryItem.card_status), { 'status-struck': isStruck(selectedLibraryItem.card_status) }] : undefined">{{ selectedLibraryItem.title }}</h1>
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
<style src="./styles/app/index.css"></style>
