import { request } from './http'
import type { ScheduledTask, ScheduledTaskInput, ScheduledTaskRun, ScheduledTaskRunStatus } from './types'

export const scheduledTaskClient = {
  list(enabled?: boolean): Promise<ScheduledTask[]> {
    const params = new URLSearchParams()
    if (enabled !== undefined) params.set('enabled', String(enabled))
    const suffix = params.size ? `?${params}` : ''
    return request<ScheduledTask[]>(`/scheduled-tasks${suffix}`)
  },

  get(taskId: string): Promise<ScheduledTask> {
    return request<ScheduledTask>(`/scheduled-tasks/${encodeURIComponent(taskId)}`)
  },

  create(payload: ScheduledTaskInput): Promise<ScheduledTask> {
    return request<ScheduledTask>('/scheduled-tasks', {
      method: 'POST',
      body: JSON.stringify(payload),
    })
  },

  update(taskId: string, payload: ScheduledTaskInput): Promise<ScheduledTask> {
    return request<ScheduledTask>(`/scheduled-tasks/${encodeURIComponent(taskId)}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    })
  },

  setEnabled(taskId: string, enabled: boolean): Promise<ScheduledTask> {
    return request<ScheduledTask>(`/scheduled-tasks/${encodeURIComponent(taskId)}/enabled`, {
      method: 'PATCH',
      body: JSON.stringify({ enabled }),
    })
  },

  runNow(taskId: string): Promise<ScheduledTaskRun> {
    return request<ScheduledTaskRun>(`/scheduled-tasks/${encodeURIComponent(taskId)}/run`, {
      method: 'POST',
    })
  },

  listRuns(
    taskId: string,
    options: {
      statuses?: ScheduledTaskRunStatus[]
      limit?: number
      offset?: number
    } = {},
  ): Promise<ScheduledTaskRun[]> {
    const params = new URLSearchParams()
    for (const status of options.statuses ?? []) params.append('run_status', status)
    if (options.limit !== undefined) params.set('limit', String(options.limit))
    if (options.offset !== undefined) params.set('offset', String(options.offset))
    const suffix = params.size ? `?${params}` : ''
    return request<ScheduledTaskRun[]>(
      `/scheduled-tasks/${encodeURIComponent(taskId)}/runs${suffix}`,
    )
  },

  delete(taskId: string): Promise<{ ok: boolean }> {
    return request<{ ok: boolean }>(`/scheduled-tasks/${encodeURIComponent(taskId)}`, {
      method: 'DELETE',
    })
  },
}
