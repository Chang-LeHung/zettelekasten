<!--
  The panel: read the page you are on, talk to your local Zett agent, save what it made.

  The look and the interaction follow the browser app's conversation pane: the
  same header, the same thread (a right-aligned prompt bubble, answers as
  Markdown), and the same composer with its model and thinking-effort controls.
  What the app shows in its artifact pane, this shows inline — a card per
  artifact the agent created or changed, with the Save button that publishes it.

  Each webpage mounts its own extension frame. The tab/page key maps to one
  Zett session, restored from server history when the frame opens again.
-->

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { DEFAULT_SERVER_URL, ZettClient, ZettError } from './api/zett-client'
import { ARTIFACT_TOOLS, type AgentArtifact, type ArtifactReceipt, type Provider, type ReasoningEffort, type SessionSummary, type ToolOutcome, type TranscriptEntry } from './api/types'
import MarkdownBody from './chat/MarkdownBody.vue'
import AgentExecution from '../../../frontend/src/components/AgentExecution.vue'
import CacheHitRate from '../../../frontend/src/components/CacheHitRate.vue'
import ContextCompositionRing from '../../../frontend/src/components/ContextCompositionRing.vue'
import type { AgentContextComposition, AgentCustomEvent, AgentModelUsage } from '../../../frontend/src/api/types'
import { addAgentUsage, formatTokenCount, latestAgentUsage, summarizeAgentUsage } from '../../../frontend/src/utils/agentUsage'
import { buildMessageParts, readMessageImage, type PositionedMessageImage } from '../../../frontend/src/utils/messageParts'
import { parseUtcTimestamp } from '../../../frontend/src/utils/timestamps'
import { BrowserBridgeClient, type BrowserConsent } from './api/browser-bridge'
import { formatTurnDuration, splitTurnTimeline } from '../../../frontend/src/utils/conversationTurns'
import { settleTimeline, turnTask, updateTimeline } from './chat/timeline'
import { readActivePage } from './page/page-reader'
import { MAX_PAGE_CHARS, PAGE_TOOLS_UNAVAILABLE_NOTE, pageContext } from './page/page-text'
import { browserApprovalKey, pageKey } from './chat/page-sessions'
import { PAGE_PROMPT_MARKER, restoreTranscript } from './chat/restore-transcript'

/** Thinking effort the app offers, in the order it lists them. */
const EFFORTS: Array<{ value: ReasoningEffort; label: string }> = [
  { value: 'off', label: 'Off' },
  { value: 'low', label: 'Low' },
  { value: 'medium', label: 'Medium' },
  { value: 'high', label: 'High' },
]

const HINTS = ['Summarize this page', 'Save this page as a card', 'Key points']

const client = ref(new ZettClient(DEFAULT_SERVER_URL))
const serverUrl = ref(DEFAULT_SERVER_URL)
const serverStatus = ref('')
const settingsOpen = ref(false)
const historyOpen = ref(false)
const historySessions = ref<SessionSummary[]>([])
const historyLoading = ref(false)
const historyExhausted = ref(false)
const moreOpen = ref(false)
const modelOpen = ref(false)
const effortOpen = ref(false)
const conversationId = ref<string | null>(null)
const tabId = Number(new URLSearchParams(location.search).get('tabId'))
const owningTabId = Number.isSafeInteger(tabId) && tabId >= 0 ? tabId : null
const panelNonce = new URLSearchParams(location.search).get('panelNonce')
const pageIdentity = ref<string | null>(null)
const providers = ref<Provider[]>([])
const selectedProviderId = ref('')
const effort = ref<ReasoningEffort>('medium')
const page = ref<Awaited<ReturnType<typeof readActivePage>> | null>(null)
const transcript = ref<TranscriptEntry[]>([])
const thread = ref<HTMLElement | null>(null)
const composer = ref<HTMLFormElement | null>(null)
interface QueuedFollowUp { id: number; text: string }
/** One `ask_user` request the run is suspended on until the panel answers it. */
interface AskUserQuestion {
  toolCallId: string
  question: string
  options: string[]
  allowMultiple: boolean
  responseEvent: string
}
const queuedFollowUps = ref<QueuedFollowUp[]>([])
const steeringQueuedId = ref<number | null>(null)
const pendingQuestion = ref<AskUserQuestion | null>(null)
const queuedQuestions = ref<AskUserQuestion[]>([])
const askAnswer = ref('')
const askImages = ref<PositionedMessageImage[]>([])
const selectedAskOptions = ref<string[]>([])
const answeringQuestion = ref(false)
const askImageInput = ref<HTMLInputElement | null>(null)
const maxMessageImages = ref(1)
/** The `•••` menu's Context row owns the ring: hovering it shows the pie. */
const contextOpen = ref(false)
let nextQueuedFollowUpId = 0
/** The assistant entry the stream is currently writing into; steering closes it. */
let activeAnswerId: number | null = null
/** Steering texts whose streamed echo has not arrived yet. */
const pendingSteeringTexts: string[] = []
let steeringResponseStarted = false
const prompt = ref('')
const busy = ref(false)
const stopping = ref(false)
let activeStreamController: AbortController | null = null
const currentUsage = ref<AgentModelUsage | null>(null)
const contextComposition = ref<AgentContextComposition | null>(null)
const compactionMaxTokens = ref(0)
const browserConnected = ref(false)
const browserConnecting = ref(false)
const browserConsent = ref<BrowserConsent | null>(null)
const browserAutoApprove = ref(false)
const browserBridge = new BrowserBridgeClient(
  consent => { browserConsent.value = consent },
  reason => { browserConnected.value = false; notify(reason, 'error') },
)
const usage = computed(() => summarizeAgentUsage(transcript.value
  .filter(entry => entry.role === 'assistant')
  .map(entry => ({
    role: 'assistant',
    content: '',
    usage: entry.usage,
    generation_duration_ms: entry.generationDurationMs,
  }))))

/** When the provider started answering; the usage event closes the window. */
let generationStartedAt = 0
/** The live step's counters, or the last stored ones after a panel reopen. */
const contextUsage = computed(() => currentUsage.value ?? latestAgentUsage(transcript.value
  .filter(entry => entry.role === 'assistant')
  .map(entry => ({ role: 'assistant', content: '', usage: entry.usage }))))
const clock = ref(Date.now())
let clockTimer: ReturnType<typeof setInterval> | undefined
const savingIds = ref<string[]>([])
const notice = ref('')
const noticeKind = ref<'ok' | 'error'>('ok')
let entryId = 0
let pageSwitch = 0

const consentDetails = computed(() => {
  const change = browserConsent.value?.command.change
  if (change) return {
    action: change.action.replaceAll('_', ' '),
    target: change.selector,
    value: typeof change.value === 'string' ? change.value : String(change.value),
    extra: '',
  }
  const interaction = browserConsent.value?.command.interaction
  if (!interaction) return null
  return {
    action: interaction.action.replaceAll('_', ' '),
    target: interaction.selector,
    value: interaction.key || interaction.direction || '',
    extra: interaction.target_selector ? `→ ${interaction.target_selector}` : '',
  }
})

const selectedProvider = computed(
  () => providers.value.find((provider) => provider.id === selectedProviderId.value) ?? null,
)

function togglePicker(which: 'model' | 'effort'): void {
  if (which === 'model') {
    modelOpen.value = !modelOpen.value
    effortOpen.value = false
  } else {
    effortOpen.value = !effortOpen.value
    modelOpen.value = false
  }
  moreOpen.value = false
}

function closeMenus(): void {
  modelOpen.value = false
  effortOpen.value = false
  moreOpen.value = false
  contextOpen.value = false
}

function onDocumentPointerDown(event: PointerEvent): void {
  if (event.target instanceof Node && composer.value?.contains(event.target)) return
  closeMenus()
}

function chooseProvider(id: string): void {
  selectedProviderId.value = id
  modelOpen.value = false
}

function chooseEffort(value: ReasoningEffort): void {
  effort.value = value
  effortOpen.value = false
}

function notify(message: string, kind: 'ok' | 'error' = 'ok'): void {
  notice.value = message
  noticeKind.value = kind
}

async function connectBrowser(): Promise<void> {
  if (!conversationId.value || browserConnecting.value || owningTabId === null) return
  browserConnecting.value = true
  try {
    await browserBridge.connect(client.value.browserSocketUrl(conversationId.value), owningTabId)
    browserConnected.value = true
    notify('Page connected. DOM changes will ask for approval.')
  } catch (error) {
    browserConnected.value = false
    notify((error as Error).message, 'error')
  } finally { browserConnecting.value = false }
}

async function disconnectBrowser(): Promise<void> {
  browserConnected.value = false
  await browserBridge.disconnect()
}

/** Load the session's stored "always allow page edits" choice. */
async function loadBrowserApproval(sessionId: string | null): Promise<void> {
  const key = sessionId ? browserApprovalKey(sessionId) : null
  const stored = key ? (await chrome.storage.local.get(key))[key] : undefined
  if (conversationId.value !== sessionId) return
  browserAutoApprove.value = stored === true
  browserBridge.autoApprove = browserAutoApprove.value
}

async function rememberBrowserApproval(value: boolean): Promise<void> {
  const sessionId = conversationId.value
  if (sessionId) {
    const key = browserApprovalKey(sessionId)
    if (value) await chrome.storage.local.set({ [key]: true })
    else await chrome.storage.local.remove(key)
  }
  browserAutoApprove.value = value
  browserBridge.autoApprove = value
  notify(value
    ? 'Page edits will be applied without review for this session.'
    : 'Page edits will ask for review again.')
}

/** "Always allow in this session": approve now and skip this card from here on. */
function allowBrowserForSession(): void {
  const consent = browserConsent.value
  if (!consent) return
  void rememberBrowserApproval(true)
  consent.approve()
}

function closePanel(): void {
  if (owningTabId === null || !panelNonce) return
  void chrome.tabs.sendMessage(owningTabId, {
    channel: 'zett-dom', type: 'close-panel', panelNonce,
  }, { frameId: 0 }).catch(error => notify((error as Error).message, 'error'))
}

function stopGeneration(): void {
  if (!busy.value || stopping.value) return
  stopping.value = true
  // Stop discards what has not been injected yet, like the web composer.
  queuedFollowUps.value = []
  pendingSteeringTexts.length = 0
  clearQuestions()
  // Like the web composer, abort the HTTP stream so the backend unwinds the
  // active Agent request. Revoke the browser peer too: pending DOM consent
  // must not remain executable after Stop, even if the SSE disconnect is late.
  activeStreamController?.abort()
  void disconnectBrowser()
}

function appendEntry(role: TranscriptEntry['role'], text: string, extra: Partial<TranscriptEntry> = {}): TranscriptEntry {
  const entry: TranscriptEntry = { id: ++entryId, role, text, ...extra }
  transcript.value = [...transcript.value, entry]
  return entry
}

function followOutput(): void {
  void nextTick(() => {
    if (thread.value) thread.value.scrollTop = thread.value.scrollHeight
  })
}

function updateEntry(id: number, changes: Partial<TranscriptEntry>): void {
  transcript.value = transcript.value.map((entry) => (entry.id === id ? { ...entry, ...changes } : entry))
}

function activeEntry(): TranscriptEntry | undefined {
  return activeAnswerId === null ? undefined : transcript.value.find(entry => entry.id === activeAnswerId)
}

watch(transcript, followOutput, { deep: true })

function toggleExecution(entry: TranscriptEntry, event: MouseEvent): void {
  event.preventDefault()
  updateEntry(entry.id, { detailsOpen: !(entry.detailsOpen ?? entry.pending) })
}

function duration(entry: TranscriptEntry): string {
  return formatTurnDuration(entry.pending ? clock.value - (entry.startedAt ?? clock.value) : (entry.durationMs ?? 0))
}

function previewImage(image: { name: string; url: string }): void {
  // ToolResult only emits validated HTTP or image data URLs.
  void chrome.tabs.create({ url: image.url })
}

/** The app's rule: an artifact needs saving while its draft is unpublished. */
function needsSave(artifact: Pick<AgentArtifact, 'status' | 'content' | 'draft_content'>): boolean {
  if (artifact.status !== 'saved') return true
  return artifact.draft_content != null && JSON.stringify(artifact.draft_content) !== JSON.stringify(artifact.content)
}

/** Show one artifact card, updating the card the thread already has for it. */
function upsertArtifactEntry(card: { id: string; title: string; artifactType: AgentArtifact['artifact_type']; needsSave: boolean }): void {
  const existing = transcript.value.find((entry) => entry.artifact?.id === card.id)
  if (existing) {
    updateEntry(existing.id, { text: card.title, artifact: card })
    return
  }
  appendEntry('artifact', card.title, { artifact: card })
}

function receiptCard(receipt: ArtifactReceipt) {
  return {
    id: receipt.id,
    title: receipt.title,
    artifactType: receipt.artifact_type,
    needsSave: receipt.status !== 'saved' || receipt.pending_draft,
  }
}

function artifactCard(artifact: AgentArtifact) {
  return {
    id: artifact.id,
    title: artifact.content?.title ?? artifact.draft_content?.title ?? 'Untitled artifact',
    artifactType: artifact.artifact_type,
    needsSave: needsSave(artifact),
  }
}

async function loadSettings(): Promise<void> {
  const stored = await chrome.storage.local.get(['serverUrl', 'providerId', 'effort'])
  serverUrl.value = typeof stored.serverUrl === 'string' ? stored.serverUrl : DEFAULT_SERVER_URL
  selectedProviderId.value = typeof stored.providerId === 'string' ? stored.providerId : ''
  effort.value = EFFORTS.some((option) => option.value === stored.effort) ? (stored.effort as ReasoningEffort) : 'medium'
  client.value = new ZettClient(serverUrl.value)
}

/** Confirm the server answers, then make sure a provider and session exist. */
async function connect(): Promise<void> {
  try {
    await client.value.health()
    serverStatus.value = 'reachable'
  } catch (error) {
    serverStatus.value = 'not reachable'
    providers.value = []
    notify((error as Error).message, 'error')
    return
  }

  try {
    providers.value = (await client.value.listProviders()).filter((provider) => provider.enabled)
    if (!providers.value.some((provider) => provider.id === selectedProviderId.value)) {
      selectedProviderId.value = providers.value[0]?.id ?? ''
    }
    if (!providers.value.length) {
      notify('No enabled model provider: configure one in Zett first.', 'error')
      return
    }
    const settings = await client.value.runtimeSettings()
    if (Number.isFinite(settings.compaction_max_tokens) && settings.compaction_max_tokens > 0) {
      compactionMaxTokens.value = settings.compaction_max_tokens
    }
    if (Number.isFinite(settings.max_message_images) && settings.max_message_images > 0) {
      maxMessageImages.value = settings.max_message_images
    }
  } catch (error) {
    notify((error as Error).message, 'error')
  }
}

async function openPage(): Promise<void> {
  if (owningTabId === null) return
  const switchId = ++pageSwitch
  const tab = await chrome.tabs.get(owningTabId)
  const nextKey = pageKey(serverUrl.value, owningTabId, tab.url ?? '')
  if (nextKey === pageIdentity.value && conversationId.value) {
    if (!browserConnected.value && !browserConnecting.value) await connectBrowser()
    if (pageIdentity.value === nextKey) await readPage()
    return
  }
  await readPage()
  if (switchId !== pageSwitch) return
  // Reading is best-effort; URL identity comes from Chrome's tab, not from the
  // text-extraction result. A failed read must never erase this page's history.
  if (page.value?.url !== tab.url) page.value = null
  if (busy.value) stopGeneration()
  await disconnectBrowser()
  if (switchId !== pageSwitch) return
  pageIdentity.value = nextKey
  conversationId.value = null
  transcript.value = []
  queuedFollowUps.value = []
  pendingSteeringTexts.length = 0
  activeAnswerId = null
  steeringResponseStarted = false
  clearQuestions()
  prompt.value = ''
  currentUsage.value = null
  contextComposition.value = null
  if (!nextKey || serverStatus.value !== 'reachable' || !providers.value.length) return
  const sessionValue: unknown = (await chrome.storage.local.get(nextKey))[nextKey]
  if (switchId !== pageSwitch) return
  if (typeof sessionValue === 'string' && sessionValue.trim()) {
    try {
      const previous = await client.value.session(sessionValue)
      // A navigation may complete while the session is loading.
      if (switchId !== pageSwitch) return
      conversationId.value = sessionValue
      transcript.value = restoreTranscript(previous.messages)
      followOutput()
      entryId = transcript.value.length
      void restoreContextComposition(sessionValue)
      await showPendingArtifacts()
    } catch (error) {
      if (switchId !== pageSwitch) return
      if (!(error instanceof ZettError && error.status === 404)) {
        notify((error as Error).message, 'error')
        return
      }
      // Only a confirmed 404 means the mapped session was deleted.
      await chrome.storage.local.remove([nextKey, browserApprovalKey(String(sessionValue))])
    }
  }
  if (switchId !== pageSwitch) return
  if (!conversationId.value) await startConversation()
  if (switchId !== pageSwitch) return
  await connectBrowser()
}

async function saveSettings(): Promise<void> {
  ++pageSwitch
  await disconnectBrowser()
  const next = (serverUrl.value || DEFAULT_SERVER_URL).trim()
  await chrome.storage.local.set({ serverUrl: next })
  client.value = new ZettClient(next)
  // Every server has its own page-session keys.
  serverStatus.value = ''
  providers.value = []
  pageIdentity.value = null
  conversationId.value = null
  transcript.value = []
  queuedFollowUps.value = []
  pendingSteeringTexts.length = 0
  activeAnswerId = null
  steeringResponseStarted = false
  clearQuestions()
  currentUsage.value = null
  contextComposition.value = null
  compactionMaxTokens.value = 0
  notify(`Talking to ${next}`)
  await connect()
  await openPage()
}

async function startConversation(): Promise<void> {
  const key = pageIdentity.value
  if (!key) throw new Error('Open an HTTP(S) webpage before starting a conversation')
  const session = await client.value.startSession()
  if (pageIdentity.value !== key) return
  conversationId.value = session.conversation_id
  await chrome.storage.local.set({ [key]: session.conversation_id })
}

function formatSessionTime(value: string): string {
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(parseUtcTimestamp(value))
}

/** One page of conversations per request; the list asks for the next on scroll. */
const HISTORY_PAGE_SIZE = 20

async function loadHistory(reset: boolean): Promise<void> {
  if (historyLoading.value || (!reset && historyExhausted.value)) return
  historyLoading.value = true
  try {
    const offset = reset ? 0 : historySessions.value.length
    const page = await client.value.listSessions(HISTORY_PAGE_SIZE, offset)
    historySessions.value = reset ? page : [...historySessions.value, ...page]
    historyExhausted.value = page.length < HISTORY_PAGE_SIZE
  } catch (error) {
    if (reset) historySessions.value = []
    notify((error as Error).message, 'error')
  } finally {
    historyLoading.value = false
  }
}

async function toggleHistory(): Promise<void> {
  historyOpen.value = !historyOpen.value
  settingsOpen.value = false
  if (!historyOpen.value) return
  historySessions.value = []
  historyExhausted.value = false
  await loadHistory(true)
}

function loadMoreHistory(event: Event): void {
  const element = event.target as HTMLElement
  if (element.scrollHeight - element.scrollTop - element.clientHeight > 48) return
  void loadHistory(false)
}

/** Rebind this page to an older conversation and restore its transcript. */
async function openSession(sessionId: string): Promise<void> {
  const key = pageIdentity.value
  if (!key) return
  historyOpen.value = false
  await chrome.storage.local.set({ [key]: sessionId })
  // Clearing the identity makes openPage run its full switch path: stop any
  // turn, drop the old browser peer, restore, and rebind the page connection.
  pageIdentity.value = null
  conversationId.value = null
  await openPage()
  notify('Conversation restored')
}

async function newChat(): Promise<void> {
  try {
    if (busy.value) return
    await disconnectBrowser()
    await startConversation()
    transcript.value = []
    queuedFollowUps.value = []
    pendingSteeringTexts.length = 0
    activeAnswerId = null
    steeringResponseStarted = false
    clearQuestions()
    currentUsage.value = null
    contextComposition.value = null
    entryId = 0
    await connectBrowser()
    notify('New conversation')
  } catch (error) {
    notify((error as Error).message, 'error')
  }
}

async function readPage(): Promise<void> {
  try {
    page.value = await readActivePage(MAX_PAGE_CHARS, owningTabId ?? undefined)
  } catch (error) {
    page.value = null
    // Page extraction is optional. DOM tools still connect to supported pages,
    // and a read failure must never replace or erase that page's session.
    if (serverStatus.value === 'reachable') notify((error as Error).message, 'error')
  }
}

/** Surface the artifacts of this conversation that still wait for a save. */
async function showPendingArtifacts(): Promise<void> {
  if (!conversationId.value) return
  const artifacts = await client.value.listArtifacts(conversationId.value)
  for (const artifact of artifacts.filter(needsSave)) upsertArtifactEntry(artifactCard(artifact))
}

/** A reopened panel keeps the stored composition, not only a live one. */
async function restoreContextComposition(sessionId: string): Promise<void> {
  try {
    const composition = await client.value.sessionContextComposition(sessionId)
    if (conversationId.value === sessionId) contextComposition.value = composition
  } catch {
    if (conversationId.value === sessionId) contextComposition.value = null
  }
}

/** Artifact receipts also surface a Save card; execution details keep the tool. */
function onTool(outcome: ToolOutcome): void {
  if (outcome.state !== 'succeeded') return
  const output = outcome.output as Partial<ArtifactReceipt> | null
  if (ARTIFACT_TOOLS.includes(outcome.name as (typeof ARTIFACT_TOOLS)[number]) && output && typeof output.id === 'string') {
    upsertArtifactEntry(receiptCard(output as ArtifactReceipt))
  }
}

/** Enter queues while a turn runs and starts the next turn otherwise, exactly
 * like the web conversation's composer. */
async function send(): Promise<void> {
  const text = prompt.value.trim()
  if (!text) return
  if (busy.value) {
    queueFollowUp(text)
    return
  }
  await sendTurn(text)
}

function queueFollowUp(text: string): void {
  queuedFollowUps.value = [...queuedFollowUps.value, { id: nextQueuedFollowUpId++, text }]
  prompt.value = ''
}

function removeQueuedFollowUp(id: number): void {
  queuedFollowUps.value = queuedFollowUps.value.filter(item => item.id !== id)
}

function drainQueuedFollowUps(): void {
  if (busy.value || !queuedFollowUps.value.length) return
  const [next, ...remaining] = queuedFollowUps.value
  queuedFollowUps.value = remaining
  if (next) void sendTurn(next.text)
}

/** Steering is published as its own user message, so close the answer that was
 * streaming and let the continuation land after the injected prompt. */
function checkpointAnswerForSteering(): void {
  const id = activeAnswerId
  if (id === null) return
  const entry = transcript.value.find(item => item.id === id)
  if (!entry) return
  updateEntry(id, {
    timeline: settleTimeline(entry.timeline ?? []),
    pending: false,
    durationMs: Date.now() - (entry.startedAt ?? Date.now()),
  })
  activeAnswerId = null
}

function appendSteeringMessage(text: string): void {
  checkpointAnswerForSteering()
  appendEntry('user', text, { steering: 'waiting' })
  activeAnswerId = appendEntry('assistant', '', { pending: true, timeline: [], startedAt: Date.now() }).id
}

function settleSteeringMessages(): void {
  transcript.value = transcript.value.map(entry => (
    entry.steering === 'waiting' ? { ...entry, steering: 'responded' as const } : entry
  ))
}

/** The runtime echoes an injected steering message; a steer sent from another
 * client reaches the panel only here. */
function applyStreamedSteering(text: string): void {
  const index = pendingSteeringTexts.indexOf(text)
  if (index >= 0) pendingSteeringTexts.splice(index, 1)
  else appendSteeringMessage(text)
  steeringResponseStarted = true
}

async function steerQueuedFollowUp(item: QueuedFollowUp): Promise<void> {
  if (!conversationId.value || !busy.value || steeringQueuedId.value !== null) return
  steeringQueuedId.value = item.id
  try {
    const result = await client.value.steerAgent(conversationId.value, item.text)
    if (!result.accepted) {
      notify('The agent is not accepting steering right now', 'error')
      return
    }
    pendingSteeringTexts.push(item.text)
    appendSteeringMessage(item.text)
    queuedFollowUps.value = queuedFollowUps.value.filter(queued => queued.id !== item.id)
  } catch (error) {
    notify((error as Error).message, 'error')
  } finally {
    if (steeringQueuedId.value === item.id) steeringQueuedId.value = null
  }
}

function askOptionLetter(index: number): string {
  return String.fromCharCode('A'.charCodeAt(0) + index)
}

function resetAskState(): void {
  askAnswer.value = ''
  askImages.value = []
  selectedAskOptions.value = []
}

/** `ask_user` suspends the run until the matching response event arrives, so
 * the panel must answer it or the turn never finishes. */
function handleAskUserEvent(event: AgentCustomEvent): void {
  if (event.name !== 'ask_user') return
  const payload = event.payload
  if (typeof payload.tool_call_id !== 'string' || typeof payload.question !== 'string') return
  const question: AskUserQuestion = {
    toolCallId: payload.tool_call_id,
    question: payload.question,
    options: Array.isArray(payload.options)
      ? payload.options.filter((item): item is string => typeof item === 'string')
      : [],
    allowMultiple: payload.allow_multiple === true,
    responseEvent: typeof payload.response_event === 'string' ? payload.response_event : 'ask_user_response',
  }
  if (pendingQuestion.value?.toolCallId === question.toolCallId) return
  if (pendingQuestion.value) {
    queuedQuestions.value.push(question)
    return
  }
  pendingQuestion.value = question
  resetAskState()
}

function showNextAskQuestion(): void {
  pendingQuestion.value = queuedQuestions.value.shift() || null
  resetAskState()
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
    ? selectedAskOptions.value.filter(item => item !== option)
    : [...selectedAskOptions.value, option]
}

function updateAskAnswer(value: string): void {
  askAnswer.value = value
  if (value.trim() && !pendingQuestion.value?.allowMultiple) selectedAskOptions.value = []
}

async function attachAskImages(files: File[]): Promise<void> {
  const images = files.filter(file => file.type.startsWith('image/'))
  const accepted = images.slice(0, Math.max(0, maxMessageImages.value - askImages.value.length))
  if (!accepted.length) return
  try {
    askImages.value = [
      ...askImages.value,
      ...await Promise.all(accepted.map(file => readMessageImage(file, askAnswer.value.length))),
    ]
    if (accepted.length < images.length) {
      notify(`An answer can contain up to ${maxMessageImages.value} images`, 'error')
    }
  } catch (error) {
    notify((error as Error).message, 'error')
  }
}

function onAskImagePick(event: Event): void {
  const input = event.target as HTMLInputElement
  void attachAskImages(Array.from(input.files || []))
  input.value = ''
}

function onAskPaste(event: ClipboardEvent): void {
  const files = Array.from(event.clipboardData?.items || [])
    .filter(item => item.kind === 'file' && item.type.startsWith('image/'))
    .map(item => item.getAsFile())
    .filter((file): file is File => file !== null)
  if (!files.length) return
  event.preventDefault()
  void attachAskImages(files)
}

function removeAskImage(id: string): void {
  askImages.value = askImages.value.filter(image => image.id !== id)
}

async function answerQuestion(): Promise<void> {
  const question = pendingQuestion.value
  const activeId = conversationId.value
  if (!question || !activeId || answeringQuestion.value) return
  const typed = askAnswer.value.trim()
  const answer = question.allowMultiple
    ? [...selectedAskOptions.value, ...(typed ? [typed] : [])]
    : typed || selectedAskOptions.value[0]
  if ((!answer || (Array.isArray(answer) && !answer.length)) && !askImages.value.length) return
  const answerText = Array.isArray(answer) ? answer.join('\n') : answer || ''
  const parts = askImages.value.length ? buildMessageParts(answerText, askImages.value) : []
  answeringQuestion.value = true
  try {
    await client.value.emitAgentEvent(activeId, question.responseEvent, {
      session_id: activeId,
      tool_call_id: question.toolCallId,
      answer,
      parts,
    })
    askImages.value = []
    showNextAskQuestion()
  } catch (error) {
    notify((error as Error).message, 'error')
  } finally {
    answeringQuestion.value = false
  }
}

function clearQuestions(): void {
  pendingQuestion.value = null
  queuedQuestions.value = []
  resetAskState()
}

/** Say why a running turn has no execution details instead of looking stuck. */
function turnLabel(entry: TranscriptEntry): string {
  if (entry.pending && pendingQuestion.value) return 'Waiting for your answer'
  return turnTask(entry.timeline ?? [])
}

async function sendTurn(text: string): Promise<void> {
  if (owningTabId !== null) {
    const tab = await chrome.tabs.get(owningTabId)
    if (pageKey(serverUrl.value, owningTabId, tab.url ?? '') !== pageIdentity.value) {
      await openPage()
      notify('Page changed. Send again in this page’s conversation.', 'error')
      return
    }
  }
  if (!conversationId.value || !selectedProviderId.value) {
    notify('Zett is not ready yet: check the server and a provider.', 'error')
    return
  }
  busy.value = true
  stopping.value = false
  const controller = new AbortController()
  activeStreamController = controller
  notify('')
  // When connected, the Agent reads live page state through its tools. The
  // bounded excerpt only helps if DOM bridge is temporarily unavailable; the
  // note keeps the model from probing tools this turn does not register.
  const outgoing = browserConnected.value ? text
    : `${PAGE_TOOLS_UNAVAILABLE_NOTE}\n\n${page.value ? pageContext(page.value) : ''}${PAGE_PROMPT_MARKER}${text}`
  if (!browserConnected.value) {
    notify('Page tools are off, so the Agent only sees the page excerpt. Press “Connect page” in the ••• menu to let it read and edit the page.')
  }
  appendEntry('user', text)
  const startedAt = Date.now()
  clock.value = startedAt
  clockTimer = setInterval(() => { clock.value = Date.now() }, 200)
  activeAnswerId = appendEntry('assistant', '', { pending: true, timeline: [], startedAt }).id
  // Clear the composer the moment the turn is sent, not when it finishes: the
  // prompt is already part of the thread, and a failed or slow turn must not
  // leave the user's text stuck in the box.
  prompt.value = ''
  try {
    await client.value.streamTurn({
      conversationId: conversationId.value,
      providerId: selectedProviderId.value,
      reasoningEffort: effort.value,
      text: outgoing,
      signal: controller.signal,
      browserToken: browserConnected.value ? browserBridge.token : undefined,
      onUsage: (next) => {
        if (controller.signal.aborted) return
        currentUsage.value = next
        const entry = activeEntry()
        if (entry) {
          updateEntry(entry.id, {
            usage: addAgentUsage(entry.usage ?? null, next),
            generationDurationMs: (entry.generationDurationMs ?? 0) + (generationStartedAt ? performance.now() - generationStartedAt : 0),
          })
        }
        generationStartedAt = 0
      },
      onModelStarted: () => { generationStartedAt = performance.now() },
      onComposition: (composition) => {
        if (!controller.signal.aborted) contextComposition.value = composition
      },
      onEvent: (event) => {
        if (controller.signal.aborted) return
        // A message after a steering echo means the run consumed the steer.
        if (event.type === 'message' && steeringResponseStarted) {
          settleSteeringMessages()
          steeringResponseStarted = false
        }
        const current = activeEntry()
        if (current) updateEntry(current.id, { timeline: updateTimeline(current.timeline ?? [], event) })
      },
      onSteering: (message) => { if (!controller.signal.aborted) applyStreamedSteering(message.content) },
      onCustom: (event) => { if (!controller.signal.aborted) handleAskUserEvent(event) },
      onTool: (outcome) => { if (!controller.signal.aborted) onTool(outcome) },
    })
  } catch (error) {
    // Keep partial text and tool results available to expand even after failure.
    if (!controller.signal.aborted) {
      const entry = activeEntry()
      if (entry) updateEntry(entry.id, { error: (error as Error).message })
      notify((error as Error).message, 'error')
    }
  } finally {
    clearInterval(clockTimer)
    clockTimer = undefined
    const current = activeEntry()
    if (current) {
      updateEntry(current.id, {
        timeline: settleTimeline(current.timeline ?? []),
        pending: false,
        stopped: controller.signal.aborted,
        durationMs: Date.now() - startedAt,
      })
    }
    settleSteeringMessages()
    steeringResponseStarted = false
    activeAnswerId = null
    busy.value = false
    stopping.value = false
    if (activeStreamController === controller) activeStreamController = null
    drainQueuedFollowUps()
  }
}

/** Publish one artifact's draft — what the app's Save button does. */
async function saveOne(artifactId: string): Promise<void> {
  if (!conversationId.value || savingIds.value.includes(artifactId)) return
  savingIds.value = [...savingIds.value, artifactId]
  try {
    const saved = await client.value.saveArtifact(conversationId.value, artifactId)
    upsertArtifactEntry(artifactCard(saved))
    notify(`Saved “${saved.content?.title ?? 'the artifact'}”`)
  } catch (error) {
    notify((error as Error).message, 'error')
  } finally {
    savingIds.value = savingIds.value.filter((id) => id !== artifactId)
  }
}

/** Publish every artifact of this conversation that still has something to save. */
async function saveAll(): Promise<void> {
  if (!conversationId.value || busy.value) return
  savingIds.value = ['*']
  try {
    const artifacts = await client.value.listArtifacts(conversationId.value)
    const pending = artifacts.filter(needsSave)
    if (!pending.length) {
      notify('Nothing to save: every artifact is published')
      return
    }
    for (const artifact of pending) {
      const saved = await client.value.saveArtifact(conversationId.value, artifact.id)
      upsertArtifactEntry(artifactCard(saved))
    }
    notify(pending.length === 1 ? 'Saved 1 artifact' : `Saved ${pending.length} artifacts`)
  } catch (error) {
    notify((error as Error).message, 'error')
  } finally {
    savingIds.value = []
  }
}

const onTabUpdated: Parameters<typeof chrome.tabs.onUpdated.addListener>[0] = (changedId, changeInfo) => {
  if (changedId !== owningTabId) return
  if (changeInfo.status === 'loading' || changeInfo.url) {
    void disconnectBrowser()
  }
  if (changeInfo.status === 'complete') void openPage()
}

onMounted(async () => {
  if (owningTabId === null || !panelNonce) return
  try {
    const ready = await chrome.tabs.sendMessage(owningTabId, {
      channel: 'zett-dom', type: 'panel-hello', panelNonce,
    }, { frameId: 0 })
    if (ready?.ok !== true) throw new Error('This panel was not opened from the webpage')
    const tab = await chrome.tabs.get(owningTabId)
    if (tab.url !== ready.url) throw new Error('The page changed before the panel could connect')
  } catch {
    notify('Open Zettelekasten using the toolbar button on an HTTP(S) page.', 'error')
    return
  }
  await loadSettings()
  await connect()
  await openPage()
  chrome.tabs.onUpdated.addListener(onTabUpdated)
  document.addEventListener('pointerdown', onDocumentPointerDown)
})

onBeforeUnmount(() => {
  ++pageSwitch
  activeStreamController?.abort()
  clearInterval(clockTimer)
  chrome.tabs.onUpdated.removeListener(onTabUpdated)
  document.removeEventListener('pointerdown', onDocumentPointerDown)
  // A closing panel must not drain what was queued for it.
  queuedFollowUps.value = []
  pendingSteeringTexts.length = 0
  clearQuestions()
  void disconnectBrowser()
})

// The two composer picks belong to the panel, not to one turn.
watch([selectedProviderId, effort], () => {
  void chrome.storage.local.set({ providerId: selectedProviderId.value, effort: effort.value })
})

// Each conversation keeps its own page-edit approval policy.
watch(conversationId, (sessionId) => { void loadBrowserApproval(sessionId) })
</script>

<template>
  <header class="chat-header">
    <span class="mark" aria-hidden="true"><img src="/logo.png" alt="" /></span>
    <div class="chat-title">
      <strong>Zettelkasten Agent</strong>
      <small>
        <i class="status-dot" :class="{ online: Boolean(selectedProviderId) }" />
        {{ selectedProvider ? `${selectedProvider.model} · online` : 'No model provider' }}
      </small>
    </div>
    <div class="header-actions">
      <button type="button" title="Previous conversations" aria-label="Previous conversations" @click="toggleHistory">
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M4 12a8 8 0 1 0 2.3-5.7M4 4v4h4" />
          <path d="M12 8.5V12l2.5 1.5" />
        </svg>
      </button>
      <button type="button" title="Start a new conversation" aria-label="Start a new conversation" :disabled="busy" @click="newChat">
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v14M5 12h14" /></svg>
      </button>
      <button type="button" title="Server settings" aria-label="Server settings" @click="settingsOpen = !settingsOpen">
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M4 8h16M4 16h16" />
          <circle cx="9" cy="8" r="2.2" />
          <circle cx="15" cy="16" r="2.2" />
        </svg>
      </button>
      <button class="close-panel" type="button" title="Close panel" aria-label="Close panel" @click="closePanel">×</button>
    </div>
  </header>

  <section
    v-if="historyOpen"
    class="session-history"
    aria-label="Previous conversations"
    @scroll="loadMoreHistory"
  >
    <header>
      <strong>Previous conversations</strong>
      <small v-if="historyLoading && !historySessions.length">Loading…</small>
    </header>
    <p v-if="!historyLoading && !historySessions.length" class="session-history-empty">No conversations yet.</p>
    <button
      v-for="session in historySessions"
      :key="session.id"
      class="session-history-item"
      :class="{ current: session.id === conversationId }"
      type="button"
      @click="openSession(session.id)"
    >
      <strong>{{ session.title || 'Untitled conversation' }}</strong>
      <small>{{ formatSessionTime(session.updated_at) }} · {{ session.message_count }} messages</small>
    </button>
    <p v-if="historySessions.length && historyLoading" class="session-history-empty">Loading more…</p>
    <p v-else-if="historySessions.length && historyExhausted" class="session-history-empty">That's every conversation.</p>
  </section>

  <section v-if="settingsOpen" class="settings">
    <label>
      <span>Zett server</span>
      <input v-model="serverUrl" type="url" spellcheck="false" placeholder="http://127.0.0.1:6280" />
    </label>
    <div class="settings-row">
      <button type="button" :disabled="busy" @click="saveSettings">Save</button>
      <small>{{ serverStatus }}</small>
    </div>
    <p>
      Start the server with <code>zett start</code>. This panel talks to the same HTTP API the browser app uses,
      so nothing here reaches your files directly.
    </p>
  </section>

  <section ref="thread" class="thread">
    <div v-if="!transcript.length" class="welcome">
      <span class="welcome-mark" aria-hidden="true"><img src="/logo.png" alt="" /></span>
      <h2>Turn a conversation into knowledge</h2>
      <p>Zett reads the page with you, answers with its tools, and drafts artifacts you can save.</p>
      <div class="prompt-hints">
        <button v-for="hint in HINTS" :key="hint" type="button" @click="prompt = hint">{{ hint }}</button>
      </div>
    </div>
    <div v-for="entry in transcript" :key="entry.id" class="turn" :class="entry.role">
      <div v-if="entry.role === 'user'" class="user-entry">
        <div class="prompt-bubble">{{ entry.text }}</div>
        <p v-if="entry.steering === 'waiting'" class="steering-pending">Will respond after the current tool call or turn finishes.</p>
      </div>
      <article v-else-if="entry.role === 'artifact' && entry.artifact" class="artifact-card" :class="{ saved: !entry.artifact.needsSave }">
        <div class="artifact-copy">
          <strong>{{ entry.artifact.title }}</strong>
          <small>
            {{ entry.artifact.artifactType }} · {{ entry.artifact.needsSave ? 'unsaved draft' : 'saved' }}
          </small>
        </div>
        <button
          v-if="entry.artifact.needsSave"
          type="button"
          :disabled="savingIds.includes(entry.artifact.id) || savingIds.includes('*')"
          @click="saveOne(entry.artifact.id)"
        >
          {{ savingIds.includes(entry.artifact.id) ? 'Saving…' : 'Save' }}
        </button>
        <span v-else class="saved-note">✓</span>
      </article>
      <template v-else-if="entry.role === 'assistant'">
        <AgentExecution
          :timeline="splitTurnTimeline(entry.timeline ?? []).execution"
          :running="Boolean(entry.pending)"
          :open="entry.detailsOpen ?? Boolean(entry.pending)"
          :task="turnLabel(entry)"
          :duration="duration(entry)"
          @toggle="toggleExecution(entry, $event)"
          @preview-image="previewImage"
        >
          <template #metrics><CacheHitRate :usage="entry.usage" label="Cache" /></template>
          <template #markdown="{ content }"><MarkdownBody :content="content" /></template>
        </AgentExecution>
        <section class="turn-response" aria-label="Agent response">
          <MarkdownBody v-for="segment in splitTurnTimeline(entry.timeline ?? []).answer" :key="segment.id" :content="segment.content" />
          <span v-if="entry.pending" class="streaming-dots" aria-label="Generating"><i /><i /><i /></span>
          <p v-else-if="entry.stopped" class="pending-note">Stopped. Send a message to continue.</p>
          <p v-else-if="!entry.error && !splitTurnTimeline(entry.timeline ?? []).answer.length" class="pending-note">No response was recorded for this turn.</p>
          <p v-if="entry.error" class="notice error" role="alert">{{ entry.error }}</p>
        </section>
      </template>
    </div>
  </section>

  <section v-if="browserConsent" class="browser-consent" role="region" aria-label="Review webpage change">
    <header><span class="consent-mark" aria-hidden="true">✦</span><div><strong>Review page action</strong><small>{{ browserConsent.command.change?.description || browserConsent.command.interaction?.description }}</small></div></header>
    <dl v-if="consentDetails">
      <div><dt>Action</dt><dd>{{ consentDetails.action }}</dd></div>
      <div><dt>Element</dt><dd><code>{{ consentDetails.target }}</code> {{ consentDetails.extra }}</dd></div>
      <div v-if="consentDetails.value"><dt>Value</dt><dd class="consent-value">{{ consentDetails.value }}</dd></div>
    </dl>
    <p class="consent-warning">This may trigger changes on the website. Review before allowing.</p>
    <p class="consent-note">Always allow skips this review for the rest of this conversation; turn it off again from the ••• menu.</p>
    <div class="consent-actions">
      <button type="button" @click="browserConsent.reject">Reject</button>
      <button class="allow" type="button" @click="browserConsent.approve">Allow once</button>
      <button class="allow-session" type="button" @click="allowBrowserForSession">Always allow in this session</button>
    </div>
  </section>

  <section v-if="pendingQuestion" class="ask-user" aria-live="polite" @paste="onAskPaste">
    <header>
      <div>
        <span>Agent question</span>
        <small>
          {{ pendingQuestion.allowMultiple ? 'Select one or more options' : 'Select one option' }}
          <template v-if="queuedQuestions.length"> · {{ queuedQuestions.length }} more waiting</template>
        </small>
      </div>
      <span class="ask-waiting"><i />Waiting for you</span>
    </header>
    <h3>{{ pendingQuestion.question }}</h3>
    <form @submit.prevent="answerQuestion">
      <div v-if="askImages.length" class="ask-images">
        <figure v-for="image in askImages" :key="image.id">
          <img :src="image.content_url" :alt="image.name" />
          <button type="button" :aria-label="`Remove ${image.name}`" @click="removeAskImage(image.id)">×</button>
        </figure>
      </div>
      <div class="ask-choices">
        <label
          v-for="(option, index) in pendingQuestion.options"
          :key="`${index}-${option}`"
          class="ask-choice"
          :class="{ selected: selectedAskOptions.includes(option) }"
        >
          <input
            :type="pendingQuestion.allowMultiple ? 'checkbox' : 'radio'"
            name="agent-question"
            :checked="selectedAskOptions.includes(option)"
            @change="toggleAskOption(option)"
          />
          <span class="ask-letter">{{ askOptionLetter(index) }}</span>
          <span class="ask-text">{{ option }}</span>
        </label>
        <label class="ask-choice custom" :class="{ selected: Boolean(askAnswer.trim()) }">
          <span class="ask-letter">{{ askOptionLetter(pendingQuestion.options.length) }}</span>
          <span class="ask-text">
            <strong>Other</strong>
            <input
              :value="askAnswer"
              type="text"
              :placeholder="pendingQuestion.options.length ? 'Enter a different answer…' : 'Type your answer…'"
              aria-label="Custom answer"
              @input="updateAskAnswer(($event.target as HTMLInputElement).value)"
            />
          </span>
        </label>
      </div>
      <footer>
        <div class="ask-attach">
          <button type="button" title="Attach images" aria-label="Attach images" @click="askImageInput?.click()">Image</button>
          <small>{{ pendingQuestion.allowMultiple ? 'You may combine choices, text, and images.' : 'Choose an option, type an answer, or attach images.' }}</small>
          <input ref="askImageInput" type="file" accept="image/*" multiple hidden @change="onAskImagePick" />
        </div>
        <button
          class="ask-submit"
          type="submit"
          :disabled="answeringQuestion || (!askAnswer.trim() && !selectedAskOptions.length && !askImages.length)"
        >
          {{ answeringQuestion ? 'Sending…' : 'Continue' }}
        </button>
      </footer>
    </form>
  </section>

  <div v-if="queuedFollowUps.length" class="queued-followups" aria-label="Queued follow-up messages" aria-live="polite">
    <article v-for="item in queuedFollowUps" :key="item.id" class="queued-followup">
      <p>{{ item.text }}</p>
      <button
        class="queued-followup-steer"
        type="button"
        :disabled="steeringQueuedId === item.id || !busy"
        :aria-label="`Steer with ${item.text}`"
        title="Inject this follow-up into the running turn"
        @click="steerQueuedFollowUp(item)"
      >
        {{ steeringQueuedId === item.id ? 'Sending…' : 'Steer' }}
      </button>
      <button class="queued-followup-remove" type="button" aria-label="Remove queued message" @click="removeQueuedFollowUp(item.id)">×</button>
    </article>
  </div>

  <form ref="composer" class="agent-input" @submit.prevent="send">
    <div class="composer-wrap">
      <textarea
        v-model="prompt"
        placeholder="Continue the conversation…"
        @keydown.enter.exact.prevent="send"
      />
      <button
        class="send-button"
        :class="{ stop: busy }"
        type="button"
        :disabled="busy ? stopping : !prompt.trim()"
        :aria-label="busy ? (stopping ? 'Stopping generation' : 'Stop generation') : 'Send'"
        :title="busy ? (stopping ? 'Stopping…' : 'Stop generation') : 'Send'"
        @click="busy ? stopGeneration() : send()"
      >
        <svg v-if="busy" viewBox="0 0 24 24" aria-hidden="true"><rect x="7" y="7" width="10" height="10" rx="1.5" /></svg>
        <svg v-else viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12h14m-6-6 6 6-6 6" /></svg>
      </button>
    </div>
    <div class="input-footer">
      <div class="composer-picks">
        <div class="picker" @pointerleave="modelOpen = false">
          <button class="picker-trigger model-trigger" type="button" :disabled="busy" :aria-expanded="modelOpen" aria-label="Model provider" @click="togglePicker('model')">
            <span class="picker-label">{{ selectedProvider?.name || 'Connection' }}</span>
            <strong>{{ selectedProvider?.model || 'Choose model' }}</strong><span class="picker-chevron">⌄</span>
          </button>
          <div v-if="modelOpen" class="picker-popover model-popover" role="listbox" aria-label="Choose model">
            <button v-for="provider in providers" :key="provider.id" type="button" class="model-option" :class="{ selected: provider.id === selectedProviderId }" @click="chooseProvider(provider.id)">
              <strong>{{ provider.model }}</strong><small>{{ provider.name }} · {{ provider.provider.replaceAll('_', ' ') }}</small>
            </button>
            <button v-if="!providers.length" type="button" @click="settingsOpen = true; modelOpen = false">Configure provider</button>
          </div>
        </div>
        <div class="picker" @pointerleave="effortOpen = false">
          <button class="picker-trigger effort-trigger" type="button" :disabled="busy" :aria-expanded="effortOpen" aria-label="Thinking effort" @click="togglePicker('effort')">
            <span class="picker-label">Thinking</span><strong>{{ EFFORTS.find(option => option.value === effort)?.label }}</strong><span class="picker-chevron">⌄</span>
          </button>
          <div v-if="effortOpen" class="picker-popover effort-popover" role="listbox" aria-label="Thinking effort options">
            <button v-for="option in EFFORTS" :key="option.value" type="button" :class="{ selected: option.value === effort }" @click="chooseEffort(option.value)">
              {{ option.label }}
            </button>
          </div>
        </div>
      </div>
      <div class="more-menu" @pointerenter="moreOpen = true" @pointerleave="closeMenus()">
        <button class="more-trigger" type="button" :aria-expanded="moreOpen" aria-label="More options" title="More options" @click="moreOpen = !moreOpen; modelOpen = false; effortOpen = false">•••</button>
        <div v-if="moreOpen" class="more-popover">
          <div v-if="usage" class="usage-details">
            <span>Cache <strong>{{ usage.cache_hit_rate === null ? '—' : `${(usage.cache_hit_rate * 100).toFixed(1)}%` }}</strong></span>
            <span>Tokens <strong>{{ formatTokenCount(usage.input_tokens + usage.output_tokens) }}</strong></span>
            <span title="Output tokens per second of model generation">Speed <strong>{{ usage.tokens_per_second === null ? '—' : `${usage.tokens_per_second.toFixed(1)} tok/s` }}</strong></span>
            <span
              v-if="contextUsage && compactionMaxTokens > 0"
              class="usage-context"
              @pointerenter="contextOpen = true"
              @pointerleave="contextOpen = false"
              @focusin="contextOpen = true"
              @focusout="contextOpen = false"
            >
              <span>Context <strong>{{ Math.round((contextUsage.input_tokens + contextUsage.output_tokens) / compactionMaxTokens * 100) }}%</strong></span>
              <ContextCompositionRing
                v-if="contextOpen"
                :composition="contextComposition"
                :current-tokens="contextUsage.input_tokens + contextUsage.output_tokens"
                :max-tokens="compactionMaxTokens"
                always-open
              />
            </span>
          </div>
          <button v-if="!browserConnected" type="button" :disabled="browserConnecting || !conversationId" @click="connectBrowser(); moreOpen = false">{{ browserConnecting ? 'Connecting…' : 'Connect page' }}</button>
          <button v-else type="button" @click="disconnectBrowser(); moreOpen = false">Disconnect page</button>
          <button v-if="browserAutoApprove" type="button" @click="rememberBrowserApproval(false); moreOpen = false">Ask before page edits again</button>
          <button type="button" :disabled="savingIds.length > 0 || busy" @click="saveAll(); moreOpen = false">Save all artifacts</button>
        </div>
      </div>
    </div>
    <p v-if="notice" class="notice" :class="noticeKind">{{ notice }}</p>
  </form>
</template>

<style>
:root {
  --accent: #476957;
  --accent-dark: #345243;
  --accent-soft: #e5eee9;
  --text: #1d1d1f;
  --secondary: #6e6e73;
  --tertiary: #929298;
  --line: rgba(29, 29, 31, .1);
  font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Helvetica Neue", sans-serif;
  font-size: 16px;
  color: var(--text);
  background: #fff;
}

* { box-sizing: border-box; }

html, body { height: 100%; }
body { margin: 0; overflow: hidden; background: #fff; }

/* Only the thread flexes and scrolls. The optional settings section takes its
   own height without moving the composer below the viewport. */
#app {
  display: flex;
  flex-direction: column;
  height: 100%;
}
#app > :not(.thread) { flex-shrink: 0; }

button {
  border: 1px solid var(--line);
  border-radius: .55rem;
  color: #55555a;
  background: #f7f8f7;
  font: inherit;
  font-size: .72rem;
  cursor: pointer;
}
button:hover:not(:disabled) { color: var(--accent-dark); background: var(--accent-soft); border-color: rgba(71, 105, 87, .3); }
button:disabled { opacity: .45; cursor: not-allowed; }
button svg { width: .9rem; height: .9rem; fill: none; stroke: currentColor; stroke-width: 1.7; stroke-linecap: round; stroke-linejoin: round; }

/* Header: the app's conversation header, sized for a panel. */
.chat-header { min-height: 3.6rem; display: flex; align-items: center; gap: .62rem; padding: .6rem .8rem; border-bottom: 1px solid var(--line); }
.chat-header { min-height: 3.35rem; padding: .55rem 1rem; border-bottom-color: rgba(29,29,31,.055); }
.header-actions { margin-left: auto; }
.header-actions button { background: transparent; border-color: transparent; color: #8a948d; }
.header-actions button:hover { background: #f3f6f4; }
.header-actions .close-panel { font-size: 1.25rem; font-weight: 350; }
/* The product mark is the app's logo, so the panel wears the same icon the
   browser app and the toolbar button do. */
.mark, .welcome-mark { display: grid; place-items: center; flex: 0 0 auto; width: 1.75rem; height: 1.75rem; }
.mark img, .welcome-mark img { display: block; width: 100%; height: 100%; object-fit: contain; filter: drop-shadow(0 3px 4px rgba(53, 83, 67, .18)); }
.chat-title { min-width: 0; flex: 1 1 auto; }
.chat-title strong { display: block; overflow: hidden; font-size: .84rem; font-weight: 620; text-overflow: ellipsis; white-space: nowrap; }
.chat-title small { display: flex; align-items: center; gap: .32rem; margin-top: .12rem; color: var(--tertiary); font-size: .6rem; }
.status-dot { width: .42rem; height: .42rem; flex: 0 0 auto; border-radius: 50%; background: #c2c8c4; }
.status-dot.online { background: #347b51; }
.header-actions { display: flex; gap: .28rem; }
.header-actions button { display: grid; place-items: center; width: 1.9rem; height: 1.9rem; padding: 0; }

.settings { display: grid; gap: .45rem; padding: .6rem .8rem; border-bottom: 1px solid var(--line); background: #f7f8f7; }
/* Previous conversations: rebind this page to any recent session. */
.session-history { display: grid; gap: .2rem; max-height: 12rem; padding: .5rem .6rem; overflow-y: auto; border-bottom: 1px solid var(--line); background: #f7f8f7; scrollbar-width: thin; }
.session-history header { display: flex; align-items: baseline; justify-content: space-between; gap: .5rem; padding: 0 .25rem .15rem; }
.session-history header strong { color: #3f624e; font-size: .66rem; font-weight: 740; letter-spacing: .025em; }
.session-history header small { color: var(--tertiary); font-size: .58rem; }
.session-history-empty { margin: 0; padding: .3rem .25rem; color: var(--tertiary); font-size: .62rem; }
.session-history-item { display: grid; gap: .1rem; width: 100%; min-height: 2.5rem; padding: .4rem .55rem; border: 1px solid transparent; border-radius: .6rem; background: transparent; text-align: left; }
.session-history-item:hover { border-color: #e0e6e2; background: #fff; }
.session-history-item.current { border-color: #b9cdc1; background: #edf4ef; }
.session-history-item strong { overflow: hidden; color: #45594b; font-size: .7rem; font-weight: 620; text-overflow: ellipsis; white-space: nowrap; }
.session-history-item small { overflow: hidden; color: var(--tertiary); font-size: .58rem; text-overflow: ellipsis; white-space: nowrap; }
.settings label { display: grid; gap: .2rem; font-size: .68rem; color: var(--secondary); }
.settings-row { display: flex; align-items: center; gap: .5rem; }
.settings-row button { padding: .3rem .6rem; }
.settings p { margin: 0; color: var(--tertiary); font-size: .62rem; line-height: 1.5; }
.settings input { padding: .38rem .5rem; border: 1px solid var(--line); border-radius: .5rem; font: inherit; font-size: .72rem; color: var(--text); background: #fff; }
.settings code { padding: .1em .3em; border-radius: .3em; background: #eceaea; font-size: .92em; }

/* Thread: user turns right-aligned, answers as plain Markdown, like the app. */
.thread { flex: 1 1 0; min-height: 0; padding: 1.05rem 1.15rem .4rem; overflow-y: auto; overscroll-behavior: contain; scrollbar-width: thin; scrollbar-gutter: stable; }
.turn { font-size: .9rem; line-height: 1.65; }
.turn + .turn { margin-top: .8rem; }
.turn.user { display: flex; justify-content: flex-end; padding-left: 12%; }
.prompt-bubble { width: fit-content; max-width: 100%; padding: .6rem .85rem; border-radius: 1rem 1rem .3rem 1rem; color: #34483d; background: #eef1ef; white-space: pre-wrap; }
.user-entry { min-width: 0; display: grid; justify-items: end; gap: .18rem; }
.steering-pending { margin: 0; color: #5f7d69; font-size: .6rem; }
.pending-note { margin: 0; color: var(--tertiary); font-size: .72rem; }
.turn-response { min-width: 0; padding-top: .68rem; }
.streaming-dots { display: inline-flex; gap: .2rem; margin-top: .45rem; }
.streaming-dots i { width: .2rem; height: .2rem; border-radius: 50%; background: #72907d; animation: activity-pulse 1.1s ease-in-out infinite; }
.streaming-dots i:nth-child(2) { animation-delay: .15s; }
.streaming-dots i:nth-child(3) { animation-delay: .3s; }
@keyframes activity-pulse { 50% { opacity: .4; } }
@media (prefers-reduced-motion: reduce) { .streaming-dots i { animation: none; } }

/* One artifact the agent created or changed, with the Save that publishes it. */
.artifact-card { display: flex; align-items: center; gap: .5rem; padding: .5rem .6rem; border: 1px solid rgba(71, 105, 87, .18); border-radius: .7rem; background: #fafcfb; }
.artifact-card.saved { border-color: #e6e9e7; background: #fbfbfb; }
.artifact-copy { min-width: 0; flex: 1 1 auto; }
.artifact-copy strong, .artifact-copy small { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.artifact-copy strong { font-size: .72rem; font-weight: 620; }
.artifact-copy small { margin-top: .1rem; color: var(--tertiary); font-size: .58rem; text-transform: uppercase; letter-spacing: .04em; }
.artifact-card button { flex: 0 0 auto; padding: .3rem .6rem; }
.saved-note { flex: 0 0 auto; color: #347b51; font-size: .8rem; }

.welcome { display: grid; place-items: center; gap: .1rem; padding: 2.2rem .6rem; text-align: center; }
.welcome-mark { width: 2.6rem; height: 2.6rem; }
.welcome h2 { margin: 1rem 0 .35rem; font-size: 1rem; letter-spacing: -.025em; }
.welcome p { max-width: 20rem; margin: 0; color: var(--secondary); font-size: .72rem; line-height: 1.6; }
.prompt-hints { display: flex; flex-wrap: wrap; justify-content: center; gap: .4rem; margin-top: 1rem; }
.prompt-hints button { padding: .42rem .6rem; border-radius: .58rem; color: #606065; background: rgba(247, 247, 248, .9); font-size: .62rem; }

/* Ask-user card: the running turn is suspended until this is answered, so it
   carries the same choices, free text and images the web composer offers. */
.ask-user { margin: .55rem .8rem 0; padding: .8rem; border: 1px solid rgba(71,105,87,.16); border-radius: .9rem; background: #f8faf8; box-shadow: 0 3px 14px rgba(42,65,51,.045); }
.ask-user header { display: flex; align-items: center; justify-content: space-between; gap: .6rem; }
.ask-user header > div { min-width: 0; display: flex; align-items: baseline; gap: .4rem; }
.ask-user header div > span { color: #3f624e; font-size: .66rem; font-weight: 740; letter-spacing: .025em; }
.ask-user header small { color: #858e88; font-size: .58rem; }
.ask-waiting { display: inline-flex; align-items: center; gap: .3rem; color: #738078; font-size: .58rem; white-space: nowrap; }
.ask-waiting i { width: .36rem; height: .36rem; border-radius: 50%; background: #65a67d; box-shadow: 0 0 0 3px rgba(101,166,125,.1); }
.ask-user h3 { margin: .55rem 0 .65rem; color: #252a27; font-size: .82rem; font-weight: 650; line-height: 1.5; }
.ask-choices { display: grid; gap: .3rem; min-width: 0; }
.ask-choice { min-width: 0; min-height: 2.4rem; display: grid; grid-template-columns: 1.5rem minmax(0,1fr); align-items: center; gap: .5rem; padding: .3rem .6rem .3rem .4rem; border: 1px solid #e0e6e2; border-radius: .68rem; color: #505b54; background: rgba(255,255,255,.88); cursor: pointer; font-size: .7rem; }
.ask-choice:hover { border-color: #b9c9bf; background: #fff; }
.ask-choice.selected { border-color: #87a593; color: #294d39; background: #edf4ef; }
.ask-choice > input[type='radio'], .ask-choice > input[type='checkbox'] { position: absolute; width: 1px; height: 1px; opacity: 0; pointer-events: none; }
.ask-letter { width: 1.5rem; height: 1.5rem; display: grid; place-items: center; border: 1px solid #d8e0db; border-radius: .45rem; color: #657269; background: #f4f7f5; font-size: .6rem; font-weight: 750; }
.ask-choice.selected .ask-letter { border-color: #88a593; color: #315541; background: #fff; }
.ask-text { min-width: 0; line-height: 1.4; }
.ask-choice.custom { align-items: start; }
.ask-choice.custom .ask-letter { margin-top: .1rem; }
.ask-text strong { display: block; margin-bottom: .15rem; color: #56625a; font-size: .64rem; }
.ask-choice.custom input[type='text'] { width: 100%; padding: 0; border: 0; outline: 0; color: #252a27; background: transparent; font: inherit; font-size: .74rem; }
.ask-choice.custom input::placeholder { color: #a1a8a3; }
.ask-user footer { display: flex; align-items: center; justify-content: space-between; gap: .6rem; margin-top: .6rem; }
.ask-images { display: flex; gap: .4rem; margin-bottom: .55rem; overflow-x: auto; scrollbar-width: thin; }
.ask-images figure { position: relative; width: 3.2rem; height: 3.2rem; flex: 0 0 auto; margin: 0; }
.ask-images img { width: 100%; height: 100%; display: block; border: 1px solid #dbe3dd; border-radius: .55rem; object-fit: cover; background: #eef1ef; }
.ask-images button { position: absolute; top: -.28rem; right: -.28rem; width: 1rem; height: 1rem; display: grid; place-items: center; padding: 0; border: 2px solid #fff; border-radius: 50%; color: #fff; background: #59645d; font-size: .67rem; line-height: 1; }
.ask-attach { min-width: 0; display: flex; align-items: center; gap: .45rem; }
.ask-attach > button { min-height: 1.9rem; padding: 0 .55rem; border: 1px solid #d6e0d9; border-radius: .55rem; color: #557062; background: #fff; font-size: .63rem; font-weight: 650; }
.ask-attach > button:hover { border-color: #9db4a5; color: #315541; background: #edf4ef; }
.ask-attach small { min-width: 0; overflow: hidden; color: #858e88; font-size: .58rem; text-overflow: ellipsis; white-space: nowrap; }
.ask-submit { min-height: 1.9rem; padding: 0 .8rem; border: 0; border-radius: .6rem; color: #fff; background: #476957; font-size: .68rem; font-weight: 680; }
.ask-submit:hover:not(:disabled) { background: #395b48; }
.ask-submit:disabled { opacity: .42; }

/* Queued follow-ups mirror the web composer: Enter queues while a turn runs,
   and each item can be injected into that turn or dropped. */
.queued-followups { max-height: 8rem; margin: .45rem .8rem 0; padding: .2rem .3rem; overflow-y: auto; border: 1px solid rgba(29,29,31,.08); border-radius: .8rem; background: #f3f6f4; }
.queued-followup { min-width: 0; display: flex; align-items: center; gap: .4rem; padding: .3rem .25rem; }
.queued-followup + .queued-followup { border-top: 1px solid rgba(54,73,61,.1); }
.queued-followup p { min-width: 0; flex: 1 1 auto; margin: 0; overflow: hidden; color: #59635d; font-size: .68rem; text-overflow: ellipsis; white-space: nowrap; }
.queued-followup button { flex: 0 0 auto; }
.queued-followup-steer { padding: .28rem .5rem; border-color: rgba(71,105,87,.28); color: #3f5b4a; background: #eef4f0; }
.queued-followup-remove { width: 1.5rem; height: 1.5rem; padding: 0; border: 0; background: transparent; color: #93a096; font-size: .9rem; line-height: 1; }
.queued-followups + .agent-input { margin-top: .35rem; }

/* Composer: the app's `.agent-input`, with its model and effort picks. */
.agent-input { position: relative; container-type: inline-size; container-name: composer-footer; margin: .45rem .8rem .85rem; padding: .35rem; border: 1px solid #e3e8e4; border-radius: 1.15rem; background: #fff; box-shadow: 0 6px 24px rgba(37, 51, 42, .055); }
.agent-input:focus-within { border-color: rgba(71, 105, 87, .4); box-shadow: 0 0 0 3px rgba(71, 105, 87, .1), 0 5px 20px rgba(0, 0, 0, .06); }
.composer-wrap { position: relative; z-index: 1; }
.agent-input textarea { display: block; width: 100%; min-height: 4.3rem; max-height: 8rem; padding: .75rem 3.2rem .2rem .8rem; resize: vertical; border: 0; outline: 0; color: var(--text); caret-color: var(--text); background: transparent; font-family: inherit; font-size: .9rem; line-height: 1.5; }
.send-button { position: absolute; right: .35rem; top: .5rem; display: grid; place-items: center; width: 2.3rem; height: 2.3rem; padding: 0; border: 0; border-radius: .7rem; color: #fff; background: var(--accent); }
.send-button svg { width: 1.1rem; height: 1.1rem; transform: rotate(-90deg); }
.send-button:hover:not(:disabled) { color: #fff; background: var(--accent-dark); border-color: transparent; }
.send-button:disabled { opacity: .35; }
.send-button.stop { background: #59635d; }
.send-button.stop svg { transform: none; fill: currentColor; }
.input-footer { position: relative; z-index: 2; display: flex; align-items: center; justify-content: space-between; gap: .35rem; padding: .1rem .25rem .2rem .45rem; }
.composer-picks { display: flex; min-width: 0; align-items: center; gap: .25rem; }
.picker { position: relative; min-width: 0; }
.picker-trigger { position: relative; display: grid; grid-template-columns: minmax(0,1fr) auto; gap: .05rem .4rem; align-items: center; min-width: 0; max-width: 11rem; padding: .25rem .4rem; border: 0; border-radius: .55rem; background: transparent; text-align: left; }
.picker-trigger:hover, .picker-trigger[aria-expanded="true"] { background: #f3f6f4; }
.picker-trigger .picker-label { grid-column: 1; overflow: hidden; color: #98a19b; font-size: .58rem; text-overflow: ellipsis; white-space: nowrap; }
.picker-trigger strong { grid-column: 1; overflow: hidden; color: #45594b; font-size: .72rem; font-weight: 620; text-overflow: ellipsis; white-space: nowrap; }
.picker-trigger .picker-chevron { grid-column: 2; grid-row: 1 / 3; color: #9ea8a0; font-size: 1rem; }
.model-trigger { width: 9.6rem; }
.effort-trigger { width: 5.8rem; }
/* Menus sit flush against their trigger: the pointer never crosses a gap, so
   leaving the trigger or the menu can close it immediately. */
.picker-popover { position: absolute; z-index: 20; bottom: 100%; left: 0; width: min(17rem,calc(100vw - 3rem)); max-height: 50dvh; padding: .35rem; overflow-y: auto; border: 1px solid #e3e9e4; border-radius: .8rem; background: #fff; box-shadow: 0 16px 44px rgba(30,45,34,.16); }
.picker-popover button { display: grid; gap: .1rem; width: 100%; min-height: 2.4rem; padding: .45rem .6rem; border: 0; border-radius: .55rem; background: transparent; text-align: left; }
.picker-popover button:hover, .picker-popover button.selected { background: #edf4ef; }
.picker-popover button strong { overflow: hidden; color: #435649; text-overflow: ellipsis; white-space: nowrap; }
.picker-popover button small { overflow: hidden; color: #8c9790; text-overflow: ellipsis; white-space: nowrap; }
.effort-popover { width: 9rem; }
.more-trigger { flex: 0 0 auto; width: 2rem; height: 2rem; border: 0; border-radius: 50%; background: transparent; color: #7c8b80; letter-spacing: .07em; }
.more-trigger:hover, .more-trigger[aria-expanded="true"] { background: #eef3ef; }
.more-menu { position: relative; flex: 0 0 auto; }
.more-popover { position: absolute; z-index: 22; right: 0; bottom: 100%; display: grid; gap: .2rem; width: min(15rem,calc(100vw - 2.5rem)); padding: .45rem; border: 1px solid #e3e9e4; border-radius: .8rem; background: #fff; box-shadow: 0 16px 44px rgba(30,45,34,.16); }
.more-popover > button { padding: .5rem .65rem; border: 0; background: transparent; text-align: left; }
.more-popover > button:hover { background: #edf4ef; }
.usage-details { display: grid; gap: .35rem; padding: .5rem .65rem; color: #8b978e; font-size: .64rem; }
.usage-details span { display: flex; justify-content: space-between; gap: .5rem; }
.usage-details strong { color: #425748; }
/* The Context row owns the pie: hovering it shows the shared ring plus its
   breakdown beside the menu instead of covering the menu's own actions. */
.usage-details .usage-context { align-items: center; }
.usage-details .usage-context .context-ring-control { position: static; margin: 0; padding: 0; cursor: pointer; }
.usage-details .usage-context .context-ring { width: 1.35rem; height: 1.35rem; }
/* The ring's own popover is positioned against the menu, so the pie and its
   breakdown sit beside the `•••` menu instead of covering its metrics. */
.usage-details .usage-context .context-popover { right: calc(100% + .4rem); bottom: 0; }
/* A panel too narrow for that room puts the pie above the menu instead, so
   neither the percentages nor the legend are clipped. */
@container composer-footer (max-width: 430px) {
  .usage-details .usage-context .context-popover { right: -.35rem; bottom: calc(100% + .35rem); }
}
.browser-consent { margin: 0 .8rem .25rem; padding: .85rem; max-height: 40dvh; overflow: auto; border: 1px solid #e4ebe6; border-radius: 1rem; background: #fff; box-shadow: 0 10px 35px rgba(30,45,34,.09); font-size: .75rem; }
.browser-consent header { display: flex; gap: .55rem; align-items: center; }
.browser-consent header > div { min-width: 0; display: grid; gap: .1rem; }
.browser-consent header strong { font-size: .8rem; color: #354d3d; }
.browser-consent header small { color: #87938a; line-height: 1.4; }
.consent-mark { display: grid; place-items: center; width: 1.55rem; height: 1.55rem; flex: 0 0 auto; border-radius: .5rem; color: #456b53; background: #edf4ef; }
.browser-consent dl { display: grid; gap: .45rem; margin: .75rem 0 .5rem; padding: .65rem; border-radius: .7rem; background: #f7f9f7; }
.browser-consent dl > div { display: grid; grid-template-columns: 3.4rem minmax(0,1fr); gap: .5rem; }
.browser-consent dt { color: #929e95; }
.browser-consent dd { min-width: 0; margin: 0; overflow-wrap: anywhere; color: #405649; }
.browser-consent code { font-size: .72rem; }
.consent-value { max-height: 4.5rem; overflow-y: auto; white-space: pre-wrap; }
.browser-consent p { margin: .4rem 0 .65rem; overflow-wrap: anywhere; }
.browser-consent .consent-actions { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: .5rem; }
.browser-consent button { padding: .45rem .7rem; }
.browser-consent button.allow { border-color: #476957; background: #476957; color: #fff; }
.browser-consent button.allow-session { border-color: #cbd9d1; color: #3f5b4a; background: #eef4f0; }
.consent-warning { color: #796339; font-size: .65rem; }
.consent-note { margin: -.25rem 0 .55rem; color: var(--tertiary); font-size: .6rem; }
.notice { margin: .15rem .6rem .35rem; font-size: .66rem; }
.notice.ok { color: var(--accent-dark); }
.notice.error { color: #a33e3e; }
@media (max-width: 355px) {
  .model-trigger { width: 7.4rem; }
  .effort-trigger { width: 5.1rem; }
  .picker-popover { width: min(15rem,calc(100vw - 2.5rem)); }
}
</style>
