import { API_URL, ApiError, request } from '../http'
import type { SessionAsset } from '../types'

export const sessionAssetApi = {
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
}
