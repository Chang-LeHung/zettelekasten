export type ScheduledTaskRunStatus =
  | 'pending'
  | 'running'
  | 'succeeded'
  | 'failed'
  | 'skipped'
  | 'cancelled'
  | 'interrupted'

export type ScheduledTaskTrigger = 'scheduled' | 'manual'

export interface CronSchedule {
  expression: string
  timezone: string
}

export interface ScheduledTaskAction {
  kind: string
  payload: Record<string, unknown>
}

export interface ScheduledTaskInput {
  name: string
  schedule: CronSchedule
  action: ScheduledTaskAction
  enabled?: boolean
  timeout_seconds?: number
  overlap_policy?: 'skip'
}

export interface ScheduledTask {
  id: string
  name: string
  enabled: boolean
  schedule: CronSchedule
  action: ScheduledTaskAction
  next_run_at: string
  timeout_seconds: number
  overlap_policy: 'skip'
  lease_run_id: string | null
  lease_expires_at: string | null
  created_at: string
  updated_at: string
}

export interface ScheduledTaskRun {
  id: string
  task_id: string
  scheduled_for: string
  trigger_kind: ScheduledTaskTrigger
  status: ScheduledTaskRunStatus
  idempotency_key: string
  action: ScheduledTaskAction
  started_at: string | null
  completed_at: string | null
  output: Record<string, unknown> | null
  error_type: string | null
  error_message: string | null
  created_at: string
  updated_at: string
}
