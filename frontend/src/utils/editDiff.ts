import { diffLines } from './artifactDiff'
import { diffSequences } from './pdfTypesetDiff'

/** A stretch of one line; `strong` marks the part that changed inside a modified line. */
export interface EditSegment {
  text: string
  strong: boolean
}

export interface EditDiffRow {
  kind: 'context' | 'added' | 'removed'
  segments: EditSegment[]
}

/** Largest edit (old + new lines) shown with a full diff; beyond it every line is plain add or remove. */
const MAX_LINES = 400
/** A modified line is emphasised only when this share of its tokens survived; otherwise it is a rewrite. */
const MIN_SHARED = 0.3

function tokens(line: string): string[] {
  return line.match(/\s+|\w+|[^\w\s]/gu) ?? []
}

function plain(kind: EditDiffRow['kind'], text: string): EditDiffRow {
  return { kind, segments: [{ text, strong: false }] }
}

function join(parts: readonly string[], marked: ReadonlySet<number>): EditSegment[] {
  const segments: EditSegment[] = []
  parts.forEach((text, index) => {
    const strong = marked.has(index) && text.trim() !== ''
    const last = segments[segments.length - 1]
    if (last && last.strong === strong) last.text += text
    else segments.push({ text, strong })
  })
  return segments
}

/** Pair a removed line with the added line that replaced it and emphasise only what differs. */
function modified(before: string, after: string): [EditDiffRow, EditDiffRow] {
  const left = tokens(before)
  const right = tokens(after)
  const { removed, added, coarse } = diffSequences(left, right)
  const shared = Math.min(left.length - removed.size, right.length - added.size)
  const keep = Math.max(left.length, right.length)
  if (coarse || keep === 0 || shared / keep < MIN_SHARED) return [plain('removed', before), plain('added', after)]
  return [
    { kind: 'removed', segments: join(left, removed) },
    { kind: 'added', segments: join(right, added) },
  ]
}

/**
 * Rows for an `edit` tool call: context lines, removed and added lines.
 *
 * A line that was changed in place (a removed line and an added line side by side) gets its
 * changed words emphasised, so the eye lands on what differs. A line that was only added or only
 * deleted has nothing to compare with and stays plain.
 */
export function editDiffRows(before: string, after: string): EditDiffRow[] {
  // An empty side is a pure insertion or deletion, not an edit of one empty line.
  if (before === '') return after.split('\n').map((text) => plain('added', text))
  if (after === '') return before.split('\n').map((text) => plain('removed', text))
  const lines = diffLines(before, after)
  const rows: EditDiffRow[] = []
  const oversize = lines.length > MAX_LINES
  let index = 0
  while (index < lines.length) {
    const line = lines[index]
    if (line.kind === 'context') {
      rows.push(plain('context', line.text))
      index += 1
      continue
    }
    const removed: string[] = []
    const added: string[] = []
    while (index < lines.length && lines[index].kind === 'removed') removed.push(lines[index++].text)
    while (index < lines.length && lines[index].kind === 'added') added.push(lines[index++].text)
    const paired = oversize ? 0 : Math.min(removed.length, added.length)
    const old: EditDiffRow[] = []
    const next: EditDiffRow[] = []
    for (let at = 0; at < removed.length; at += 1) {
      if (at < paired) {
        const [a, b] = modified(removed[at], added[at])
        old.push(a)
        next.push(b)
      } else old.push(plain('removed', removed[at]))
    }
    for (let at = paired; at < added.length; at += 1) next.push(plain('added', added[at]))
    rows.push(...old, ...next)
  }
  return rows
}

export interface EditChange {
  before: string
  after: string
}

function pair(value: unknown): EditChange | null {
  if (!value || typeof value !== 'object') return null
  const item = value as Record<string, unknown>
  const before = item.old_string ?? item.old_text
  const after = item.new_string ?? item.new_text
  return typeof before === 'string' && typeof after === 'string' ? { before, after } : null
}

/** Every before/after pair of an `edit` call: one pair, or an `edits` list; empty when the arguments are not that shape. */
export function editArguments(args: Record<string, unknown> | undefined): EditChange[] {
  if (!args) return []
  const single = pair(args)
  if (single) return [single]
  if (!Array.isArray(args.edits)) return []
  return args.edits.map(pair).filter((item): item is EditChange => item !== null)
}
