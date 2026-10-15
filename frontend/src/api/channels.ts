import { request } from './http'
import type { Channel, ChannelLogin, ChannelLoginStart, ChannelPluginInfo, ChannelUpdate } from './types'

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
