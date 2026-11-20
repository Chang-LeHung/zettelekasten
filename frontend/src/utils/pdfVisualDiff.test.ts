import { describe, expect, it } from 'vitest'
import { visualChanges, type Pixels } from './pdfVisualDiff'

function blank(width: number, height: number): Pixels {
  const data = new Uint8ClampedArray(width * height * 4).fill(255)
  return { width, height, data }
}

function paint(image: Pixels, left: number, top: number, width: number, height: number): void {
  for (let y = top; y < top + height; y += 1) {
    for (let x = left; x < left + width; x += 1) {
      const index = (y * image.width + x) * 4
      ;(image.data as Uint8ClampedArray).set([0, 0, 0, 255], index)
    }
  }
}

describe('visualChanges', () => {
  it('reports nothing for identical renderings', () => {
    expect(visualChanges(blank(100, 100), blank(100, 100), 1, [])).toEqual([])
  })

  it('boxes a figure that appears and converts back to page units', () => {
    const before = blank(200, 200)
    const after = blank(200, 200)
    paint(after, 40, 60, 50, 30)
    const [box] = visualChanges(before, after, 2, [])
    expect(box.x).toBeCloseTo(20, 0)
    expect(box.y).toBeCloseTo(30, 0)
    expect(box.width).toBeGreaterThanOrEqual(25)
    expect(box.height).toBeGreaterThanOrEqual(15)
  })

  it('ignores a change that lies under a text run', () => {
    const before = blank(200, 200)
    const after = blank(200, 200)
    paint(after, 40, 60, 50, 30)
    expect(visualChanges(before, after, 1, [{ x: 30, y: 50, width: 80, height: 50 }])).toEqual([])
  })

  it('drops a speck smaller than the minimum box', () => {
    const before = blank(100, 100)
    const after = blank(100, 100)
    paint(after, 12, 12, 4, 4)
    expect(visualChanges(before, after, 1, [], { minCells: 2 })).toEqual([])
  })

  it('does not compare pages of different size', () => {
    const after = blank(100, 120)
    paint(after, 10, 10, 40, 40)
    expect(visualChanges(blank(100, 100), after, 1, [])).toEqual([])
  })

  it('splits two far-apart changes instead of washing the page between them', () => {
    const before = blank(300, 300)
    const after = blank(300, 300)
    paint(after, 20, 10, 60, 20)
    paint(after, 20, 250, 60, 20)
    const boxes = visualChanges(before, after, 1, [])
    expect(boxes.length).toBeGreaterThanOrEqual(2)
    expect(Math.max(...boxes.map((box) => box.height))).toBeLessThan(100)
  })

  it('sees a figure that disappears and a recolour at equal brightness', () => {
    const grey = blank(100, 100)
    paint(grey, 20, 20, 40, 40)
    expect(visualChanges(grey, blank(100, 100), 1, []).length).toBe(1)
    const red = blank(100, 100)
    const green = blank(100, 100)
    for (let y = 20; y < 60; y += 1) for (let x = 20; x < 60; x += 1) {
      const index = (y * 100 + x) * 4
      ;(red.data as Uint8ClampedArray).set([200, 60, 60, 255], index)
      ;(green.data as Uint8ClampedArray).set([60, 150, 60, 255], index)
    }
    expect(visualChanges(red, green, 1, []).length).toBe(1)
  })
})
