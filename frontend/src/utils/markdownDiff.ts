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
  const left = splitBlocks(before).map((block) => block.text).filter((text) => norm(text) !== '')
  const right = splitBlocks(after).map((block) => block.text).filter((text) => norm(text) !== '')
  const { removed, added } = diffSequences(left.map(norm), right.map(norm))
  const blocks: MarkdownDiffBlock[] = []
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
      dropped.forEach((index, offset) => blocks.push({ key: `r${index}`, kind: 'removed', text: left[index], pair: offset < paired ? pairs + offset : null }))
      inserted.forEach((index, offset) => blocks.push({ key: `a${index}`, kind: 'added', text: right[index], pair: offset < paired ? pairs + offset : null }))
      pairs += paired
    } else if (j < right.length && added.has(j)) {
      blocks.push({ key: `a${j}`, kind: 'added', text: right[j], pair: null })
      j += 1
    } else {
      blocks.push({ key: `s${j}`, kind: 'same', text: right[j] ?? left[i], pair: null })
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
        const before = flags.slice(0, index).reverse().find((value) => value !== null)
        const after = flags.slice(index + 1).find((value) => value !== null)
        flag = Boolean(before && after)
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

/** What a card or article reads as when the whole artifact is rendered: title, summary, body. */
export function artifactMarkdown(content: ArtifactContent | null): string | null {
  if (!content || (content.artifact_type !== 'card' && content.artifact_type !== 'article')) return null
  const parts = [`# ${content.title}`]
  if (content.artifact_type === 'article' && content.subtitle) parts.push(`*${content.subtitle}*`)
  if (content.summary) parts.push(`> ${content.summary.replace(/\n+/g, ' ')}`)
  parts.push(content.content)
  return parts.join('\n\n')
}
