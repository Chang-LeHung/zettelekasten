export type ProcessRole = 'scheduler' | 'worker'

export type ProcessHeartbeatStatus = 'starting' | 'running' | 'stopped'

export interface ProcessHeartbeatInput {
  role: ProcessRole
  instance_id: string
  pid: number
  status: ProcessHeartbeatStatus
  metadata?: Record<string, string>
}

export interface ProcessHeartbeatRecord extends Required<ProcessHeartbeatInput> {
  started_at: string
  heartbeat_at: string
  stopped_at: string | null
}

export interface ProcessInstanceHealth {
  instance_id: string
  pid: number
  status: ProcessHeartbeatStatus
  heartbeat_at: string
  age_seconds: number
}

export interface ProcessRoleHealth {
  role: ProcessRole
  healthy: boolean
  active_processes: number
  required_processes: number
  stale_after_seconds: number
  instances: ProcessInstanceHealth[]
}

export interface ProcessHealthReport {
  healthy: boolean
  checked_at: string
  roles: ProcessRoleHealth[]
}
