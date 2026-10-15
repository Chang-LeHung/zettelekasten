import { artifactEditableContent } from '../utils/artifactEditor'
import { request } from './http'
import type { AgentArtifact, ArtifactContent, ArtifactCreateContent, ArtifactStatus, CardListOptions, CardStatus, LibraryItem, LibraryItemType, LibraryItemUpdate } from './types'

const artifactIndex = new Map<string, AgentArtifact>()

/**
 * Filters of one library read, shared by the paged list and the count so the
 * two can never describe different queries. Pagination stays out of the count:
 * the header names the whole library, not the pages fetched so far.
 */
function libraryQueryParams(options: CardListOptions, paged: boolean): URLSearchParams {
  const params = new URLSearchParams()
  if (options.query) params.set('q', options.query)
  for (const artifactType of options.artifactTypes ?? ['card', 'article', 'slides', 'latex_pdf']) {
    params.append('artifact_types', artifactType)
  }
  params.append('statuses', 'saved')
  for (const cardStatus of options.cardStatuses ?? []) params.append('card_statuses', cardStatus)
  if (options.tagId) params.append('tag_ids', options.tagId)
  if (options.publishedOnly) params.set('published_only', 'true')
  if (paged && options.limit !== undefined) params.set('limit', String(options.limit))
  if (paged && options.offset) params.set('offset', String(options.offset))
  return params
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
    const params = libraryQueryParams(options, true)
    const suffix = params.size ? `?${params}` : ''
    const artifacts = await request<AgentArtifact[]>(`/artifacts${suffix}`)
    artifacts.forEach((artifact) => artifactIndex.set(artifact.id, artifact))
    return artifacts.map(artifactToLibraryItem)
  },

  /** How many artifacts the same filters match, for the library's item count. */
  async count(options: CardListOptions = {}): Promise<number> {
    const params = libraryQueryParams(options, false)
    const suffix = params.size ? `?${params}` : ''
    const result = await request<{ count: number }>(`/artifacts/count${suffix}`)
    return result.count
  },

  delete(_itemType: LibraryItemType, itemId: string): Promise<{ ok: boolean }> {
    const artifact = requireIndexedArtifact(itemId)
    // Forget the artifact only once the server has deleted it: a refused or failed
    // delete must leave it deletable again, which a bulk delete's retry relies on.
    return request<{ ok: boolean }>(`/agent/${artifact.session_id}/artifacts/${itemId}`, { method: 'DELETE' }).then((result) => {
      if (result.ok) artifactIndex.delete(itemId)
      return result
    })
  },

  /**
   * Move a card to a new status. A status is not a document edit, so it
   * takes effect at once with no draft, no save, and no version change.
   */
  async setCardStatus(itemId: string, status: CardStatus): Promise<LibraryItem> {
    const artifact = requireIndexedArtifact(itemId)
    const updated = await request<AgentArtifact>(
      `/agent/${artifact.session_id}/artifacts/${encodeURIComponent(itemId)}/card-status`,
      { method: 'PUT', body: JSON.stringify({ status }) },
    )
    artifactIndex.set(updated.id, updated)
    return artifactToLibraryItem(updated)
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
    card_status: artifact.card_status ?? null,
    status: artifact.status,
    tags: artifact.tags?.map((tag) => tag.path) ?? [],
    metadata: artifact.metadata,
    created_at: artifact.created_at,
    updated_at: artifact.updated_at,
  }
}
