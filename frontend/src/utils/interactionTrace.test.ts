import { describe, expect, it } from 'vitest'
import type { AgentPersistedMessage } from '../api/types'
import { buildInteractionTrace } from './interactionTrace'

function record(
  sequence: number,
  role: AgentPersistedMessage['role'],
  changes: Partial<AgentPersistedMessage> = {},
): AgentPersistedMessage {
  return {
    id: `message-${sequence}`,
    session_id: 'session-1',
    request_id: 'request-1',
    sequence,
    role,
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

describe('buildInteractionTrace', () => {
  it('keeps raw messages grouped by request and aggregates assistant usage', () => {
    const trace = buildInteractionTrace([
      record(1, 'user', { content: 'Inspect it' }),
      record(2, 'assistant', {
        content: 'Reading',
        model: 'gpt-test',
        provider: 'openai',
        tool_calls: [{ id: 'call-1', name: 'read_file', arguments: { path: 'README.md' } }],
        input_tokens: 10,
        output_tokens: 4,
        reasoning_tokens: 2,
      }),
      record(3, 'tool', {
        content: 'contents',
        tool_call_id: 'call-1',
        tool_name: 'read_file',
        tool_success: true,
      }),
      record(4, 'assistant', {
        request_id: 'request-2',
        content: 'Done',
        model: 'gpt-test',
        provider: 'openai',
        input_tokens: 20,
        output_tokens: 3,
      }),
    ])

    expect(trace).toHaveLength(2)
    expect(trace[0]).toMatchObject({
      id: 'request-1',
      index: 1,
      model: 'gpt-test',
      provider: 'openai',
      duration_ms: 3,
      usage: { input_tokens: 10, output_tokens: 4, reasoning_tokens: 2 },
    })
    expect(trace[0]?.messages.map((message) => message.role)).toEqual(['user', 'assistant', 'tool'])
    expect(trace[1]?.messages.map((message) => message.role)).toEqual(['assistant'])
  })
})
