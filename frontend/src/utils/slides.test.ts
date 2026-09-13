import { describe, expect, it } from 'vitest'
import { slideDensity, splitSlides } from './slides'

describe('splitSlides', () => {
  it('splits LF and CRLF decks on standalone separators', () => {
    expect(splitSlides('# One\n\n---\n\n## Two')).toEqual(['# One', '## Two'])
    expect(splitSlides('# One\r\n---\r\n## Two')).toEqual(['# One', '## Two'])
  })

  it('does not split inline dashes and ignores empty pages', () => {
    expect(splitSlides('alpha --- beta\n---\n\n---\ngamma')).toEqual(['alpha --- beta', 'gamma'])
    expect(splitSlides('alpha\n --- \nbeta')).toEqual(['alpha\n --- \nbeta'])
    expect(splitSlides('   ')).toEqual([''])
  })
})

describe('slideDensity', () => {
  it('selects progressively smaller scales for long slides', () => {
    expect(slideDensity('# Short')).toBe('normal')
    expect(slideDensity('x'.repeat(521))).toBe('compact')
    expect(slideDensity('x'.repeat(901))).toBe('dense')
    expect(slideDensity(Array.from({ length: 17 }, (_, index) => `${index}`).join('\n'))).toBe('dense')
  })
})
