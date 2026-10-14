import type { MessagePart } from './agentMessages'
import type { AgentArtifact } from './artifacts'
import type { SessionAsset } from './assets'
import type { ShellApprovalMode } from './common'
import type { AIProviderKind } from './providers'

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
