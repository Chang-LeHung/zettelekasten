/**
 * Pixel comparison for what text cannot show: figures, plots, rules, equation art.
 *
 * Two renderings of the same page are compared in a coarse grid. Cells that overlap any text run are
 * ignored, because the word diff already covers text and a reflowed paragraph would otherwise paint
 * the whole page. The remaining changed cells are joined into boxes.
 */
import type { DiffRect } from './pdfTypesetDiff'

export interface Pixels {
  width: number
  height: number
  data: ArrayLike<number>
}

export interface VisualOptions {
  /** Edge of one grid cell, in rendered pixels. */
  cell?: number
  /** Share of a cell's pixels that must differ before the cell counts as changed. */
  ratio?: number
  /** Smallest per-pixel luminance step that counts as a difference. */
  step?: number
  /** Boxes made of fewer cells than this are noise (anti-aliasing at a moved edge). */
  minCells?: number
}

const DEFAULTS: Required<VisualOptions> = { cell: 10, ratio: 0.04, step: 48, minCells: 2 }

/** Largest per-channel step, so a figure recoloured at equal brightness still counts. */
function delta(a: ArrayLike<number>, b: ArrayLike<number>, index: number): number {
  return Math.max(Math.abs(a[index] - b[index]), Math.abs(a[index + 1] - b[index + 1]), Math.abs(a[index + 2] - b[index + 2]))
}

function cellBox(c0: number, r0: number, c1: number, r1: number, cell: number, scale: number): DiffRect {
  return { x: (c0 * cell) / scale, y: (r0 * cell) / scale, width: ((c1 - c0 + 1) * cell) / scale, height: ((r1 - r0 + 1) * cell) / scale }
}

/** Changed boxes in page units (rendered pixels divided by `scale`). Pages of unequal size have no pixel comparison. */
export function visualChanges(
  base: Pixels,
  target: Pixels,
  scale: number,
  textBoxes: readonly DiffRect[],
  options: VisualOptions = {},
): DiffRect[] {
  if (base.width !== target.width || base.height !== target.height || scale <= 0) return []
  const { cell, ratio, step, minCells } = { ...DEFAULTS, ...options }
  const columns = Math.ceil(base.width / cell)
  const rows = Math.ceil(base.height / cell)
  const changed = new Uint8Array(columns * rows)

  for (let row = 0; row < rows; row += 1) {
    for (let column = 0; column < columns; column += 1) {
      let differing = 0
      let total = 0
      const yEnd = Math.min(base.height, (row + 1) * cell)
      const xEnd = Math.min(base.width, (column + 1) * cell)
      for (let y = row * cell; y < yEnd; y += 1) {
        for (let x = column * cell; x < xEnd; x += 1) {
          const index = (y * base.width + x) * 4
          total += 1
          if (delta(base.data, target.data, index) > step) differing += 1
        }
      }
      if (total && differing / total >= ratio) changed[row * columns + column] = 1
    }
  }

  // Text is the word diff's job: clear every cell a text run touches, with one cell of margin.
  for (const box of textBoxes) {
    const left = Math.max(0, Math.floor((box.x * scale) / cell) - 1)
    const right = Math.min(columns - 1, Math.floor(((box.x + box.width) * scale) / cell) + 1)
    const top = Math.max(0, Math.floor((box.y * scale) / cell) - 1)
    const bottom = Math.min(rows - 1, Math.floor(((box.y + box.height) * scale) / cell) + 1)
    for (let row = top; row <= bottom; row += 1) {
      for (let column = left; column <= right; column += 1) changed[row * columns + column] = 0
    }
  }

  const seen = new Uint8Array(columns * rows)
  const boxes: DiffRect[] = []
  for (let start = 0; start < changed.length; start += 1) {
    if (!changed[start] || seen[start]) continue
    const stack = [start]
    seen[start] = 1
    const cells: number[] = []
    let count = 0
    let minColumn = columns
    let maxColumn = 0
    let minRow = rows
    let maxRow = 0
    while (stack.length) {
      const at = stack.pop() as number
      const row = Math.floor(at / columns)
      const column = at % columns
      count += 1
      cells.push(at)
      minColumn = Math.min(minColumn, column)
      maxColumn = Math.max(maxColumn, column)
      minRow = Math.min(minRow, row)
      maxRow = Math.max(maxRow, row)
      for (let dy = -1; dy <= 1; dy += 1) {
        for (let dx = -1; dx <= 1; dx += 1) {
          const nextRow = row + dy
          const nextColumn = column + dx
          if (nextRow < 0 || nextColumn < 0 || nextRow >= rows || nextColumn >= columns) continue
          const next = nextRow * columns + nextColumn
          if (!changed[next] || seen[next]) continue
          seen[next] = 1
          stack.push(next)
        }
      }
    }
    if (count < minCells) continue
    const area = (maxColumn - minColumn + 1) * (maxRow - minRow + 1)
    if (area <= count * 3) {
      boxes.push(cellBox(minColumn, minRow, maxColumn, maxRow, cell, scale))
      continue
    }
    // A sparse cluster (a rule at the top joined to a figure far below) would wash over everything
    // between, so report each horizontal run of cells separately.
    const byRow = new Map<number, number[]>()
    for (const at of cells) {
      const row = Math.floor(at / columns)
      byRow.set(row, [...(byRow.get(row) ?? []), at % columns])
    }
    for (const [row, list] of byRow) {
      list.sort((p, q) => p - q)
      let start = list[0]
      for (let index = 1; index <= list.length; index += 1) {
        if (index < list.length && list[index] - list[index - 1] <= 1) continue
        boxes.push(cellBox(start, row, list[index - 1], row, cell, scale))
        start = list[index]
      }
    }
  }
  return boxes
}
