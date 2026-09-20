import { describe, expect, it } from 'vitest'
import { AtCommandInput } from './atCommand'

describe('AtCommandInput', () => {
  it('opens on a bare @', () => {
    expect(AtCommandInput.match('@', 1)).toEqual({ start: 0, end: 1, query: '' })
  })

  it('opens after prose that has no whitespace, such as Chinese text', () => {
    const value = '总结一下@rep'
    expect(AtCommandInput.match(value, value.length)).toEqual({ start: 4, end: 8, query: 'rep' })
  })

  it('stays closed inside a word or an email address', () => {
    expect(AtCommandInput.match('mail me at a@b.com', 17)).toBeNull()
    expect(AtCommandInput.match('fragment@report', 15)).toBeNull()
  })

  it('inserts one reference and keeps typing in the request', () => {
    const match = AtCommandInput.match('@rep', 4)
    expect(AtCommandInput.insert('@rep', match!, 'report')).toEqual({
      value: '@report ',
      caret: 8,
    })

    const inline = 'compare @rep with the draft'
    const inserted = AtCommandInput.insert(inline, AtCommandInput.match(inline, 12)!, 'report')
    expect(inserted.value).toBe('compare @report with the draft')
    expect(inserted.value.slice(0, inserted.caret) + '总结' + inserted.value.slice(inserted.caret))
      .toBe('compare @report 总结with the draft')
  })

  it('detects every reference the message already contains', () => {
    const value = 'compare @report-md with @slides-deck and @other'
    expect(AtCommandInput.tokens(value)).toEqual([
      { name: 'report-md', start: 8, end: 18 },
      { name: 'slides-deck', start: 24, end: 36 },
      { name: 'other', start: 41, end: 47 },
    ])
    expect(AtCommandInput.contains(value, 'slides-deck')).toBe(true)
    expect(AtCommandInput.contains(value, 'missing')).toBe(false)
    expect(AtCommandInput.range('总结 @report 的内容', 'report')).toEqual({ start: 3, end: 10 })
  })

  it('deletes a whole reference token with Backspace or Delete', () => {
    const value = 'compare @report carefully'
    expect(AtCommandInput.deleteAtomically(value, 'report', 15, 15, 'Backspace')).toEqual({
      value: 'compare carefully',
      caret: 8,
    })
    expect(AtCommandInput.deleteAtomically(value, 'report', 8, 15, 'Backspace')).toEqual({
      value: 'compare carefully',
      caret: 8,
    })
    expect(AtCommandInput.deleteAtomically(value, 'report', 8, 8, 'Delete')).toEqual({
      value: 'compare carefully',
      caret: 8,
    })
  })
})
