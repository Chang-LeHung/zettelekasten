/** Pure helpers the scheduled-task screens share: validation, labels, and run output. */
import type { ScheduledTask, ScheduledTaskRun, ScheduledTaskRunStatus } from '../api/types'

export function message(errorValue: unknown): string {
  return errorValue instanceof Error ? errorValue.message : 'Scheduled task request failed'
}

export function validCronShape(value: string): boolean {
  const fields = value.trim().split(/\s+/).filter(Boolean)
  if (fields.length === 1 && fields[0]!.startsWith('@')) return /^@[a-z]+$/i.test(fields[0]!)
  if (fields.length !== 5 && fields.length !== 6) return false
  return fields.every((field) => /^[0-9A-Za-z*?/,\-#]+$/.test(field))
}

export function validTimeZone(value: string): boolean {
  const normalized = value.trim()
  if (!normalized) return false
  try {
    new Intl.DateTimeFormat(undefined, { timeZone: normalized })
    return true
  } catch {
    return false
  }
}

export function actionPayload(task: ScheduledTask): Record<string, unknown> {
  return task.action.payload
}

export function actionPrompt(task: ScheduledTask): string {
  const prompt = actionPayload(task).message
  return typeof prompt === 'string' ? prompt : 'No prompt'
}

export function statusLabel(status: ScheduledTaskRunStatus): string {
  return status.charAt(0).toUpperCase() + status.slice(1)
}

export function formatDate(value: string | null): string {
  if (!value) return 'Not yet'
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value))
}

export function duration(run: ScheduledTaskRun): string {
  if (!run.started_at || !run.completed_at) return '—'
  const milliseconds = new Date(run.completed_at).getTime() - new Date(run.started_at).getTime()
  if (milliseconds < 1000) return `${milliseconds} ms`
  return `${(milliseconds / 1000).toFixed(1)} s`
}

export function outputValue(run: ScheduledTaskRun, key: string): string | null {
  const value = run.output?.[key]
  return typeof value === 'string' && value ? value : null
}

export function outputPreview(run: ScheduledTaskRun): string | null {
  return outputValue(run, 'content_preview')
}

export function outputModel(run: ScheduledTaskRun): string | null {
  return outputValue(run, 'model')
}

export function outputProvider(run: ScheduledTaskRun): string | null {
  return outputValue(run, 'provider_id')
}

export function outputSessionId(run: ScheduledTaskRun): string | null {
  return outputValue(run, 'session_id')
}

export function rawOutput(run: ScheduledTaskRun): string | null {
  if (!run.output) return null
  return JSON.stringify(run.output, null, 2)
}

export function runPreview(run: ScheduledTaskRun): string {
  return outputPreview(run) || run.error_message || (run.status === 'pending' || run.status === 'running'
    ? 'Waiting for execution result.'
    : 'No output preview.')
}

export function shortId(value: string): string {
  return value.length > 16 ? `${value.slice(0, 8)}…${value.slice(-5)}` : value
}
