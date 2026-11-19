/**
 * Word-level comparison of two typeset PDFs.
 *
 * Both documents are flattened into one word sequence each, diffed once across
 * the whole document (so a paragraph that moves to the next page is an edit, not
 * a rewrite of every following page), and the changed words are mapped back to
 * page rectangles. Coordinates are CSS pixels at scale 1 with the origin at the
 * page's top-left corner.
 */

/** One text run from a PDF text layer, already in top-left page coordinates. */
export interface TextBox {
  str: string
  x: number
  y: number
  width: number
  height: number
}

export interface DiffRect {
  x: number
  y: number
  width: number
  height: number
}

export interface PageChanges {
  /** One-based page number. */
  page: number
  rects: DiffRect[]
  /** Changed words on this page. */
  words: number
}

export interface TypesetChanges {
  /** Pages of the older PDF that lost text. */
  base: PageChanges[]
  /** Pages of the newer PDF that gained text. */
  target: PageChanges[]
  removedWords: number
  addedWords: number
  /** True when the edit script was too large to compute exactly. */
  coarse: boolean
}

interface Word extends DiffRect {
  text: string
  page: number
}

/** Edit distance beyond which the diff stops being exact. */
export const MAX_EDIT_DISTANCE = 1500

/** Collapse ligatures and width variants so the same word compares equal. */
function normalize(word: string): string {
  return word.normalize('NFKC')
}

export function wordsOf(pages: readonly (readonly TextBox[])[]): Word[] {
  const words: Word[] = []
  pages.forEach((items, pageIndex) => {
    for (const item of items) {
      const length = item.str.length
      if (!length || !item.width) continue
      const perChar = item.width / length
      for (const match of item.str.matchAll(/\S+/g)) {
        const start = match.index ?? 0
        words.push({
          text: normalize(match[0]),
          page: pageIndex + 1,
          x: item.x + start * perChar,
          y: item.y,
          width: match[0].length * perChar,
          height: item.height,
        })
      }
    }
  })
  return words
}

interface WordDiff {
  removed: Set<number>
  added: Set<number>
  coarse: boolean
}

/** Myers' O(ND) shortest edit script over word texts. */
export function diffSequences(left: readonly string[], right: readonly string[], maxDistance = MAX_EDIT_DISTANCE): WordDiff {
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

/** Merge neighbouring changed words on one line into a single padded box. */
export function mergeRects(words: readonly DiffRect[]): DiffRect[] {
  const ordered = [...words].sort((p, q) => p.y - q.y || p.x - q.x)
  const merged: DiffRect[] = []
  for (const word of ordered) {
    const previous = merged[merged.length - 1]
    const sameLine = previous && Math.abs(previous.y - word.y) < word.height * 0.6
    const gap = previous ? word.x - (previous.x + previous.width) : 0
    if (previous && sameLine && gap < word.height * 1.4) {
      const right = Math.max(previous.x + previous.width, word.x + word.width)
      const bottom = Math.max(previous.y + previous.height, word.y + word.height)
      previous.x = Math.min(previous.x, word.x)
      previous.y = Math.min(previous.y, word.y)
      previous.width = right - previous.x
      previous.height = bottom - previous.y
    } else {
      merged.push({ x: word.x, y: word.y, width: word.width, height: word.height })
    }
  }
  return merged
}

function pageChanges(words: readonly Word[], indexes: ReadonlySet<number>): PageChanges[] {
  const byPage = new Map<number, Word[]>()
  for (const index of indexes) {
    const word = words[index]
    byPage.set(word.page, [...(byPage.get(word.page) ?? []), word])
  }
  return [...byPage.entries()]
    .sort(([p], [q]) => p - q)
    .map(([page, changed]) => ({ page, words: changed.length, rects: mergeRects(changed) }))
}

/** Compare two documents given their per-page text runs. */
export function typesetChanges(
  basePages: readonly (readonly TextBox[])[],
  targetPages: readonly (readonly TextBox[])[],
): TypesetChanges {
  const base = wordsOf(basePages)
  const target = wordsOf(targetPages)
  const diff = diffSequences(base.map((word) => word.text), target.map((word) => word.text))
  return {
    base: pageChanges(base, diff.removed),
    target: pageChanges(target, diff.added),
    removedWords: diff.removed.size,
    addedWords: diff.added.size,
    coarse: diff.coarse,
  }
}

/** Pages worth visiting in the newer document, in order, including pages that only lost text. */
export function changedPageNumbers(changes: TypesetChanges, targetPageCount: number): number[] {
  const pages = new Set(changes.target.map((entry) => entry.page))
  for (const entry of changes.base) pages.add(Math.min(entry.page, Math.max(1, targetPageCount)))
  return [...pages].sort((p, q) => p - q)
}
