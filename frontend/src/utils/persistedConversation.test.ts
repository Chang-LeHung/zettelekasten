import { describe, expect, it } from 'vitest'
import type { AgentPersistedMessage } from '../api/types'
import { restorePersistedConversation } from './persistedConversation'

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
    completed_at: '2026-01-01T00:00:00Z',
    duration_ns: 0,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...changes,
  }
}

describe('restorePersistedConversation', () => {
  it('restores thinking, tool calls, results, and final text in model order', () => {
    const restored = restorePersistedConversation([
      record(1, 'user', { content: 'Inspect the project' }),
      record(2, 'assistant', {
        content: 'I will inspect the file.',
        reasoning_content: 'I should read the file.',
        tool_calls: [{ id: 'call-1', name: 'read_file', arguments: { path: 'README.md' } }],
      }),
      record(3, 'tool', {
        content: '{"lines":12}',
        tool_call_id: 'call-1',
        tool_name: 'read_file',
        tool_success: true,
        duration_ns: 4_000_000,
      }),
      record(4, 'assistant', { content: 'The project has twelve lines.' }),
    ])

    expect(restored.initialPrompt).toBe('Inspect the project')
    expect(restored.messages).toHaveLength(2)
    expect(restored.messages[0]?.timeline?.map((entry) => entry.type)).toEqual(['reasoning', 'message', 'tool'])
    expect(restored.messages[0]?.activities?.[0]).toMatchObject({
      id: 'call-1',
      state: 'succeeded',
      arguments: { path: 'README.md' },
      output: { lines: 12 },
      duration_ms: 4,
    })
    expect(restored.messages[1]?.timeline?.map((entry) => entry.type)).toEqual(['message'])
  })

  it('marks failed calls and ignores unrelated internal records', () => {
    const restored = restorePersistedConversation([
      record(1, 'agent', { content: 'internal' }),
      record(2, 'user', { content: 'Run it' }),
      record(3, 'assistant', {
        tool_calls: [{ id: 'call-2', name: 'shell', arguments: { command: 'false' } }],
      }),
      record(4, 'tool', {
        content: 'command failed',
        tool_call_id: 'call-2',
        tool_name: 'shell',
        tool_success: false,
      }),
    ])

    expect(restored.initialPrompt).toBe('Run it')
    expect(restored.messages).toHaveLength(1)
    expect(restored.messages[0]?.activities?.[0]).toMatchObject({
      state: 'failed',
      error_message: 'command failed',
    })
  })
})
