// @vitest-environment jsdom
import { describe, expect, it } from 'vitest'
import { diffMarkdown, markWords, renderedWords, wordMask } from './markdownDiff'

describe('diffMarkdown', () => {
  it('reports no change for equal documents', () => {
    const diff = diffMarkdown('# A\n\nbody', '# A\n\nbody')
    expect(diff.changed).toBe(false)
    expect(diff.blocks.every((block) => block.kind === 'same')).toBe(true)
  })

  it('pairs a rewritten paragraph and keeps the neighbours as unchanged', () => {
    const diff = diffMarkdown('# A\n\nold text\n\nend', '# A\n\nnew text\n\nend')
    expect(diff.blocks.map((block) => block.kind)).toEqual(['same', 'removed', 'added', 'same'])
    const [, removed, added] = diff.blocks
    expect(removed.pair).not.toBeNull()
    expect(removed.pair).toBe(added.pair)
  })

  it('never splits a code fence at its blank line', () => {
    const diff = diffMarkdown('```\na\n\nb\n```', '```\na\n\nc\n```')
    expect(diff.blocks).toHaveLength(2)
    expect(diff.removed).toBe(1)
    expect(diff.added).toBe(1)
  })

  it('reports a pure insertion without a removal', () => {
    const diff = diffMarkdown('one', 'one\n\ntwo')
    expect(diff.removed).toBe(0)
    expect(diff.added).toBe(1)
  })
})

describe('markWords', () => {
  it('wraps only the changed words and joins neighbours', () => {
    const root = document.createElement('p')
    root.innerHTML = 'keep <b>this</b> brave new world'
    const before = ['keep', 'this', 'brave', 'old', 'world']
    const mask = wordMask(before, renderedWords(root))
    markWords(root, mask.added, 'w')
    const marks = [...root.querySelectorAll('mark')].map((node) => node.textContent)
    expect(marks).toEqual(['new'])
    expect(root.textContent).toBe('keep this brave new world')
  })

  it('joins a marked run across the space between words', () => {
    const root = document.createElement('p')
    root.textContent = 'a b c d'
    markWords(root, new Set([1, 2]), 'w')
    expect(root.querySelector('mark')?.textContent).toBe('b c')
  })
})
