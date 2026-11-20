import { describe, expect, it } from 'vitest'
import { wordsOf, changedPageNumbers, diffSequences, mergeRects, typesetChanges, type TextBox } from './pdfTypesetDiff'

function line(str: string, y = 10, x = 0): TextBox {
  return { str, x, y, width: str.length * 5, height: 10 }
}

describe('diffSequences', () => {
  it('reports nothing for equal sequences', () => {
    const diff = diffSequences(['a', 'b'], ['a', 'b'])
    expect(diff.removed.size + diff.added.size).toBe(0)
  })

  it('finds a replaced word in the middle', () => {
    const diff = diffSequences(['a', 'b', 'c', 'd'], ['a', 'x', 'c', 'd'])
    expect([...diff.removed]).toEqual([1])
    expect([...diff.added]).toEqual([1])
  })

  it('finds an insertion and a deletion spread apart', () => {
    const left = 'the quick brown fox jumps over the lazy dog today'.split(' ')
    const right = 'the quick red brown fox jumps over the dog today'.split(' ')
    const diff = diffSequences(left, right)
    expect([...diff.added]).toEqual([2])
    expect([...diff.removed]).toEqual([7])
  })

  it('treats a moved block as a delete and an insert, not a page rewrite', () => {
    const left = ['one', 'two', 'three', 'four', 'five']
    const right = ['one', 'four', 'five', 'two', 'three']
    const diff = diffSequences(left, right)
    expect(diff.removed.size).toBe(diff.added.size)
    expect(diff.removed.size).toBeLessThan(5)
  })

  it('falls back to a coarse diff past the distance limit', () => {
    const diff = diffSequences(['a', 'b', 'c', 'd'], ['w', 'x', 'y', 'z'], 2)
    expect(diff.coarse).toBe(true)
    expect(diff.removed.size).toBe(4)
    expect(diff.added.size).toBe(4)
  })

  it('handles one empty side', () => {
    expect([...diffSequences([], ['a']).added]).toEqual([0])
    expect([...diffSequences(['a'], []).removed]).toEqual([0])
  })
})

describe('mergeRects', () => {
  it('joins neighbouring words on one line and keeps separate lines apart', () => {
    const rects = mergeRects([
      { x: 0, y: 0, width: 20, height: 10 },
      { x: 24, y: 0, width: 20, height: 10 },
      { x: 0, y: 30, width: 20, height: 10 },
    ])
    expect(rects).toHaveLength(2)
    expect(rects[0]).toMatchObject({ x: 0, width: 44 })
  })
})

describe('typesetChanges', () => {
  it('maps changed words back to their pages', () => {
    const base = [[line('hello brave world')], [line('same page')]]
    const target = [[line('hello new world')], [line('same page')]]
    const changes = typesetChanges(base, target)
    expect(changes.removedWords).toBe(1)
    expect(changes.addedWords).toBe(1)
    expect(changes.base.map((entry) => entry.page)).toEqual([1])
    expect(changes.target[0].rects[0].x).toBeCloseTo(30)
    expect(changedPageNumbers(changes, 2)).toEqual([1])
  })

  it('does not flag a paragraph that only moved to the next page as rewritten', () => {
    const base = [[line('intro text'), line('moved paragraph here', 30)], [line('end')]]
    const target = [[line('intro text')], [line('moved paragraph here'), line('end', 30)]]
    const changes = typesetChanges(base, target)
    expect(changes.removedWords).toBe(0)
    expect(changes.addedWords).toBe(0)
  })

  it('compares ligatures and plain letters as equal', () => {
    const changes = typesetChanges([[line('\ufb01nal')]], [[line('final')]])
    expect(changes.removedWords + changes.addedWords).toBe(0)
  })
})

describe('wordsOf and page grouping', () => {
  it('splits a run into words positioned along its width', () => {
    const [first, second] = wordsOf([[{ str: 'ab cd', x: 10, y: 5, width: 50, height: 8 }]])
    expect(first).toMatchObject({ text: 'ab', page: 1, x: 10 })
    expect(second.x).toBeCloseTo(40)
  })

  it('clamps removed pages beyond the new page count', () => {
    const changes = typesetChanges([[line('a')], [line('b')], [line('gone here')]], [[line('a')], [line('b')]])
    expect(changedPageNumbers(changes, 2)).toEqual([2])
    expect(changes.base[0].page).toBe(3)
  })
})

describe('hunks', () => {
  it('groups a replaced phrase into one change with both sides', () => {
    const changes = typesetChanges([[line('alpha old text omega', 10)]], [[line('alpha new omega', 10)]])
    expect(changes.hunks).toHaveLength(1)
    expect(changes.hunks[0].before).toMatchObject({ page: 1, words: 2, text: 'old text' })
    expect(changes.hunks[0].after).toMatchObject({ page: 1, words: 1, text: 'new' })
  })

  it('has only a before side for a pure deletion and only an after side for an insertion', () => {
    const deleted = typesetChanges([[line('keep one', 10), line('gone words', 30), line('keep two', 50)]], [[line('keep one', 10), line('keep two', 30)]])
    expect(deleted.hunks).toHaveLength(1)
    expect(deleted.hunks[0].after).toBeNull()
    expect(deleted.hunks[0].before?.text).toBe('gone words')
    const inserted = typesetChanges([[line('a')]], [[line('a b')]])
    expect(inserted.hunks[0].before).toBeNull()
    expect(inserted.hunks[0].after?.text).toBe('b')
  })

  it('keeps distant edits apart and merges neighbouring ones', () => {
    const base = [[line('one a', 10), line('keep', 200), line('two b', 400)]]
    const target = [[line('one x', 10), line('keep', 200), line('two y', 400)]]
    expect(typesetChanges(base, target).hunks).toHaveLength(2)
    expect(typesetChanges([[line('p a q b r', 10)]], [[line('p x q y r', 10)]]).hunks).toHaveLength(1)
  })

  it('never pairs an insertion with a distant deletion', () => {
    const base = [[line('top keep', 10), line('keep mid', 100), line('gone words here', 300), line('tail keep', 400)]]
    const target = [[line('top NEW keep', 10), line('keep mid', 100), line('tail keep', 300)]]
    const hunks = typesetChanges(base, target).hunks
    expect(hunks).toHaveLength(2)
    expect(hunks[0].before).toBeNull()
    expect(hunks[0].after?.text).toBe('NEW')
    expect(hunks[1].after).toBeNull()
    expect(hunks[1].before?.text).toBe('gone words here')
  })

  it('keeps an insertion and a deletion on different pages apart', () => {
    const base = [[line('keep a', 10)], [line('keep b', 10), line('gone', 40)]]
    const target = [[line('keep a NEW', 10)], [line('keep b', 10)]]
    const hunks = typesetChanges(base, target).hunks
    expect(hunks).toHaveLength(2)
    expect(hunks[0]).toMatchObject({ before: null, after: { page: 1 } })
    expect(hunks[1]).toMatchObject({ before: { page: 2 }, after: null })
  })

  it('counts only the words of the page it shows', () => {
    const base = [[line('keep start', 700)], [line('second half keep', 10)]]
    const target = [[line('keep', 700)], [line('keep', 10)]]
    const side = typesetChanges(base, target).hunks[0].before
    expect(side).toMatchObject({ page: 1 })
    expect(side?.words).toBe(side?.text.split(' ').length)
  })

  it('has none when nothing changed', () => {
    expect(typesetChanges([[line('same')]], [[line('same')]]).hunks).toEqual([])
  })
})
