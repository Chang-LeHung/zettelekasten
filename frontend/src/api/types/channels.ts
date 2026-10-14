import type { ReasoningEffort } from './common'

/** Channel plugins are discovered at runtime, so platform ids stay open. */
export type ChannelType = string

export interface ChannelPluginInfo {
  channel_type: ChannelType
  label: string
}

export interface Channel {
  id: string
  name: string
  channel_type: ChannelType
  provider_id: string
  enabled: boolean
  reasoning_effort: ReasoningEffort
  allow_coding: boolean
  config: Record<string, unknown>
  secret_keys: string[]
  created_at: string
  updated_at: string
}

export interface ChannelUpdate {
  name?: string
  provider_id?: string
  enabled?: boolean
  reasoning_effort?: ReasoningEffort
  allow_coding?: boolean
}

export type ChannelLoginStatus = 'pending' | 'scanned' | 'verify_required' | 'connected' | 'failed' | 'expired'

export interface ChannelLoginStart {
  channel_type?: ChannelType
  provider_id: string
  name?: string
}

export interface ChannelLogin {
  id: string
  channel_type: ChannelType
  provider_id: string
  name: string | null
  status: ChannelLoginStatus
  qr_url: string | null
  qr_data_url: string | null
  message: string | null
  channel_id: string | null
  expires_at: string
  created_at: string
  updated_at: string
}
