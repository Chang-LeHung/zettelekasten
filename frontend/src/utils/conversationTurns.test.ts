import { describe, expect, it } from 'vitest'

import type { AnalysisMessage } from '../api/types'
import { buildConversationTurns, formatTurnDuration, splitTurnTimeline, summarizeTurnPrompt } from './conversationTurns'

describe('buildConversationTurns', () => {
  it('groups the initial prompt and later messages into turns', () => {
    const messages: AnalysisMessage[] = [
      { role: 'assistant', content: 'First answer' },
      { role: 'user', content: 'Follow up' },
      { role: 'assistant', content: 'Second answer' },
    ]

    expect(buildConversationTurns('Initial request', messages)).toEqual([
      {
        id: 'turn-0',
        prompt: { role: 'user', content: 'Initial request' },
        responses: [{ role: 'assistant', content: 'First answer' }],
        response: { role: 'assistant', content: 'First answer' },
      },
      {
        id: 'turn-1',
        prompt: { role: 'user', content: 'Follow up' },
        responses: [{ role: 'assistant', content: 'Second answer' }],
        response: { role: 'assistant', content: 'Second answer' },
      },
    ])
  })

  it('keeps the active user turn without inventing an answer', () => {
    expect(buildConversationTurns('', [{ role: 'user', content: 'Still running' }])).toEqual([
      { id: 'turn-0', prompt: { role: 'user', content: 'Still running' }, responses: [] },
    ])
  })

  it('uses the final assistant message after intermediate model-tool iterations', () => {
    expect(buildConversationTurns('', [
      { role: 'user', content: 'Create a card' },
      { role: 'assistant', content: '', reasoning: 'Selecting a tool' },
      { role: 'assistant', content: 'The card is ready.' },
    ])).toEqual([
      {
        id: 'turn-0',
        prompt: { role: 'user', content: 'Create a card' },
        responses: [
          { role: 'assistant', content: '', reasoning: 'Selecting a tool' },
          { role: 'assistant', content: 'The card is ready.' },
        ],
        response: { role: 'assistant', content: 'The card is ready.' },
      },
    ])
  })

  it('retains every assistant model step for turn-level usage aggregation', () => {
    const turns = buildConversationTurns('', [
      { role: 'user', content: 'Run tools' },
      {
        role: 'assistant',
        content: '',
        usage: { input_tokens: 10, output_tokens: 2, cache_read_tokens: 0, cache_write_tokens: 0, reasoning_tokens: 0 },
      },
      {
        role: 'assistant',
        content: 'Finished',
        usage: { input_tokens: 20, output_tokens: 4, cache_read_tokens: 10, cache_write_tokens: 0, reasoning_tokens: 0 },
      },
    ])

    expect(turns[0]?.responses).toHaveLength(2)
    expect(turns[0]?.response?.content).toBe('Finished')
  })

  it('ignores orphan assistant records instead of attaching them incorrectly', () => {
    expect(buildConversationTurns('', [{ role: 'assistant', content: 'Orphan' }])).toEqual([])
  })
})

describe('splitTurnTimeline', () => {
  it('keeps intermediate prose in execution order and exposes only terminal prose as the answer', () => {
    const sections = splitTurnTimeline([
      { id: 'thinking', type: 'reasoning', content: 'Inspect first' },
      { id: 'progress', type: 'message', content: 'I will read the file.' },
      {
        id: 'tool',
        type: 'tool',
        activity: { id: 'call-1', name: 'read_file', state: 'succeeded' },
      },
      { id: 'answer', type: 'message', content: 'The file is valid.' },
    ])

    expect(sections.execution.map((entry) => entry.id)).toEqual(['thinking', 'progress', 'tool'])
    expect(sections.answer.map((entry) => entry.id)).toEqual(['answer'])
  })

  it('does not treat prose followed by a tool call as a final answer', () => {
    const sections = splitTurnTimeline([
      { id: 'progress', type: 'message', content: 'I will run the command.' },
      {
        id: 'tool',
        type: 'tool',
        activity: { id: 'call-1', name: 'run_shell', state: 'started' },
      },
    ])

    expect(sections.execution).toHaveLength(2)
    expect(sections.answer).toEqual([])
  })
})

describe('turn presentation', () => {
  it.each([
    [0, '0s'],
    [59_999, '59s'],
    [60_000, '1m'],
    [81_900, '1m 21s'],
  ])('formats %i milliseconds as %s', (milliseconds, expected) => {
    expect(formatTurnDuration(milliseconds)).toBe(expected)
  })

  it('normalizes whitespace and truncates long task summaries', () => {
    expect(summarizeTurnPrompt('  one\n two  ')).toBe('one two')
    expect(summarizeTurnPrompt('abcdefgh', 6)).toBe('abcde…')
  })
})
