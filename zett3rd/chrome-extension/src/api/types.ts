/**
 * The slice of Zett's HTTP API this panel uses.
 *
 * Only the fields the panel reads are typed: a response carries more, and
 * spelling out the whole row here would mean updating the panel every time an
 * unrelated field moves. Everything is optional-safe where the server may omit
 * it, so a shape change surfaces as a type error at the call site.
 */

import type { AgentTimelineEntry, AgentToolActivity, AIProvider, AgentModelUsage } from '../../../../frontend/src/api/types'

export type ArtifactType = 'card' | 'article' | 'slides'

export type { ReasoningEffort } from '../../../../frontend/src/api/types'

export interface HealthResponse {
  ok: boolean
}

export interface SessionStart {
  conversation_id: string
}

export interface Provider {
  id: string
  name: string
  provider: AIProvider['provider']
  model: string
  enabled: boolean
}

export interface ArtifactTagRef {
  id: string
  path: string
  name: string
}

/** One stored artifact, as the artifact routes answer with it. */
export interface AgentArtifact {
  id: string
  artifact_type: ArtifactType
  status: 'draft' | 'saved'
  content: { title: string; summary?: string; content?: string } | null
  draft_content: { title: string; summary?: string; content?: string } | null
  metadata: Record<string, unknown>
  tags: ArtifactTagRef[]
  version: number
}

/**
 * What an artifact tool answers with.
 *
 * The model-facing receipt, not the stored row: identity and state, the confirmed
 * tag paths, and the server-assigned locations. The panel needs exactly this to
 * show a card for the artifact and to know whether it still needs saving.
 */
export interface ArtifactReceipt {
  id: string
  artifact_type: ArtifactType
  status: 'draft' | 'saved'
  version: number
  title: string
  pending_draft: boolean
  tags: string[]
  content_url: string | null
  project_path?: string | null
  pdf_name?: string | null
  asset_path?: string | null
}

/** One tool call as the stream reports it, with its result when it has one. */
export type ToolOutcome = AgentToolActivity

/** The tools that answer with an artifact receipt, so the panel can show a card. */
export const ARTIFACT_TOOLS = ['create_artifact', 'update_artifact', 'set_artifact_tags'] as const

/** One page as the panel read it out of the tab. */
export interface PageSnapshot {
  title: string
  url: string
  description: string
  selection: string
  text: string
  truncated: boolean
}

/** One message or artifact card in the panel's transcript. */
export interface TranscriptEntry {
  id: number
  role: 'user' | 'assistant' | 'artifact'
  text: string
  /** Set on a steering message: waiting for the run to answer it, or answered. */
  steering?: 'waiting' | 'responded'
  pending?: boolean
  stopped?: boolean
  timeline?: AgentTimelineEntry[]
  startedAt?: number
  durationMs?: number
  /** Model wall-clock time behind this answer, the denominator of tok/s. */
  generationDurationMs?: number
  detailsOpen?: boolean
  error?: string
  usage?: AgentModelUsage
  /** Set on `artifact` entries: the card the thread shows and its Save button. */
  artifact?: {
    id: string
    title: string
    artifactType: ArtifactType
    needsSave: boolean
  }
}
