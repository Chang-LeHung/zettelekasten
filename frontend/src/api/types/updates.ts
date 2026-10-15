export interface UpdateStatus {
  current: string
  installed: string
  restart_required: boolean
  latest: string | null
  update_available: boolean
  can_install: boolean
  detail: string
  checked_at: string | null
  check_failed: boolean
}

export interface UpdateInstallResult {
  ok: boolean
  version: string
  needs_restart: boolean
  detail: string
  output_tail: string[]
}

export interface UpdateRestartResult {
  ok: boolean
  detail: string
}
