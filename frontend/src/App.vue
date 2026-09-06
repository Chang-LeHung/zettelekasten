<script setup lang="ts">
import { computed, defineAsyncComponent, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ApiError, aiClient, libraryClient, tagClient } from './api/client'
import type { AgentArtifact, AgentCompactionActivity, AgentSession, AgentTimelineEntry, AgentToolActivity, AgentUsage, AIProvider, AIProviderInput, AnalysisMessage, ArtifactContent, CardType, LibraryItem, LibraryItemUpdate, ReasoningEffort, SessionAsset, Tag } from './api/types'
import ConfirmDialog from './components/ConfirmDialog.vue'
import { jsonSnapshot } from './utils/jsonSnapshot'

const MarkdownContent = defineAsyncComponent(() => import('./components/MarkdownContent.vue'))
const LibraryEditor = defineAsyncComponent(() => import('./components/LibraryEditor.vue'))

type View = 'library' | 'search' | 'new' | 'settings'
type NoticeKind = 'success' | 'error'
type AssetEditorMode = 'closed' | 'text' | 'link'
type AssetFilter = 'all' | 'documents' | 'images' | 'links' | 'notes' | 'code'
interface SessionTelemetry {
  totalTokens: number
  inputTokens: number
  cacheReadTokens: number
  outputTokensPerSecond: number | null
}
interface ConfirmationState {
  open: boolean
  title: string
  message: string
  confirmLabel: string
}

const libraryItems = ref<LibraryItem[]>([])
const selectedLibraryItem = ref<LibraryItem | null>(null)
const libraryEditorItem = ref<LibraryItem | null>(null)
const libraryEditorSaving = ref(false)
const libraryLoading = ref(false)
const deletingLibraryItemId = ref<string | null>(null)
const tags = ref<Tag[]>([])
const query = ref('')
const activeQuery = ref('')
const selectedTag = ref<number | null>(null)
const view = ref<View>('new')
const raw = ref('')
const artifactContent = ref<ArtifactContent | null>(null)
const conversation = ref<AnalysisMessage[]>([])
const followUp = ref('')
const streamingMessage = ref('')
const streamingReasoning = ref('')
const streamingActivities = ref<AgentToolActivity[]>([])
const streamingTimeline = ref<AgentTimelineEntry[]>([])
const streamingResponseVisible = ref(false)
const sessionTelemetry = ref<SessionTelemetry>({ totalTokens: 0, inputTokens: 0, cacheReadTokens: 0, outputTokensPerSecond: null })
let turnTelemetryBaseline: SessionTelemetry = { totalTokens: 0, inputTokens: 0, cacheReadTokens: 0, outputTokensPerSecond: null }
let agentScrollFrame: number | null = null
let followAgentOutput = true
const streamingStatus = ref('idle')
const activeStreamController = ref<AbortController | null>(null)
const artifactPreview = ref(true)
const conversationId = ref<string | null>(null)
const editingSessionId = ref<string | null>(null)
const sessionTitleDraft = ref('')
const artifacts = ref<AgentArtifact[]>([])
const assets = ref<SessionAsset[]>([])
const assetEditorMode = ref<AssetEditorMode>('closed')
const assetName = ref('')
const assetValue = ref('')
const assetUploading = ref(false)
const assetQuery = ref('')
const assetFilter = ref<AssetFilter>('all')
const assetDragging = ref(false)
const sessions = ref<AgentSession[]>([])
const sessionsLoading = ref(false)
const sessionsHaveMore = ref(true)
const sessionPageSize = 20
const selectedArtifactId = ref<string | null>(null)
const loading = ref(false)
const saving = ref(false)
const notice = ref('')
const noticeKind = ref<NoticeKind>('success')
const confirmation = ref<ConfirmationState>({ open: false, title: '', message: '', confirmLabel: 'Delete' })
let resolveConfirmation: ((confirmed: boolean) => void) | null = null
const selectedSuggestions = ref<string[]>([])
const providers = ref<AIProvider[]>([])
const selectedProviderId = ref<number | null>(null)
const reasoningEffort = ref<ReasoningEffort>('medium')
const editingProviderId = ref<number | null>(null)
const ai = ref<AIProviderInput>({
  name: '',
  provider: 'openai-compatible',
  model: '',
  base_url: '',
  api_key: '',
  temperature: 0.2,
  enabled: true,
})
const tagName = ref('')
const tagParent = ref<number | null>(null)
const searchInput = ref<HTMLInputElement | null>(null)
const agentThread = ref<HTMLElement | null>(null)
const assetFileInput = ref<HTMLInputElement | null>(null)
const titleRefreshTimers: number[] = []
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

const flatTags = computed(() => flatten(tags.value))
const selectedTagName = computed(() => flatTags.value.find((tag) => tag.id === selectedTag.value)?.path)
const pageTitle = computed(() => {
  if (view.value === 'search') return activeQuery.value ? `Results for “${activeQuery.value}”` : 'Search library'
  return selectedTagName.value || 'All knowledge'
})
const pageDescription = computed(() => {
  if (view.value === 'search') return `${libraryItems.value.length} matching ${libraryItems.value.length === 1 ? 'item' : 'items'}`
  return `${libraryItems.value.length} ${libraryItems.value.length === 1 ? 'item' : 'items'} in your library`
})
const conversationStarted = computed(
  () => conversationId.value !== null || artifactContent.value !== null || conversation.value.length > 0,
)
const selectedArtifact = computed(() => artifacts.value.find((artifact) => artifact.id === selectedArtifactId.value) || null)
const selectedImageUrl = computed(() => {
  const content = artifactContent.value
  if (content?.artifact_type !== 'image') return null
  if (content.source_url) return content.source_url
  return assets.value.find((asset) => asset.id === content.asset_id)?.content_url || null
})
const sessionCacheHitRate = computed(() => (
  sessionTelemetry.value.inputTokens
    ? sessionTelemetry.value.cacheReadTokens / sessionTelemetry.value.inputTokens
    : null
))
const visibleSessions = computed(() => sessions.value.filter((session) => (
  session.message_count > 0
  || (session.id === conversationId.value && (artifacts.value.length > 0 || assets.value.length > 0))
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

function resetStreamState(): void {
  turnTelemetryBaseline = { ...sessionTelemetry.value }
  streamingMessage.value = ''
  streamingReasoning.value = ''
  streamingActivities.value = []
  streamingTimeline.value = []
  streamingStatus.value = 'starting'
  streamingResponseVisible.value = true
}

function updateSessionTelemetry(usage: AgentUsage): void {
  sessionTelemetry.value = {
    totalTokens: turnTelemetryBaseline.totalTokens + usage.total_tokens,
    inputTokens: turnTelemetryBaseline.inputTokens + usage.input_tokens,
    cacheReadTokens: turnTelemetryBaseline.cacheReadTokens + usage.cache_read_tokens,
    outputTokensPerSecond: usage.output_tokens_per_second ?? turnTelemetryBaseline.outputTokensPerSecond,
  }
}

function applySessionTelemetry(session: AgentSession): void {
  sessionTelemetry.value = {
    totalTokens: session.total_tokens,
    inputTokens: session.total_input_tokens,
    cacheReadTokens: session.total_cache_read_tokens,
    outputTokensPerSecond: session.average_output_tokens_per_second,
  }
}

function updateToolActivity(activity: AgentToolActivity): void {
  const index = streamingActivities.value.findIndex((item) => item.id === activity.id)
  if (index < 0) streamingActivities.value.push(activity)
  else streamingActivities.value.splice(index, 1, { ...streamingActivities.value[index], ...activity })

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

function updateCompactionActivity(activity: AgentCompactionActivity): void {
  const index = streamingTimeline.value.findIndex((item) => item.type === 'compaction')
  const entry: AgentTimelineEntry = { id: 'context-compaction', type: 'compaction', activity }
  if (index < 0) streamingTimeline.value.push(entry)
  else streamingTimeline.value.splice(index, 1, entry)
}

function updateStreamText(type: 'reasoning' | 'message', content: string): void {
  const previous = type === 'reasoning' ? streamingReasoning.value : streamingMessage.value
  const delta = content.startsWith(previous) ? content.slice(previous.length) : content
  if (type === 'reasoning') streamingReasoning.value = content
  else streamingMessage.value = content
  if (!delta) return

  const last = streamingTimeline.value.at(-1)
  if (last?.type === type) {
    last.content += delta
    streamingTimeline.value = [...streamingTimeline.value]
    return
  }
  streamingTimeline.value.push({
    id: `${type}-${streamingTimeline.value.length}`,
    type,
    content: delta,
  })
}

function historicalTimeline(message: AnalysisMessage): AgentTimelineEntry[] {
  if (message.timeline?.length) return message.timeline
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

function restorePersistedTimeline(
  metadata: Record<string, unknown>,
  activities: AgentToolActivity[],
): AgentTimelineEntry[] | undefined {
  const stored = metadata.timeline
  if (!Array.isArray(stored)) return undefined

  const entries = stored.flatMap((value, index): AgentTimelineEntry[] => {
    if (!value || typeof value !== 'object') return []
    const event = value as Record<string, unknown>
    if ((event.type === 'reasoning' || event.type === 'message') && typeof event.content === 'string') {
      return [{ id: `persisted-${index}`, type: event.type, content: event.content }]
    }
    if (event.type === 'tool' && typeof event.tool_call_id === 'string') {
      const activity = activities.find((item) => item.id === event.tool_call_id)
      return activity ? [{ id: `persisted-${index}`, type: 'tool', activity }] : []
    }
    return []
  })
  return entries.length ? entries : undefined
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

function streamCallbacks() {
  return {
    onStatus: (state: string) => { streamingStatus.value = state },
    onReasoning: (content: string) => { updateStreamText('reasoning', content) },
    onMessage: (content: string) => { updateStreamText('message', content) },
    onTool: updateToolActivity,
    onCompaction: updateCompactionActivity,
    onUsage: updateSessionTelemetry,
    onArtifacts: applyArtifacts,
  }
}

function handleAgentThreadScroll(): void {
  const thread = agentThread.value
  if (!thread) return
  followAgentOutput = thread.scrollHeight - thread.scrollTop - thread.clientHeight < 96
}

function scrollAgentThread(force = false): void {
  void nextTick(() => {
    const thread = agentThread.value
    if (!thread || (!force && !followAgentOutput)) return
    if (agentScrollFrame !== null) window.cancelAnimationFrame(agentScrollFrame)
    agentScrollFrame = window.requestAnimationFrame(() => {
      agentScrollFrame = null
      thread.scrollTop = thread.scrollHeight
      followAgentOutput = true
    })
  })
}

function scheduleSessionTitleRefresh(): void {
  for (const delay of [1500, 4000, 8000]) {
    titleRefreshTimers.push(window.setTimeout(() => void loadSessions(true), delay))
  }
}

watch(
  [streamingMessage, streamingReasoning, () => streamingTimeline.value.length],
  () => scrollAgentThread(),
)
watch(
  () => conversation.value.length,
  () => scrollAgentThread(true),
)
watch(loading, (isLoading) => {
  if (isLoading) scrollAgentThread(true)
})

function flatten(nodes: Tag[], depth = 0): Array<Tag & { depth: number }> {
  return nodes.flatMap((tag) => [{ ...tag, depth }, ...flatten(tag.children || [], depth + 1)])
}

function showNotice(message: string, kind: NoticeKind = 'success'): void {
  notice.value = message
  noticeKind.value = kind
  window.setTimeout(() => {
    if (notice.value === message) notice.value = ''
  }, 3200)
}

function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return `Request failed (${error.status})`
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
    })
  } catch (error) {
    showNotice(errorMessage(error), 'error')
  } finally {
    libraryLoading.value = false
  }
}

async function loadInitialData(): Promise<void> {
  try {
    const [tagData, libraryData, providerData] = await Promise.all([
      tagClient.list(),
      libraryClient.list(),
      aiClient.listProviders(),
    ])
    tags.value = tagData
    libraryItems.value = libraryData
    providers.value = providerData
    const firstProvider = providerData.find((provider) => provider.enabled)
    if (firstProvider) {
      selectedProviderId.value = firstProvider.id
      selectProvider(firstProvider)
    }
  } catch (error) {
    showNotice(errorMessage(error), 'error')
  }
}

function navigate(nextView: View): void {
  view.value = nextView
  notice.value = ''
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

function openLibraryItem(item: LibraryItem): void {
  selectedLibraryItem.value = item
}

function openLibraryEditor(item: LibraryItem): void {
  selectedLibraryItem.value = null
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
}

async function saveLibraryEditor(payload: LibraryItemUpdate): Promise<void> {
  const item = libraryEditorItem.value
  if (!item || libraryEditorSaving.value) return
  libraryEditorSaving.value = true
  try {
    const updated = await libraryClient.update(item.item_type, item.id, payload)
    libraryItems.value = libraryItems.value.map((candidate) => (
      candidate.item_type === updated.item_type && candidate.id === updated.id ? updated : candidate
    ))
    libraryEditorItem.value = updated
    if (selectedLibraryItem.value?.item_type === updated.item_type && selectedLibraryItem.value.id === updated.id) {
      selectedLibraryItem.value = updated
    }
    showNotice(`${updated.item_type === 'article' ? 'Article' : 'Card'} saved`)
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

async function deleteLibraryItem(item: LibraryItem): Promise<void> {
  if (deletingLibraryItemId.value !== null) return
  const confirmed = await requestConfirmation(
    `Delete this ${item.item_type}?`,
    `“${item.title}” will be permanently removed from your library. This action cannot be undone.`,
    `Delete ${item.item_type}`,
  )
  if (!confirmed) return
  deletingLibraryItemId.value = item.id
  try {
    await libraryClient.delete(item.item_type, item.id)
    libraryItems.value = libraryItems.value.filter((candidate) => candidate.id !== item.id)
    if (selectedLibraryItem.value?.id === item.id) selectedLibraryItem.value = null
    if (libraryEditorItem.value?.id === item.id) libraryEditorItem.value = null
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

async function filterByTag(tagId: number | null): Promise<void> {
  selectedTag.value = tagId
  activeQuery.value = ''
  query.value = ''
  view.value = 'library'
  await loadLibrary()
}

async function analyze(): Promise<void> {
  if (!raw.value.trim()) return
  if (selectedProviderId.value === null) {
    showNotice('Add and select an AI provider first', 'error')
    view.value = 'settings'
    return
  }
  loading.value = true
  const controller = new AbortController()
  activeStreamController.value = controller
  resetStreamState()
  try {
    const activeConversationId = await ensureConversation()
    const result = await aiClient.analyzeStream(
      activeConversationId,
      raw.value.trim(),
      selectedProviderId.value,
      reasoningEffort.value,
      [],
      streamCallbacks(),
      controller.signal,
    )
    streamingResponseVisible.value = false
    conversation.value = [{
      role: 'assistant',
      content: streamingMessage.value || (result ? 'The artifact is ready.' : 'How would you like to continue?'),
      reasoning: streamingReasoning.value || undefined,
      activities: [...streamingActivities.value],
      timeline: jsonSnapshot(streamingTimeline.value),
    }]
    await refreshArtifacts(true)
    await loadSessions(true)
    scheduleSessionTitleRefresh()
  } catch (error) {
    if (controller.signal.aborted || isAbortError(error)) {
      streamingResponseVisible.value = false
      if (streamingMessage.value || streamingReasoning.value || streamingTimeline.value.length) {
        conversation.value = [{
          role: 'assistant',
          content: streamingMessage.value,
          reasoning: streamingReasoning.value || undefined,
          activities: [...streamingActivities.value],
          timeline: jsonSnapshot(streamingTimeline.value),
        }]
      }
      streamingStatus.value = 'cancelled'
      await loadSessions(true)
    } else {
      showNotice(errorMessage(error), 'error')
    }
  } finally {
    streamingResponseVisible.value = false
    if (activeStreamController.value === controller) activeStreamController.value = null
    loading.value = false
    if (streamingStatus.value !== 'cancelled') streamingStatus.value = 'idle'
  }
}

async function refine(): Promise<void> {
  const content = followUp.value.trim()
  if (!content) return
  const history: AnalysisMessage[] = [...conversation.value, { role: 'user', content }]
  conversation.value = history
  followUp.value = ''
  loading.value = true
  const controller = new AbortController()
  activeStreamController.value = controller
  resetStreamState()
  try {
    if (selectedProviderId.value === null) throw new Error('Select an AI provider first')
    const activeConversationId = await ensureConversation()
    await syncSelectedArtifact()
    const result = await aiClient.analyzeStream(
      activeConversationId,
      raw.value.trim(),
      selectedProviderId.value,
      reasoningEffort.value,
      history,
      streamCallbacks(),
      controller.signal,
    )
    streamingResponseVisible.value = false
    conversation.value = [
      ...history,
      {
        role: 'assistant',
        content: streamingMessage.value || (result ? 'The artifact is ready.' : 'How would you like to continue?'),
        reasoning: streamingReasoning.value || undefined,
        activities: [...streamingActivities.value],
        timeline: jsonSnapshot(streamingTimeline.value),
      },
    ]
    await refreshArtifacts(true)
    await loadSessions(true)
  } catch (error) {
    if (controller.signal.aborted || isAbortError(error)) {
      streamingResponseVisible.value = false
      if (streamingMessage.value || streamingReasoning.value || streamingTimeline.value.length) {
        conversation.value = [
          ...history,
          {
            role: 'assistant',
            content: streamingMessage.value,
            reasoning: streamingReasoning.value || undefined,
            activities: [...streamingActivities.value],
            timeline: jsonSnapshot(streamingTimeline.value),
          },
        ]
      }
      streamingStatus.value = 'cancelled'
      await loadSessions(true)
    } else {
      showNotice(errorMessage(error), 'error')
    }
  } finally {
    streamingResponseVisible.value = false
    if (activeStreamController.value === controller) activeStreamController.value = null
    loading.value = false
    if (streamingStatus.value !== 'cancelled') streamingStatus.value = 'idle'
  }
}

function submitConversation(): void {
  if (loading.value) return
  if (conversationStarted.value) void refine()
  else void analyze()
}

function handleComposerEnter(event: KeyboardEvent): void {
  if (loading.value) return
  event.preventDefault()
  submitConversation()
}

function stopGeneration(): void {
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
      return persisted.id
    } catch {
      window.localStorage.removeItem(activeSessionKey)
    }
  }
  const started = await aiClient.startAgent()
  sessionTelemetry.value = { totalTokens: 0, inputTokens: 0, cacheReadTokens: 0, outputTokensPerSecond: null }
  conversationId.value = started.conversation_id
  window.localStorage.setItem(activeSessionKey, started.conversation_id)
  applyArtifacts(started.artifacts)
  assets.value = started.assets
  return started.conversation_id
}

function applySession(session: AgentSession): void {
  conversationId.value = session.id
  window.localStorage.setItem(activeSessionKey, session.id)
  applyArtifacts(session.artifacts, false)
  assets.value = session.assets
  applySessionTelemetry(session)
  const visibleMessages = session.messages.filter((message) => message.role === 'user' || message.role === 'assistant')
  const firstUser = visibleMessages.find((message) => message.role === 'user')
  raw.value = firstUser?.content || ''
  let skippedFirstUser = false
  conversation.value = visibleMessages.flatMap((message): AnalysisMessage[] => {
    if (message.role === 'user' && !skippedFirstUser) {
      skippedFirstUser = true
      return []
    }
    const run = session.runs.find((item) => item.turn_id === message.turn_id)
    const activities = message.role === 'assistant' ? run?.tool_calls.map((toolCall) => ({
      id: toolCall.id,
      name: toolCall.tool_name,
      state: toolCall.status,
      arguments: toolCall.input,
      output: toolCall.output,
      error_message: toolCall.error_message,
      duration_ms: toolCall.duration_ms ?? undefined,
    })) || [] : []
    return [{
      role: message.role as 'user' | 'assistant',
      content: message.content,
      reasoning: message.reasoning_content || undefined,
      activities: message.role === 'assistant' ? activities : undefined,
      timeline: message.role === 'assistant'
        ? restorePersistedTimeline(message.metadata, activities)
        : undefined,
    }]
  })
  followUp.value = ''
}

async function openSession(sessionId: string): Promise<void> {
  if (loading.value || sessionId === conversationId.value) return
  sessionsLoading.value = true
  try {
    applySession(await aiClient.getAgentSession(sessionId))
    view.value = 'new'
  } catch (error) {
    showNotice(errorMessage(error), 'error')
  } finally {
    sessionsLoading.value = false
  }
}

function startSessionTitleEdit(session: AgentSession): void {
  editingSessionId.value = session.id
  sessionTitleDraft.value = session.title || 'New conversation'
}

function cancelSessionTitleEdit(): void {
  editingSessionId.value = null
  sessionTitleDraft.value = ''
}

async function saveSessionTitle(sessionId: string): Promise<void> {
  const title = sessionTitleDraft.value.trim()
  if (!title) return
  try {
    const updated = await aiClient.updateAgentSessionTitle(sessionId, title)
    sessions.value = sessions.value.map((session) => session.id === updated.id ? updated : session)
    cancelSessionTitleEdit()
  } catch (error) {
    showNotice(errorMessage(error), 'error')
  }
}

async function deleteSession(session: AgentSession): Promise<void> {
  const title = session.title || 'New conversation'
  const confirmed = await requestConfirmation(
    'Delete this conversation?',
    `“${title}” and all of its messages, draft artifacts, and session assets will be permanently removed.`,
    'Delete conversation',
  )
  if (!confirmed) return
  try {
    await aiClient.deleteAgentSession(session.id)
    sessions.value = sessions.value.filter((item) => item.id !== session.id)
    if (editingSessionId.value === session.id) cancelSessionTitleEdit()
    if (conversationId.value === session.id) await resetWorkspace()
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
    const activeSession = sessions.value.find((session) => session.id === conversationId.value)
    if (activeSession) applySessionTelemetry(activeSession)
  } catch (error) {
    showNotice(errorMessage(error), 'error')
  } finally {
    sessionsLoading.value = false
  }
}

function selectArtifact(artifact: AgentArtifact): void {
  selectedArtifactId.value = artifact.id
  artifactContent.value = jsonSnapshot(artifact.content)
  selectedSuggestions.value = artifact.content.suggested_tags.map((tag) => tag.path)
}

function applyArtifacts(nextArtifacts: AgentArtifact[], preferLatest = true): void {
  artifacts.value = nextArtifacts
  if (!nextArtifacts.length) {
    selectedArtifactId.value = null
    artifactContent.value = null
    return
  }
  const current = nextArtifacts.find((artifact) => artifact.id === selectedArtifactId.value)
  const target = preferLatest
    ? [...nextArtifacts].sort((left, right) => right.updated_at.localeCompare(left.updated_at))[0]
    : current || nextArtifacts[0]
  if (target) selectArtifact(target)
}

async function refreshArtifacts(preferLatest = false): Promise<void> {
  if (!conversationId.value) return
  applyArtifacts(await aiClient.listAgentArtifacts(conversationId.value), preferLatest)
}

async function syncSelectedArtifact(): Promise<void> {
  if (!conversationId.value || !selectedArtifactId.value || !artifactContent.value) return
  const updated = await aiClient.updateAgentArtifact(conversationId.value, selectedArtifactId.value, artifactContent.value)
  const index = artifacts.value.findIndex((artifact) => artifact.id === updated.id)
  if (index >= 0) artifacts.value.splice(index, 1, updated)
}

async function resetWorkspace(): Promise<void> {
  artifactContent.value = null
  conversation.value = []
  followUp.value = ''
  selectedSuggestions.value = []
  artifacts.value = []
  assets.value = []
  selectedArtifactId.value = null
  artifactPreview.value = true
  conversationId.value = null
  sessionTelemetry.value = { totalTokens: 0, inputTokens: 0, cacheReadTokens: 0, outputTokensPerSecond: null }
  resetStreamState()
  streamingStatus.value = 'idle'
  window.localStorage.removeItem(activeSessionKey)
  await loadSessions(true)
}

function showAssetEditor(mode: Exclude<AssetEditorMode, 'closed'>): void {
  assetEditorMode.value = assetEditorMode.value === mode ? 'closed' : mode
  assetName.value = ''
  assetValue.value = ''
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

async function pasteAssets(event: ClipboardEvent): Promise<void> {
  const clipboard = event.clipboardData
  if (!clipboard || assetUploading.value) return
  const itemFiles = Array.from(clipboard.items)
    .filter((item) => item.kind === 'file')
    .map((item) => item.getAsFile())
    .filter((file): file is File => file !== null)
  const files = itemFiles.length ? itemFiles : Array.from(clipboard.files)
  if (files.length) {
    event.preventDefault()
    await uploadAssetFiles(files)
    showNotice(`${files.length} pasted ${files.length === 1 ? 'asset' : 'assets'} added`)
    return
  }

  const target = event.target
  const insideAssetPane = target instanceof Element && target.closest('.assets-pane') !== null
  const editableTarget = target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement
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

function openAsset(asset: SessionAsset): void {
  const target = asset.source_url || asset.content_url
  if (target) window.open(target, '_blank', 'noopener,noreferrer')
}

async function removeAsset(asset: SessionAsset): Promise<void> {
  if (!conversationId.value) return
  const confirmed = await requestConfirmation(
    'Delete this asset?',
    `“${asset.name}” will be removed from this conversation and its local file will be deleted.`,
    'Delete asset',
  )
  if (!confirmed) return
  try {
    await aiClient.deleteSessionAsset(conversationId.value, asset.id)
    assets.value = assets.value.filter((item) => item.id !== asset.id)
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

async function saveSelectedArtifact(): Promise<void> {
  if (!artifactContent.value || !conversationId.value || !selectedArtifactId.value) return
  saving.value = true
  try {
    artifactContent.value.suggested_tags = artifactContent.value.suggested_tags.filter((tag) => selectedSuggestions.value.includes(tag.path))
    await syncSelectedArtifact()
    const saved = await aiClient.saveAgentArtifact(conversationId.value, selectedArtifactId.value)
    const index = artifacts.value.findIndex((artifact) => artifact.id === saved.id)
    if (index >= 0) artifacts.value.splice(index, 1, saved)
    if (artifactContent.value.artifact_type !== 'image') await loadLibrary()
    showNotice(
      artifactContent.value.artifact_type === 'image'
        ? 'Image changes saved'
        : `${artifactContent.value.artifact_type === 'article' ? 'Article' : 'Card'} saved to your library`,
    )
  } catch (error) {
    showNotice(errorMessage(error), 'error')
  } finally {
    saving.value = false
  }
}

async function deleteSelectedArtifact(): Promise<void> {
  if (!conversationId.value || !selectedArtifactId.value) return
  const artifactTitle = artifactContent.value?.title || 'Untitled artifact'
  const confirmed = await requestConfirmation(
    'Delete this artifact?',
    `“${artifactTitle}” will be permanently removed from this conversation. A linked library resource will also be deleted.`,
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
  saving.value = true
  try {
    const providerId = editingProviderId.value
    const isNew = providerId === null
    const saved = isNew
      ? await aiClient.createProvider(ai.value)
      : await aiClient.updateProvider(providerId, ai.value)
    providers.value = await aiClient.listProviders()
    selectedProviderId.value = saved.id
    selectProvider(saved)
    showNotice(isNew ? 'Provider added' : 'Provider settings saved')
  } catch (error) {
    showNotice(errorMessage(error), 'error')
  } finally {
    saving.value = false
  }
}

function selectProvider(provider: AIProvider): void {
  editingProviderId.value = provider.id
  selectedProviderId.value = provider.id
  ai.value = {
    name: provider.name,
    provider: provider.provider,
    model: provider.model,
    base_url: provider.base_url || '',
    api_key: '',
    temperature: provider.temperature,
    enabled: provider.enabled,
  }
}

function newProvider(): void {
  editingProviderId.value = null
  ai.value = { name: '', provider: 'openai-compatible', model: '', base_url: '', api_key: '', temperature: 0.2, enabled: true }
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
  if (next) selectProvider(next)
  else newProvider()
  showNotice('Provider removed')
}

async function addTag(): Promise<void> {
  if (!tagName.value.trim()) return
  saving.value = true
  try {
    await tagClient.create({ name: tagName.value.trim(), parent_id: tagParent.value })
    tagName.value = ''
    tags.value = await tagClient.list()
    showNotice('Tag added to your taxonomy')
  } catch (error) {
    showNotice(errorMessage(error), 'error')
  } finally {
    saving.value = false
  }
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', year: 'numeric' }).format(parseUtcTimestamp(value))
}

function formatDateTime(value: string): string {
  return new Intl.DateTimeFormat(undefined, {
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
  await loadInitialData()
  const persistedId = window.localStorage.getItem(activeSessionKey)
  if (persistedId) {
    try {
      applySession(await aiClient.getAgentSession(persistedId))
    } catch {
      window.localStorage.removeItem(activeSessionKey)
    }
  }
  await loadSessions(true)
}

onMounted(() => {
  window.addEventListener('keydown', handleShortcut)
  void initializeWorkspace()
})
onBeforeUnmount(() => {
  resolveConfirmation?.(false)
  activeStreamController.value?.abort()
  if (agentScrollFrame !== null) window.cancelAnimationFrame(agentScrollFrame)
  window.removeEventListener('keydown', handleShortcut)
  for (const timer of titleRefreshTimers) window.clearTimeout(timer)
})
</script>

<template>
  <div class="app-shell">
    <svg class="icon-library" aria-hidden="true">
      <symbol id="icon-cards" viewBox="0 0 24 24"><rect x="4" y="4" width="16" height="16" rx="3"/><path d="M8 9h8M8 13h5"/></symbol>
      <symbol id="icon-search" viewBox="0 0 24 24"><circle cx="11" cy="11" r="6.5"/><path d="m16 16 4 4"/></symbol>
      <symbol id="icon-add" viewBox="0 0 24 24"><path d="M12 5v14M5 12h14"/></symbol>
      <symbol id="icon-settings" viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path d="M19 13.5v-3l-2.1-.5a7 7 0 0 0-.7-1.7l1.1-1.8-2.1-2.1-1.8 1.1a7 7 0 0 0-1.7-.7L11.2 3h-3l-.5 2.1a7 7 0 0 0-1.7.7L4.2 4.7 2.1 6.8l1.1 1.8a7 7 0 0 0-.7 1.7L.5 10.8v3l2.1.5a7 7 0 0 0 .7 1.7l-1.1 1.8 2.1 2.1 1.8-1.1a7 7 0 0 0 1.7.7l.5 2.1h3l.5-2.1a7 7 0 0 0 1.7-.7l1.8 1.1 2.1-2.1-1.1-1.8a7 7 0 0 0 .7-1.7z" transform="translate(1.5 -0.25) scale(.88)"/></symbol>
      <symbol id="icon-spark" viewBox="0 0 24 24"><path d="m12 2 1.3 5.1L18 9l-4.7 1.9L12 16l-1.3-5.1L6 9l4.7-1.9zM19 15l.7 2.3L22 18l-2.3.7L19 21l-.7-2.3L16 18l2.3-.7z"/></symbol>
      <symbol id="icon-arrow" viewBox="0 0 24 24"><path d="M5 12h14m-5-5 5 5-5 5"/></symbol>
      <symbol id="icon-stop" viewBox="0 0 24 24"><rect x="7" y="7" width="10" height="10" rx="1.5"/></symbol>
      <symbol id="icon-check" viewBox="0 0 24 24"><path d="m5 12 4 4L19 6"/></symbol>
      <symbol id="icon-user" viewBox="0 0 24 24"><circle cx="12" cy="8" r="3.5"/><path d="M5.5 20c.6-4 2.8-6 6.5-6s5.9 2 6.5 6"/></symbol>
      <symbol id="icon-attachment" viewBox="0 0 24 24"><path d="m8.5 12.5 6.2-6.2a3 3 0 0 1 4.2 4.2l-8.1 8.1a5 5 0 0 1-7.1-7.1l8-8"/></symbol>
      <symbol id="icon-link" viewBox="0 0 24 24"><path d="M10 13a5 5 0 0 0 7.5.5l2-2a5 5 0 0 0-7-7l-1.1 1.1M14 11a5 5 0 0 0-7.5-.5l-2 2a5 5 0 0 0 7 7l1.1-1.1"/></symbol>
      <symbol id="icon-text" viewBox="0 0 24 24"><path d="M5 6h14M12 6v13M8 19h8"/></symbol>
      <symbol id="icon-trash" viewBox="0 0 24 24"><path d="M4 7h16M9 7V4h6v3m3 0-1 13H7L6 7m4 4v5m4-5v5"/></symbol>
      <symbol id="icon-edit" viewBox="0 0 24 24"><path d="m4 20 4.2-1 10.7-10.7a2.1 2.1 0 0 0-3-3L5.2 16zM14.7 6.5l3 3"/></symbol>
      <symbol id="icon-copy" viewBox="0 0 24 24"><rect x="8" y="8" width="11" height="11" rx="2"/><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/></symbol>
    </svg>

    <aside class="sidebar">
      <button class="brand" type="button" aria-label="Open library" @click="navigate('library')">
        <span class="brand-mark"><img src="/logo.png" alt="" /></span>
        <span><strong>Commonplace</strong><small>Knowledge cards</small></span>
      </button>

      <nav class="primary-nav" aria-label="Main navigation">
        <button :class="{ active: view === 'new' }" type="button" @click="navigate('new')">
          <svg><use href="#icon-spark" /></svg><span>AI workspace</span>
        </button>
        <button :class="{ active: view === 'library' && selectedTag === null }" type="button" @click="navigate('library')">
          <svg><use href="#icon-cards" /></svg><span>Library</span><small>{{ libraryItems.length }}</small>
        </button>
        <button :class="{ active: view === 'search' }" type="button" @click="openSearch">
          <svg><use href="#icon-search" /></svg><span>Search</span><kbd>⌘ K</kbd>
        </button>
      </nav>

      <div v-if="view === 'new'" class="sidebar-section session-section">
        <div class="sidebar-heading"><span>Conversations</span><button type="button" aria-label="Start a new session" @click="resetWorkspace"><svg><use href="#icon-add" /></svg></button></div>
        <div class="session-history-list">
          <div v-for="session in visibleSessions" :key="session.id" class="session-history-item" :class="{ active: conversationId === session.id }">
            <form v-if="editingSessionId === session.id" class="session-title-editor" @submit.prevent="saveSessionTitle(session.id)">
              <input v-model="sessionTitleDraft" maxlength="100" aria-label="Conversation title" autofocus @keydown.esc.prevent="cancelSessionTitleEdit" />
              <button type="submit" aria-label="Save title">Save</button>
              <button type="button" aria-label="Cancel title edit" @click="cancelSessionTitleEdit">Cancel</button>
            </form>
            <button v-else class="session-open-button" type="button" @click="openSession(session.id)">
              <span><strong title="Click to rename" @click.stop="startSessionTitleEdit(session)">{{ session.title || 'New conversation' }}</strong><small>{{ formatDateTime(session.created_at) }}</small></span>
              <small>{{ session.message_count }}</small>
            </button>
            <button v-if="editingSessionId !== session.id" class="session-delete-button" type="button" :aria-label="`Delete ${session.title || 'conversation'}`" title="Delete conversation" @click.stop="deleteSession(session)"><svg><use href="#icon-trash" /></svg></button>
          </div>
          <p v-if="!visibleSessions.length && !sessionsLoading" class="sidebar-empty">No previous conversations.</p>
          <button v-if="sessionsHaveMore" class="load-more-sessions" :disabled="sessionsLoading" type="button" @click="loadSessions()">{{ sessionsLoading ? 'Loading…' : 'Load more' }}</button>
        </div>
      </div>

      <div v-else class="sidebar-section">
        <div class="sidebar-heading"><span>Collections</span><button type="button" aria-label="Add tag" @click="navigate('settings')"><svg><use href="#icon-add" /></svg></button></div>
        <div class="tag-list">
          <button
            v-for="tag in flatTags"
            :key="tag.id"
            :class="{ active: selectedTag === tag.id && view === 'library' }"
            :style="{ '--tag-depth': tag.depth }"
            type="button"
            @click="filterByTag(tag.id)"
          >
            <span class="tag-dot" :style="tag.color ? { background: tag.color } : undefined" />
            <span class="tag-label">{{ tag.name }}</span><small>{{ tag.card_count }}</small>
          </button>
          <p v-if="!flatTags.length" class="sidebar-empty">Tags will appear here.</p>
        </div>
      </div>

      <div class="sidebar-footer">
        <button :class="{ active: view === 'settings' }" type="button" @click="navigate('settings')">
          <svg><use href="#icon-settings" /></svg><span>Settings</span>
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
      <LibraryEditor v-if="libraryEditorItem" :item="libraryEditorItem" :saving="libraryEditorSaving" @close="closeLibraryEditor" @save="saveLibraryEditor" />

      <template v-if="view === 'library' || view === 'search'">
        <header class="topbar">
          <form class="search-field" role="search" @submit.prevent="search">
            <svg><use href="#icon-search" /></svg>
            <input ref="searchInput" v-model="query" aria-label="Search library" placeholder="Search cards, articles, and sources" />
            <button v-if="query" type="button" aria-label="Clear search" @click="query = ''; search()">×</button>
            <kbd v-else>⌘ K</kbd>
          </form>
          <button class="primary-action" type="button" @click="navigate('new')"><svg><use href="#icon-add" /></svg>New card</button>
        </header>

        <section class="content library-view">
          <div class="page-heading">
            <div><p class="eyebrow">Your knowledge</p><h1>{{ pageTitle }}</h1><p>{{ pageDescription }}</p></div>
            <button v-if="selectedTag !== null" class="text-button" type="button" @click="filterByTag(null)">Clear filter</button>
          </div>

          <div v-if="libraryLoading" class="card-grid" aria-label="Loading library">
            <div v-for="index in 6" :key="index" class="card skeleton" />
          </div>
          <div v-else-if="libraryItems.length" class="card-grid">
            <article v-for="item in libraryItems" :key="`${item.item_type}-${item.id}`" class="card" :class="`library-${item.item_type}`" role="button" tabindex="0" :aria-label="`Open ${item.title}`" @click="openLibraryItem(item)" @keydown.enter="openLibraryItem(item)" @keydown.space.prevent="openLibraryItem(item)">
              <div class="card-topline">
                <span class="card-type">{{ item.item_type === 'article' ? 'article' : item.card_type }}</span>
                <div class="card-topline-actions">
                  <time>{{ formatDate(item.updated_at) }}</time>
                  <button class="card-action-button" type="button" :aria-label="`Edit ${item.title}`" title="Edit and preview" @click.stop="openLibraryEditor(item)" @keydown.stop>
                    <svg><use href="#icon-edit" /></svg>
                  </button>
                  <button class="card-action-button" type="button" :aria-label="`Copy ID for ${item.title}`" title="Copy resource ID" @click.stop="copyLibraryItemId(item)" @keydown.stop>
                    <svg><use href="#icon-copy" /></svg>
                  </button>
                  <button class="card-action-button danger" :disabled="deletingLibraryItemId !== null" type="button" :aria-label="`Delete ${item.title}`" :title="deletingLibraryItemId === item.id ? 'Deleting…' : `Delete ${item.item_type}`" @click.stop="deleteLibraryItem(item)" @keydown.stop>
                    <svg><use href="#icon-trash" /></svg>
                  </button>
                </div>
              </div>
              <h2>{{ item.title }}</h2>
              <p v-if="item.item_type === 'article' && item.subtitle" class="library-article-subtitle">{{ item.subtitle }}</p>
              <MarkdownContent class="card-excerpt" :content="item.summary || item.content" />
              <div class="card-footer">
                <div class="card-tags"><span v-for="path in item.tag_paths.slice(0, 3)" :key="path">{{ path }}</span></div>
                <svg><use href="#icon-arrow" /></svg>
              </div>
            </article>
          </div>
          <div v-else class="empty-state">
            <span class="empty-icon"><svg><use :href="view === 'search' ? '#icon-search' : '#icon-cards'" /></svg></span>
            <h2>{{ view === 'search' ? 'Nothing found' : 'Your library is ready' }}</h2>
            <p>{{ view === 'search' ? 'Try a different phrase or browse your collections.' : 'Capture a thought and let AI shape it into a useful card or article.' }}</p>
            <button class="primary-action" type="button" @click="view === 'search' ? navigate('library') : navigate('new')">
              {{ view === 'search' ? 'Browse library' : 'Create your first card' }}
            </button>
          </div>
        </section>
      </template>

      <template v-else-if="view === 'new'">
        <header class="topbar compact chat-topbar">
          <div class="chat-topbar-title"><span class="status-dot online" /><span>AI workspace</span></div>
          <button class="close-button" type="button" aria-label="Close" @click="navigate('library')">×</button>
        </header>
        <section class="content create-view">
          <div class="agent-workspace" @paste="pasteAssets">
            <aside class="assets-pane" aria-label="Session assets" tabindex="0">
              <header class="assets-header">
                <div><strong>Assets</strong><small>Session resources</small></div>
                <div class="assets-header-actions">
                  <button type="button" title="Add text note" aria-label="Add text note" @click="showAssetEditor('text')"><svg><use href="#icon-text" /></svg></button>
                  <button type="button" title="Add link" aria-label="Add link" @click="showAssetEditor('link')"><svg><use href="#icon-link" /></svg></button>
                  <button type="button" title="Upload files" aria-label="Upload files" @click="assetFileInput?.click()"><svg><use href="#icon-attachment" /></svg></button>
                </div>
              </header>

              <div class="assets-search">
                <svg><use href="#icon-search" /></svg>
                <input v-model="assetQuery" type="search" placeholder="Search assets" aria-label="Search assets" />
              </div>

              <div class="asset-filter-list" aria-label="Asset type">
                <button v-for="filter in assetFilters" :key="filter.value" :class="{ active: assetFilter === filter.value }" type="button" @click="assetFilter = filter.value">{{ filter.label }}</button>
              </div>

              <div class="asset-list-heading">
                <span>{{ filteredAssets.length }} {{ filteredAssets.length === 1 ? 'asset' : 'assets' }}</span>
                <small>Newest</small>
              </div>

              <form v-if="assetEditorMode !== 'closed'" class="asset-editor" @submit.prevent="addInlineAsset">
                <strong>{{ assetEditorMode === 'link' ? 'Add a link' : 'Add a note' }}</strong>
                <input v-model="assetName" :placeholder="assetEditorMode === 'link' ? 'Link name' : 'Note name'" />
                <textarea v-model="assetValue" :placeholder="assetEditorMode === 'link' ? 'https://…' : 'Text content'" rows="3" />
                <div><button :disabled="assetUploading || !assetName.trim() || !assetValue.trim()" type="submit">Add asset</button><button type="button" @click="assetEditorMode = 'closed'">Cancel</button></div>
              </form>

              <div class="asset-browser-list">
                <article v-for="asset in filteredAssets" :key="asset.id" class="asset-row">
                  <button class="asset-row-main" type="button" @click="openAsset(asset)">
                    <span class="asset-thumbnail" :class="classifyAsset(asset)">
                      <img v-if="asset.asset_type === 'image' && asset.content_url" :src="asset.content_url" alt="" />
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
                </article>
                <div v-if="!filteredAssets.length" class="asset-empty">
                  <svg><use :href="assets.length ? '#icon-search' : '#icon-attachment'" /></svg>
                  <strong>{{ assets.length ? 'No matching assets' : 'No assets yet' }}</strong>
                  <small>{{ assets.length ? 'Try another search or filter.' : 'Add reference material for this conversation.' }}</small>
                </div>
              </div>

              <button class="asset-drop-zone" :class="{ dragging: assetDragging }" type="button" @click="assetFileInput?.click()" @dragenter.prevent="assetDragging = true" @dragover.prevent="assetDragging = true" @dragleave.prevent="assetDragging = false" @drop.prevent="dropAssets">
                <svg><use href="#icon-attachment" /></svg>
                <strong>{{ assetUploading ? 'Uploading…' : 'Drop or paste assets here' }}</strong>
                <small>Click this area, then press Ctrl/⌘ + V</small>
              </button>
              <input ref="assetFileInput" type="file" multiple hidden @change="uploadAssets" />
            </aside>

            <section class="agent-chat" aria-label="Knowledge card conversation">
              <div class="agent-chat-header">
                <div class="agent-identity"><img src="/logo.png" alt="" /><div><strong>Zett Agent</strong><small>Turn a conversation into knowledge</small></div></div>
                <span class="streaming-status"><i />Zett Agent online</span>
              </div>

              <div ref="agentThread" class="agent-thread" :class="{ empty: !conversationStarted }" aria-live="polite" @scroll.passive="handleAgentThreadScroll">
                <div v-if="!conversationStarted" class="agent-welcome">
                  <span class="feature-icon"><svg><use href="#icon-spark" /></svg></span>
                  <h2>What should we remember?</h2>
                  <p>Share a rough thought, excerpt, or question. You can refine the result through conversation before saving it.</p>
                  <div class="prompt-hints"><button type="button" @click="raw = 'I have an idea: '">Capture an idea</button><button type="button" @click="raw = 'Key point from what I just read: '">Summarize a note</button></div>
                </div>
                <template v-else>
                  <div class="message user-message">
                    <div class="message-profile user-profile" aria-hidden="true"><svg><use href="#icon-user" /></svg></div>
                    <div class="message-body">
                      <div class="message-author"><strong>You</strong><small>Personal workspace</small></div>
                      <MarkdownContent class="message-content" :content="raw" />
                    </div>
                  </div>
                  <div v-for="(message, index) in conversation" :key="index" class="message" :class="`${message.role}-message`">
                    <div class="message-profile" :class="message.role === 'assistant' ? 'agent-profile' : 'user-profile'" aria-hidden="true">
                      <img v-if="message.role === 'assistant'" src="/logo.png" alt="" />
                      <svg v-else><use href="#icon-user" /></svg>
                    </div>
                    <div class="message-body">
                      <div class="message-author"><strong>{{ message.role === 'assistant' ? 'Zett Agent' : 'You' }}</strong><small>{{ message.role === 'assistant' ? 'Knowledge assistant' : 'Personal workspace' }}</small></div>
                      <div class="agent-event-timeline">
                        <template v-for="entry in historicalTimeline(message)" :key="entry.id">
                          <details v-if="entry.type === 'reasoning'" class="reasoning-panel">
                            <summary><span>Reasoning</span><small>Show process</small></summary>
                            <MarkdownContent class="reasoning-content" :content="entry.content" />
                          </details>
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
                              <div><strong>{{ entry.activity.error_message ? 'Error' : 'Result' }}</strong><pre :class="{ error: entry.activity.error_message }">{{ entry.activity.error_message || formatToolValue(entry.activity.output) }}</pre></div>
                            </div>
                          </details>
                          <MarkdownContent v-else class="message-content" :content="entry.content" />
                        </template>
                      </div>
                    </div>
                  </div>
                  <div v-if="loading && streamingResponseVisible" class="message assistant-message streaming-message">
                    <div class="message-profile agent-profile" aria-hidden="true"><img src="/logo.png" alt="" /></div>
                    <div class="message-body">
                      <div class="message-author"><strong>Zett Agent</strong><small class="live-agent-state"><i />{{ streamingStatus.replaceAll('_', ' ') }}</small></div>
                      <div v-if="streamingTimeline.length" class="agent-event-timeline">
                        <template v-for="(entry, entryIndex) in streamingTimeline" :key="entry.id">
                          <details v-if="entry.type === 'reasoning'" class="reasoning-panel streaming-reasoning" :open="entryIndex === streamingTimeline.length - 1">
                            <summary><span>Reasoning</span><small>{{ entryIndex === streamingTimeline.length - 1 ? 'Streaming' : 'Show process' }}</small></summary>
                            <MarkdownContent class="reasoning-content" :content="entry.content" />
                          </details>
                          <details v-else-if="entry.type === 'compaction'" class="reasoning-panel compaction-panel" :open="entry.activity.state !== 'completed'">
                            <summary><span>Context compaction</span><small>{{ entry.activity.state === 'completed' ? 'Completed' : 'Streaming' }}</small></summary>
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
                              <div><strong>{{ entry.activity.error_message ? 'Error' : 'Result' }}</strong><pre :class="{ error: entry.activity.error_message }">{{ entry.activity.error_message || formatToolValue(entry.activity.output) }}</pre></div>
                            </div>
                          </details>
                          <MarkdownContent v-else class="message-content" :content="entry.content" />
                        </template>
                        <span v-if="streamingMessage" class="streaming-dots compact" aria-label="Generating"><i /><i /><i /></span>
                      </div>
                      <p v-else class="stream-waiting"><i /><i /><i /></p>
                    </div>
                  </div>
                </template>
              </div>

              <form class="agent-input" @submit.prevent="submitConversation">
                <textarea v-if="!conversationStarted" v-model="raw" rows="3" autofocus placeholder="Message Zett Agent…" @keydown.enter.exact="handleComposerEnter" />
                <textarea v-else v-model="followUp" rows="3" placeholder="Continue the conversation…" @keydown.enter.exact="handleComposerEnter" />
                <div class="agent-input-footer">
                  <div class="composer-controls">
                    <label class="composer-select model-select">
                      <svg><use href="#icon-spark" /></svg>
                      <select v-if="providers.some((provider) => provider.enabled)" v-model.number="selectedProviderId" :disabled="loading" aria-label="Model">
                        <option v-for="provider in providers.filter((item) => item.enabled)" :key="provider.id" :value="provider.id">{{ provider.model }}</option>
                      </select>
                      <button v-else type="button" @click="navigate('settings')">Add provider</button>
                    </label>
                    <label class="composer-select reasoning-select">
                      <select v-model="reasoningEffort" :disabled="loading" aria-label="Reasoning effort">
                        <option value="off">off</option>
                        <option value="low">low</option>
                        <option value="medium">medium</option>
                        <option value="high">high</option>
                      </select>
                    </label>
                    <div class="composer-telemetry" aria-label="Session telemetry">
                      <span title="Total tokens used in this session"><small>Tokens</small><strong>{{ sessionTelemetry.totalTokens.toLocaleString() }}</strong></span>
                      <span title="Share of session input tokens served from provider cache"><small>Cache</small><strong>{{ sessionCacheHitRate === null ? '—' : `${(sessionCacheHitRate * 100).toFixed(1)}%` }}</strong></span>
                      <span title="Current speed while generating, otherwise the session average"><small>Speed</small><strong>{{ sessionTelemetry.outputTokensPerSecond == null ? '—' : `${sessionTelemetry.outputTokensPerSecond.toFixed(1)} tok/s` }}</strong></span>
                    </div>
                  </div>
                  <div class="composer-submit"><small>{{ loading ? 'Enter for a new line' : 'Enter to send' }}</small><button class="send-button" :class="{ stop: loading }" :disabled="!loading && (conversationStarted ? !followUp.trim() : !raw.trim())" type="button" :aria-label="loading ? 'Stop generating' : 'Send message'" @click="loading ? stopGeneration() : submitConversation()"><svg><use :href="loading ? '#icon-stop' : '#icon-arrow'" /></svg></button></div>
                </div>
              </form>
            </section>

            <aside class="artifact-pane artifact-workspace">
              <header class="artifact-collection-header">
                <div><strong>Artifacts</strong><small>{{ artifacts.length }} in this conversation</small></div>
                <span v-if="loading" class="artifact-syncing"><i />Updating</span>
              </header>
              <div v-if="artifacts.length" class="artifact-list" aria-label="Conversation artifacts">
                <button v-for="artifact in artifacts" :key="artifact.id" :class="{ active: artifact.id === selectedArtifactId }" type="button" @click="selectArtifact(artifact)">
                  <span class="artifact-kind-icon">{{ artifact.artifact_type === 'card' ? '◇' : artifact.artifact_type === 'article' ? '¶' : '▧' }}</span>
                  <span><strong>{{ artifact.content.title }}</strong><small>{{ artifact.artifact_type }} · v{{ artifact.version }} · {{ artifact.status }}</small></span>
                </button>
              </div>
              <div v-if="!artifactContent" class="artifact-placeholder">
                <span><svg><use href="#icon-cards" /></svg></span>
                <h2>No artifacts yet</h2>
                <p>Keep talking with Zett Agent. Cards, articles, and images will appear here when the conversation produces them.</p>
              </div>
              <div v-else class="artifact-panel artifact-editor">
                <div class="artifact-editor-accent" />
                <header class="artifact-editor-header">
                  <div class="artifact-state"><i :class="{ saved: selectedArtifact?.status === 'saved' }" /><span><strong>{{ selectedArtifact?.artifact_type }} artifact</strong><small>{{ selectedArtifact?.status }} · version {{ selectedArtifact?.version }}</small></span></div>
                  <div class="artifact-mode-switch" aria-label="Artifact display mode"><button type="button" :class="{ active: !artifactPreview }" @click="artifactPreview = false">Edit</button><button type="button" :class="{ active: artifactPreview }" @click="artifactPreview = true">Preview</button></div>
                </header>
                <div class="artifact-editor-body">
                  <div v-if="artifactContent.artifact_type === 'card'" class="card-meta-row">
                    <div class="card-type-control">
                      <span>Card type</span>
                      <div class="card-type-options" role="group" aria-label="Card type">
                        <button v-for="cardType in cardTypes" :key="cardType" :class="{ active: artifactContent.card_type === cardType }" type="button" @click="artifactContent.card_type = cardType">{{ cardType }}</button>
                      </div>
                    </div>
                  </div>
                  <template v-if="!artifactPreview">
                    <label class="card-title-control"><span>Title</span><textarea v-model="artifactContent.title" rows="2" /></label>
                    <label v-if="artifactContent.artifact_type === 'article'" class="card-summary-control"><span>Subtitle</span><textarea v-model="artifactContent.subtitle" rows="2" placeholder="Optional article subtitle" /></label>
                    <label class="card-summary-control"><span>{{ artifactContent.artifact_type === 'image' ? 'Caption' : 'Summary' }}</span><textarea v-model="artifactContent.summary" rows="3" /></label>
                    <label v-if="artifactContent.artifact_type === 'image'" class="card-content-control"><span>Image prompt</span><textarea v-model="artifactContent.prompt" placeholder="Creative direction or generation prompt" /></label>
                    <label v-if="artifactContent.artifact_type === 'image'" class="card-summary-control"><span>Alt text</span><textarea v-model="artifactContent.alt_text" rows="3" /></label>
                    <label v-if="artifactContent.artifact_type === 'image'" class="card-summary-control"><span>Source URL</span><textarea v-model="artifactContent.source_url" rows="2" placeholder="https://…" /></label>
                    <label v-else class="card-content-control"><span>{{ artifactContent.artifact_type === 'article' ? 'Article' : 'Knowledge' }} · Markdown</span><textarea v-model="artifactContent.content" /></label>
                  </template>
                  <article v-else class="artifact-preview" :class="`artifact-preview-${artifactContent.artifact_type}`">
                    <span class="artifact-preview-label">{{ artifactContent.artifact_type }}</span>
                    <h1>{{ artifactContent.title }}</h1>
                    <p v-if="artifactContent.artifact_type === 'article' && artifactContent.subtitle" class="article-subtitle">{{ artifactContent.subtitle }}</p>
                    <img v-if="artifactContent.artifact_type === 'image' && selectedImageUrl" :src="selectedImageUrl" :alt="artifactContent.alt_text" />
                    <div v-else-if="artifactContent.artifact_type === 'image'" class="image-brief-placeholder"><span>Image brief</span><p>{{ artifactContent.prompt || 'Waiting for an image source or generation step.' }}</p></div>
                    <MarkdownContent v-if="artifactContent.summary" class="preview-summary" :content="artifactContent.summary" />
                    <div v-if="artifactContent.artifact_type !== 'image'" class="preview-divider" />
                    <MarkdownContent v-if="artifactContent.artifact_type !== 'image'" class="preview-content" :content="artifactContent.content" />
                  </article>
                  <div v-if="artifactContent.suggested_tags.length" class="suggestions card-tags-editor"><span>Classification</span><div class="suggestion-list"><label v-for="tag in artifactContent.suggested_tags" :key="tag.path" :class="{ selected: selectedSuggestions.includes(tag.path) }"><input v-model="selectedSuggestions" type="checkbox" :value="tag.path" /><span>{{ tag.path }}</span><small>{{ Math.round(tag.confidence * 100) }}%</small></label></div></div>
                </div>
                <footer class="panel-actions artifact-editor-actions"><button class="danger-button" type="button" @click="deleteSelectedArtifact">Delete</button><button class="primary-action" :disabled="saving || !artifactContent.title.trim()" type="button" @click="saveSelectedArtifact">{{ saving ? 'Saving…' : artifactContent.artifact_type === 'card' ? selectedArtifact?.status === 'saved' ? 'Update library card' : 'Save to library' : artifactContent.artifact_type === 'article' ? selectedArtifact?.status === 'saved' ? 'Update library article' : 'Save to library' : 'Save changes' }}<svg><use href="#icon-arrow" /></svg></button></footer>
              </div>
            </aside>
          </div>
        </section>
      </template>

      <template v-else>
        <header class="topbar compact"><div><p class="eyebrow">Preferences</p><h1>Settings</h1></div></header>
        <section class="content settings-view">
          <div class="settings-intro"><div><h2>AI providers</h2><p>Keep multiple model connections and choose one for each conversation.</p></div><button class="secondary-action" type="button" @click="newProvider"><svg><use href="#icon-add" /></svg>New provider</button></div>
          <div v-if="providers.length" class="provider-list">
            <button v-for="provider in providers" :key="provider.id" :class="{ active: editingProviderId === provider.id }" type="button" @click="selectProvider(provider)"><span class="status-dot" :class="{ online: provider.enabled }" /><span><strong>{{ provider.name }}</strong><small>{{ provider.provider }} · {{ provider.model }}</small></span></button>
          </div>
          <form class="settings-card" @submit.prevent="saveAI">
            <div class="form-grid">
              <label class="field"><span>Connection name</span><input v-model="ai.name" placeholder="e.g. Fast OpenAI" /><small>Shown in the conversation provider picker.</small></label>
              <label class="field"><span>Provider</span><select v-model="ai.provider"><option value="openai-compatible">OpenAI compatible</option><option value="openai">OpenAI</option><option value="anthropic">Anthropic</option><option value="gemini">Gemini</option><option value="ollama">Ollama</option></select><small>The API format used for model requests.</small></label>
              <label class="field"><span>Model</span><input v-model="ai.model" placeholder="e.g. gpt-4.1-mini" /><small>Use the exact model identifier from your provider.</small></label>
              <label class="field full"><span>Base URL <em>Optional</em></span><input v-model="ai.base_url" placeholder="https://api.example.com/v1" /><small>Only needed for compatible APIs or a local Ollama instance.</small></label>
              <label class="field full"><span>API key</span><input v-model="ai.api_key" type="password" autocomplete="new-password" placeholder="Leave blank to keep the saved key" /><small>Your key is encrypted locally and never returned by the API.</small></label>
              <label class="field temperature-field"><span>Temperature <output>{{ ai.temperature.toFixed(1) }}</output></span><input v-model.number="ai.temperature" type="range" min="0" max="2" step="0.1" /></label>
            </div>
            <div class="settings-actions"><button v-if="editingProviderId !== null" class="danger-button" type="button" @click="removeProvider">Delete provider</button><span v-else>Credentials are encrypted in your local database.</span><div><label class="switch"><input v-model="ai.enabled" type="checkbox" /><span /><small>{{ ai.enabled ? 'Enabled' : 'Disabled' }}</small></label><button class="primary-action" :disabled="saving || !ai.name || !ai.model" type="submit">{{ saving ? 'Saving…' : editingProviderId === null ? 'Add provider' : 'Save provider' }}</button></div></div>
          </form>

          <div class="settings-intro taxonomy-heading"><div><h2>Tag taxonomy</h2><p>Add a root tag or nest one beneath any existing collection.</p></div></div>
          <form class="settings-card taxonomy-form" @submit.prevent="addTag">
            <label class="field"><span>Tag name</span><input v-model="tagName" placeholder="e.g. Distributed systems" /></label>
            <label class="field"><span>Parent</span><select v-model="tagParent"><option :value="null">No parent — root tag</option><option v-for="tag in flatTags" :key="tag.id" :value="tag.id">{{ '— '.repeat(tag.depth) }}{{ tag.path }}</option></select></label>
            <button class="primary-action" :disabled="saving || !tagName.trim()" type="submit"><svg><use href="#icon-add" /></svg>Add tag</button>
          </form>
        </section>
      </template>

      <Transition name="sheet">
        <div v-if="selectedLibraryItem" class="detail-backdrop" @click.self="selectedLibraryItem = null">
          <aside class="detail-sheet" role="dialog" aria-modal="true" :aria-label="selectedLibraryItem.title">
            <header class="detail-header">
              <div><span class="card-type">{{ selectedLibraryItem.item_type === 'article' ? 'article' : selectedLibraryItem.card_type }}</span></div>
              <div class="detail-header-actions">
                <button class="detail-header-button" type="button" @click="copyLibraryItemId(selectedLibraryItem)"><svg><use href="#icon-copy" /></svg>Copy ID</button>
                <button class="detail-header-button" type="button" @click="openLibraryEditor(selectedLibraryItem)"><svg><use href="#icon-edit" /></svg>Edit</button>
                <button class="detail-delete-button" :disabled="deletingLibraryItemId !== null" type="button" @click="deleteSelectedLibraryItem"><svg><use href="#icon-trash" /></svg>Delete</button>
                <button class="close-button" type="button" aria-label="Close resource details" @click="selectedLibraryItem = null">×</button>
              </div>
            </header>
            <div class="detail-content">
              <h1>{{ selectedLibraryItem.title }}</h1>
              <p v-if="selectedLibraryItem.item_type === 'article' && selectedLibraryItem.subtitle" class="detail-subtitle">{{ selectedLibraryItem.subtitle }}</p>
              <MarkdownContent v-if="selectedLibraryItem.summary" class="detail-summary" :content="selectedLibraryItem.summary" />
              <div v-if="selectedLibraryItem.tag_paths.length" class="detail-tags"><span v-for="path in selectedLibraryItem.tag_paths" :key="path">{{ path }}</span></div>

              <section class="detail-section"><h2>{{ selectedLibraryItem.item_type === 'article' ? 'Article' : 'Content' }}</h2><MarkdownContent class="detail-body" :content="selectedLibraryItem.content" /></section>
              <section v-if="selectedLibraryItem.source" class="detail-section"><h2>Source</h2><p>{{ selectedLibraryItem.source }}</p></section>
              <section v-if="selectedLibraryItem.raw_content" class="detail-section raw-section"><h2>Original input</h2><div class="detail-body">{{ selectedLibraryItem.raw_content }}</div></section>

              <dl class="detail-metadata">
                <div><dt>Type</dt><dd>{{ selectedLibraryItem.item_type }}</dd></div>
                <div><dt>Status</dt><dd>{{ selectedLibraryItem.status }}</dd></div>
                <div><dt>Created</dt><dd>{{ formatDateTime(selectedLibraryItem.created_at) }}</dd></div>
                <div><dt>Updated</dt><dd>{{ formatDateTime(selectedLibraryItem.updated_at) }}</dd></div>
                <div><dt>Resource ID</dt><dd>{{ selectedLibraryItem.id }}</dd></div>
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
.sidebar { position: sticky; top: 0; height: 100vh; display: flex; flex-direction: column; padding: 1.25rem 0.85rem 0.9rem; overflow: hidden; background: var(--sidebar); border-right: 1px solid rgba(255, 255, 255, 0.62); box-shadow: inset -1px 0 rgba(29, 29, 31, 0.06); backdrop-filter: blur(28px) saturate(150%); -webkit-backdrop-filter: blur(28px) saturate(150%); z-index: 10; }
.brand { display: flex; align-items: center; gap: 0.72rem; width: 100%; padding: 0.35rem 0.55rem 1.35rem; border: 0; background: transparent; color: var(--text); text-align: left; cursor: pointer; }
.brand-mark { display: grid; place-items: center; width: 2.15rem; height: 2.15rem; flex: 0 0 auto; }
.brand-mark img { display: block; width: 100%; height: 100%; object-fit: contain; filter: drop-shadow(0 4px 5px rgba(53, 83, 67, 0.18)); }
.brand strong, .brand small { display: block; }
.brand strong { font-size: 0.94rem; line-height: 1.2; letter-spacing: -0.012em; }
.brand small { margin-top: 0.12rem; color: var(--secondary); font-size: 0.69rem; letter-spacing: 0.01em; }
.primary-nav { display: grid; gap: 0.18rem; }
.primary-nav button, .sidebar-footer button, .tag-list button { position: relative; display: flex; align-items: center; width: 100%; border: 0; color: #3b3b3e; background: transparent; cursor: pointer; text-align: left; }
.primary-nav button, .sidebar-footer button { gap: 0.7rem; min-height: 2.35rem; padding: 0 0.7rem; border-radius: 0.62rem; font-size: 0.83rem; font-weight: 530; }
.primary-nav button:hover, .sidebar-footer button:hover, .tag-list button:hover { background: rgba(255, 255, 255, 0.48); }
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
.tag-list button { gap: 0.58rem; height: 2rem; padding: 0 0.55rem 0 calc(0.7rem + var(--tag-depth) * 0.72rem); border-radius: 0.5rem; font-size: 0.77rem; }
.tag-list button.active { color: var(--accent-dark); background: rgba(255,255,255,.64); font-weight: 600; }
.tag-dot { width: .42rem; height: .42rem; flex: 0 0 auto; border-radius: 50%; background: #91a89b; box-shadow: inset 0 0 0 1px rgba(0,0,0,.06); }
.tag-label { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.tag-list small { margin-left: auto; color: #98989d; font-size: .66rem; }
.session-section { overflow: hidden; }
.session-history-list { min-height: 0; display: grid; flex: 1; align-content: start; gap: .18rem; overflow-y: auto; padding-bottom: .7rem; scrollbar-width: thin; }
.session-history-item { position: relative; min-width: 0; border-radius: .58rem; }
.session-history-item:hover { background: rgba(255,255,255,.5); }
.session-history-item.active { background: rgba(255,255,255,.86); box-shadow: 0 1px 5px rgba(0,0,0,.05); }
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
.load-more-sessions { min-height: 2rem; margin: .25rem .45rem 0; border: 1px solid var(--line); border-radius: .55rem; color: var(--accent-dark); background: rgba(255,255,255,.5); cursor: pointer; font-size: .65rem; font-weight: 620; }
.load-more-sessions:disabled { opacity: .55; cursor: wait; }
.sidebar-empty { padding: .55rem; color: var(--tertiary); font-size: .72rem; }
.sidebar-footer { padding-top: .65rem; border-top: 1px solid rgba(29,29,31,.07); }
.status-dot { margin-left: auto; width: .43rem; height: .43rem; border-radius: 50%; background: #aaa; box-shadow: 0 0 0 3px rgba(0,0,0,.03); }
.status-dot.online { background: #49a369; box-shadow: 0 0 0 3px rgba(73,163,105,.12); }

.workspace { min-width: 0; min-height: 100vh; }
.topbar { position: sticky; top: 0; z-index: 8; min-height: 5rem; display: flex; align-items: center; gap: 1rem; padding: 1rem clamp(1.5rem, 4vw, 4rem); background: rgba(245,245,247,.72); backdrop-filter: blur(22px) saturate(160%); -webkit-backdrop-filter: blur(22px) saturate(160%); }
.topbar::after { content: ""; position: absolute; left: 0; right: 0; bottom: -0.8rem; height: .8rem; background: linear-gradient(rgba(245,245,247,.55), transparent); pointer-events: none; }
.topbar.compact { justify-content: space-between; }
.topbar.compact h1 { margin: .1rem 0 0; font-size: 1.45rem; }
.chat-topbar { min-height: 4.5rem; }
.chat-topbar-title { display: flex; align-items: center; gap: .55rem; color: var(--secondary); font-size: .75rem; font-weight: 620; }
.chat-topbar-title .status-dot { margin-left: 0; }
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
.secondary-action { min-height: 2.55rem; padding: 0 1rem; border-radius: .72rem; color: #55555a; background: #efeff1; font-size: .8rem; font-weight: 560; }
.text-button { color: var(--accent-dark); background: transparent; font-size: .8rem; font-weight: 560; }
.close-button { width: 2rem; height: 2rem; border-radius: 50%; color: #606065; background: rgba(224,224,227,.78); font-size: 1.2rem; line-height: 1; }

.content { width: min(100%, 76rem); margin: 0 auto; padding: 2.15rem clamp(1.5rem, 4vw, 4rem) 5rem; }
.library-view { width: min(100%, 84rem); }
.page-heading { display: flex; align-items: end; justify-content: space-between; gap: 1rem; margin-bottom: 1.75rem; }
.eyebrow { margin: 0; color: var(--accent); font-size: .67rem; font-weight: 700; letter-spacing: .075em; text-transform: uppercase; }
.page-heading h1 { margin: .35rem 0 .3rem; font-size: clamp(1.85rem, 3vw, 2.45rem); line-height: 1.06; letter-spacing: -.032em; }
.page-heading p:last-child, .settings-intro p, .editor-intro p { margin: 0; color: var(--secondary); font-size: .82rem; line-height: 1.55; }
.card-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 17rem), 1fr)); gap: 1rem; }
.card { min-height: 15.8rem; display: flex; flex-direction: column; padding: 1.25rem 1.25rem 1rem; overflow: hidden; border: 1px solid rgba(29,29,31,.075); border-radius: 1rem; background: var(--surface); box-shadow: 0 1px 2px rgba(0,0,0,.025); backdrop-filter: blur(14px); transition: transform 260ms cubic-bezier(.2,.8,.2,1), box-shadow 260ms cubic-bezier(.2,.8,.2,1), background 180ms ease; }
.card[role="button"] { cursor: pointer; }
.card:hover { transform: translateY(-3px); background: rgba(255,255,255,.96); box-shadow: var(--shadow); }
.card:active { transform: scale(.985); transition-duration: 100ms; }
.card-topline { display: flex; align-items: center; justify-content: space-between; }
.card-topline-actions { display: flex; align-items: center; gap: .16rem; }
.card-topline-actions time { margin-right: .25rem; }
.card-action-button { display: grid; place-items: center; width: 1.75rem; height: 1.75rem; padding: 0; border: 0; border-radius: .5rem; color: #8b918d; background: transparent; cursor: pointer; transition: color 160ms ease, background 160ms ease, transform 160ms ease; }
.card-action-button:hover, .card-action-button:focus-visible { color: #365845; background: #e9f0ec; outline: none; transform: scale(1.04); }
.card-action-button.danger:hover, .card-action-button.danger:focus-visible { color: #a33e3e; background: #f8eded; }
.card-action-button:disabled { opacity: .4; cursor: wait; transform: none; }
.card-action-button svg { width: .86rem; height: .86rem; }
.card-type { padding: .25rem .5rem; border-radius: 2rem; color: var(--accent-dark); background: var(--accent-soft); font-size: .62rem; font-weight: 680; letter-spacing: .04em; text-transform: uppercase; }
.card time { color: var(--tertiary); font-size: .65rem; }
.card h2 { margin: 1.25rem 0 .55rem; font-size: 1.08rem; line-height: 1.25; letter-spacing: -.017em; }
.library-article .card-type { color: #665139; background: #f4ede3; }
.library-article-subtitle { margin: -.25rem 0 .55rem; overflow: hidden; color: #858078; font-size: .68rem; line-height: 1.4; text-overflow: ellipsis; white-space: nowrap; }
.card > .card-excerpt { max-height: 5.1rem; margin: 0; overflow: hidden; color: var(--secondary); font-size: .78rem; line-height: 1.58; }
.card-footer { display: flex; align-items: end; justify-content: space-between; gap: .5rem; margin-top: auto; padding-top: 1rem; }
.card-tags { display: flex; flex-wrap: wrap; gap: .3rem; }
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
.assets-pane, .agent-chat, .artifact-pane { min-height: 0; overflow: hidden; border: 1px solid rgba(29,29,31,.08); border-radius: 1.15rem; background: rgba(255,255,255,.84); box-shadow: var(--shadow); backdrop-filter: blur(18px); }
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
.assets-pane { display: flex; flex-direction: column; background: rgba(249,250,249,.92); }
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
.assets-search { height: 2.45rem; display: flex; align-items: center; gap: .45rem; margin: .75rem .75rem .55rem; padding: 0 .65rem; border: 1px solid #dfe4e1; border-radius: .65rem; background: white; box-shadow: 0 1px 3px rgba(27,39,32,.03); }
.assets-search:focus-within { border-color: rgba(71,105,87,.45); box-shadow: 0 0 0 3px rgba(71,105,87,.08); }
.assets-search svg { width: .83rem; height: .83rem; flex: 0 0 auto; color: #8a928d; }
.assets-search input { min-width: 0; width: 100%; border: 0; outline: 0; color: #343a36; background: transparent; font-size: .7rem; }
.asset-filter-list { display: flex; gap: .25rem; padding: 0 .75rem .62rem; overflow-x: auto; scrollbar-width: none; }
.asset-filter-list::-webkit-scrollbar { display: none; }
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
.asset-row-copy { min-width: 0; display: block; padding-right: 1.15rem; }
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
.asset-drop-zone { min-height: 5.2rem; display: grid; place-items: center; align-content: center; gap: .24rem; margin: .65rem; border: 1px dashed #bfcac3; border-radius: .75rem; color: #718078; background: rgba(255,255,255,.58); cursor: pointer; }
.asset-drop-zone:hover, .asset-drop-zone.dragging { border-color: #668873; color: #42604f; background: #edf4ef; }
.asset-drop-zone svg { width: 1rem; height: 1rem; }
.asset-drop-zone strong { font-size: .62rem; }
.asset-drop-zone small { color: #989e9a; font-size: .48rem; }
.agent-thread { min-height: 0; padding: 1.2rem; overflow-y: auto; scrollbar-width: thin; scrollbar-gutter: stable; overflow-anchor: none; }
.agent-thread.empty { display: grid; place-items: center; }
.agent-welcome { max-width: 25rem; text-align: center; }
.agent-welcome .feature-icon { margin: 0 auto; }
.agent-welcome h2 { margin: 1rem 0 .4rem; font-size: 1.25rem; letter-spacing: -.025em; }
.agent-welcome > p { margin: 0 auto; color: var(--secondary); font-size: .76rem; line-height: 1.6; }
.prompt-hints { display: flex; justify-content: center; gap: .45rem; margin-top: 1.1rem; }
.prompt-hints button { padding: .48rem .65rem; border: 1px solid var(--line); border-radius: .58rem; color: #606065; background: rgba(247,247,248,.8); cursor: pointer; font-size: .64rem; }
.agent-input { margin: .8rem; padding: .25rem; border: 1px solid rgba(29,29,31,.11); border-radius: .9rem; background: white; box-shadow: 0 3px 16px rgba(0,0,0,.055); }
.agent-input:focus-within { border-color: rgba(71,105,87,.4); box-shadow: 0 0 0 3px rgba(71,105,87,.1), 0 5px 20px rgba(0,0,0,.06); }
.agent-input textarea { display: block; width: 100%; min-height: 4rem; padding: .7rem .8rem .25rem; resize: none; border: 0; outline: 0; color: var(--text); background: transparent; font-size: .78rem; line-height: 1.5; }
.agent-input-footer { display: flex; align-items: center; justify-content: space-between; gap: .5rem; min-height: 2.45rem; padding: 0 .3rem .1rem .45rem; }
.agent-input-footer small { color: var(--tertiary); font-size: .55rem; }
.agent-input .send-button { position: static; }
.composer-controls, .composer-submit { min-width: 0; display: flex; align-items: center; gap: .35rem; }
.composer-controls { flex-wrap: wrap; }
.composer-select { position: relative; min-width: 0; display: flex; align-items: center; border: 1px solid transparent; border-radius: .55rem; color: #606065; background: #f5f5f6; }
.composer-select:hover { border-color: var(--line); background: #f0f0f2; }
.composer-select svg { position: absolute; left: .48rem; z-index: 1; width: .72rem; height: .72rem; pointer-events: none; }
.composer-select select, .composer-select button { height: 1.85rem; min-width: 0; padding: 0 1.55rem 0 .55rem; overflow: hidden; border: 0; outline: 0; color: inherit; background: transparent; cursor: pointer; font-size: .61rem; font-weight: 590; text-overflow: ellipsis; white-space: nowrap; }
.model-select select, .model-select button { width: clamp(8rem, 15vw, 13rem); padding-left: 1.45rem; }
.reasoning-select select { width: clamp(7.7rem, 10vw, 9.5rem); }
.composer-telemetry { min-width: 0; display: flex; align-items: center; gap: .25rem; flex-wrap: wrap; }
.composer-telemetry > span { min-height: 1.85rem; display: inline-flex; align-items: center; gap: .32rem; padding: 0 .52rem; border: 1px solid #e4e7e5; border-radius: .55rem; color: #59645d; background: #f7f8f7; white-space: nowrap; }
.composer-telemetry small { color: #929994; font-size: .5rem; font-weight: 600; letter-spacing: .035em; text-transform: uppercase; }
.composer-telemetry strong { font-size: .58rem; font-weight: 650; }
.composer-submit { flex: 0 0 auto; }
.artifact-pane { overflow: hidden; background: #f3f4f1; }
.artifact-workspace { display: flex; flex-direction: column; }
.artifact-collection-header { display: flex; align-items: center; justify-content: space-between; gap: .7rem; padding: .85rem 1rem .72rem; border-bottom: 1px solid #e4e8e5; background: rgba(255,255,255,.92); }
.artifact-collection-header strong, .artifact-collection-header small { display: block; }
.artifact-collection-header strong { color: #303632; font-size: .78rem; }
.artifact-collection-header small { margin-top: .1rem; color: var(--tertiary); font-size: .58rem; }
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
.message { width: 100%; display: flex; align-items: flex-start; gap: .68rem; margin-bottom: 1.15rem; }
.message-profile { width: 2rem; height: 2rem; flex: 0 0 auto; display: grid; place-items: center; overflow: hidden; border-radius: .68rem; }
.message-profile svg { width: 1rem; height: 1rem; fill: none; stroke: currentColor; stroke-width: 1.75; stroke-linecap: round; }
.message-profile img { width: 1.45rem; height: 1.45rem; object-fit: contain; }
.agent-profile { border: 1px solid rgba(71,105,87,.12); color: var(--accent-dark); background: #edf2ee; box-shadow: 0 2px 8px rgba(53,83,67,.08); }
.user-profile { color: #fff; background: linear-gradient(145deg, #75827b, #4e5d55); box-shadow: 0 2px 8px rgba(45,58,51,.14); }
.message-body { min-width: 0; max-width: min(84%, 44rem); }
.message-author { min-height: 1.65rem; display: flex; align-items: baseline; gap: .42rem; padding: 0 .12rem .32rem; }
.message-author strong { color: #3b3e3c; font-size: .72rem; font-weight: 680; letter-spacing: -.006em; }
.message-author small { color: var(--tertiary); font-size: .6rem; }
.message-content, .message-body > p { margin: 0; padding: .78rem .9rem; border: 1px solid rgba(29,29,31,.035); border-radius: .88rem; color: #303431; background: #f0f1f2; font-size: .76rem; line-height: 1.58; overflow-wrap: anywhere; }
.assistant-message .message-content, .assistant-message .message-body > p { border-top-left-radius: .3rem; background: #f0f1f2; }
.user-message { flex-direction: row-reverse; }
.user-message .message-body { display: flex; flex-direction: column; align-items: flex-end; }
.user-message .message-author { justify-content: flex-end; }
.user-message .message-content { width: fit-content; max-width: 100%; border-color: rgba(71,105,87,.12); border-top-right-radius: .3rem; color: #294237; background: #e5ede8; box-shadow: 0 3px 12px rgba(46,77,60,.07); }
.user-message .message-content h1, .user-message .message-content h2, .user-message .message-content h3, .user-message .message-content h4, .user-message .message-content p, .user-message .message-content li, .user-message .message-content strong, .user-message .message-content em { color: #294237; }
.user-message .message-content a { color: #2f6849; text-decoration-color: rgba(47,104,73,.45); }
.user-message .message-content blockquote { border-left-color: rgba(71,105,87,.34); color: #53685c; }
.user-message .message-content code:not(pre code) { color: #315441; background: rgba(255,255,255,.72); }
.live-agent-state { display: inline-flex; align-items: center; gap: .3rem; text-transform: capitalize; }
.live-agent-state i { width: .36rem; height: .36rem; border-radius: 50%; background: #4b9867; box-shadow: 0 0 0 .18rem rgba(75,152,103,.12); animation: activity-pulse 1.1s ease-in-out infinite; }
.agent-event-timeline { width: 100%; display: grid; gap: .5rem; }
.agent-event-timeline > .reasoning-panel, .agent-event-timeline > .tool-activity { margin: 0; }
.tool-activity-list { display: grid; gap: .32rem; margin: 0 0 .48rem; }
.tool-activity { min-width: min(100%, 25rem); overflow: hidden; border: 1px solid rgba(71,105,87,.12); border-radius: .68rem; color: #607067; background: #f5f8f6; font-size: .64rem; }
.tool-activity summary { display: flex; align-items: center; gap: .38rem; min-height: 2rem; padding: .38rem .55rem; cursor: pointer; list-style: none; text-transform: capitalize; user-select: none; }
.tool-activity summary::-webkit-details-marker { display: none; }
.tool-activity summary::after { content: '›'; margin-left: .1rem; color: #8b948f; font-size: .82rem; transition: transform 150ms ease; }
.tool-activity[open] summary::after { transform: rotate(90deg); }
.tool-activity summary i { width: .38rem; height: .38rem; flex: 0 0 auto; border-radius: 50%; background: #d59b45; animation: activity-pulse 1.1s ease-in-out infinite; }
.tool-activity.succeeded summary i { background: #4b9867; animation: none; }
.tool-activity.failed { color: #914d4d; background: #fff6f6; }
.tool-activity.failed summary i { background: #bd5656; animation: none; }
.tool-activity summary small { margin-left: auto; color: var(--tertiary); font-size: .58rem; text-transform: none; }
.tool-activity-details { display: grid; gap: .55rem; padding: .6rem; border-top: 1px solid rgba(71,105,87,.1); background: rgba(255,255,255,.72); }
.tool-activity-details strong { display: block; margin-bottom: .28rem; color: #78827c; font-size: .56rem; letter-spacing: .055em; text-transform: uppercase; }
.tool-activity-details pre { max-height: 11rem; margin: 0; padding: .52rem .58rem; overflow: auto; border: 1px solid rgba(29,29,31,.07); border-radius: .5rem; color: #39443e; background: #f3f4f3; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; font-size: .62rem; line-height: 1.48; text-transform: none; white-space: pre-wrap; overflow-wrap: anywhere; }
.tool-activity-details pre.error { color: #8d4040; background: #fff1f1; }
.reasoning-panel { width: 100%; margin: 0 0 .5rem; overflow: hidden; border: 1px solid rgba(71,105,87,.11); border-radius: .72rem; color: #526158; background: #f7f9f7; }
.reasoning-panel summary { display: flex; align-items: center; gap: .42rem; min-height: 2.15rem; padding: .48rem .68rem; cursor: pointer; list-style: none; font-size: .7rem; font-weight: 650; user-select: none; }
.reasoning-panel summary::-webkit-details-marker { display: none; }
.reasoning-panel summary::before { content: '›'; color: #75827a; font-size: .9rem; transition: transform 150ms ease; }
.reasoning-panel[open] summary::before { transform: rotate(90deg); }
.reasoning-panel summary small { margin-left: auto; color: var(--tertiary); font-size: .58rem; font-weight: 500; }
.reasoning-content { max-height: 14rem; padding: .62rem .75rem .72rem; overflow: auto; border-top: 1px solid rgba(71,105,87,.08); color: #657068; font-size: .71rem; line-height: 1.58; }
.compaction-panel { border-color: rgba(95, 79, 166, .16); background: #f8f7fc; }
.compaction-content > small { display: block; padding: .48rem .75rem .65rem; color: var(--tertiary); font-size: .61rem; }
.streaming-reasoning { box-shadow: inset .16rem 0 #9ab3a3; }
.streaming-message .message-body { width: min(84%, 44rem); }
.streaming-message .message-content, .streaming-message .message-body > p { width: fit-content; }
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
.send-button { position: absolute; right: 1.05rem; top: 1.15rem; display: grid; place-items: center; width: 2rem; height: 2rem; padding: 0; border: 0; border-radius: .62rem; color: white; background: var(--accent); cursor: pointer; }
.send-button:disabled { opacity: .35; cursor: not-allowed; transform: none; }
.send-button svg { width: .85rem; height: .85rem; transform: rotate(-90deg); }
.send-button.stop { background: #59635d; }
.send-button.stop svg { width: .72rem; height: .72rem; transform: none; fill: currentColor; }
.artifact-panel { padding: 1.5rem; border: 1px solid rgba(29,29,31,.08); border-radius: 1.1rem; background: rgba(255,255,255,.88); box-shadow: var(--shadow); backdrop-filter: blur(18px); transform-origin: 50% 0; }
.artifact-panel.artifact-editor { position: relative; display: flex; flex-direction: column; padding: 0; overflow: hidden; color: #252a27; background: #fff; }
.artifact-editor-accent { height: .26rem; flex: 0 0 auto; background: linear-gradient(90deg, #385d49, #77a087 70%, #b5cabb); }
.artifact-editor-header { display: flex; align-items: center; justify-content: space-between; gap: 1rem; padding: 1rem 1.15rem .9rem; border-bottom: 1px solid #e9ece9; }
.artifact-state { min-width: 0; display: flex; align-items: center; gap: .62rem; }
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
.artifact-mode-switch { display: flex; padding: .18rem; border: 1px solid #e1e5e2; border-radius: .6rem; background: #f2f4f2; }
.artifact-mode-switch button { min-height: 1.72rem; padding: 0 .65rem; border: 0; border-radius: .43rem; color: #7a807c; background: transparent; cursor: pointer; font-size: .65rem; font-weight: 620; }
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
.settings-intro { margin: .5rem 0 1rem; }
.settings-card { padding: 1.5rem; border: 1px solid rgba(29,29,31,.075); border-radius: 1rem; background: rgba(255,255,255,.84); box-shadow: 0 2px 12px rgba(0,0,0,.025); }
.provider-list { display: flex; gap: .55rem; margin: 0 0 .8rem; padding: .15rem 0; overflow-x: auto; }
.provider-list > button { min-width: 11rem; display: flex; align-items: center; gap: .6rem; padding: .68rem .75rem; border: 1px solid var(--line); border-radius: .72rem; color: var(--text); background: rgba(255,255,255,.48); cursor: pointer; text-align: left; }
.provider-list > button.active { border-color: rgba(71,105,87,.28); background: var(--accent-soft); box-shadow: 0 2px 8px rgba(52,82,67,.08); }
.provider-list strong, .provider-list small { display: block; }
.provider-list strong { max-width: 9rem; overflow: hidden; font-size: .72rem; text-overflow: ellipsis; white-space: nowrap; }
.provider-list small { margin-top: .18rem; color: var(--secondary); font-size: .58rem; }
.settings-card .form-grid { margin-top: 0; }
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
.agent-input textarea { font-size: .88rem; }
.agent-input-footer small { font-size: .63rem; }
.composer-select select, .composer-select button { font-size: .69rem; }
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
  .primary-nav { display: grid; grid-template-columns: repeat(3, 1fr); width: 75%; }
  .primary-nav button, .sidebar-footer button { height: 3.25rem; flex-direction: column; justify-content: center; gap: .2rem; padding: 0; font-size: .68rem; }
  .primary-nav button small, .primary-nav kbd, .status-dot { display: none; }
  .primary-nav button svg, .sidebar-footer button svg { width: 1.15rem; height: 1.15rem; }
  .sidebar-footer { position: absolute; right: .65rem; bottom: max(.45rem, env(safe-area-inset-bottom)); width: calc((100% - 1.3rem) / 4); padding: 0; border: 0; }
  .topbar { min-height: 4.5rem; padding: .8rem 1rem; }
  .topbar .primary-action { width: 2.65rem; padding: 0; font-size: 0; }
  .topbar .primary-action svg { width: 1rem; height: 1rem; }
  .content { padding: 1.3rem 1rem 3rem; }
  .card-grid { grid-template-columns: 1fr; }
  .card { min-height: 13rem; }
  .form-grid, .taxonomy-form { grid-template-columns: 1fr; }
  .artifact-pane .form-grid { grid-template-columns: 1fr; }
  .refinement-workspace { grid-template-columns: 1fr; }
  .initial-agent-layout.streaming { grid-template-columns: 1fr; }
  .agent-workspace { height: auto; min-height: 0; grid-template-columns: 1fr; }
  .assets-pane { min-height: 28rem; max-height: 70vh; }
  .agent-chat { min-height: 70vh; }
  .artifact-pane { min-height: 30rem; }
  .composer-submit small { display: none; }
  .model-select select, .model-select button { width: min(42vw, 10rem); }
  .composer-telemetry { width: 100%; flex-wrap: nowrap; overflow-x: auto; scrollbar-width: none; }
  .composer-telemetry::-webkit-scrollbar { display: none; }
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
