import { API_URL, ApiError, request } from './http'
import type { StaticAsset } from './types'

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
