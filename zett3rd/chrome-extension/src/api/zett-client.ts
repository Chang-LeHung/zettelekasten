/**
 * Talk to the local Zett server the way the desktop UI does.
 *
 * The panel is an extension page with host permissions, so these requests are
 * not subject to a page's CORS rules. Every call goes to the same HTTP API the
 * browser app uses; nothing here reaches into Zett's database or files.
 */

import { parseSseChunk } from './sse'
import type {
  AgentContextComposition,
  AgentCustomEvent,
  AgentModelUsage,
  AgentSteeringMessage,
  AgentTimelineEntry,
} from '../../../../frontend/src/api/types'
import type { AgentPersistedMessage } from '../../../../frontend/src/api/types'
import { asContextComposition } from '../../../../frontend/src/utils/contextComposition'
import type {
  AgentArtifact,
  HealthResponse,
  Provider,
  ReasoningEffort,
  SessionStart,
  ToolOutcome,
} from './types'

/** The default matches `zett start` with no flags. */
export const DEFAULT_SERVER_URL = 'http://127.0.0.1:6280'

export class ZettError extends Error {
  readonly status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ZettError'
    this.status = status
  }
}

export interface StreamTurnOptions {
  conversationId: string
  providerId: string
  reasoningEffort: ReasoningEffort
  text: string
  onDelta?: (delta: string) => void
  onModelStarted?: () => void
  onTool?: (outcome: ToolOutcome) => void
  onEvent?: (entry: AgentTimelineEntry) => void
  onUsage?: (usage: AgentModelUsage) => void
  onComposition?: (composition: AgentContextComposition) => void
  onSteering?: (message: AgentSteeringMessage) => void
  onCustom?: (event: AgentCustomEvent) => void
  browserToken?: string
  signal?: AbortSignal
}

export class ZettClient {
  readonly baseUrl: string

  constructor(baseUrl: string = DEFAULT_SERVER_URL) {
    this.baseUrl = baseUrl.replace(/\/$/, '')
  }

  private async request<T>(path: string, options: RequestInit = {}): Promise<T> {
    let response: Response
    try {
      response = await fetch(`${this.baseUrl}${path}`, {
        ...options,
        headers: { 'Content-Type': 'application/json', ...(options.headers ?? {}) },
      })
    } catch (error) {
      throw new ZettError(`Zett did not answer at ${this.baseUrl}: ${(error as Error).message}`, 0)
    }
    if (!response.ok) throw new ZettError(await describeFailure(response), response.status)
    const text = await response.text()
    return (text ? JSON.parse(text) : null) as T
  }

  async health(): Promise<HealthResponse> {
    return await this.request<HealthResponse>('/api/health')
  }

  async runtimeSettings(): Promise<{ compaction_max_tokens: number; max_message_images: number }> {
    return await this.request('/api/settings')
  }

  /** Inject one urgent message into the turn that is already running. */
  async steerAgent(conversationId: string, rawContent: string): Promise<{ accepted: boolean }> {
    return await this.request(`/api/agent/${encodeURIComponent(conversationId)}/steer`, {
      method: 'POST',
      body: JSON.stringify({ raw_content: rawContent, parts: [] }),
    })
  }

  /** Answer one extension request, such as an Agent question or an approval. */
  async emitAgentEvent(
    conversationId: string,
    name: string,
    payload: Record<string, unknown>,
  ): Promise<{ accepted: boolean }> {
    return await this.request(`/api/agent/${encodeURIComponent(conversationId)}/events`, {
      method: 'POST',
      body: JSON.stringify({ name, payload }),
    })
  }

  browserSocketUrl(sessionId: string): string {
    const url = new URL(`${this.baseUrl}/api/agent/${encodeURIComponent(sessionId)}/browser`)
    url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
    return url.href
  }

  /** Create a conversation for the current tab/page, not the whole extension. */
  async startSession(): Promise<SessionStart> {
    return await this.request<SessionStart>('/api/agent/start', { method: 'POST' })
  }

  async session(sessionId: string): Promise<{ messages: AgentPersistedMessage[] }> {
    return await this.request(`/api/agent/sessions/${encodeURIComponent(sessionId)}`)
  }

  /** The stored composition of the latest model context, for a reopened panel. */
  async sessionContextComposition(sessionId: string): Promise<AgentContextComposition> {
    return await this.request(`/api/agent/sessions/${encodeURIComponent(sessionId)}/context-composition`)
  }

  /** List configured models, of which a turn needs one enabled provider. */
  async listProviders(): Promise<Provider[]> {
    return await this.request<Provider[]>('/api/ai/providers')
  }

  /** Read every artifact of one conversation, newest first. */
  async listArtifacts(conversationId: string): Promise<AgentArtifact[]> {
    return await this.request<AgentArtifact[]>(`/api/agent/${conversationId}/artifacts`)
  }

  /** Publish one artifact's pending draft: the user action the app's Save calls. */
  async saveArtifact(conversationId: string, artifactId: string): Promise<AgentArtifact> {
    return await this.request<AgentArtifact>(
      `/api/agent/${conversationId}/artifacts/${artifactId}/save`,
      { method: 'POST' },
    )
  }

  /**
   * Run one turn and stream its text back.
   *
   * `shell_approval_mode: allow_all` is deliberate. A browser panel has no way
   * to answer the runtime's approval prompt, and that prompt waits without a
   * timeout, so asking for review here would freeze the turn and hold the
   * session's lock. The desktop UI is the place that reviews commands.
   *
   * No history travels with the request either: the server restores the
   * conversation from the session id it already stores.
   */
  async streamTurn(options: StreamTurnOptions): Promise<string> {
    const { conversationId, providerId, reasoningEffort, text, onDelta, onTool, onEvent, signal } = options
    const response = await fetch(`${this.baseUrl}/api/agent/${conversationId}/messages`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        raw_content: text,
        provider_id: providerId,
        reasoning_effort: reasoningEffort,
        shell_approval_mode: 'allow_all',
        browser_token: options.browserToken,
      }),
      signal,
    })
    if (!response.ok) throw new ZettError(await describeFailure(response), response.status)
    if (!response.body) throw new ZettError('Zett did not return a response stream', response.status)

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let answer = ''
    let sequence = 0
    try {
      for (;;) {
        const { value, done } = await reader.read()
        if (signal?.aborted) throw new DOMException('Generation stopped', 'AbortError')
        const decoded = decoder.decode(value ?? new Uint8Array(), { stream: !done })
        const { events, rest } = parseSseChunk(buffer, decoded)
        buffer = rest
        for (const { event, data } of events) {
          if (signal?.aborted) throw new DOMException('Generation stopped', 'AbortError')
          if (!data || typeof data !== 'object' || Array.isArray(data)) continue
          const payload = data as Record<string, unknown>
          if (event === 'model_completed') {
            const usage = asRecord(payload.usage)
            const keys = ['input_tokens', 'output_tokens', 'cache_read_tokens', 'cache_write_tokens', 'reasoning_tokens'] as const
            if (keys.every(key => typeof usage[key] === 'number' && Number.isFinite(usage[key]) && usage[key] >= 0)) {
              options.onUsage?.(Object.fromEntries(keys.map(key => [key, usage[key]])) as unknown as AgentModelUsage)
            }
          }
          if (event === 'model_started') options.onModelStarted?.()
          if (event === 'custom') {
            if (payload.name === 'context_composition') {
              const composition = asContextComposition(asRecord(payload.payload))
              if (composition) options.onComposition?.(composition)
            }
            options.onCustom?.({ name: String(payload.name || ''), payload: asRecord(payload.payload) })
          }
          if (event === 'text_delta' && typeof payload.delta === 'string') {
            answer += payload.delta
            onDelta?.(payload.delta)
            onEvent?.({ id: `message-${++sequence}`, type: 'message', content: payload.delta })
          }
          if (event === 'steering_started') {
            const steering = asRecord(payload.steering_message)
            if (typeof steering.text === 'string') {
              options.onSteering?.({
                content: steering.text,
                parts: Array.isArray(steering.parts) ? steering.parts as AgentSteeringMessage['parts'] : [],
              })
            }
          }
          if (event === 'reasoning_delta' && typeof payload.delta === 'string') {
            onEvent?.({ id: `reasoning-${++sequence}`, type: 'reasoning', content: payload.delta })
          }
          if (event === 'tool_started' && Array.isArray(payload.tool_calls)) {
            for (const value of payload.tool_calls) {
              const call = asRecord(value)
              if (typeof call.id !== 'string' || !call.id || typeof call.name !== 'string') continue
              const activity: ToolOutcome = { id: call.id, name: call.name, arguments: asRecord(call.arguments), state: 'started' }
              onTool?.(activity)
              onEvent?.({ id: `tool-${call.id}`, type: 'tool', activity })
            }
          }
          if (['tool_completed', 'tool_failed', 'tool_skipped'].includes(event)) {
            const message = asRecord(payload.message)
            if (typeof message.tool_call_id !== 'string' || !message.tool_call_id || typeof message.name !== 'string') continue
            const failed = event === 'tool_failed' || message.success === false
            const activity: ToolOutcome = {
              id: message.tool_call_id,
              name: message.name,
              state: event === 'tool_skipped' ? 'cancelled' : failed ? 'failed' : 'succeeded',
              output: message.output,
              error_message: failed ? String(asRecord(payload.error).message || 'The tool failed') : null,
            }
            onTool?.(activity)
            onEvent?.({ id: `tool-${activity.id}`, type: 'tool', activity })
          }
          if (['server_tool_started', 'server_tool_input_delta', 'server_tool_completed', 'server_tool_failed'].includes(event)) {
            const call = asRecord(payload.server_tool_call)
            const delta = asRecord(payload.server_tool_input_delta)
            const result = asRecord(payload.server_tool_result)
            const id = String(call.id || delta.call_id || result.call_id || '')
            if (!id) continue
            onEvent?.({ id: `server-tool-${id}`, type: 'server_tool', activity: {
              id,
              name: String(call.name || result.name || ''),
              state: event === 'server_tool_started' ? 'started' : event === 'server_tool_input_delta' ? 'streaming' : event === 'server_tool_completed' ? 'succeeded' : 'failed',
              input: call.input && typeof call.input === 'object' ? asRecord(call.input) : null,
              input_delta: typeof delta.delta === 'string' ? delta.delta : undefined,
              output: result.output,
              error_code: typeof result.error_code === 'string' ? result.error_code : null,
            } })
          }
          if (event.startsWith('compaction_')) {
            onEvent?.({ id: `compaction-${++sequence}`, type: 'compaction', activity: {
              state: event === 'compaction_started' ? 'started' : event === 'compaction_completed' ? 'completed' : 'streaming',
              content: event === 'compaction_text_delta' ? String(payload.delta || '') : '',
              reasoning: event === 'compaction_reasoning_delta' ? String(payload.delta || '') : '',
            } })
          }
          if (event === 'error') throw new Error(String(payload.message || 'AI analysis failed'))
        }
        if (done) break
      }
    } finally {
      // Includes an SSE error: never leave a reader locked on a failed turn.
      await reader.cancel().catch(() => {})
      reader.releaseLock()
    }
    return answer
  }
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {}
}

/** Turn a failed response into something a person can act on. */
async function describeFailure(response: Response): Promise<string> {
  const body = await response.text()
  try {
    const parsed = JSON.parse(body) as { detail?: unknown }
    if (typeof parsed?.detail === 'string') return parsed.detail
    if (Array.isArray(parsed?.detail)) {
      return parsed.detail.map((item) => (item as { msg?: string })?.msg ?? JSON.stringify(item)).join('; ')
    }
  } catch {
    // A non-JSON body is still worth showing, trimmed to keep the panel readable.
  }
  return body ? `${response.status}: ${body.slice(0, 300)}` : `${response.status} ${response.statusText}`
}
