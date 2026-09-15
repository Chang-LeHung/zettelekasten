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

export interface RuntimeSettings {
  max_message_images: number
  max_turn_iterations: number
  compaction_max_tokens: number
  compaction_keep_recent_tokens: number
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
  text_content: string | null
  source_url: string | null
  content_url: string | null
  metadata: Record<string, unknown>
  created_at: string
  updated_at: string
}

export interface AnalysisMessage {
  role: 'user' | 'assistant'
  content: string
  parts?: MessageContentPart[]
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

export type MessageContentPart = MessageTextPart | MessageImagePart

export interface MessageTextPartInput {
  type: 'text'
  text: string
}

export interface MessageImagePartInput {
  type: 'image'
  name: string
  mime_type: string
  data_base64: string
}

export type MessagePartInput = MessageTextPartInput | MessageImagePartInput

export interface AgentModelUsage {
  input_tokens: number
  output_tokens: number
  cache_read_tokens: number
  cache_write_tokens: number
  reasoning_tokens: number
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
  source_url: string | null
  asset_id: string | null
}

export interface SlidesArtifactContent extends ArtifactContentBase {
  artifact_type: 'slides'
  subtitle: string
  content: string
}

export interface LatexPdfArtifactContent {
  artifact_type: 'latex_pdf'
  project_path: string
  pdf_name: string
}

export type ArtifactContent = CardArtifactContent | ArticleArtifactContent | ImageArtifactContent | SlidesArtifactContent | LatexPdfArtifactContent

export interface AgentArtifact {
  id: string
  session_id: string
  artifact_type: ArtifactType
  status: ArtifactStatus
  content: ArtifactContent
  raw_content: string | null
  version: number
  metadata: Record<string, unknown>
  tags: Array<{ id: string; path: string; name: string }>
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
  parts: MessageContentPart[]
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

export interface SessionModelPreference {
  provider_id: string
  provider: AIProviderKind
  model: string
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

export interface TagCreateRequest {
  name: string
  parent_id: number | null
}
