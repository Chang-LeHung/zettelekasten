import { expect, it } from 'vitest'
import type { AgentPersistedMessage } from '../../../../frontend/src/api/types'
import { PAGE_PROMPT_MARKER, restoreTranscript, visiblePrompt } from './restore-transcript'

function record(role: AgentPersistedMessage['role'], sequence: number, changes: Partial<AgentPersistedMessage> = {}): AgentPersistedMessage {
  return {
    id: `message-${sequence}`, session_id: 'session', request_id: 'turn', sequence,
    role, content: '', parts: [], reasoning_content: null, model: null, provider: null,
    tool_calls: [], tool_call_id: null, tool_name: null, tool_success: null,
    attributes: {}, metadata: {}, tags: {}, input_tokens: null, output_tokens: null,
    cache_read_tokens: null, cache_write_tokens: null, reasoning_tokens: null,
    total_tokens: null, cache_hit_rate: null, duration_ns: 1_000_000,
    started_at: '2026-01-01T00:00:00Z', completed_at: '2026-01-01T00:00:00Z',
    created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z',
    ...changes,
  }
}

it('restores each page turn with its final answer, tool result and cached token counts', () => {
  const restored = restoreTranscript([
    record('user', 1, { content: `Page — https://example.com\n\nvisible content${PAGE_PROMPT_MARKER}Summarize` }),
    record('assistant', 2, {
      tool_calls: [{ id: 'read', name: 'get_browser_page', arguments: {} }],
      reasoning_content: 'Read before answering.',
    }),
    record('tool', 3, { tool_call_id: 'read', tool_name: 'get_browser_page', tool_success: true, content: '{"ok":true}' }),
    record('assistant', 4, {
      content: 'Page summary',
      input_tokens: 100, output_tokens: 20, cache_read_tokens: 75, cache_write_tokens: 0, reasoning_tokens: 3,
    }),
  ])
  expect(restored).toHaveLength(2)
  expect(restored[0]).toMatchObject({ role: 'user', text: 'Summarize' })
  expect(restored[1]).toMatchObject({ role: 'assistant', usage: { input_tokens: 100, cache_read_tokens: 75 } })
  expect(restored[1].timeline).toEqual(expect.arrayContaining([
    expect.objectContaining({ type: 'tool', activity: expect.objectContaining({ id: 'read', state: 'succeeded' }) }),
    expect.objectContaining({ type: 'message', content: 'Page summary' }),
  ]))
})

it('keeps the full user request when no page excerpt was injected', () => {
  expect(visiblePrompt('Fill this page')).toBe('Fill this page')
  expect(restoreTranscript([])).toEqual([])
})
