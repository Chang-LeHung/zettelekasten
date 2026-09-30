import type {
  AnalysisMessage,
  AgentArtifact,
  AgentContextComposition,
  AgentModelUsageActivitySeries,
  AgentModelUsage,
  AgentUsageActivityDay,
  AgentServerToolActivity,
  AgentAtCommand,
  AgentSlashCommand,
  AgentSteeringMessage,
  AgentStreamCallbacks,
  AgentSession,
  AgentStart,
  AIProvider,
  AIProviderDetail,
  AIProviderInput,
  ArtifactContent,
  ArtifactCreateContent,
  ArtifactStatus,
  CardListOptions,
  Channel,
  ChannelLogin,
  ChannelLoginStart,
  ChannelPluginInfo,
  ChannelUpdate,
  LibraryItem,
  LibraryItemType,
  LibraryItemUpdate,
  MessagePart,
  ProcessHealthReport,
  ProcessHeartbeatInput,
  ProcessHeartbeatRecord,
  ReasoningEffort,
  RuntimeSettings,
  ScheduledTask,
  ScheduledTaskInput,
  ScheduledTaskRun,
  ScheduledTaskRunStatus,
  SessionModelPreference,
  SessionType,
  ShellApprovalSettings,
  ShellApprovalMode,
  StaticAsset,
  Tag,
  TagCreateInput,
  TagRecord,
  SessionAsset,
} from './types'
import { artifactEditableContent } from '../utils/artifactEditor'

const API_URL = (import.meta.env.VITE_API_URL ?? '/api').replace(/\/$/, '')
const artifactIndex = new Map<string, AgentArtifact>()

/**
 * Endpoint of a container-registered capability that runs one turn: either a
 * slash command ID or an `@` reference ID.
 */
type AgentCommandTarget = { slug: 'slash-commands' | 'at-commands'; id: string }

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

export const libraryClient = {
  /**
   * Create an artifact that belongs to no conversation. The server stores it
   * under its hidden library session, so it appears in the library list like
   * any other artifact and stays out of the conversation sidebar.
   *
   * `source` names who creates it and is required: an artifact with no
   * conversation has nothing else to attribute it to, and the server refuses a
   * blank one.
   */
  async createArtifact(
    content: ArtifactCreateContent,
    options: { source: string; status?: ArtifactStatus; rawContent?: string; metadata?: Record<string, unknown> },
  ): Promise<AgentArtifact> {
    if (!options.source.trim()) throw new Error('source is required: name who creates this artifact')
    return await request<AgentArtifact>('/artifacts', {
      method: 'POST',
      body: JSON.stringify({
        content,
        status: options.status ?? 'saved',
        metadata: { ...options.metadata, source: options.source.trim() },
        ...(options.rawContent === undefined ? {} : { raw_content: options.rawContent }),
      }),
    })
  },

  getArtifact(artifactId: string): Promise<AgentArtifact> {
    return request<AgentArtifact>(`/artifacts/${encodeURIComponent(artifactId)}`)
  },

  /**
   * Delete an artifact that belongs to no conversation. The server refuses one
   * a conversation owns (403), because that conversation deletes it.
   */
  deleteArtifact(artifactId: string): Promise<{ ok: boolean }> {
    return request<{ ok: boolean }>(`/artifacts/${encodeURIComponent(artifactId)}`, { method: 'DELETE' })
  },

  documentReference(itemId: string): Pick<AgentArtifact, 'id' | 'session_id' | 'content_url'> {
    const { id, session_id, content_url } = requireIndexedArtifact(itemId)
    return { id, session_id, content_url }
  },

  async list(options: CardListOptions = {}): Promise<LibraryItem[]> {
    const params = new URLSearchParams()
    if (options.query) params.set('q', options.query)
    for (const artifactType of options.artifactTypes ?? ['card', 'article', 'slides', 'latex_pdf']) {
      params.append('artifact_types', artifactType)
    }
    params.append('statuses', 'saved')
    if (options.tagId) params.append('tag_ids', options.tagId)
    if (options.publishedOnly) params.set('published_only', 'true')
    const suffix = params.size ? `?${params}` : ''
    const artifacts = await request<AgentArtifact[]>(`/artifacts${suffix}`)
    artifacts.forEach((artifact) => artifactIndex.set(artifact.id, artifact))
    return artifacts.map(artifactToLibraryItem)
  },

  delete(_itemType: LibraryItemType, itemId: string): Promise<{ ok: boolean }> {
    const artifact = requireIndexedArtifact(itemId)
    artifactIndex.delete(itemId)
    return request<{ ok: boolean }>(`/agent/${artifact.session_id}/artifacts/${itemId}`, { method: 'DELETE' })
  },

  async update(itemType: LibraryItemType, itemId: string, payload: LibraryItemUpdate): Promise<LibraryItem> {
    const artifact = requireIndexedArtifact(itemId)
    const current = artifactEditableContent(artifact)
    if (!current) throw new Error('Artifact has neither published nor draft content')
    if (current.artifact_type === 'latex_pdf' || itemType === 'latex_pdf') {
      throw new Error('Edit the LaTeX project files, not Markdown.')
    }
    const suggestedTags = (payload.tags ?? current.suggested_tags.map((tag) => tag.path)).map((path) => ({
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
          keywords: current.keywords,
        }
      : {
          artifact_type: 'card',
          title: payload.title,
          card_type: current.artifact_type === 'card' ? current.card_type : 'note',
          summary: payload.summary || '',
          content: payload.content,
          suggested_tags: suggestedTags,
          keywords: current.keywords,
        }
    const updated = await request<AgentArtifact>(`/agent/${artifact.session_id}/artifacts/${itemId}`, {
      method: 'PUT',
      body: JSON.stringify({
        content,
        ...(payload.expectedVersion === undefined ? {} : { expected_version: payload.expectedVersion }),
      }),
    })
    artifactIndex.set(updated.id, updated)
    return artifactToLibraryItem(updated)
  },
}

export const tagClient = {
  /**
   * Read the taxonomy, or one library's collection tree.
   *
   * `target` keeps only the tags that kind classifies and reports that kind's
   * counts, which is what each library browses; without it the complete taxonomy
   * comes back with counts for both kinds.
   */
  list(target: 'artifact' | 'asset' | null = null): Promise<Tag[]> {
    const suffix = target ? `?target=${target}` : ''
    return request<Tag[]>(`/library/tags${suffix}`)
  },

  create(payload: TagCreateInput): Promise<TagRecord> {
    return request<TagRecord>('/library/tags', {
      method: 'POST',
      body: JSON.stringify(payload),
    })
  },

  get(tagId: string): Promise<TagRecord> {
    return request<TagRecord>(`/library/tags/${encodeURIComponent(tagId)}`)
  },

  replaceArtifactTags(artifactId: string, paths: string[]): Promise<AgentArtifact> {
    return request<AgentArtifact>(`/library/tags/artifacts/${encodeURIComponent(artifactId)}`, {
      method: 'PUT',
      body: JSON.stringify({ paths }),
    })
  },

  /** Attach one tag without rewriting the artifact's other assignments. */
  assignTag(tagId: string, artifactId: string): Promise<AgentArtifact> {
    return request<AgentArtifact>(
      `/library/tags/${encodeURIComponent(tagId)}/artifacts/${encodeURIComponent(artifactId)}`,
      { method: 'PUT' },
    )
  },

  /** Detach one tag without rewriting the artifact's other assignments. */
  detachTag(tagId: string, artifactId: string): Promise<AgentArtifact> {
    return request<AgentArtifact>(
      `/library/tags/${encodeURIComponent(tagId)}/artifacts/${encodeURIComponent(artifactId)}`,
      { method: 'DELETE' },
    )
  },

  /** Attach one tag to a static asset, keeping the tags it already carries. */
  assignAssetTag(tagId: string, assetId: string): Promise<StaticAsset> {
    return request<StaticAsset>(
      `/library/tags/${encodeURIComponent(tagId)}/assets/${encodeURIComponent(assetId)}`,
      { method: 'PUT' },
    )
  },

  /** Detach one tag from a static asset, keeping its other assignments. */
  detachAssetTag(tagId: string, assetId: string): Promise<StaticAsset> {
    return request<StaticAsset>(
      `/library/tags/${encodeURIComponent(tagId)}/assets/${encodeURIComponent(assetId)}`,
      { method: 'DELETE' },
    )
  },

  /** Replace the complete tag set of one static asset. */
  replaceAssetTags(assetId: string, paths: string[]): Promise<StaticAsset> {
    return request<StaticAsset>(`/library/tags/assets/${encodeURIComponent(assetId)}`, {
      method: 'PUT',
      body: JSON.stringify({ paths }),
    })
  },

  delete(tagId: string): Promise<{ ok: boolean }> {
    const params = new URLSearchParams({ recursive: 'true', force: 'true' })
    return request<{ ok: boolean }>(`/library/tags/${encodeURIComponent(tagId)}?${params}`, {
      method: 'DELETE',
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
    parts: MessagePart[] = [],
    shellApprovalMode: ShellApprovalMode = 'review',
    command: AgentCommandTarget | null = null,
  ): Promise<AgentArtifact | null> {
    const path = command
      ? `/agent/${conversationId}/${command.slug}/${encodeURIComponent(command.id)}`
      : `/agent/${conversationId}/messages`
    const response = await fetch(`${API_URL}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        raw_content: rawContent,
        provider_id: providerId,
        reasoning_effort: reasoningEffort,
        messages,
        parts,
        shell_approval_mode: shellApprovalMode,
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
        if (event === 'steering_started') {
          const steering = payload.steering_message as Record<string, unknown> | undefined
          if (steering && typeof steering.text === 'string') {
            callbacks.onSteering?.({
              content: steering.text,
              parts: Array.isArray(steering.parts)
                ? steering.parts as AgentSteeringMessage['parts']
                : [],
            })
          }
        }
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

  slashCommandStream(
    conversationId: string,
    commandId: string,
    rawContent: string,
    providerId: string,
    reasoningEffort: ReasoningEffort,
    messages: AnalysisMessage[],
    callbacks: AgentStreamCallbacks = {},
    signal?: AbortSignal,
    parts: MessagePart[] = [],
    shellApprovalMode: ShellApprovalMode = 'review',
  ): Promise<AgentArtifact | null> {
    return this.analyzeStream(
      conversationId,
      rawContent,
      providerId,
      reasoningEffort,
      messages,
      callbacks,
      signal,
      parts,
      shellApprovalMode,
      { slug: 'slash-commands', id: commandId },
    )
  },

  /**
   * Run one turn that references a conversation resource. The browser submits
   * the `@` item ID it resolved from the composer text, and the backend injects
   * that reference before streaming the Agent events.
   */
  atCommandStream(
    conversationId: string,
    itemId: string,
    rawContent: string,
    providerId: string,
    reasoningEffort: ReasoningEffort,
    messages: AnalysisMessage[],
    callbacks: AgentStreamCallbacks = {},
    signal?: AbortSignal,
    parts: MessagePart[] = [],
    shellApprovalMode: ShellApprovalMode = 'review',
  ): Promise<AgentArtifact | null> {
    return this.analyzeStream(
      conversationId,
      rawContent,
      providerId,
      reasoningEffort,
      messages,
      callbacks,
      signal,
      parts,
      shellApprovalMode,
      { slug: 'at-commands', id: itemId },
    )
  },

  startAgent(): Promise<AgentStart> {
    return request<AgentStart>('/agent/start', { method: 'POST' })
  },

  listSlashCommands(conversationId: string): Promise<AgentSlashCommand[]> {
    return request<AgentSlashCommand[]>(`/agent/${conversationId}/slash-commands`)
  },

  listAtCommands(conversationId: string): Promise<AgentAtCommand[]> {
    return request<AgentAtCommand[]>(`/agent/${conversationId}/at-commands`)
  },

  getAgentSession(conversationId: string): Promise<AgentSession> {
    return request<AgentSession>(`/agent/sessions/${conversationId}`)
  },

  getAgentSessionMessages(conversationId: string, limit = 500): Promise<AgentSession['messages']> {
    const params = new URLSearchParams({ limit: String(limit) })
    return request<AgentSession['messages']>(`/agent/sessions/${conversationId}/messages?${params}`)
  },

  getAgentSessionModel(conversationId: string): Promise<SessionModelPreference | null> {
    return request<SessionModelPreference | null>(`/agent/sessions/${conversationId}/model`)
  },

  getAgentSessionContextComposition(conversationId: string): Promise<AgentContextComposition> {
    return request<AgentContextComposition>(`/agent/sessions/${conversationId}/context-composition`)
  },

  getAgentSessionShellApproval(conversationId: string): Promise<ShellApprovalSettings> {
    return request<ShellApprovalSettings>(`/agent/sessions/${conversationId}/shell-approval`)
  },

  updateAgentSessionShellApproval(
    conversationId: string,
    mode: ShellApprovalMode,
  ): Promise<ShellApprovalSettings> {
    return request<ShellApprovalSettings>(`/agent/sessions/${conversationId}/shell-approval`, {
      method: 'PUT',
      body: JSON.stringify({ mode }),
    })
  },

  updateAgentSessionTitle(conversationId: string, title: string): Promise<AgentSession> {
    return request<AgentSession>(`/agent/sessions/${conversationId}/title`, {
      method: 'PATCH',
      body: JSON.stringify({ title }),
    })
  },

  listAgentSessions(limit = 20, offset = 0, types: SessionType[] = ['normal']): Promise<AgentSession[]> {
    const params = new URLSearchParams({ limit: String(limit), offset: String(offset) })
    types.forEach((type) => params.append('types', type))
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

  steerAgent(
    conversationId: string,
    rawContent: string,
    parts: MessagePart[] = [],
  ): Promise<{ accepted: boolean }> {
    return request<{ accepted: boolean }>(`/agent/${conversationId}/steer`, {
      method: 'POST',
      body: JSON.stringify({ raw_content: rawContent, parts }),
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

  importStaticAsset(conversationId: string, staticAssetId: string): Promise<SessionAsset> {
    return request<SessionAsset>(`/agent/${conversationId}/assets/import/static/${staticAssetId}`, {
      method: 'POST',
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

  renameSessionAsset(conversationId: string, assetId: string, name: string): Promise<SessionAsset> {
    return request<SessionAsset>(`/agent/${conversationId}/assets/${assetId}/name`, {
      method: 'PATCH',
      body: JSON.stringify({ name }),
    })
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

  /**
   * Write editing as a draft. Published content only changes through
   * `saveAgentArtifact`, so an editor save never rewrites the original.
   */
  updateAgentArtifactDraft(
    conversationId: string,
    artifactId: string,
    content: ArtifactContent,
  ): Promise<AgentArtifact> {
    return request<AgentArtifact>(`/agent/${conversationId}/artifacts/${artifactId}/draft`, {
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

  getProvider(providerId: string): Promise<AIProviderDetail> {
    return request<AIProviderDetail>(`/ai/providers/${providerId}`)
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

export const assetClient = {
  /**
   * List library files. `tagId` narrows them to one collection, expanding the
   * tag's descendants server-side so a parent collection shows its whole subtree.
   */
  list(query = '', limit = 500, offset = 0, tagId: string | null = null): Promise<StaticAsset[]> {
    const params = new URLSearchParams({ limit: String(limit), offset: String(offset) })
    if (query) params.set('query', query)
    if (tagId) params.set('tag_ids', tagId)
    return request<StaticAsset[]>(`/assets?${params}`)
  },

  async upload(file: File): Promise<StaticAsset> {
    const params = new URLSearchParams({ name: file.name || 'asset.bin' })
    const response = await fetch(`${API_URL}/assets/upload?${params}`, {
      method: 'POST',
      headers: { 'Content-Type': file.type || 'application/octet-stream' },
      body: file,
    })
    if (!response.ok) throw new ApiError(response.status, await response.text())
    return response.json() as Promise<StaticAsset>
  },

  async getUrlContent(url: string, signal?: AbortSignal): Promise<ArrayBuffer> {
    const response = await fetch(url, { signal })
    if (!response.ok) throw new ApiError(response.status, await response.text())
    return response.arrayBuffer()
  },

  delete(assetId: string): Promise<{ ok: boolean }> {
    return request<{ ok: boolean }>(`/assets/${assetId}`, { method: 'DELETE' })
  },
}

export const settingsClient = {
  get(): Promise<RuntimeSettings> {
    return request<RuntimeSettings>('/settings')
  },

  update(payload: RuntimeSettings): Promise<RuntimeSettings> {
    return request<RuntimeSettings>('/settings', { method: 'PUT', body: JSON.stringify(payload) })
  },

  getUsageActivity(days = 365): Promise<AgentUsageActivityDay[]> {
    return request<AgentUsageActivityDay[]>(`/settings/usage-activity?days=${days}`)
  },

  getModelUsageActivity(days = 365): Promise<AgentModelUsageActivitySeries[]> {
    return request<AgentModelUsageActivitySeries[]>(`/settings/model-usage-activity?days=${days}`)
  },
}

export const healthClient = {
  processes(): Promise<ProcessHealthReport> {
    return request<ProcessHealthReport>('/health/processes')
  },

  reportHeartbeat(payload: ProcessHeartbeatInput): Promise<ProcessHeartbeatRecord> {
    return request<ProcessHeartbeatRecord>('/health/processes/heartbeat', {
      method: 'POST',
      body: JSON.stringify(payload),
    })
  },
}

export const scheduledTaskClient = {
  list(enabled?: boolean): Promise<ScheduledTask[]> {
    const params = new URLSearchParams()
    if (enabled !== undefined) params.set('enabled', String(enabled))
    const suffix = params.size ? `?${params}` : ''
    return request<ScheduledTask[]>(`/scheduled-tasks${suffix}`)
  },

  get(taskId: string): Promise<ScheduledTask> {
    return request<ScheduledTask>(`/scheduled-tasks/${encodeURIComponent(taskId)}`)
  },

  create(payload: ScheduledTaskInput): Promise<ScheduledTask> {
    return request<ScheduledTask>('/scheduled-tasks', {
      method: 'POST',
      body: JSON.stringify(payload),
    })
  },

  update(taskId: string, payload: ScheduledTaskInput): Promise<ScheduledTask> {
    return request<ScheduledTask>(`/scheduled-tasks/${encodeURIComponent(taskId)}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    })
  },

  setEnabled(taskId: string, enabled: boolean): Promise<ScheduledTask> {
    return request<ScheduledTask>(`/scheduled-tasks/${encodeURIComponent(taskId)}/enabled`, {
      method: 'PATCH',
      body: JSON.stringify({ enabled }),
    })
  },

  runNow(taskId: string): Promise<ScheduledTaskRun> {
    return request<ScheduledTaskRun>(`/scheduled-tasks/${encodeURIComponent(taskId)}/run`, {
      method: 'POST',
    })
  },

  listRuns(
    taskId: string,
    options: {
      statuses?: ScheduledTaskRunStatus[]
      limit?: number
      offset?: number
    } = {},
  ): Promise<ScheduledTaskRun[]> {
    const params = new URLSearchParams()
    for (const status of options.statuses ?? []) params.append('run_status', status)
    if (options.limit !== undefined) params.set('limit', String(options.limit))
    if (options.offset !== undefined) params.set('offset', String(options.offset))
    const suffix = params.size ? `?${params}` : ''
    return request<ScheduledTaskRun[]>(
      `/scheduled-tasks/${encodeURIComponent(taskId)}/runs${suffix}`,
    )
  },

  delete(taskId: string): Promise<{ ok: boolean }> {
    return request<{ ok: boolean }>(`/scheduled-tasks/${encodeURIComponent(taskId)}`, {
      method: 'DELETE',
    })
  },
}

export const channelClient = {
  list(): Promise<Channel[]> {
    return request<Channel[]>('/channels')
  },

  plugins(): Promise<ChannelPluginInfo[]> {
    return request<ChannelPluginInfo[]>('/channels/plugins')
  },

  update(channelId: string, payload: ChannelUpdate): Promise<Channel> {
    return request<Channel>(`/channels/${encodeURIComponent(channelId)}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    })
  },

  delete(channelId: string): Promise<{ ok: boolean }> {
    return request<{ ok: boolean }>(`/channels/${encodeURIComponent(channelId)}`, {
      method: 'DELETE',
    })
  },

  startLogin(payload: ChannelLoginStart): Promise<ChannelLogin> {
    return request<ChannelLogin>('/channels/login/start', {
      method: 'POST',
      body: JSON.stringify(payload),
    })
  },

  pollLogin(loginId: string, verifyCode?: string): Promise<ChannelLogin> {
    const params = new URLSearchParams()
    if (verifyCode?.trim()) params.set('verify_code', verifyCode.trim())
    const suffix = params.size ? `?${params}` : ''
    return request<ChannelLogin>(`/channels/login/${encodeURIComponent(loginId)}${suffix}`)
  },
}

function requireIndexedArtifact(id: string): AgentArtifact {
  const artifact = artifactIndex.get(id)
  if (!artifact) throw new Error(`Artifact ${id} is not loaded`)
  return artifact
}

function artifactToLibraryItem(artifact: AgentArtifact): LibraryItem {
  const content = artifactEditableContent(artifact)
  if (!content) throw new Error('Artifact has neither published nor draft content')
  if (content.artifact_type === 'image') throw new Error('Image artifacts are not library documents')
  return {
    id: artifact.id,
    session_id: artifact.session_id,
    item_type: content.artifact_type,
    title: content.artifact_type === 'latex_pdf' ? content.pdf_name.replace(/\.pdf$/, '') : content.title,
    subtitle: content.artifact_type === 'article' || content.artifact_type === 'slides' ? content.subtitle : null,
    summary: content.artifact_type === 'latex_pdf' ? 'LaTeX · PDF document' : content.summary || null,
    content: content.artifact_type === 'latex_pdf' ? '' : content.content,
    raw_content: artifact.raw_content,
    card_type: content.artifact_type === 'card' ? content.card_type : null,
    status: artifact.status,
    tags: artifact.tags?.map((tag) => tag.path) ?? [],
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
