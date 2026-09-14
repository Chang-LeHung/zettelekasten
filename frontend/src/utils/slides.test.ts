import { describe, expect, it } from 'vitest'
import { isSlideCover, presentationSections, slideDensity, slideWithTitle, splitSlideSections, splitSlides } from './slides'

describe('presentationSections', () => {
  it('adds chapter title pages while preserving body pages', () => {
    expect(presentationSections('# Intro\n\n- Body\n--\n## Details\n---\n# End')).toEqual([
      ['# Intro', '# Intro\n\n- Body', '## Details'], ['# End'],
    ])
  })
  it('uses only explicitly marked Markdown as a cover', () => {
    const cover = '<!-- slide:cover -->\n# Talk\n\n## Subtitle\n\nAuthor\n\n[Website](https://example.com)\n\n![A](/a.png) ![B](/b.png)'
    expect(isSlideCover(cover)).toBe(true)
    expect(presentationSections(cover + '\n---\n# Content\n\n- Detail')).toEqual([
      [cover], ['# Content', '# Content\n\n- Detail'],
    ])
    expect(isSlideCover('# Title\n\n```python\nprint(1)\n```')).toBe(false)
    expect(isSlideCover('# Title\n\n> Quote')).toBe(false)
    expect(isSlideCover('# Title\n\n# Other')).toBe(false)
    expect(isSlideCover('# Talk\n\nAuthor')).toBe(false)
    expect(slideWithTitle(cover, 1)).toBe(cover.split('\n').slice(1).join('\n'))
    const html = '<!-- slide:html -->\n<div style="display:grid"><h1>Custom</h1></div>'
    expect(presentationSections(html)).toEqual([[html]])
    expect(slideWithTitle(html, 1)).toBe('<div style="display:grid"><h1>Custom</h1></div>')
  })
  it('reuses title-only pages and gives untitled chapters a fallback', () => {
    expect(presentationSections('## Topic\n--\nContent')).toEqual([['# Topic', 'Content']])
    expect(presentationSections('Body')).toEqual([['# Section 1', 'Body']])
  })
})

describe('slideWithTitle', () => {
  it('keeps authored headings and adds a title without losing untitled content', () => {
    expect(slideWithTitle('### Detail\n\nText', 2)).toBe('### Detail\n\nText')
    expect(slideWithTitle('Text\n\n- Detail', 3)).toBe('# Slide 3\n\nText\n\n- Detail')
    expect(slideWithTitle('', 1)).toBe('# Slide 1\n\n')
    expect(slideWithTitle('#hashtag', 2)).toBe('# Slide 2\n\n#hashtag')
  })
})

describe('splitSlideSections', () => {
  it('uses horizontal sections and vertical slides', () => {
    expect(splitSlideSections('# One\n--\n## Detail\n---\n# Two')).toEqual([
      ['# One', '## Detail'],
      ['# Two'],
    ])
    expect(splitSlideSections('# One\r\n--\r\n## Detail')).toEqual([['# One', '## Detail']])
  })

  it('does not treat inline or indented dashes as navigation boundaries', () => {
    expect(splitSlideSections('alpha -- beta\n--\ngamma')).toEqual([['alpha -- beta', 'gamma']])
    expect(splitSlideSections('alpha\n -- \nbeta')).toEqual([['alpha\n -- \nbeta']])
  })
})

describe('splitSlides', () => {
  it('splits LF and CRLF decks on standalone separators', () => {
    expect(splitSlides('# One\n\n---\n\n## Two')).toEqual(['# One', '## Two'])
    expect(splitSlides('# One\r\n---\r\n## Two')).toEqual(['# One', '## Two'])
  })

  it('does not split inline dashes and ignores empty pages', () => {
    expect(splitSlides('alpha --- beta\n---\n\n---\ngamma')).toEqual(['alpha --- beta', 'gamma'])
    expect(splitSlides('alpha\n --- \nbeta')).toEqual(['alpha\n --- \nbeta'])
    expect(splitSlides('alpha\n--\nbeta\n---\ngamma')).toEqual(['alpha', 'beta', 'gamma'])
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
