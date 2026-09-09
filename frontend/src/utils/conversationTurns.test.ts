import { describe, expect, it } from 'vitest'

import type { AnalysisMessage } from '../api/types'
import { buildConversationTurns, formatTurnDuration, summarizeTurnPrompt } from './conversationTurns'

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
        response: { role: 'assistant', content: 'First answer' },
      },
      {
        id: 'turn-1',
        prompt: { role: 'user', content: 'Follow up' },
        response: { role: 'assistant', content: 'Second answer' },
      },
    ])
  })

  it('keeps the active user turn without inventing an answer', () => {
    expect(buildConversationTurns('', [{ role: 'user', content: 'Still running' }])).toEqual([
      { id: 'turn-0', prompt: { role: 'user', content: 'Still running' } },
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
        response: { role: 'assistant', content: 'The card is ready.' },
      },
    ])
  })

  it('ignores orphan assistant records instead of attaching them incorrectly', () => {
    expect(buildConversationTurns('', [{ role: 'assistant', content: 'Orphan' }])).toEqual([])
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
