// @vitest-environment jsdom
import { createApp, h, nextTick } from 'vue'
import { afterEach, expect, it, vi } from 'vitest'
import type { ScheduledTask, ScheduledTaskRun } from '../api/types'

const mocks = vi.hoisted(() => ({
  list: vi.fn(),
  listRuns: vi.fn(),
  create: vi.fn(),
  listProviders: vi.fn(),
}))

vi.mock('../api/client', () => ({
  scheduledTaskClient: {
    list: mocks.list,
    listRuns: mocks.listRuns,
    create: mocks.create,
    setEnabled: vi.fn(),
    runNow: vi.fn(),
    delete: vi.fn(),
  },
  aiClient: {
    listProviders: mocks.listProviders,
  },
}))

import ScheduledTasksView from './ScheduledTasksView.vue'

const task: ScheduledTask = {
  id: 'task-1',
  name: 'Daily knowledge review',
  enabled: true,
  schedule: { expression: '0 9 * * *', timezone: 'Asia/Shanghai' },
  action: {
    kind: 'agent_prompt',
    payload: { provider_id: 'provider-1', message: 'Review recent notes.', reasoning_effort: 'medium' },
  },
  next_run_at: '2026-09-22T01:00:00Z',
  timeout_seconds: 600,
  overlap_policy: 'skip',
  lease_run_id: null,
  lease_expires_at: null,
  created_at: '2026-09-21T00:00:00Z',
  updated_at: '2026-09-21T00:00:00Z',
}

const run: ScheduledTaskRun = {
  id: 'run-1',
  task_id: 'task-1',
  scheduled_for: '2026-09-21T01:00:00Z',
  trigger_kind: 'scheduled',
  status: 'succeeded',
  idempotency_key: 'scheduled:task-1',
  action: task.action,
  started_at: '2026-09-21T01:00:00Z',
  completed_at: '2026-09-21T01:00:02Z',
  output: {
    session_id: 'session-1',
    model: 'test-model',
    provider_id: 'provider-1',
    content_preview: 'Daily summary from the scheduled run.',
  },
  error_type: null,
  error_message: null,
  created_at: '2026-09-21T01:00:00Z',
  updated_at: '2026-09-21T01:00:02Z',
}

afterEach(() => {
  mocks.list.mockReset()
  mocks.listRuns.mockReset()
  mocks.create.mockReset()
  mocks.listProviders.mockReset()
})

it('lists scheduled tasks, runs, and creates an Agent prompt task', async () => {
  mocks.list.mockResolvedValue([task])
  mocks.listRuns.mockResolvedValue([run])
  mocks.listProviders.mockResolvedValue([{
    id: 'provider-1',
    name: 'Local model',
    provider: 'openai_compatible',
    model: 'test-model',
    base_url: null,
    api_key_configured: true,
    enabled: true,
    temperature: 0.2,
    response: false,
    created_at: '',
    updated_at: '',
  }])
  mocks.create.mockResolvedValue({ ...task, id: 'task-2', name: 'Morning review' })
  const host = document.createElement('div')
  document.body.append(host)
  const opened = vi.fn()
  const app = createApp({
    render: () => h(ScheduledTasksView, { onOpenSession: opened }),
  })
  app.mount(host)
  try {
    await vi.waitFor(() => expect(host.textContent).toContain('Daily knowledge review'))
    await vi.waitFor(() => expect(host.textContent).toContain('Succeeded'))
    expect(host.textContent).toContain('Review recent notes.')
    expect(host.textContent).toContain('Daily summary from the scheduled run.')
    expect(host.textContent).toContain('Model test-model')
    host.querySelector<HTMLButtonElement>('.run-session-button')!.click()
    expect(opened).toHaveBeenCalledWith('session-1')

    host.querySelector<HTMLButtonElement>('.new-scheduled-task-button')!.click()
    await nextTick()
    const name = document.body.querySelector<HTMLInputElement>('input[placeholder="Daily knowledge review"]')!
    const prompt = document.body.querySelector<HTMLTextAreaElement>('textarea')!
    name.value = 'Morning review'
    name.dispatchEvent(new Event('input', { bubbles: true }))
    prompt.value = 'Summarize yesterday.'
    prompt.dispatchEvent(new Event('input', { bubbles: true }))
    await nextTick()
    document.body.querySelector<HTMLFormElement>('.scheduled-create')!.dispatchEvent(
      new Event('submit', { bubbles: true, cancelable: true }),
    )

    await vi.waitFor(() => expect(mocks.create).toHaveBeenCalledWith(expect.objectContaining({
      name: 'Morning review',
      action: expect.objectContaining({
        kind: 'agent_prompt',
        payload: expect.objectContaining({
          provider_id: 'provider-1',
          message: 'Summarize yesterday.',
        }),
      }),
    })))
  } finally {
    app.unmount()
    host.remove()
  }
})
