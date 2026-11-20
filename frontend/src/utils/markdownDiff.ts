/**
 * Block-level diff of two Markdown documents, meant to be rendered rather than read as source.
 *
 * Both sides are cut into verbatim blocks (so a fence or a display-math pair is never split), the
 * blocks are diffed as units, and a run of removed blocks followed by added blocks is paired
 * one-to-one so the view can emphasise the words that changed inside a rewritten paragraph.
 */
import type { ArtifactContent } from '../api/types'
import { splitBlocks } from './markdownBlocks'
import { diffSequences } from './pdfTypesetDiff'

export type MarkdownDiffKind = 'same' | 'added' | 'removed'

export interface MarkdownDiffBlock {
  key: string
  kind: MarkdownDiffKind
  text: string
  /** The whitespace that followed the block in its own document, verbatim. */
  gap: string
  /** Shared by a removed block and the added block that replaces it. */
  pair: number | null
}

export interface MarkdownDiff {
  blocks: MarkdownDiffBlock[]
  added: number
  removed: number
  changed: boolean
}

const norm = (text: string): string => text.replace(/\r\n/g, '\n').trim()

export function diffMarkdown(before: string, after: string): MarkdownDiff {
  const nonBlank = (source: string) => splitBlocks(source).filter((block) => norm(block.text) !== '')
  const left = nonBlank(before)
  const right = nonBlank(after)
  const { removed, added } = diffSequences(left.map((block) => norm(block.text)), right.map((block) => norm(block.text)))
  const blocks: MarkdownDiffBlock[] = []
  const make = (key: string, kind: MarkdownDiffKind, block: { text: string; gap: string }, pair: number | null): MarkdownDiffBlock => ({ key, kind, text: block.text, gap: block.gap, pair })
  let pairs = 0
  let i = 0
  let j = 0
  while (i < left.length || j < right.length) {
    if (i < left.length && removed.has(i)) {
      const dropped: number[] = []
      const inserted: number[] = []
      while (i < left.length && removed.has(i)) dropped.push(i++)
      while (j < right.length && added.has(j)) inserted.push(j++)
      const paired = Math.min(dropped.length, inserted.length)
      dropped.forEach((index, offset) => blocks.push(make(`r${index}`, 'removed', left[index], offset < paired ? pairs + offset : null)))
      inserted.forEach((index, offset) => blocks.push(make(`a${index}`, 'added', right[index], offset < paired ? pairs + offset : null)))
      pairs += paired
    } else if (j < right.length && added.has(j)) {
      blocks.push(make(`a${j}`, 'added', right[j], null))
      j += 1
    } else {
      blocks.push(make(`s${j}`, 'same', right[j] ?? left[i], null))
      i += 1
      j += 1
    }
  }
  return { blocks, added: added.size, removed: removed.size, changed: added.size + removed.size > 0 }
}

/** The words of one rendered block, in reading order, as the DOM walk below will see them. */
export function wordsOfText(text: string): string[] {
  return text.match(/\S+/g) ?? []
}

export interface WordMask {
  removed: Set<number>
  added: Set<number>
}

export function wordMask(before: string[], after: string[]): WordMask {
  const { removed, added } = diffSequences(before, after)
  return { removed, added }
}

const SKIP = new Set(['SCRIPT', 'STYLE', 'SVG'])

/** Text nodes of a rendered block, in the order words are numbered. */
export function textNodes(root: Node): Text[] {
  const found: Text[] = []
  const walk = (node: Node): void => {
    if (node.nodeType === Node.TEXT_NODE) found.push(node as Text)
    else if (!(node instanceof Element && SKIP.has(node.tagName.toUpperCase()))) node.childNodes.forEach(walk)
  }
  walk(root)
  return found
}

export function renderedWords(root: Node): string[] {
  return textNodes(root).flatMap((node) => wordsOfText(node.data))
}

/** Wrap the words at the given positions in `<mark>`; a gap between two marked words joins them. */
export function markWords(root: Node, indexes: ReadonlySet<number>, className: string): void {
  if (!indexes.size) return
  let position = 0
  for (const node of textNodes(root)) {
    const tokens = node.data.split(/(\s+)/).filter((token) => token !== '')
    const flags = tokens.map((token) => (/^\s+$/.test(token) ? null : indexes.has(position++)))
    if (!flags.some(Boolean)) continue
    // The nearest word flag on each side, so a gap between two marked words joins them.
    const previous: Array<boolean | null> = []
    let seenFlag: boolean | null = null
    flags.forEach((value, index) => { if (value !== null) seenFlag = value; previous[index] = seenFlag })
    const following: Array<boolean | null> = []
    seenFlag = null
    for (let index = flags.length - 1; index >= 0; index -= 1) {
      const value = flags[index]
      if (value !== null) seenFlag = value
      following[index] = seenFlag
    }
    const fragment = document.createDocumentFragment()
    let run = ''
    let marked = false
    const flush = (): void => {
      if (!run) return
      if (marked) {
        const mark = document.createElement('mark')
        mark.className = className
        mark.textContent = run
        fragment.append(mark)
      } else fragment.append(document.createTextNode(run))
      run = ''
    }
    tokens.forEach((token, index) => {
      let flag = flags[index]
      if (flag === null) {
        flag = Boolean(previous[index] && following[index])
      }
      if (flag !== marked) {
        flush()
        marked = flag
      }
      run += token
    })
    flush()
    node.replaceWith(fragment)
  }
}

/** What the reader sees above the body: title, subtitle, summary and card type. */
export interface ArtifactParts {
  header: string
  body: string
}

export function artifactParts(content: ArtifactContent | null): ArtifactParts | null {
  if (!content || (content.artifact_type !== 'card' && content.artifact_type !== 'article')) return null
  const lines = [`# ${content.title}`]
  if (content.artifact_type === 'article' && content.subtitle) lines.push(`*${content.subtitle}*`)
  if (content.artifact_type === 'card') lines.push(`Card type: **${content.card_type}**`)
  if (content.summary) lines.push(`> ${content.summary.replace(/\n+/g, ' ')}`)
  return { header: lines.join('\n\n'), body: content.content }
}

/**
 * The body after the user has rejected some hunks: a rejected removal puts the old block back, a
 * rejected addition drops the new one, and every other block stays as the draft has it.
 */
export function applyRejections(blocks: readonly MarkdownDiffBlock[], rejected: ReadonlySet<string>): string {
  const kept = blocks.filter((block) => block.kind === 'same'
    || (block.kind === 'removed' && rejected.has(block.key))
    || (block.kind === 'added' && !rejected.has(block.key)))
  // Each block keeps its own text and gap; a gap that cannot separate two blocks becomes a blank line.
  return kept.map((block, index) => {
    if (index === kept.length - 1) return block.text + block.gap
    return block.text + (block.gap.includes('\n') ? block.gap : '\n\n')
  }).join('')
}
