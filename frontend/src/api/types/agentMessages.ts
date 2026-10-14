import type { AgentArtifact } from './artifacts'
import type { SessionAsset } from './assets'

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
