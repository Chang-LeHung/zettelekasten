import { describe, expect, it } from 'vitest'
import {
  blockKind,
  continueList,
  exitList,
  hasOpenFence,
  isWrapped,
  headingLevel,
  isPrefixOnly,
  joinBlocks,
  keepsLineBreaks,
  makeLink,
  reconcileBlocks,
  shiftLines,
  slideMarker,
  splitBlocks,
  toggleInline,
  turnInto,
  withoutSlideMarker,
} from './markdownBlocks'

const texts = (source: string, slides = false) => splitBlocks(source, { slides }).map((block) => block.text)

describe('splitting a document into blocks', () => {
  it('rebuilds every document byte for byte, however odd its spacing', () => {
    const documents = [
      '',
      '\n',
      '\n\n',
      'one',
      'one\n',
      'one\n\n',
      '\n\nlead',
      'a\n\nb',
      'a\n\n\n\nb\n\n',
      'a\n \t\nb',
      '# T\n\n```py\nx = 1\n\ny = 2\n```\n\nafter',
      '```\nnever closed\n\nstill code',
      '$$\na\n\nb\n$$\n\nend',
      '<div>\n\n<p>x</p>\n\n</div>\n\ntext',
      '- a\n- b\n\n1. c',
      'A\r\n\r\nB\r\n',
      '<!-- slide:cover -->\n# Title\n\n---\n\n# Next',
      'x\n--\ny\n---\nz',
    ]
    for (const source of documents) {
      for (const slides of [false, true]) {
        expect(joinBlocks(splitBlocks(source, { slides }))).toBe(source)
      }
    }
  })

  it('cuts at blank lines but never inside a fence, display math, or an HTML element', () => {
    expect(texts('a\n\nb\n\n\nc')).toEqual(['a', 'b', 'c'])
    expect(texts('```js\nx\n\ny\n```\n\nafter')).toEqual(['```js\nx\n\ny\n```', 'after'])
    expect(texts('~~~\na\n\nb\n~~~')).toEqual(['~~~\na\n\nb\n~~~'])
    expect(texts('$$\na\n\nb\n$$\n\nz')).toEqual(['$$\na\n\nb\n$$', 'z'])
    expect(texts('<div>\n\n<p>x</p>\n\n</div>\n\ntext')).toEqual(['<div>\n\n<p>x</p>\n\n</div>', 'text'])
  })

  it('treats a carriage return like any other blank character', () => {
    expect(texts('A\r\n\r\nB\r\n')).toEqual(['A\r', 'B\r'])
  })

  it('keeps a closing fence of the wrong kind inside the block', () => {
    expect(texts('````\n```\ninner\n```\n````\n\nz')).toEqual(['````\n```\ninner\n```\n````', 'z'])
    expect(texts('```\na\n~~~\n\nb\n```')).toEqual(['```\na\n~~~\n\nb\n```'])
  })

  it('keeps an inline backtick span at the start of a line out of fence handling', () => {
    expect(texts('```not a fence``` here\n\nnext')).toEqual(['```not a fence``` here', 'next'])
  })

  it('lets an element that never closes end at the blank line instead of swallowing the page', () => {
    expect(texts('<div>\n\nrest')).toEqual(['<div>', 'rest'])
  })

  it('continues a paragraph that starts with a balanced inline tag', () => {
    expect(texts('<b>bold</b> start\nsecond line\n\nnext')).toEqual(['<b>bold</b> start\nsecond line', 'next'])
  })

  it('does not treat an HTML comment as an element', () => {
    expect(texts('<!-- note -->\n\nbody')).toEqual(['<!-- note -->', 'body'])
  })

  it('splits slide separators without blank lines around them, only for decks', () => {
    expect(texts('# A\n---\n# B\n--\n# C', true)).toEqual(['# A', '---', '# B', '--', '# C'])
    expect(texts('# A\n---\n# B')).toEqual(['# A\n---\n# B'])
  })

  it('keeps a separator inside a fence as code, even in a deck', () => {
    expect(texts('```\n---\n--\n```', true)).toEqual(['```\n---\n--\n```'])
  })

  it('gives an empty document one editable block', () => {
    expect(splitBlocks('')).toHaveLength(1)
    expect(splitBlocks('')[0]).toMatchObject({ text: '', gap: '' })
  })

  it('numbers blocks uniquely', () => {
    const ids = splitBlocks('a\n\nb\n\nc').map((block) => block.id)
    expect(new Set(ids).size).toBe(3)
  })
})

describe('reconciling after a change elsewhere', () => {
  it('keeps ids in place and reuses the same blocks when nothing changed', () => {
    const before = splitBlocks('a\n\nb')
    expect(reconcileBlocks(before, 'a\n\nb').map((block) => block.id)).toEqual(before.map((block) => block.id))
  })

  it('keeps the id of a block that was edited where it stands', () => {
    const before = splitBlocks('a\n\nb\n\nc')
    const after = reconcileBlocks(before, 'a\n\nB!\n\nc')
    expect(after.map((block) => block.id)).toEqual(before.map((block) => block.id))
    expect(after[1]!.text).toBe('B!')
  })

  it('adds fresh ids when the document grew', () => {
    const before = splitBlocks('a')
    const after = reconcileBlocks(before, 'a\n\nb')
    expect(after[0]!.id).toBe(before[0]!.id)
    expect(after[1]!.id).not.toBe(before[0]!.id)
  })
})

describe('what kind of block this is', () => {
  const kind = (text: string, slides = false) => blockKind(text, { slides })

  it('names the common kinds', () => {
    expect(kind('')).toBe('empty')
    expect(kind('  \n ')).toBe('empty')
    expect(kind('plain words')).toBe('paragraph')
    expect(kind('## Section')).toBe('heading')
    expect(kind('#nospace')).toBe('paragraph')
    expect(kind('- a\n- b')).toBe('list')
    expect(kind('3. c')).toBe('list')
    expect(kind('- [ ] task')).toBe('todo')
    expect(kind('- [x] done')).toBe('todo')
    expect(kind('> quote')).toBe('quote')
    expect(kind('```py\nx\n```')).toBe('code')
    expect(kind('```mermaid\ngraph TD\n```')).toBe('diagram')
    expect(kind('$$\nx\n$$')).toBe('math')
    expect(kind('| a | b |\n| --- | --- |\n| 1 | 2 |')).toBe('table')
    expect(kind('![alt](https://x/y.png "Cap")')).toBe('image')
    expect(kind('<div>x</div>')).toBe('html')
    expect(kind('***')).toBe('divider')
  })

  it('names deck separators and markers only in a deck', () => {
    expect(kind('---')).toBe('divider')
    expect(kind('---', true)).toBe('sectionBreak')
    expect(kind('--', true)).toBe('slideBreak')
    expect(kind('<!-- slide:cover -->\n# T')).toBe('slideMarker')
    expect(kind('<!--slide:html-->\n<div>x</div>')).toBe('slideMarker')
  })

  it('reads the marker and removes its line for display', () => {
    expect(slideMarker('<!-- slide:cover -->\n# T')).toBe('cover')
    expect(slideMarker('<!-- slide:html -->')).toBe('html')
    expect(slideMarker('# T')).toBeNull()
    expect(withoutSlideMarker('<!-- slide:cover -->\n# T\n\nAuthor')).toBe('# T\n\nAuthor')
    expect(withoutSlideMarker('# T')).toBe('# T')
  })

  it('reads a heading depth', () => {
    expect(headingLevel('### x')).toBe(3)
    expect(headingLevel('text')).toBe(0)
  })

  it('knows which blocks keep Enter as a line break', () => {
    expect(keepsLineBreaks('code', '```\nx\n```')).toBe(true)
    expect(keepsLineBreaks('table', '| a |')).toBe(true)
    expect(keepsLineBreaks('paragraph', 'text')).toBe(false)
    // A fence still being typed has no kind yet, but must not split on Enter.
    expect(keepsLineBreaks('paragraph', '```')).toBe(true)
    expect(hasOpenFence('```\nx\n```')).toBe(false)
  })
})

describe('lists', () => {
  it('continues a bullet, a numbered item, and a task', () => {
    expect(continueList('- one', 5)).toEqual({ action: 'continue', insert: '\n- ' })
    expect(continueList('2. two', 6)).toEqual({ action: 'continue', insert: '\n3. ' })
    expect(continueList('9) nine', 7)).toEqual({ action: 'continue', insert: '\n10) ' })
    expect(continueList('- [x] done', 10)).toEqual({ action: 'continue', insert: '\n- [ ] ' })
    expect(continueList('  - nested', 10)).toEqual({ action: 'continue', insert: '\n  - ' })
  })

  it('exits on an empty item, and ignores a line that is not a list', () => {
    expect(continueList('- one\n- ', 8)).toEqual({ action: 'exit', insert: '' })
    expect(continueList('- [ ] ', 6)).toEqual({ action: 'exit', insert: '' })
    expect(continueList('plain', 5)).toBeNull()
  })

  it('continues a quote and leaves it on an empty line', () => {
    expect(continueList('> said', 6)).toEqual({ action: 'continue', insert: '\n> ' })
    expect(continueList('> said\n> ', 9)).toEqual({ action: 'exit', insert: '' })
    expect(continueList('>', 1)).toEqual({ action: 'exit', insert: '' })
  })

  it('knows a block that is only its prefix', () => {
    for (const text of ['- ', '1. ', '## ', '> ', '- [ ] ']) expect(isPrefixOnly(text)).toBe(true)
    for (const text of ['', '- a', 'plain', '- \n- b']) expect(isPrefixOnly(text)).toBe(false)
  })

  it('removes the empty item when leaving a list', () => {
    expect(exitList('- one\n- two\n- ', 14)).toEqual({ text: '- one\n- two', caret: 11 })
    expect(exitList('- ', 2)).toEqual({ text: '', caret: 0 })
  })

  it('indents and outdents every touched line', () => {
    expect(shiftLines('- a\n- b', 0, 7, 1)).toEqual({ text: '  - a\n  - b', start: 2, end: 11 })
    expect(shiftLines('  - a\n  - b', 0, 11, -1)).toEqual({ text: '- a\n- b', start: 0, end: 7 })
    expect(shiftLines('- a', 3, 3, -1)).toEqual({ text: '- a', start: 3, end: 3 })
  })
})

describe('inline formatting', () => {
  it('wraps a selection and selects the words again', () => {
    expect(toggleInline('say hello now', 4, 9, '**')).toEqual({ text: 'say **hello** now', start: 6, end: 11 })
  })

  it('unwraps when the selection sits inside the markers', () => {
    expect(toggleInline('say **hello** now', 6, 11, '**')).toEqual({ text: 'say hello now', start: 4, end: 9 })
  })

  it('unwraps when the selection includes the markers', () => {
    expect(toggleInline('say **hello** now', 4, 13, '**')).toEqual({ text: 'say hello now', start: 4, end: 9 })
  })

  it('does not mistake the stars of a bold word for italic', () => {
    expect(isWrapped('a **bold** b', 4, 8, '*')).toBe(false)
    expect(isWrapped('a **bold** b', 4, 8, '**')).toBe(true)
    expect(toggleInline('a **bold** b', 4, 8, '*')).toEqual({ text: 'a ***bold*** b', start: 5, end: 9 })
    expect(isWrapped('a *it* b', 3, 5, '*')).toBe(true)
    expect(toggleInline('a *it* b', 3, 5, '*')).toEqual({ text: 'a it b', start: 2, end: 4 })
  })

  it('does not toggle an empty selection', () => {
    expect(isWrapped('****', 2, 2, '**')).toBe(false)
  })

  it('can use different opening and closing markers', () => {
    expect(toggleInline('x', 0, 1, '$', '$')).toEqual({ text: '$x$', start: 1, end: 2 })
  })

  it('makes a link and selects the URL to type over', () => {
    const edit = makeLink('see docs here', 4, 8)
    expect(edit.text).toBe('see [docs](https://) here')
    expect(edit.text.slice(edit.start, edit.end)).toBe('https://')
  })

  it('links a placeholder word when nothing is selected', () => {
    expect(makeLink('', 0, 0).text).toBe('[link](https://)')
  })
})

describe('turning a block into another kind', () => {
  it('rewrites the prefix and keeps the words', () => {
    expect(turnInto('plain text', 'h2')).toBe('## plain text')
    expect(turnInto('# Title', 'paragraph')).toBe('Title')
    expect(turnInto('# Title', 'h3')).toBe('### Title')
    expect(turnInto('one\ntwo', 'bullet')).toBe('- one\n- two')
    expect(turnInto('- one\n- two', 'numbered')).toBe('1. one\n2. two')
    expect(turnInto('1. one\n2. two', 'todo')).toBe('- [ ] one\n- [ ] two')
    expect(turnInto('> quoted', 'bullet')).toBe('- quoted')
    expect(turnInto('text', 'quote')).toBe('> text')
  })

  it('wraps in a fence and unwraps from one', () => {
    expect(turnInto('x = 1', 'code')).toBe('```\nx = 1\n```')
    expect(turnInto('```py\nx = 1\n```', 'paragraph')).toBe('x = 1')
    expect(turnInto('```py\nx = 1\n```', 'code')).toBe('```\nx = 1\n```')
  })
})
