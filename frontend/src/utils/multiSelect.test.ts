import { expect, it } from 'vitest'
import {
  boxesIntersect, boxFromPoints, exceedsThreshold, idsInBox, pruned, rangeBetween, settleLimited, toggled,
} from './multiSelect'

const card = (id: string, left: number, top: number) => ({ id, box: { left, top, right: left + 100, bottom: top + 80 } })

it('builds a rectangle from two corners in any direction', () => {
  expect(boxFromPoints(50, 40, 10, 90)).toEqual({ left: 10, top: 40, right: 50, bottom: 90 })
})

it('selects the cards a drag rectangle covers, and not ones it only touches', () => {
  const cards = [card('a', 0, 0), card('b', 120, 0), card('c', 0, 100)]
  expect(idsInBox(boxFromPoints(50, 40, 150, 60), cards)).toEqual(['a', 'b'])
  expect(idsInBox(boxFromPoints(100, 0, 120, 80), cards)).toEqual([])
  expect(boxesIntersect({ left: 0, top: 0, right: 10, bottom: 10 }, { left: 5, top: 5, right: 20, bottom: 20 })).toBe(true)
})

it('treats a tiny movement as a click, not a drag', () => {
  expect(exceedsThreshold(1, 2)).toBe(false)
  expect(exceedsThreshold(4, 0)).toBe(true)
})

it('spans from the anchor to the target in list order, either way round', () => {
  const order = ['a', 'b', 'c', 'd', 'e']
  expect(rangeBetween(order, 'b', 'd')).toEqual(['b', 'c', 'd'])
  expect(rangeBetween(order, 'd', 'b')).toEqual(['b', 'c', 'd'])
  expect(rangeBetween(order, null, 'c')).toEqual(['c'])
  expect(rangeBetween(order, 'gone', 'c')).toEqual(['c'])
  expect(rangeBetween(order, 'a', 'missing')).toEqual([])
})

it('toggles without mutating and drops ids that left the list', () => {
  const selection = new Set(['a'])
  expect([...toggled(selection, 'b')]).toEqual(['a', 'b'])
  expect([...toggled(selection, 'a')]).toEqual([])
  expect([...selection]).toEqual(['a'])
  expect([...pruned(new Set(['a', 'x']), ['a', 'b'])]).toEqual(['a'])
})

it('runs a batch with bounded concurrency and reports every outcome', async () => {
  let running = 0
  let peak = 0
  const results = await settleLimited([1, 2, 3, 4, 5, 6, 7], 3, async (n) => {
    running++
    peak = Math.max(peak, running)
    await new Promise((resolve) => setTimeout(resolve, 5))
    running--
    if (n === 4) throw new Error('nope')
    return n * 2
  })
  expect(peak).toBeLessThanOrEqual(3)
  expect(results.map((r) => r.status)).toEqual(['fulfilled', 'fulfilled', 'fulfilled', 'rejected', 'fulfilled', 'fulfilled', 'fulfilled'])
  expect(results[6]).toEqual({ status: 'fulfilled', value: 14 })
  expect(await settleLimited([], 4, async () => 1)).toEqual([])
})
