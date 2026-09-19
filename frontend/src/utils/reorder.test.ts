import { describe, expect, it } from 'vitest'
import { moveItemBeforeOrAfter } from './reorder'

const items = [{ id: 1 }, { id: 2 }, { id: 3 }, { id: 4 }]
const ids = (value: Array<{ id: number }>) => value.map(item => item.id)

describe('moveItemBeforeOrAfter', () => {
  it('moves an item before a target', () => {
    expect(ids(moveItemBeforeOrAfter(items, 4, 2, false, item => item.id))).toEqual([1, 4, 2, 3])
  })

  it('moves an item after a target', () => {
    expect(ids(moveItemBeforeOrAfter(items, 1, 3, true, item => item.id))).toEqual([2, 3, 1, 4])
  })

  it('leaves the list unchanged for same or missing identifiers', () => {
    expect(ids(moveItemBeforeOrAfter(items, 2, 2, false, item => item.id))).toEqual([1, 2, 3, 4])
    expect(ids(moveItemBeforeOrAfter(items, 10, 2, false, item => item.id))).toEqual([1, 2, 3, 4])
  })
})
