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

it('renders request messages, tool calls, and model usage', async () => {
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
        reasoning_tokens: 2,
      }),
    ],
    loading: false,
    error: '',
  })
  app.mount(host)
  cleanups.push(() => { app.unmount(); host.remove() })
  await nextTick()

  expect(host.textContent).toContain('Turn 1')
  expect(host.textContent).toContain('gpt-test')
  expect(host.textContent).toContain('User message')
  expect(host.textContent).toContain('Inspect README')
  expect(host.textContent).toContain('1 tool call')
  expect(host.textContent).toContain('Input 12')
  expect(host.textContent).toContain('Output 5')
})
