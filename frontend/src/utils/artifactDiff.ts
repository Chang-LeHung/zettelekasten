import type { ArtifactContent } from '../api/types'

export type DiffLineKind = 'context' | 'added' | 'removed'

export interface DiffLine {
  kind: DiffLineKind
  text: string
}

export interface ArtifactDiffField {
  label: string
  changed: boolean
  /** Changed regions with surrounding context; empty when the field is unchanged. */
  hunks: DiffLine[][]
}

export interface ArtifactDiff {
  fields: ArtifactDiffField[]
  changed: boolean
}

/** Lines of untouched context kept around every change. */
export const DIFF_CONTEXT_LINES = 3
/** Above this product the line diff degrades to one removed and one added block. */
const MAX_LCS_CELLS = 2_000_000
/** Artifact types this view compares; others keep their specialized editors. */
const DIFF_TYPES = new Set(['card', 'article'])

function splitLines(value: string): string[] {
  return value.replace(/\r\n/g, '\n').split('\n')
}

function lcsTable(left: readonly string[], right: readonly string[]): number[][] {
  const table: number[][] = Array.from({ length: left.length + 1 }, () => new Array<number>(right.length + 1).fill(0))
  for (let i = left.length - 1; i >= 0; i -= 1) {
    for (let j = right.length - 1; j >= 0; j -= 1) {
      table[i][j] = left[i] === right[j] ? table[i + 1][j + 1] + 1 : Math.max(table[i + 1][j], table[i][j + 1])
    }
  }
  return table
}

/**
 * Diff two texts line by line. Common leading and trailing lines are kept out of
 * the dynamic-programming table so ordinary edits stay cheap, and a very large
 * rewrite falls back to one removed block followed by one added block.
 */
export function diffLines(before: string, after: string): DiffLine[] {
  const left = splitLines(before)
  const right = splitLines(after)
  const lines: DiffLine[] = []

  let prefix = 0
  while (prefix < left.length && prefix < right.length && left[prefix] === right[prefix]) {
    lines.push({ kind: 'context', text: left[prefix] })
    prefix += 1
  }
  let suffix = 0
  while (
    suffix < left.length - prefix
    && suffix < right.length - prefix
    && left[left.length - suffix - 1] === right[right.length - suffix - 1]
  ) {
    suffix += 1
  }

  const leftMiddle = left.slice(prefix, left.length - suffix)
  const rightMiddle = right.slice(prefix, right.length - suffix)
  const trailing = suffix > 0 ? left.slice(left.length - suffix) : []

  if (leftMiddle.length * rightMiddle.length > MAX_LCS_CELLS) {
    lines.push(...leftMiddle.map((text): DiffLine => ({ kind: 'removed', text })))
    lines.push(...rightMiddle.map((text): DiffLine => ({ kind: 'added', text })))
  } else {
    const table = lcsTable(leftMiddle, rightMiddle)
    let i = 0
    let j = 0
    while (i < leftMiddle.length && j < rightMiddle.length) {
      if (leftMiddle[i] === rightMiddle[j]) {
        lines.push({ kind: 'context', text: leftMiddle[i] })
        i += 1
        j += 1
      } else if (table[i + 1][j] >= table[i][j + 1]) {
        lines.push({ kind: 'removed', text: leftMiddle[i] })
        i += 1
      } else {
        lines.push({ kind: 'added', text: rightMiddle[j] })
        j += 1
      }
    }
    while (i < leftMiddle.length) {
      lines.push({ kind: 'removed', text: leftMiddle[i] })
      i += 1
    }
    while (j < rightMiddle.length) {
      lines.push({ kind: 'added', text: rightMiddle[j] })
      j += 1
    }
  }

  lines.push(...trailing.map((text): DiffLine => ({ kind: 'context', text })))
  return lines
}

/** Group changed regions with a few unchanged lines of context around each one. */
export function diffHunks(lines: readonly DiffLine[], context = DIFF_CONTEXT_LINES): DiffLine[][] {
  const changed = lines.flatMap((line, index) => (line.kind === 'context' ? [] : [index]))
  if (!changed.length) return []
  const hunks: DiffLine[][] = []
  let start = Math.max(0, changed[0] - context)
  let end = Math.min(lines.length, changed[0] + context + 1)
  for (const index of changed.slice(1)) {
    if (index - context <= end) {
      end = Math.min(lines.length, index + context + 1)
      continue
    }
    hunks.push(lines.slice(start, end))
    start = Math.max(0, index - context)
    end = Math.min(lines.length, index + context + 1)
  }
  hunks.push(lines.slice(start, end))
  return hunks
}

function titleOf(content: ArtifactContent): string {
  return 'title' in content ? content.title : content.pdf_name
}

function summaryOf(content: ArtifactContent): string {
  return 'summary' in content ? content.summary : ''
}

function subtitleOf(content: ArtifactContent): string {
  return 'subtitle' in content ? content.subtitle : ''
}

function bodyOf(content: ArtifactContent): string {
  return 'content' in content ? content.content : ''
}

function field(label: string, before: string, after: string, context: number): ArtifactDiffField {
  const lines = diffLines(before, after)
  const hunks = diffHunks(lines, context)
  return { label, changed: hunks.length > 0, hunks }
}

/**
 * Compare the published artifact with the model's draft, field by field.
 * Returns null when there is nothing to compare or the type keeps a specialized
 * editor instead of this text diff.
 */
export function diffArtifactContent(
  published: ArtifactContent | null,
  draft: ArtifactContent | null,
  context = DIFF_CONTEXT_LINES,
): ArtifactDiff | null {
  if (!published || !draft) return null
  if (!DIFF_TYPES.has(published.artifact_type) || !DIFF_TYPES.has(draft.artifact_type)) return null

  const fields = [
    field('Title', titleOf(published), titleOf(draft), context),
    field('Summary', summaryOf(published), summaryOf(draft), context),
  ]
  if (published.artifact_type === 'article' || draft.artifact_type === 'article') {
    fields.push(field('Subtitle', subtitleOf(published), subtitleOf(draft), context))
  }
  if ('card_type' in published && 'card_type' in draft) {
    fields.push(field('Card type', published.card_type, draft.card_type, context))
  }
  fields.push(field('Body', bodyOf(published), bodyOf(draft), context))
  return { fields, changed: fields.some((entry) => entry.changed) }
}
