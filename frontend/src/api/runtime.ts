import { request } from './http'
import type { AgentModelUsageActivitySeries, AgentUsageActivityDay, ProcessHealthReport, ProcessHeartbeatInput, ProcessHeartbeatRecord, RuntimeSettings, UpdateInstallResult, UpdateRestartResult, UpdateStatus } from './types'

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

export const updateClient = {
  /** The newest release on PyPI, and how this copy would install it. */
  get(refresh = false): Promise<UpdateStatus> {
    return request<UpdateStatus>(`/updates${refresh ? '?refresh=true' : ''}`)
  },

  /** Download that release and let this copy's installer install it. */
  install(version: string): Promise<UpdateInstallResult> {
    return request<UpdateInstallResult>('/updates/install', {
      method: 'POST',
      body: JSON.stringify({ version }),
    })
  },

  /**
   * Ask this server to restart itself. The answer only says a helper was started: the
   * helper stops the very process that answered, so the page waits for the new one.
   */
  restart(): Promise<UpdateRestartResult> {
    return request<UpdateRestartResult>('/updates/restart', { method: 'POST' })
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
