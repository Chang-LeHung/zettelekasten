export interface SequenceDiff {
  removed: Set<number>
  added: Set<number>
  coarse: boolean
}

/** Edit distance beyond which the diff stops being exact. */
export const MAX_EDIT_DISTANCE = 1500

/** Myers' O(ND) shortest edit script over word texts. */
export function diffSequences(left: readonly string[], right: readonly string[], maxDistance = MAX_EDIT_DISTANCE): SequenceDiff {
  let start = 0
  while (start < left.length && start < right.length && left[start] === right[start]) start += 1
  let leftEnd = left.length
  let rightEnd = right.length
  while (leftEnd > start && rightEnd > start && left[leftEnd - 1] === right[rightEnd - 1]) {
    leftEnd -= 1
    rightEnd -= 1
  }
  const a = left.slice(start, leftEnd)
  const b = right.slice(start, rightEnd)
  const removed = new Set<number>()
  const added = new Set<number>()
  if (!a.length && !b.length) return { removed, added, coarse: false }
  if (!a.length || !b.length) {
    for (let i = 0; i < a.length; i += 1) removed.add(start + i)
    for (let i = 0; i < b.length; i += 1) added.add(start + i)
    return { removed, added, coarse: false }
  }

  const n = a.length
  const m = b.length
  const limit = Math.min(n + m, maxDistance)
  const offset = limit + 1
  const frontier = new Int32Array(2 * limit + 3)
  const trace: Int32Array[] = []
  let found = -1
  for (let d = 0; d <= limit && found < 0; d += 1) {
    trace.push(frontier.slice(offset - d - 1, offset + d + 2))
    for (let k = -d; k <= d; k += 2) {
      const index = k + offset
      let x = k === -d || (k !== d && frontier[index - 1] < frontier[index + 1])
        ? frontier[index + 1]
        : frontier[index - 1] + 1
      let y = x - k
      while (x < n && y < m && a[x] === b[y]) {
        x += 1
        y += 1
      }
      frontier[index] = x
      if (x >= n && y >= m) {
        found = d
        break
      }
    }
  }

  if (found < 0) {
    for (let i = 0; i < a.length; i += 1) removed.add(start + i)
    for (let i = 0; i < b.length; i += 1) added.add(start + i)
    return { removed, added, coarse: true }
  }

  const at = (d: number, k: number): number => trace[d][k + d + 1]
  let x = n
  let y = m
  for (let d = found; d > 0; d -= 1) {
    const k = x - y
    const previousK = k === -d || (k !== d && at(d, k - 1) < at(d, k + 1)) ? k + 1 : k - 1
    const previousX = at(d, previousK)
    const previousY = previousX - previousK
    while (x > previousX && y > previousY) {
      x -= 1
      y -= 1
    }
    if (x === previousX) {
      y -= 1
      added.add(start + y)
    } else {
      x -= 1
      removed.add(start + x)
    }
  }
  return { removed, added, coarse: false }
}
