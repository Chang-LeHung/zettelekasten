export interface Tag {
  id: number
  name: string
  parent_id: number | null
  description: string | null
  color: string | null
  created_at: string
  path: string
  card_count: number
  children: Tag[]
}

export interface Card {
  id: string
  type: string
  title: string
  content: string
  raw_content: string | null
  summary: string | null
  source: string | null
  status: string
  created_at: string
  updated_at: string
  tag_ids: number[]
  tags: Tag[]
}

export interface CardCreateRequest {
  type: string
  title: string
  content: string
  raw_content?: string | null
  summary?: string | null
  source?: string | null
  tag_ids: number[]
}

export interface CardListOptions {
  query?: string
  tagId?: number | null
}

export type LibraryItemType = 'card' | 'article'

export interface LibraryItem {
  id: string
  item_type: LibraryItemType
  title: string
  subtitle: string | null
  summary: string | null
  content: string
  raw_content: string | null
  source: string | null
  card_type: CardType | null
  status: string
  tag_paths: string[]
  created_at: string
  updated_at: string
}

export interface LibraryItemUpdate {
  title: string
  subtitle: string | null
  summary: string | null
  content: string
}

export interface SuggestedTag {
  path: string
  existing: boolean
  confidence: number
  reason?: string | null
}

export type CardType = 'note' | 'idea' | 'quote' | 'todo' | 'reference'
export type ArtifactType = 'card' | 'article' | 'image'
export type ArtifactStatus = 'draft' | 'saved'
export type SessionAssetType = 'text' | 'image' | 'link' | 'file'
export type ReasoningEffort = 'off' | 'low' | 'medium' | 'high'

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
  reasoning?: string
  activities?: AgentToolActivity[]
  timeline?: AgentTimelineEntry[]
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
  | { id: string; type: 'compaction'; activity: AgentCompactionActivity }

export interface AgentPersistedToolCall {
  id: string
  run_id: string
  session_id: string
  tool_name: string
  status: 'started' | 'succeeded' | 'failed' | 'cancelled'
  input: Record<string, unknown>
  output: unknown
  duration_ms: number | null
  error_message: string | null
  started_at: string
  ended_at: string | null
}

export interface AgentRun {
  id: string
  turn_id: string
  tool_calls: AgentPersistedToolCall[]
  [key: string]: unknown
}

export interface AgentUsage {
  input_tokens: number
  output_tokens: number
  total_tokens: number
  cache_read_tokens: number
  cache_creation_tokens: number
  input_cost: number | null
  output_cost: number | null
  total_cost: number | null
  model_call_count: number
  cache_hit_rate: number | null
  output_tokens_per_second: number | null
}

export interface AgentStreamCallbacks {
  onStatus?: (state: string) => void
  onReasoning?: (content: string) => void
  onMessage?: (content: string) => void
  onTool?: (activity: AgentToolActivity) => void
  onCompaction?: (activity: AgentCompactionActivity) => void
  onUsage?: (usage: AgentUsage) => void
  onMetrics?: (metrics: Record<string, unknown>) => void
  onArtifacts?: (artifacts: AgentArtifact[]) => void
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

export type ArtifactContent = CardArtifactContent | ArticleArtifactContent | ImageArtifactContent

export interface AgentArtifact {
  id: string
  session_id: string
  artifact_type: ArtifactType
  status: ArtifactStatus
  content: ArtifactContent
  raw_content: string | null
  linked_resource_id: string | null
  version: number
  metadata: Record<string, unknown>
  created_at: string
  updated_at: string
}

export interface AgentPersistedMessage {
  id: string
  session_id: string
  turn_id: string
  sequence: number
  role: 'system' | 'user' | 'assistant' | 'tool'
  content: string
  reasoning_content: string | null
  model: string | null
  provider: string | null
  tool_name: string | null
  metadata: Record<string, unknown>
  created_at: string
}

export interface AgentSession {
  id: string
  agent_name: string
  title: string | null
  status: 'active' | 'completed' | 'failed' | 'archived'
  created_at: string
  updated_at: string
  last_activity_at: string
  message_count: number
  turn_count: number
  total_input_tokens: number
  total_output_tokens: number
  total_reasoning_tokens: number
  total_cache_read_tokens: number
  total_tokens: number
  total_cost: number | null
  average_time_to_first_token_ms: number | null
  average_output_tokens_per_second: number | null
  cache_hit_rate: number | null
  metadata: Record<string, unknown>
  messages: AgentPersistedMessage[]
  runs: AgentRun[]
  artifacts: AgentArtifact[]
  assets: SessionAsset[]
}

export interface AISettings {
  provider: string
  model: string
  base_url: string
  api_key: string
  temperature: number
  enabled: boolean
}

export interface AIProviderInput {
  name: string
  provider: string
  model: string
  base_url: string
  api_key: string
  temperature: number
  enabled: boolean
}

export interface AIProvider extends Omit<AIProviderInput, 'api_key' | 'base_url'> {
  id: number
  base_url: string | null
  api_key_configured: boolean
  created_at: string
  updated_at: string
}

export interface TagCreateRequest {
  name: string
  parent_id: number | null
}
