import { describe, expect, it } from 'vitest'
import { linkedScrollTop, scrollProgress } from './linkedScroll'

describe('linked Markdown editor scrolling', () => {
  it('maps proportional progress between panes with different heights', () => {
    expect(linkedScrollTop(
      { scrollTop: 400, scrollHeight: 1000, clientHeight: 200 },
      { scrollTop: 0, scrollHeight: 2000, clientHeight: 400 },
    )).toBe(800)
  })

  it('keeps both panes aligned at the bottom', () => {
    expect(linkedScrollTop(
      { scrollTop: 800, scrollHeight: 1000, clientHeight: 200 },
      { scrollTop: 0, scrollHeight: 900, clientHeight: 300 },
    )).toBe(600)
  })

  it('handles panes that do not scroll', () => {
    expect(scrollProgress({ scrollTop: 0, scrollHeight: 300, clientHeight: 300 })).toBe(0)
    expect(linkedScrollTop(
      { scrollTop: 0, scrollHeight: 300, clientHeight: 300 },
      { scrollTop: 0, scrollHeight: 900, clientHeight: 300 },
    )).toBe(0)
    expect(linkedScrollTop(
      { scrollTop: 200, scrollHeight: 600, clientHeight: 300 },
      { scrollTop: 0, scrollHeight: 200, clientHeight: 300 },
    )).toBe(0)
  })

  it('clamps stale browser positions to valid progress', () => {
    expect(scrollProgress({ scrollTop: -10, scrollHeight: 1000, clientHeight: 200 })).toBe(0)
    expect(scrollProgress({ scrollTop: 900, scrollHeight: 1000, clientHeight: 200 })).toBe(1)
  })
})
