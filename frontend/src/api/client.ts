import type {
  AnalysisMessage,
  AgentArtifact,
  AgentStreamCallbacks,
  AgentCustomEvent,
  AgentSession,
  AgentStart,
  AIProvider,
  AIProviderInput,
  ArtifactContent,
  Card,
  CardCreateRequest,
  CardListOptions,
  LibraryItem,
  LibraryItemType,
  LibraryItemUpdate,
  ReasoningEffort,
  Tag,
  TagCreateRequest,
  SessionAsset,
} from './types'

const API_URL = (import.meta.env.VITE_API_URL ?? '/api').replace(/\/$/, '')

class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly body: string,
  ) {
    super(`API request failed with status ${status}`)
  }
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

export const cardClient = {
  list(options: CardListOptions = {}): Promise<Card[]> {
    const params = new URLSearchParams()
    if (options.query) params.set('q', options.query)
    if (options.tagId) params.set('tag_id', String(options.tagId))
    const suffix = params.size ? `?${params}` : ''
    return request<Card[]>(`/cards${suffix}`)
  },

  create(payload: CardCreateRequest): Promise<Card> {
    return request<Card>('/cards', { method: 'POST', body: JSON.stringify(payload) })
  },

  get(cardId: string): Promise<Card> {
    return request<Card>(`/cards/${cardId}`)
  },

  delete(cardId: string): Promise<{ ok: boolean }> {
    return request<{ ok: boolean }>(`/cards/${cardId}`, { method: 'DELETE' })
  },
}

export const libraryClient = {
  list(options: CardListOptions = {}): Promise<LibraryItem[]> {
    const params = new URLSearchParams()
    if (options.query) params.set('q', options.query)
    if (options.tagId) params.set('tag_id', String(options.tagId))
    const suffix = params.size ? `?${params}` : ''
    return request<LibraryItem[]>(`/library${suffix}`)
  },

  delete(itemType: LibraryItemType, itemId: string): Promise<{ ok: boolean }> {
    return request<{ ok: boolean }>(`/library/${itemType}/${itemId}`, { method: 'DELETE' })
  },

  update(itemType: LibraryItemType, itemId: string, payload: LibraryItemUpdate): Promise<LibraryItem> {
    return request<LibraryItem>(`/library/${itemType}/${itemId}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    })
  },
}

export const tagClient = {
  list(): Promise<Tag[]> {
    return request<Tag[]>('/tags')
  },

  create(payload: TagCreateRequest): Promise<Tag> {
    return request<Tag>('/tags', { method: 'POST', body: JSON.stringify(payload) })
  },
}

export const aiClient = {
  async analyzeStream(
    conversationId: string,
    rawContent: string,
    providerId: number,
    reasoningEffort: ReasoningEffort,
    messages: AnalysisMessage[],
    callbacks: AgentStreamCallbacks = {},
    signal?: AbortSignal,
  ): Promise<AgentArtifact | null> {
    const response = await fetch(`${API_URL}/agent/${conversationId}/messages`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        raw_content: rawContent,
        provider_id: providerId,
        reasoning_effort: reasoningEffort,
        messages,
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
        if (event === 'status') callbacks.onStatus?.(String(payload.state || ''))
        if (event === 'reasoning') callbacks.onReasoning?.(String(payload.content || ''))
        if (event === 'message') callbacks.onMessage?.(String(payload.content || ''))
        if (event === 'tool') await callbacks.onTool?.(payload as unknown as Parameters<NonNullable<typeof callbacks.onTool>>[0])
        if (event === 'compaction') callbacks.onCompaction?.(payload as unknown as Parameters<NonNullable<typeof callbacks.onCompaction>>[0])
        if (event === 'custom') callbacks.onCustom?.(payload as unknown as AgentCustomEvent)
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

  listAgentArtifacts(conversationId: string): Promise<AgentArtifact[]> {
    return request<AgentArtifact[]>(`/agent/${conversationId}/artifacts`)
  },

  getAgentArtifact(conversationId: string, artifactId: string): Promise<AgentArtifact> {
    return request<AgentArtifact>(`/agent/${conversationId}/artifacts/${artifactId}`)
  },

  updateAgentArtifact(conversationId: string, artifactId: string, content: ArtifactContent): Promise<AgentArtifact> {
    return request<AgentArtifact>(`/agent/${conversationId}/artifacts/${artifactId}`, {
      method: 'PUT',
      body: JSON.stringify(content),
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

  updateProvider(providerId: number, payload: AIProviderInput): Promise<AIProvider> {
    return request<AIProvider>(`/ai/providers/${providerId}`, { method: 'PUT', body: JSON.stringify(payload) })
  },

  deleteProvider(providerId: number): Promise<{ ok: boolean }> {
    return request<{ ok: boolean }>(`/ai/providers/${providerId}`, { method: 'DELETE' })
  },

}

export { ApiError }
