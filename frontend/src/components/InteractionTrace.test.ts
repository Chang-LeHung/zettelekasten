// @vitest-environment jsdom
import { createApp, nextTick } from 'vue'
import { afterEach, expect, it } from 'vitest'
import type { AgentPersistedMessage } from '../api/types'
import InteractionTrace from './InteractionTrace.vue'

const cleanups: (() => void)[] = []
afterEach(() => cleanups.splice(0).forEach(cleanup => cleanup()))

function record(sequence: number, changes: Partial<AgentPersistedMessage> = {}): AgentPersistedMessage {
  return {
    id: `message-${sequence}`,
    session_id: 'session',
    request_id: 'request',
    sequence,
    role: 'assistant',
    content: '',
    parts: [],
    reasoning_content: null,
    model: null,
    provider: null,
    tool_calls: [],
    tool_call_id: null,
    tool_name: null,
    tool_success: null,
    attributes: {},
    metadata: {},
    tags: {},
    input_tokens: null,
    output_tokens: null,
    cache_read_tokens: null,
    cache_write_tokens: null,
    reasoning_tokens: null,
    total_tokens: null,
    cache_hit_rate: null,
    started_at: '2026-01-01T00:00:00Z',
    completed_at: '2026-01-01T00:00:01Z',
    duration_ns: 1_000_000,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...changes,
  }
}

it('shows one button per turn and renders the selected turn', async () => {
  const host = document.createElement('div')
  document.body.append(host)
  const app = createApp(InteractionTrace, {
    messages: [
      record(1, { role: 'user', content: 'Inspect README' }),
      record(2, {
        content: 'Reading it',
        model: 'gpt-test',
        provider: 'openai',
        tool_calls: [{ id: 'call-1', name: 'read_file', arguments: { path: 'README.md' } }],
        input_tokens: 12,
        output_tokens: 5,
        cache_read_tokens: 9,
        reasoning_tokens: 2,
        cache_hit_rate: 0.75,
      }),
      record(3, {
        role: 'tool',
        content: '{"ok":true,"items":[1,2]}',
        tool_call_id: 'call-1',
        tool_name: 'read_file',
        tool_success: true,
      }),
      record(4, { request_id: 'request-2', role: 'user', content: 'Follow up' }),
      record(5, { request_id: 'request-2', role: 'assistant', content: 'Second answer' }),
    ],
    loading: false,
    error: '',
  })
  app.mount(host)
  cleanups.push(() => { app.unmount(); host.remove() })
  await nextTick()

  const buttons = host.querySelectorAll<HTMLButtonElement>('.trace-turn-list button')
  expect(buttons).toHaveLength(2)
  expect(buttons[0]!.textContent).toContain('Cache 75%')
  expect(buttons[0]!.querySelector('.trace-turn-cache')?.classList.contains('high')).toBe(true)
  expect(host.querySelector('.trace-detail')?.textContent).toContain('Second answer')

  buttons[0]!.click()
  await nextTick()

  const detail = host.querySelector('.trace-detail')!
  expect(detail.textContent).toContain('Turn 1')
  expect(detail.textContent).toContain('gpt-test')
  expect(detail.textContent).toContain('User message')
  expect(detail.textContent).toContain('Inspect README')
  expect(detail.textContent).toContain('1 tool call')
  expect(detail.textContent).toContain('Input 12')
  expect(detail.textContent).toContain('Output 5')
  expect(
    Array.from(detail.querySelectorAll('.trace-message-content')).some((element) =>
      element.textContent?.includes('"ok": true'),
    ),
  ).toBe(true)
  expect(detail.querySelector('.trace-cache-rate')?.textContent).toContain('Cache hit 75%')
  expect(detail.querySelector('.trace-cache-rate')?.classList.contains('high')).toBe(true)
  expect(detail.textContent).not.toContain('Second answer')
})
