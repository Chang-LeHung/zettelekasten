import { describe, expect, it } from 'vitest'
import { diffSequences } from './sequenceDiff'

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

