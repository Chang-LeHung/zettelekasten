import { describe, expect, it } from 'vitest'
import { SlashCommandInput } from './slashCommand'

describe('SlashCommandInput', () => {
  it('opens on a bare slash', () => {
    expect(SlashCommandInput.match('/', 1)).toEqual({ start: 0, end: 1, query: '' })
  })

  it('inserts one command and preserves the rest of the input', () => {
    const value = '/zett-review this'
    const match = SlashCommandInput.match(value, '/zett-review'.length)
    expect(match).toEqual({ start: 0, end: 12, query: 'zett-review' })
    expect(SlashCommandInput.insert(value, match!, 'zett-review')).toEqual({
      value: '/zett-review this',
      caret: 13,
    })
  })

  it('adds a separator when the command is inserted at the end', () => {
    const match = SlashCommandInput.match('/zett', 5)
    expect(SlashCommandInput.insert('/zett', match!, 'zett-review')).toEqual({
      value: '/zett-review ',
      caret: 13,
    })
  })

  it('leaves the caret where typing continues the request, not the command name', () => {
    const insertedAtEnd = SlashCommandInput.insert('/zett', SlashCommandInput.match('/zett', 5)!, 'zett-review')
    const typedAtEnd = insertedAtEnd.value.slice(0, insertedAtEnd.caret) + '整理一下' + insertedAtEnd.value.slice(insertedAtEnd.caret)
    expect(typedAtEnd).toBe('/zett-review 整理一下')
    expect(SlashCommandInput.contains(typedAtEnd, 'zett-review')).toBe(true)

    const value = 'Use /zett carefully'
    const insertedInline = SlashCommandInput.insert(value, SlashCommandInput.match(value, 9)!, 'zett-review')
    const typedInline = insertedInline.value.slice(0, insertedInline.caret) + '整理一下' + insertedInline.value.slice(insertedInline.caret)
    expect(typedInline).toBe('Use /zett-review 整理一下carefully')
    expect(SlashCommandInput.contains(typedInline, 'zett-review')).toBe(true)
  })

  it('detects only the selected command token', () => {
    expect(SlashCommandInput.contains('/zett-review and /other', 'zett-review')).toBe(true)
    expect(SlashCommandInput.contains('/other', 'zett-review')).toBe(false)
    expect(SlashCommandInput.contains('/zett-review-extra', 'zett-review')).toBe(false)
    expect(SlashCommandInput.range('Use /zett-review now', 'zett-review')).toEqual({ start: 4, end: 16 })
  })

  it('lists the command tokens that a typed message already contains', () => {
    expect(SlashCommandInput.tokenNames('/zett-review 整理一下')).toEqual(['zett-review'])
    expect(SlashCommandInput.tokenNames('Use /zett-review and /other')).toEqual(['zett-review', 'other'])
    expect(SlashCommandInput.tokenNames('a/b and /zett-review整理')).toEqual(['zett-review'])
    expect(SlashCommandInput.tokens('Use /zett-review now')).toEqual([{ name: 'zett-review', start: 4, end: 16 }])
  })

  it('deletes the whole command token with Backspace or Delete', () => {
    const value = 'Use /zett-review carefully'
    expect(SlashCommandInput.deleteAtomically(value, 'zett-review', 16, 16, 'Backspace')).toEqual({
      value: 'Use carefully',
      caret: 4,
    })
    expect(SlashCommandInput.deleteAtomically(value, 'zett-review', 4, 16, 'Backspace')).toEqual({
      value: 'Use carefully',
      caret: 4,
    })
    expect(SlashCommandInput.deleteAtomically(value, 'zett-review', 4, 4, 'Delete')).toEqual({
      value: 'Use carefully',
      caret: 4,
    })
  })
})
