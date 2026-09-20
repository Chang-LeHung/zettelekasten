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
    completed_at: '2026-01-01T00:00:00Z',
    duration_ns: 0,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...changes,
  }
}

describe('restorePersistedConversation', () => {
  it('shows the original slash command input instead of the expanded skill prompt', () => {
    const expanded = 'The user invoked the /zett-review slash command.\n\nSkill instructions:\nReview changes.\n\nUser request:\n/zett-review inspect the diff'
    const image = { type: 'image' as const, name: 'diff.png', mime_type: 'image/png', content_url: 'data:image/png;base64,aW1hZ2U=' }
    const restored = restorePersistedConversation([
      record(1, 'user', {
        content: expanded,
        parts: [{ type: 'text', text: expanded }, image],
        attributes: {
          slash_command: {
            name: 'zett-review',
            type: 'skill',
            raw_parts: [{ type: 'text', text: '/zett-review inspect the diff' }, image],
          },
        },
      }),
      record(2, 'assistant', { content: 'Reviewing.' }),
      record(3, 'user', {
        content: expanded,
        parts: [{ type: 'text', text: expanded }],
        attributes: {
          slash_command: {
            name: 'zett-review',
            type: 'skill',
            raw_parts: [{ type: 'text', text: '/zett-review check this diff' }],
          },
        },
      }),
    ])

    expect(restored.initialPrompt).toBe('/zett-review inspect the diff')
    expect(restored.initialParts).toEqual([{ type: 'text', text: '/zett-review inspect the diff' }, image])
    expect(restored.messages[1]).toMatchObject({
      role: 'user',
      content: '/zett-review check this diff',
      parts: [
        { type: 'text', text: '/zett-review check this diff' },
      ],
    })
  })

  it('restores ordered image tool output in the same shape as live events', () => {
    const restored = restorePersistedConversation([
      record(1, 'user', { content: 'Read the image' }),
      record(2, 'assistant', {
        tool_calls: [{ id: 'image', name: 'read_image', arguments: {} }],
      }),
      record(3, 'tool', {
        tool_call_id: 'image', tool_name: 'read_image', tool_success: true,
        content: 'beforeafter',
        parts: [
          { type: 'text', text: 'before' },
          { type: 'image', name: 'preview.png', mime_type: 'image/png', content_url: 'data:image/png;base64,aW1hZ2U=' },
          { type: 'text', text: 'after' },
        ],
      }),
    ])
    expect(restored.messages[0]?.activities?.[0]?.output).toEqual([
      { text: 'before' },
      { type: 'image', url: 'data:image/png;base64,aW1hZ2U=', alt_text: 'preview.png' },
      { text: 'after' },
    ])
  })

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

  it('restores same-named parallel calls completed in a different order', () => {
    const restored = restorePersistedConversation([
      record(1, 'user', { content: 'Read both' }),
      record(2, 'assistant', {
        tool_calls: [
          { id: 'slow', name: 'read_file', arguments: { path: 'slow' } },
          { id: 'fast', name: 'read_file', arguments: { path: 'fast' } },
        ],
      }),
      record(3, 'tool', {
        content: '"fast result"', tool_call_id: 'fast', tool_name: 'read_file', tool_success: true,
      }),
      record(4, 'tool', {
        content: 'slow failed', tool_call_id: 'slow', tool_name: 'read_file', tool_success: false,
      }),
    ])

    expect(restored.messages[0]?.activities).toMatchObject([
      { id: 'slow', state: 'failed', error_message: 'slow failed' },
      { id: 'fast', state: 'succeeded', output: 'fast result' },
    ])
  })

  it('restores ordered text and image parts on their original user messages', () => {
    const image = {
      type: 'image' as const,
      name: 'clipboard.png',
      mime_type: 'image/png',
      content_url: 'data:image/png;base64,AA==',
    }
    const initialParts = [{ type: 'text' as const, text: 'Before' }, image, { type: 'text' as const, text: 'after' }]
    const restored = restorePersistedConversation([
      record(1, 'user', { content: 'Before\nafter', parts: initialParts }),
      record(2, 'assistant', { content: 'I can see it.' }),
      record(3, 'user', { content: 'Look again', parts: [image, { type: 'text', text: 'Look again' }] }),
    ])

    expect(restored.initialParts).toEqual(initialParts)
    expect(restored.messages.at(-1)?.parts).toEqual([image, { type: 'text', text: 'Look again' }])
  })
})
