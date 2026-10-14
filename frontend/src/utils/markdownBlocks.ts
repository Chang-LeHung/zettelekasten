/**
 * Markdown as a list of blocks, without ever rewriting what the user did not touch.
 *
 * The block editor shows a document as paragraphs, headings, lists, code and so
 * on, but the document stays one Markdown string. Zett's bodies carry syntax a
 * rich-text tree cannot round-trip: raw HTML, slide separators and markers,
 * display math, captioned figures. So a block is only a slice of that string.
 * `text` is the slice, and `gap` is the exact whitespace that followed it, which
 * makes `joinBlocks(splitBlocks(x)) === x` hold for every input. An edit rewrites
 * the one block it happened in, and the rest of the document comes back byte for
 * byte.
 */

export interface Block {
  /** Stable for the life of the editor; never derived from the text. */
  id: number
  text: string
  /** Newlines (and blank lines) between this block and the next, verbatim. */
  gap: string
}

export type BlockKind =
  | 'empty'
  | 'paragraph'
  | 'heading'
  | 'list'
  | 'todo'
  | 'quote'
  | 'code'
  | 'diagram'
  | 'math'
  | 'table'
  | 'html'
  | 'image'
  | 'divider'
  | 'slideBreak'
  | 'sectionBreak'
  | 'slideMarker'

export interface SplitOptions {
  /**
   * A slide deck separates pages with a bare `--` or `---` line that needs no
   * blank line around it, so such a line always starts a block of its own.
   */
  slides?: boolean
}

let nextId = 1

export function newBlockId(): number {
  return nextId++
}

export function makeBlock(text: string, gap = '\n\n'): Block {
  return { id: newBlockId(), text, gap }
}

const FENCE = /^ {0,3}(`{3,}|~{3,})(.*)$/u
const BLANK = /^[ \t\r]*$/u
const SEPARATOR = /^(---|--)[ \t]*$/u

/** Whether the lines so far leave a fence open. */
export function hasOpenFence(text: string): boolean {
  let open: { char: string; length: number } | null = null
  for (const line of text.split('\n')) {
    const match = FENCE.exec(line)
    if (!match) continue
    const run = match[1]!
    if (!open) {
      // A backtick fence's info string may not contain a backtick, or it is inline code.
      if (run[0] === '`' && match[2]!.includes('`')) continue
      open = { char: run[0]!, length: run.length }
    } else if (run[0] === open.char && run.length >= open.length && !match[2]!.trim()) {
      open = null
    }
  }
  return open !== null
}

/** Whether a standalone `$$` line leaves display math open. */
export function hasOpenMath(text: string): boolean {
  let open = false
  for (const line of text.split('\n')) if (line.trim() === '$$') open = !open
  return open
}

const BLOCK_TAGS = /^<([a-zA-Z][\w-]*)\b/u
const VOID_TAGS = new Set(['area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'source', 'track', 'wbr'])

/**
 * The line a raw HTML block ends on, or `null` when its first tag never closes.
 * HTML written by the model often has blank lines inside one `<div>`; cutting the
 * block there would leave two halves that render as broken markup.
 */
function htmlBlockEnd(lines: readonly string[], start: number): number | null {
  const first = BLOCK_TAGS.exec(lines[start]!.trimStart())
  if (!first) return null
  const tag = first[1]!.toLowerCase()
  if (VOID_TAGS.has(tag)) return null
  const open = new RegExp(`<${tag}(?=[\\s/>])`, 'giu')
  const close = new RegExp(`</${tag}\\s*>`, 'giu')
  let depth = 0
  for (let index = start; index < lines.length; index += 1) {
    const line = lines[index]!
    depth += (line.match(open) ?? []).length - (line.match(close) ?? []).length
    if (depth <= 0) return index
  }
  return null
}

/** Cut a document into blocks. Lossless: `joinBlocks(splitBlocks(x)) === x`. */
export function splitBlocks(source: string, options: SplitOptions = {}): Block[] {
  if (source === '') return [{ id: newBlockId(), text: '', gap: '' }]
  const lines = source.split('\n')
  const blocks: Block[] = []
  let index = 0

  // Blank lines before the first block belong to an empty block of their own.
  if (BLANK.test(lines[0]!)) {
    const leading: string[] = []
    while (index < lines.length && BLANK.test(lines[index]!)) leading.push(lines[index++]!)
    blocks.push({ id: newBlockId(), text: '', gap: leading.join('\n') + (index < lines.length ? '\n' : '') })
  }

  while (index < lines.length) {
    const start = index
    const end = blockEnd(lines, start, options)
    index = end + 1
    // The gap is every line up to the next block, joined exactly as the source had them.
    const blank: string[] = []
    while (index < lines.length && BLANK.test(lines[index]!)) blank.push(lines[index++]!)
    const hasNext = index < lines.length
    const gap = (blank.length ? `\n${blank.join('\n')}` : '') + (hasNext ? '\n' : '')
    blocks.push({ id: newBlockId(), text: lines.slice(start, end + 1).join('\n'), gap })
  }
  return blocks
}

/** The last line of the block that starts on line `start`. */
function blockEnd(lines: readonly string[], start: number, options: SplitOptions): number {
  const first = lines[start]!
  if (options.slides && SEPARATOR.test(first)) return start

  const fence = FENCE.exec(first)
  if (fence && !(fence[1]![0] === '`' && fence[2]!.includes('`'))) {
    const char = fence[1]![0]!
    const length = fence[1]!.length
    for (let index = start + 1; index < lines.length; index += 1) {
      const closing = FENCE.exec(lines[index]!)
      if (closing && closing[1]![0] === char && closing[1]!.length >= length && !closing[2]!.trim()) return index
    }
    return lines.length - 1
  }
  if (first.trim() === '$$') {
    for (let index = start + 1; index < lines.length; index += 1) if (lines[index]!.trim() === '$$') return index
    return lines.length - 1
  }

  // A balanced HTML element may hold blank lines; the block runs to where it closes,
  // and then, like any paragraph, to the next blank line.
  let end = start
  if (BLOCK_TAGS.test(first.trimStart())) end = htmlBlockEnd(lines, start) ?? start
  while (end + 1 < lines.length && !BLANK.test(lines[end + 1]!)) {
    if (options.slides && SEPARATOR.test(lines[end + 1]!)) break
    end += 1
  }
  return end
}

/** Put blocks back together exactly as they were cut. */
export function joinBlocks(blocks: readonly Block[]): string {
  return blocks.map((block) => block.text + block.gap).join('')
}

/**
 * Re-cut a document after it changed somewhere else (the source column, an
 * undo), keeping the ids of the blocks that sit in the same place so the editor
 * does not lose focus or re-render everything.
 */
export function reconcileBlocks(previous: readonly Block[], source: string, options: SplitOptions = {}): Block[] {
  if (joinBlocks(previous) === source) return [...previous]
  const next = splitBlocks(source, options)
  return next.map((block, index) => {
    const before = previous[index]
    return before ? { ...block, id: before.id } : block
  })
}

const MARKER = /^<!--\s*slide:(cover|html)\s*-->/u

/** The slide layout a block's first line selects, if it carries a marker. */
export function slideMarker(text: string): 'cover' | 'html' | null {
  const match = MARKER.exec(text.trimStart())
  return match ? (match[1] as 'cover' | 'html') : null
}

/** Drop the marker line, which the editor shows as a label instead of text. */
export function withoutSlideMarker(text: string): string {
  return text.replace(/^\s*<!--\s*slide:(?:cover|html)\s*-->[ \t]*\n?/u, '')
}

/** What a block is, for its look in the editor and for what Enter should do in it. */
export function blockKind(text: string, options: SplitOptions = {}): BlockKind {
  const trimmed = text.trim()
  if (!trimmed) return 'empty'
  const first = text.split('\n')[0]!
  if (slideMarker(text)) return 'slideMarker'
  if (/^ {0,3}#{1,6}(?:[ \t]|$)/u.test(first)) return 'heading'
  const fence = FENCE.exec(first)
  if (fence) return /^mermaid\b/iu.test(fence[2]!.trim()) ? 'diagram' : 'code'
  if (trimmed.startsWith('$$')) return 'math'
  if (/^(?:---+|\*\*\*+|___+)$/u.test(trimmed)) {
    if (options.slides && trimmed === '---') return 'sectionBreak'
    return 'divider'
  }
  if (options.slides && trimmed === '--') return 'slideBreak'
  if (/^ {0,3}>/u.test(first)) return 'quote'
  if (/^[ \t]*[-*+][ \t]+\[[ xX]\](?:[ \t]|$)/u.test(first)) return 'todo'
  if (/^[ \t]*(?:[-*+]|\d{1,9}[.)])(?:[ \t]|$)/u.test(first)) return 'list'
  const lines = text.split('\n')
  if (lines.length >= 2 && first.includes('|') && /^[ \t]*\|?[ \t]*:?-{3,}:?[ \t]*(?:\|[ \t]*:?-{3,}:?[ \t]*)*\|?[ \t]*$/u.test(lines[1]!)) return 'table'
  if (/^!\[[^\]]*\]\([^)]*\)[ \t]*$/u.test(trimmed)) return 'image'
  if (/^<[a-zA-Z/!]/u.test(trimmed)) return 'html'
  return 'paragraph'
}

/** Heading depth of a heading block, or 0. */
export function headingLevel(text: string): number {
  const match = /^ {0,3}(#{1,6})(?:[ \t]|$)/u.exec(text)
  return match ? match[1]!.length : 0
}

/** Kinds whose Enter inserts a line break instead of starting a new block. */
export function keepsLineBreaks(kind: BlockKind, text: string): boolean {
  if (kind === 'code' || kind === 'diagram' || kind === 'math' || kind === 'table' || kind === 'html') return true
  return hasOpenFence(text) || hasOpenMath(text)
}

// ---------------------------------------------------------------------------
// Lists

const LIST_LINE = /^([ \t]*)((?:[-*+]|\d{1,9}[.)])[ \t]+)(\[[ xX]\][ \t]+)?(.*)$/u
const QUOTE_LINE = /^( {0,3}>[ \t]?)(.*)$/u

export interface ListContinuation {
  /** `continue` adds the marker on a new line; `exit` leaves the list. */
  action: 'continue' | 'exit'
  /** For `continue`: the text to insert at the caret, newline included. */
  insert: string
}

/** What Enter does at `caret` in a list or quote line: the next marker, or an exit when the item is empty. */
export function continueList(text: string, caret: number): ListContinuation | null {
  const lineStart = text.lastIndexOf('\n', caret - 1) + 1
  const lineEndIndex = text.indexOf('\n', caret)
  const line = text.slice(lineStart, lineEndIndex < 0 ? text.length : lineEndIndex)
  const quote = QUOTE_LINE.exec(line)
  if (quote) return quote[2]!.trim() ? { action: 'continue', insert: '\n> ' } : { action: 'exit', insert: '' }
  const match = LIST_LINE.exec(line)
  if (!match) return null
  const [, indent, marker, todo, rest] = match as unknown as [string, string, string, string | undefined, string]
  if (!rest.trim()) return { action: 'exit', insert: '' }
  const ordered = /^\d/u.test(marker)
  const nextMarker = ordered
    ? `${Number.parseInt(marker, 10) + 1}${marker.trim().slice(-1)} `
    : marker
  return { action: 'continue', insert: `\n${indent}${nextMarker}${todo ? '[ ] ' : ''}` }
}

/** Remove the (empty) list line the caret is on, for leaving a list with Enter. */
export function exitList(text: string, caret: number): { text: string; caret: number } {
  const lineStart = text.lastIndexOf('\n', caret - 1) + 1
  const lineEndIndex = text.indexOf('\n', caret)
  const lineEnd = lineEndIndex < 0 ? text.length : lineEndIndex
  const before = text.slice(0, Math.max(0, lineStart - 1))
  const after = text.slice(lineEnd + 1)
  // The list's last line is dropped together with the newline before it.
  const trimmed = lineStart === 0 ? after : before
  return { text: trimmed.replace(/[ \t]+$/u, ''), caret: trimmed.length }
}

/** Indent or outdent every line the selection touches by two spaces. */
export function shiftLines(
  text: string,
  start: number,
  end: number,
  direction: 1 | -1,
): { text: string; start: number; end: number } {
  const lineStart = text.lastIndexOf('\n', start - 1) + 1
  const lineEndIndex = text.indexOf('\n', end)
  const lineEnd = lineEndIndex < 0 ? text.length : lineEndIndex
  const lines = text.slice(lineStart, lineEnd).split('\n')
  let firstDelta = 0
  let totalDelta = 0
  const shifted = lines.map((line, index) => {
    if (direction === 1) {
      if (index === 0) firstDelta = 2
      totalDelta += 2
      return `  ${line}`
    }
    const removed = line.startsWith('  ') ? 2 : line.startsWith(' ') || line.startsWith('\t') ? 1 : 0
    if (index === 0) firstDelta = -removed
    totalDelta -= removed
    return line.slice(removed)
  })
  const replaced = shifted.join('\n')
  return {
    text: text.slice(0, lineStart) + replaced + text.slice(lineEnd),
    start: Math.max(lineStart, start + firstDelta),
    end: Math.max(lineStart, end + totalDelta),
  }
}

// ---------------------------------------------------------------------------
// Inline formatting

export interface TextEdit {
  text: string
  start: number
  end: number
}

/**
 * Whether the selection already sits in `marker … closing`, either just inside
 * them or with them selected. A single `*` is not "wrapped" by the `**` of a bold
 * word, which is how Italic tells itself apart from Bold.
 */
export function isWrapped(text: string, start: number, end: number, marker: string, closing = marker): boolean {
  if (start === end) return false
  const single = marker.length === 1 && marker === closing
  const around = (index: number, side: -1 | 1) => (side < 0 ? text[index - 1] : text[index])
  const outside =
    text.slice(Math.max(0, start - marker.length), start) === marker
    && text.slice(end, end + closing.length) === closing
    && !(single && (around(start - marker.length, -1) === marker || around(end + closing.length, 1) === marker))
  if (outside) return true
  const selected = text.slice(start, end)
  return selected.length >= marker.length + closing.length
    && selected.startsWith(marker)
    && selected.endsWith(closing)
    && !(single && (selected[1] === marker || selected[selected.length - 2] === marker))
}

/**
 * Wrap the selection in `marker` (`**`, `*`, `` ` ``…), or unwrap it when it is
 * already wrapped, which is how Bold and Italic toggle.
 */
export function toggleInline(text: string, start: number, end: number, marker: string, closing = marker): TextEdit {
  if (isWrapped(text, start, end, marker, closing)) {
    const selected = text.slice(start, end)
    if (selected.startsWith(marker) && selected.endsWith(closing) && selected.length >= marker.length + closing.length) {
      const inner = selected.slice(marker.length, selected.length - closing.length)
      return { text: text.slice(0, start) + inner + text.slice(end), start, end: start + inner.length }
    }
    return {
      text: text.slice(0, start - marker.length) + selected + text.slice(end + closing.length),
      start: start - marker.length,
      end: end - marker.length,
    }
  }
  const selected = text.slice(start, end)
  return {
    text: text.slice(0, start) + marker + selected + closing + text.slice(end),
    start: start + marker.length,
    end: end + marker.length,
  }
}

/** Turn the selection into a link and select the placeholder URL, ready to be typed over. */
export function makeLink(text: string, start: number, end: number): TextEdit {
  const label = text.slice(start, end) || 'link'
  const url = 'https://'
  const inserted = `[${label}](${url})`
  const urlStart = start + label.length + 3
  return {
    text: text.slice(0, start) + inserted + text.slice(end),
    start: urlStart,
    end: urlStart + url.length,
  }
}

// ---------------------------------------------------------------------------
// Turn a block into another kind

export type TurnTarget = 'paragraph' | 'h1' | 'h2' | 'h3' | 'bullet' | 'numbered' | 'todo' | 'quote' | 'code'

const LINE_PREFIX = /^(?: {0,3}#{1,6}[ \t]+|[ \t]*(?:[-*+]|\d{1,9}[.)])[ \t]+(?:\[[ xX]\][ \t]+)?| {0,3}>[ \t]?)/u

function stripLinePrefix(line: string): string {
  return line.replace(LINE_PREFIX, '')
}

/** Rewrite a block's text as another kind, keeping the words. */
export function turnInto(text: string, target: TurnTarget): string {
  if (target === 'code') {
    const body = text.replace(/^ {0,3}(`{3,}|~{3,})[^\n]*\n?/u, '').replace(/\n? {0,3}(`{3,}|~{3,})[ \t]*$/u, '')
    return `\`\`\`\n${body}\n\`\`\``
  }
  const fenced = /^ {0,3}(`{3,}|~{3,})[^\n]*\n([\s\S]*?)\n? {0,3}\1[ \t]*$/u.exec(text)
  const lines = (fenced ? fenced[2]! : text).split('\n').map(stripLinePrefix)
  switch (target) {
    case 'paragraph':
      return lines.join('\n')
    case 'h1':
    case 'h2':
    case 'h3':
      return `${'#'.repeat(Number(target[1]))} ${lines.join(' ')}`
    case 'bullet':
      return lines.map((line) => `- ${line}`).join('\n')
    case 'numbered':
      return lines.map((line, index) => `${index + 1}. ${line}`).join('\n')
    case 'todo':
      return lines.map((line) => `- [ ] ${line}`).join('\n')
    case 'quote':
      return lines.map((line) => `> ${line}`).join('\n')
  }
}

/** Whether a block holds nothing but its prefix (`- `, `## `, `> `), so Backspace can clear it. */
export function isPrefixOnly(text: string): boolean {
  return text.length > 0 && !text.includes('\n') && stripLinePrefix(text) === '' && LINE_PREFIX.test(text)
}
