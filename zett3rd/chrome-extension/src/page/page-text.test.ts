import { describe, expect, it } from 'vitest'

import { collapseWhitespace, pageContext, summarizePage, truncate } from './page-text'
import type { PageSnapshot } from '../api/types'

function snapshot(overrides: Partial<PageSnapshot>): PageSnapshot {
  return {
    title: '',
    url: '',
    description: '',
    selection: '',
    text: '',
    truncated: false,
    ...overrides,
  }
}

describe('page text', () => {
  it('collapses the whitespace a rendered page is made of', () => {
    expect(collapseWhitespace('  a\n\n b\tc  ')).toBe('a b c')
  })

  it('truncates a long body and says how much was left out', () => {
    const result = truncate('x'.repeat(50), 10)

    expect(result).toMatch(/^x{10}/)
    expect(result).toMatch(/truncated 40 characters/)
    expect(truncate('short', 10)).toBe('short')
  })

  it('prefers the page description for a summary and falls back to the body', () => {
    expect(summarizePage(snapshot({ description: 'A short blurb', text: 'body text' }))).toBe('A short blurb')
    expect(summarizePage(snapshot({ text: 'body text' }))).toBe('body text')
    expect(summarizePage(snapshot({}))).toBe('')
    expect(summarizePage(null)).toBe('')
  })

  it('bounds a summary that would otherwise repeat the page', () => {
    const summary = summarizePage(snapshot({ description: 'y'.repeat(500) }), 100)

    expect(summary).toHaveLength(100)
    expect(summary.endsWith('…')).toBe(true)
  })

  it('names the page in the context sent with a message', () => {
    const context = pageContext(snapshot({ title: 'Processes', url: 'https://example.com/p', text: 'Body' }))

    expect(context).toBe('Processes — https://example.com/p\n\nBody')
    expect(pageContext(snapshot({ text: 'Body' }))).toBe('Untitled page\n\nBody')
  })
})
