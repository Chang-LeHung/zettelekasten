import { request } from './http'
import type { AgentArtifact, StaticAsset, Tag, TagCreateInput, TagRecord } from './types'

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
