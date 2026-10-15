import { request } from './http'
import type { AIProvider, AIProviderDetail, AIProviderInput } from './types'

export const providerApi = {
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
