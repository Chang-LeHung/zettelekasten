export interface TagRecord {
  id: string
  name: string
  parent_id: string | null
  description: string | null
  color: string | null
  created_at: string
  updated_at: string
  path: string
  normalized_path: string
}

export interface Tag extends TagRecord {
  direct_count: number
  total_count: number
  children: Tag[]
}

export interface TagCreateInput {
  path: string
  description?: string | null
  color?: string | null
}

export interface Card {
  id: string
  type: string
  title: string
  content: string
  raw_content: string | null
  summary: string | null
  status: string
  created_at: string
  updated_at: string
  tags: string[]
  metadata: Record<string, unknown>
}

export interface CardCreateRequest {
  type: string
  title: string
  content: string
  raw_content?: string | null
  summary?: string | null
  tags: string[]
  metadata?: Record<string, unknown>
}

export interface CardListOptions {
  query?: string
  tagId?: string | null
  artifactTypes?: LibraryItemType[]
}

export type LibraryItemType = 'card' | 'article' | 'slides' | 'latex_pdf'

export interface LibraryItem {
  id: string
  session_id: string
  item_type: LibraryItemType
  title: string
  subtitle: string | null
  summary: string | null
  content: string
  raw_content: string | null
  card_type: CardType | null
  status: string
  tags: string[]
  metadata: Record<string, unknown>
  created_at: string
  updated_at: string
}

export interface LibraryItemUpdate {
  title: string
  subtitle: string | null
  summary: string | null
  content: string
  tags?: string[] | null
  metadata?: Record<string, unknown> | null
}

export interface SuggestedTag {
  path: string
  existing: boolean
  confidence: number
  reason?: string | null
}

export type CardType = 'note' | 'idea' | 'quote' | 'todo' | 'reference'
export type ArtifactType = 'card' | 'article' | 'image' | 'slides' | 'latex_pdf'
export type ArtifactStatus = 'draft' | 'saved'
export type SessionAssetType = 'text' | 'image' | 'link' | 'file'
export type ReasoningEffort = 'off' | 'low' | 'medium' | 'high'
export type ShellApprovalMode = 'review' | 'allow_all'

export interface RuntimeSettings {
  max_message_images: number
  max_turn_iterations: number
  max_asset_size_bytes: number
  compaction_max_tokens: number
  compaction_keep_recent_tokens: number
}

export type ProcessRole = 'scheduler' | 'worker'
export type ProcessHeartbeatStatus = 'starting' | 'running' | 'stopped'

export interface ProcessHeartbeatInput {
  role: ProcessRole
  instance_id: string
  pid: number
  status: ProcessHeartbeatStatus
  metadata?: Record<string, string>
}

export interface ProcessHeartbeatRecord extends Required<ProcessHeartbeatInput> {
  started_at: string
  heartbeat_at: string
  stopped_at: string | null
}

export interface ProcessInstanceHealth {
  instance_id: string
  pid: number
  status: ProcessHeartbeatStatus
  heartbeat_at: string
  age_seconds: number
}

export interface ProcessRoleHealth {
  role: ProcessRole
  healthy: boolean
  active_processes: number
  required_processes: number
  stale_after_seconds: number
  instances: ProcessInstanceHealth[]
}

export interface ProcessHealthReport {
  healthy: boolean
  checked_at: string
  roles: ProcessRoleHealth[]
}

export type ScheduledTaskRunStatus =
  | 'pending'
  | 'running'
  | 'succeeded'
  | 'failed'
  | 'skipped'
  | 'cancelled'
  | 'interrupted'

export type ScheduledTaskTrigger = 'scheduled' | 'manual'

export interface CronSchedule {
  expression: string
  timezone: string
}

export interface ScheduledTaskAction {
  kind: string
  payload: Record<string, unknown>
}

export interface ScheduledTaskInput {
  name: string
  schedule: CronSchedule
  action: ScheduledTaskAction
  enabled?: boolean
  timeout_seconds?: number
  overlap_policy?: 'skip'
}

export interface ScheduledTask {
  id: string
  name: string
  enabled: boolean
  schedule: CronSchedule
  action: ScheduledTaskAction
  next_run_at: string
  timeout_seconds: number
  overlap_policy: 'skip'
  lease_run_id: string | null
  lease_expires_at: string | null
  created_at: string
  updated_at: string
}

export interface ScheduledTaskRun {
  id: string
  task_id: string
  scheduled_for: string
  trigger_kind: ScheduledTaskTrigger
  status: ScheduledTaskRunStatus
  idempotency_key: string
  action: ScheduledTaskAction
  started_at: string | null
  completed_at: string | null
  output: Record<string, unknown> | null
  error_type: string | null
  error_message: string | null
  created_at: string
  updated_at: string
}

/** Channel plugins are discovered at runtime, so platform ids stay open. */
export type ChannelType = string

export interface ChannelPluginInfo {
  channel_type: ChannelType
  label: string
}

export interface Channel {
  id: string
  name: string
  channel_type: ChannelType
  provider_id: string
  enabled: boolean
  reasoning_effort: ReasoningEffort
  allow_coding: boolean
  config: Record<string, unknown>
  secret_keys: string[]
  created_at: string
  updated_at: string
}

export interface ChannelUpdate {
  name?: string
  provider_id?: string
  enabled?: boolean
  reasoning_effort?: ReasoningEffort
  allow_coding?: boolean
}

export type ChannelLoginStatus = 'pending' | 'scanned' | 'verify_required' | 'connected' | 'failed' | 'expired'

export interface ChannelLoginStart {
  channel_type?: ChannelType
  provider_id: string
  name?: string
}

export interface ChannelLogin {
  id: string
  channel_type: ChannelType
  provider_id: string
  name: string | null
  status: ChannelLoginStatus
  qr_url: string | null
  qr_data_url: string | null
  message: string | null
  channel_id: string | null
  expires_at: string
  created_at: string
  updated_at: string
}

export interface AgentUsageActivityDay {
  date: string
  requests: number
  input_tokens: number
  output_tokens: number
  cache_read_tokens: number
  cache_write_tokens: number
  reasoning_tokens: number
  total_tokens: number
}

export interface AgentModelUsageActivitySeries {
  provider: string | null
  model: string | null
  days: AgentUsageActivityDay[]
}

export interface AgentContextComposition {
  system_prompt: number
  tool_prompt: number
  tool_output: number
  user: number
  assistant: number
}

export interface SessionAsset {
  id: string
  session_id: string
  asset_type: SessionAssetType
  name: string
  mime_type: string | null
  size_bytes: number
  sha256: string | null
  /** Inline content stored directly in the database; no file URL exists. */
  text_content: string | null
  /** External URL only. It is not an ObjectStore key. */
  source_url: string | null
  /**
   * Relative ObjectKey for bytes owned by this asset.
   * Example: `assets/sessions/<session_id>/<asset_id>.png`.
   */
  storage_path: string | null
  /**
   * Relative ObjectKey for another stored object referenced by this asset.
   * Importing a StaticAsset stores `assets/static/<asset_id>.pdf` here.
   */
  source_path: string | null
  /**
   * Response-only URL derived from `storage_path` or `source_path`.
   * Example: `/api/files/assets/static/<asset_id>.pdf`. Never persisted.
   */
  content_url: string | null
  metadata: Record<string, unknown>
  created_at: string
  updated_at: string
}

export interface StaticAsset {
  id: string
  name: string
  mime_type: string | null
  size_bytes: number
  sha256: string
  /**
   * Relative ObjectKey for the globally owned file.
   * Example: `assets/static/<asset_id>.pdf`.
   */
  storage_path: string
  /** Derived `/api/files/...` URL; clients should not construct it themselves. */
  content_url: string
  metadata: Record<string, unknown>
  created_at: string
  updated_at: string
}

export interface AnalysisMessage {
  role: 'user' | 'assistant'
  content: string
  parts?: MessagePart[]
  steering_status?: 'waiting' | 'responded'
  reasoning?: string
  activities?: AgentToolActivity[]
  timeline?: AgentTimelineEntry[]
  duration_ms?: number
  generation_duration_ms?: number
  usage?: AgentModelUsage
  error?: string
}

export interface MessageTextPart {
  type: 'text'
  text: string
}

export interface MessageImagePart {
  type: 'image'
  name: string
  mime_type: string | null
  content_url: string
}

export type MessagePart = MessageTextPart | MessageImagePart

export interface AgentModelUsage {
  input_tokens: number
  output_tokens: number
  cache_read_tokens: number
  cache_write_tokens: number
  reasoning_tokens: number
}

export interface AgentToolDefinitionTrace {
  name: string
  description: string
  parameters: Record<string, unknown>
  deferred: boolean
}

export interface AgentServerToolDefinitionTrace {
  type: string
  configuration: Record<string, unknown>
}

export interface AgentModelRequestTrace {
  schema_version: number
  tools: AgentToolDefinitionTrace[]
  server_tools: AgentServerToolDefinitionTrace[]
}

export interface AgentToolActivity {
  id: string
  name: string
  state: 'started' | 'succeeded' | 'failed' | 'cancelled'
  arguments?: Record<string, unknown>
  output?: unknown
  error_message?: string | null
  duration_ms?: number
}

export interface AgentServerToolActivity {
  id: string
  name: string
  state: 'started' | 'streaming' | 'succeeded' | 'failed'
  input: Record<string, unknown> | null
  input_delta?: string
  output?: unknown
  error_code?: string | null
}

export interface AgentCompactionActivity {
  state: 'started' | 'streaming' | 'completed'
  applied?: boolean | null
  content: string
  reasoning: string
  compressed_from?: number | null
  compressed_to?: number | null
  kept_from?: number | null
  kept_to?: number | null
}

export type AgentTimelineEntry =
  | { id: string; type: 'reasoning'; content: string }
  | { id: string; type: 'message'; content: string }
  | { id: string; type: 'tool'; activity: AgentToolActivity }
  | { id: string; type: 'server_tool'; activity: AgentServerToolActivity }
  | { id: string; type: 'compaction'; activity: AgentCompactionActivity }

export interface AgentCustomEvent {
  name: string
  payload: Record<string, unknown>
}

export interface AgentSteeringMessage {
  content: string
  parts: MessagePart[]
}

export interface AgentSlashCommand {
  id: string
  name: string
  description: string
  type: string
}

/**
 * One conversation resource the composer may reference with an `@` token.
 * `name` is the token without its trigger, `label` is the user-facing name.
 */
export interface AgentAtCommand {
  id: string
  kind: string
  name: string
  label: string
  description: string
}

export interface AgentTodoItem {
  content: string
  status: 'pending' | 'processing' | 'completed'
}

export interface AgentTodoState {
  todos: AgentTodoItem[]
  processing_index: number | null
  processing: AgentTodoItem | null
  completed: boolean
}

export interface AgentStreamCallbacks {
  onStatus?: (state: string) => void
  onModelStarted?: () => void
  onUsage?: (usage: AgentModelUsage) => void
  onReasoning?: (content: string) => void
  onMessage?: (content: string) => void
  onSteering?: (message: AgentSteeringMessage) => void
  onTool?: (activity: AgentToolActivity) => void | Promise<void>
  onServerTool?: (activity: AgentServerToolActivity) => void
  onCompaction?: (activity: AgentCompactionActivity) => void
  onCustom?: (event: AgentCustomEvent) => void
}

export interface AgentStart {
  conversation_id: string
  artifacts: AgentArtifact[]
  assets: SessionAsset[]
}

export interface ArtifactContentBase {
  title: string
  summary: string
  suggested_tags: SuggestedTag[]
  keywords: string[]
}

export interface CardArtifactContent extends ArtifactContentBase {
  artifact_type: 'card'
  card_type: CardType
  content: string
}

export interface ArticleArtifactContent extends ArtifactContentBase {
  artifact_type: 'article'
  subtitle: string
  content: string
}

export interface ImageArtifactContent extends ArtifactContentBase {
  artifact_type: 'image'
  prompt: string
  alt_text: string
  /** External image URL only, for example `https://example.com/image.png`. */
  source_url: string | null
  /**
   * Relative ObjectKey for a locally stored image.
   * Example: `assets/sessions/<session_id>/<asset_id>.png`.
   */
  asset_path: string | null
}

export interface SlidesArtifactContent extends ArtifactContentBase {
  artifact_type: 'slides'
  subtitle: string
  content: string
}

export interface LatexPdfArtifactContent {
  artifact_type: 'latex_pdf'
  /**
   * Relative project directory ObjectKey.
   * Example: `artifacts/<session_id>/paper`.
   */
  project_path: string
  /** Plain PDF filename inside `project_path`, for example `paper.pdf`. */
  pdf_name: string
}

export type ArtifactContent = CardArtifactContent | ArticleArtifactContent | ImageArtifactContent | SlidesArtifactContent | LatexPdfArtifactContent

export interface LatexPdfArtifactCreate {
  artifact_type: 'latex_pdf'
  /** Compiled PDF basename, including `.pdf`; the server creates the project directory. */
  pdf_name: string
}

/** Content accepted when creating an artifact, before any project directory exists. */
export type ArtifactCreateContent =
  | CardArtifactContent
  | ArticleArtifactContent
  | ImageArtifactContent
  | SlidesArtifactContent
  | LatexPdfArtifactCreate

export interface AgentArtifact {
  id: string
  session_id: string
  artifact_type: ArtifactType
  status: ArtifactStatus
  /** Published content. Null until the user saves the artifact's first draft. */
  content: ArtifactContent | null
  /** Model-proposed content awaiting an explicit user save. */
  draft_content: ArtifactContent | null
  raw_content: string | null
  version: number
  metadata: Record<string, unknown>
  tags: Array<{ id: string; path: string; name: string }>
  /**
   * Response-only URL for an artifact that owns a file.
   * Example: `/api/files/artifacts/<session_id>/paper/paper.pdf`.
   * Null for inline artifacts such as cards, articles, and slides.
   */
  content_url: string | null
  created_at: string
  updated_at: string
}

export interface AgentPersistedMessage {
  id: string
  session_id: string
  request_id: string
  sequence: number
  role: 'system' | 'user' | 'assistant' | 'tool' | 'agent'
  content: string
  parts: MessagePart[]
  reasoning_content: string | null
  model: string | null
  provider: string | null
  tool_calls: Array<{ id: string; name: string; arguments: Record<string, unknown> }>
  tool_call_id: string | null
  tool_name: string | null
  tool_success: boolean | null
  attributes: Record<string, unknown>
  metadata: Record<string, unknown>
  tags: Record<string, unknown>
  input_tokens: number | null
  output_tokens: number | null
  cache_read_tokens: number | null
  cache_write_tokens: number | null
  reasoning_tokens: number | null
  total_tokens: number | null
  cache_hit_rate: number | null
  started_at: string
  completed_at: string
  duration_ns: number
  created_at: string
  updated_at: string
}

export interface AgentSession {
  id: string
  type: SessionType
  parent_session_id: string | null
  agent_name: string | null
  title: string | null
  created_at: string
  updated_at: string
  message_count: number
  messages: AgentPersistedMessage[]
  artifacts: AgentArtifact[]
  assets: SessionAsset[]
}

export type SessionType = 'normal' | 'scheduled' | 'channel'

export interface SessionModelPreference {
  provider_id: string
  provider: AIProviderKind
  model: string
}

export interface ShellApprovalSettings {
  mode: ShellApprovalMode
}

export type AIProviderKind =
  | 'openai_compatible'
  | 'responses_compatible'
  | 'openai'
  | 'deepseek'
  | 'anthropic'
  | 'google'
  | 'ollama'

export interface AIProviderInput {
  name: string
  provider: AIProviderKind
  model: string
  base_url: string
  api_key: string
  temperature: number
  response: boolean
  enabled: boolean
}

export interface AIProvider extends Omit<AIProviderInput, 'api_key' | 'base_url'> {
  id: string
  base_url: string | null
  api_key_configured: boolean
  created_at: string
  updated_at: string
}

export interface AIProviderDetail extends AIProvider {
  api_key: string | null
}

export interface TagCreateRequest {
  name: string
  parent_id: number | null
}
