import type {
  AnalysisMessage,
  AgentArtifact,
  AgentModelUsage,
  AgentServerToolActivity,
  AgentStreamCallbacks,
  AgentSession,
  AgentStart,
  AIProvider,
  AIProviderInput,
  ArtifactContent,
  CardListOptions,
  LibraryItem,
  LibraryItemType,
  LibraryItemUpdate,
  MessagePartInput,
  ReasoningEffort,
  RuntimeSettings,
  SessionModelPreference,
  Tag,
  SessionAsset,
} from './types'

const API_URL = (import.meta.env.VITE_API_URL ?? '/api').replace(/\/$/, '')
const artifactIndex = new Map<string, AgentArtifact>()
const tagIndex = new Map<number, string>()

function asNonNegativeNumber(value: unknown): number {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0 ? value : 0
}

function asModelUsage(value: unknown): AgentModelUsage | null {
  if (!value || typeof value !== 'object') return null
  const usage = value as Record<string, unknown>
  return {
    input_tokens: asNonNegativeNumber(usage.input_tokens),
    output_tokens: asNonNegativeNumber(usage.output_tokens),
    cache_read_tokens: asNonNegativeNumber(usage.cache_read_tokens),
    cache_write_tokens: asNonNegativeNumber(usage.cache_write_tokens),
    reasoning_tokens: asNonNegativeNumber(usage.reasoning_tokens),
  }
}

function asServerToolActivity(event: string, payload: Record<string, unknown>): AgentServerToolActivity | null {
  const call = payload.server_tool_call as Record<string, unknown> | undefined
  const inputDelta = payload.server_tool_input_delta as Record<string, unknown> | undefined
  const result = payload.server_tool_result as Record<string, unknown> | undefined
  const id = String(call?.id || inputDelta?.call_id || result?.call_id || '')
  const name = String(call?.name || result?.name || '')
  if (!id || (event !== 'server_tool_input_delta' && !name)) return null
  return {
    id,
    name,
    state: event === 'server_tool_started'
      ? 'started'
      : event === 'server_tool_input_delta'
        ? 'streaming'
        : event === 'server_tool_completed'
          ? 'succeeded'
          : 'failed',
    input: call?.input && typeof call.input === 'object' ? call.input as Record<string, unknown> : null,
    input_delta: event === 'server_tool_input_delta' ? String(inputDelta?.delta || '') : undefined,
    output: result?.output,
    error_code: typeof result?.error_code === 'string' ? result.error_code : null,
  }
}

class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly body: string,
  ) {
    super(apiErrorMessage(status, body))
  }
}

function apiErrorMessage(status: number, body: string): string {
  try {
    const payload = JSON.parse(body) as Record<string, unknown>
    if (typeof payload.detail === 'string' && payload.detail.trim()) return payload.detail
    const nested = payload.error
    if (nested && typeof nested === 'object') {
      const message = (nested as Record<string, unknown>).message
      if (typeof message === 'string' && message.trim()) return message
    }
  } catch {
    const plainText = body.trim()
    if (plainText && !plainText.startsWith('<')) return plainText
  }
  return `Request failed (${status})`
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
  })
  if (!response.ok) throw new ApiError(response.status, await response.text())
  return response.json() as Promise<T>
}

async function requestBinary(path: string, signal?: AbortSignal): Promise<ArrayBuffer> {
  const response = await fetch(`${API_URL}${path}`, { signal })
  if (!response.ok) throw new ApiError(response.status, await response.text())
  return response.arrayBuffer()
}

export const libraryClient = {
  async list(options: CardListOptions = {}): Promise<LibraryItem[]> {
    const params = new URLSearchParams()
    if (options.query) params.set('q', options.query)
    params.append('artifact_types', 'card')
    params.append('artifact_types', 'article')
    params.append('artifact_types', 'slides')
    params.append('statuses', 'saved')
    const suffix = params.size ? `?${params}` : ''
    const artifacts = await request<AgentArtifact[]>(`/artifacts${suffix}`)
    artifacts.forEach((artifact) => artifactIndex.set(artifact.id, artifact))
    const tagPath = options.tagId == null ? null : tagIndex.get(options.tagId)
    return artifacts.map(artifactToLibraryItem).filter((item) => !tagPath || item.tags.includes(tagPath))
  },

  delete(_itemType: LibraryItemType, itemId: string): Promise<{ ok: boolean }> {
    const artifact = requireIndexedArtifact(itemId)
    artifactIndex.delete(itemId)
    return request<{ ok: boolean }>(`/agent/${artifact.session_id}/artifacts/${itemId}`, { method: 'DELETE' })
  },

  async update(itemType: LibraryItemType, itemId: string, payload: LibraryItemUpdate): Promise<LibraryItem> {
    const artifact = requireIndexedArtifact(itemId)
    const suggestedTags = (payload.tags ?? artifact.content.suggested_tags.map((tag) => tag.path)).map((path) => ({
      path,
      existing: true,
      confidence: 1,
    }))
    const content: ArtifactContent = itemType === 'article' || itemType === 'slides'
      ? {
          artifact_type: itemType,
          title: payload.title,
          subtitle: payload.subtitle || '',
          summary: payload.summary || '',
          content: payload.content,
          suggested_tags: suggestedTags,
          keywords: artifact.content.keywords,
        }
      : {
          artifact_type: 'card',
          title: payload.title,
          card_type: artifact.content.artifact_type === 'card' ? artifact.content.card_type : 'note',
          summary: payload.summary || '',
          content: payload.content,
          suggested_tags: suggestedTags,
          keywords: artifact.content.keywords,
        }
    const updated = await request<AgentArtifact>(`/agent/${artifact.session_id}/artifacts/${itemId}`, {
      method: 'PUT',
      body: JSON.stringify({ content }),
    })
    artifactIndex.set(updated.id, updated)
    return artifactToLibraryItem(updated)
  },
}

export const tagClient = {
  async list(): Promise<Tag[]> {
    const items = await libraryClient.list()
    const paths = [...new Set(items.flatMap((item) => item.tags))].sort()
    tagIndex.clear()
    return paths.map((path, index) => {
      const id = index + 1
      tagIndex.set(id, path)
      return {
        id,
        name: path.split('/').at(-1) || path,
        parent_id: null,
        description: null,
        color: null,
        created_at: '',
        updated_at: '',
        path,
        card_count: items.filter((item) => item.tags.includes(path)).length,
        children: [],
      }
    })
  },
}

export const aiClient = {
  async analyzeStream(
    conversationId: string,
    rawContent: string,
    providerId: string,
    reasoningEffort: ReasoningEffort,
    messages: AnalysisMessage[],
    callbacks: AgentStreamCallbacks = {},
    signal?: AbortSignal,
    parts: MessagePartInput[] = [],
  ): Promise<AgentArtifact | null> {
    const response = await fetch(`${API_URL}/agent/${conversationId}/messages`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        raw_content: rawContent,
        provider_id: providerId,
        reasoning_effort: reasoningEffort,
        messages,
        parts,
      }),
      signal,
    })
    if (!response.ok) throw new ApiError(response.status, await response.text())
    if (!response.body) throw new Error('The server did not return a response stream')
    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let result: AgentArtifact | null = null
    while (true) {
      const { value, done } = await reader.read()
      buffer += decoder.decode(value, { stream: !done }).replaceAll('\r\n', '\n')
      const events = buffer.split('\n\n')
      buffer = events.pop() || ''
      for (const block of events) {
        const lines = block.split('\n')
        const event = lines.find((line) => line.startsWith('event:'))?.slice(6).trim()
        const data = lines.filter((line) => line.startsWith('data:')).map((line) => line.slice(5).trim()).join('\n')
        if (!event || !data) continue
        const payload = JSON.parse(data) as Record<string, unknown> | null
        if (event === 'result') {
          result = payload as AgentArtifact | null
          continue
        }
        if (payload === null) continue
        if (event === 'model_started') {
          callbacks.onModelStarted?.()
          callbacks.onStatus?.('generating')
        }
        if (event === 'model_completed') {
          const usage = asModelUsage(payload.usage)
          if (usage) callbacks.onUsage?.(usage)
        }
        if (event === 'reasoning_delta') callbacks.onReasoning?.(String(payload.delta || ''))
        if (event === 'text_delta') callbacks.onMessage?.(String(payload.delta || ''))
        if (event === 'tool_started') {
          for (const call of asToolCalls(payload.tool_calls)) await callbacks.onTool?.({ ...call, state: 'started' })
        }
        if (['tool_completed', 'tool_failed', 'tool_skipped'].includes(event)) {
          const message = payload.message as Record<string, unknown> | undefined
          if (message) await callbacks.onTool?.({
            id: String(message.tool_call_id || ''),
            name: String(message.name || ''),
            state: event === 'tool_completed' ? 'succeeded' : event === 'tool_skipped' ? 'cancelled' : 'failed',
            output: message.output,
            error_message: event === 'tool_failed'
              ? String((payload.error as Record<string, unknown> | undefined)?.message || '')
              : null,
          })
        }
        if ([
          'server_tool_started',
          'server_tool_input_delta',
          'server_tool_completed',
          'server_tool_failed',
        ].includes(event)) {
          const activity = asServerToolActivity(event, payload)
          if (activity) callbacks.onServerTool?.(activity)
        }
        if (event.startsWith('compaction_')) callbacks.onCompaction?.({
          state: event === 'compaction_started' ? 'started' : event === 'compaction_completed' ? 'completed' : 'streaming',
          applied: typeof payload.applied === 'boolean' ? payload.applied : null,
          content: event === 'compaction_text_delta' ? String(payload.delta || '') : '',
          reasoning: event === 'compaction_reasoning_delta' ? String(payload.delta || '') : '',
        })
        if (event === 'custom') callbacks.onCustom?.({
          name: String(payload.name || ''),
          payload: (payload.payload || {}) as Record<string, unknown>,
        })
        if (event === 'run_completed') callbacks.onStatus?.('completed')
        if (event === 'error') throw new Error(String(payload.message || 'AI analysis failed'))
      }
      if (done) break
    }
    return result
  },

  startAgent(): Promise<AgentStart> {
    return request<AgentStart>('/agent/start', { method: 'POST' })
  },

  getAgentSession(conversationId: string): Promise<AgentSession> {
    return request<AgentSession>(`/agent/sessions/${conversationId}`)
  },

  getAgentSessionModel(conversationId: string): Promise<SessionModelPreference | null> {
    return request<SessionModelPreference | null>(`/agent/sessions/${conversationId}/model`)
  },

  updateAgentSessionTitle(conversationId: string, title: string): Promise<AgentSession> {
    return request<AgentSession>(`/agent/sessions/${conversationId}/title`, {
      method: 'PATCH',
      body: JSON.stringify({ title }),
    })
  },

  listAgentSessions(limit = 20, offset = 0): Promise<AgentSession[]> {
    const params = new URLSearchParams({ limit: String(limit), offset: String(offset) })
    return request<AgentSession[]>(`/agent/sessions?${params}`)
  },

  deleteAgentSession(conversationId: string): Promise<{ ok: boolean }> {
    return request<{ ok: boolean }>(`/agent/sessions/${conversationId}`, { method: 'DELETE' })
  },

  emitAgentEvent(
    conversationId: string,
    name: string,
    payload: Record<string, unknown>,
  ): Promise<{ accepted: boolean }> {
    return request<{ accepted: boolean }>(`/agent/${conversationId}/events`, {
      method: 'POST',
      body: JSON.stringify({ name, payload }),
    })
  },

  listSessionAssets(conversationId: string): Promise<SessionAsset[]> {
    return request<SessionAsset[]>(`/agent/${conversationId}/assets`)
  },

  createTextAsset(conversationId: string, name: string, content: string): Promise<SessionAsset> {
    return request<SessionAsset>(`/agent/${conversationId}/assets/text`, {
      method: 'POST',
      body: JSON.stringify({ name, content, mime_type: 'text/plain', metadata: {} }),
    })
  },

  createLinkAsset(conversationId: string, name: string, url: string): Promise<SessionAsset> {
    return request<SessionAsset>(`/agent/${conversationId}/assets/link`, {
      method: 'POST',
      body: JSON.stringify({ name, url, metadata: {} }),
    })
  },

  async uploadAsset(conversationId: string, file: File): Promise<SessionAsset> {
    const params = new URLSearchParams({ name: file.name })
    const response = await fetch(`${API_URL}/agent/${conversationId}/assets/upload?${params}`, {
      method: 'POST',
      headers: { 'Content-Type': file.type || 'application/octet-stream' },
      body: file,
    })
    if (!response.ok) throw new ApiError(response.status, await response.text())
    return response.json() as Promise<SessionAsset>
  },

  deleteSessionAsset(conversationId: string, assetId: string): Promise<{ ok: boolean }> {
    return request<{ ok: boolean }>(`/agent/${conversationId}/assets/${assetId}`, { method: 'DELETE' })
  },

  getSessionAssetContent(conversationId: string, assetId: string, signal?: AbortSignal): Promise<ArrayBuffer> {
    return requestBinary(`/agent/${conversationId}/assets/${assetId}/content`, signal)
  },

  listAgentArtifacts(conversationId: string): Promise<AgentArtifact[]> {
    return request<AgentArtifact[]>(`/agent/${conversationId}/artifacts`)
  },

  getAgentArtifact(conversationId: string, artifactId: string): Promise<AgentArtifact> {
    return request<AgentArtifact>(`/agent/${conversationId}/artifacts/${artifactId}`)
  },

  updateAgentArtifact(
    conversationId: string,
    artifactId: string,
    content: ArtifactContent,
  ): Promise<AgentArtifact> {
    return request<AgentArtifact>(`/agent/${conversationId}/artifacts/${artifactId}`, {
      method: 'PUT',
      body: JSON.stringify({ content }),
    })
  },

  deleteAgentArtifact(conversationId: string, artifactId: string): Promise<{ ok: boolean }> {
    return request<{ ok: boolean }>(`/agent/${conversationId}/artifacts/${artifactId}`, { method: 'DELETE' })
  },

  saveAgentArtifact(conversationId: string, artifactId: string): Promise<AgentArtifact> {
    return request<AgentArtifact>(`/agent/${conversationId}/artifacts/${artifactId}/save`, { method: 'POST' })
  },

  listProviders(): Promise<AIProvider[]> {
    return request<AIProvider[]>('/ai/providers')
  },

  createProvider(payload: AIProviderInput): Promise<AIProvider> {
    return request<AIProvider>('/ai/providers', { method: 'POST', body: JSON.stringify(payload) })
  },

  updateProvider(providerId: string, payload: AIProviderInput): Promise<AIProvider> {
    return request<AIProvider>(`/ai/providers/${providerId}`, { method: 'PUT', body: JSON.stringify(payload) })
  },

  deleteProvider(providerId: string): Promise<{ ok: boolean }> {
    return request<{ ok: boolean }>(`/ai/providers/${providerId}`, { method: 'DELETE' })
  },

}

export const settingsClient = {
  get(): Promise<RuntimeSettings> {
    return request<RuntimeSettings>('/settings')
  },

  update(payload: RuntimeSettings): Promise<RuntimeSettings> {
    return request<RuntimeSettings>('/settings', { method: 'PUT', body: JSON.stringify(payload) })
  },
}

function requireIndexedArtifact(id: string): AgentArtifact {
  const artifact = artifactIndex.get(id)
  if (!artifact) throw new Error(`Artifact ${id} is not loaded`)
  return artifact
}

function artifactToLibraryItem(artifact: AgentArtifact): LibraryItem {
  const content = artifact.content
  if (content.artifact_type === 'image') throw new Error('Image artifacts are not library documents')
  return {
    id: artifact.id,
    item_type: content.artifact_type,
    title: content.title,
    subtitle: content.artifact_type === 'article' || content.artifact_type === 'slides' ? content.subtitle : null,
    summary: content.summary || null,
    content: content.content,
    raw_content: artifact.raw_content,
    card_type: content.artifact_type === 'card' ? content.card_type : null,
    status: artifact.status,
    tags: content.suggested_tags.map((tag) => tag.path),
    metadata: artifact.metadata,
    created_at: artifact.created_at,
    updated_at: artifact.updated_at,
  }
}

function asToolCalls(value: unknown): Array<{ id: string; name: string; arguments: Record<string, unknown> }> {
  if (!Array.isArray(value)) return []
  return value.flatMap((call) => {
    if (!call || typeof call !== 'object') return []
    const item = call as Record<string, unknown>
    if (typeof item.id !== 'string' || typeof item.name !== 'string') return []
    return [{
      id: item.id,
      name: item.name,
      arguments: item.arguments && typeof item.arguments === 'object'
        ? item.arguments as Record<string, unknown>
        : {},
    }]
  })
}

export { ApiError }
