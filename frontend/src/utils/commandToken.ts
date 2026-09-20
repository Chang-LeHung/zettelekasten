/**
 * Shared grammar for composer tokens such as `/command` and `@reference`.
 *
 * Both triggers accept the same token names but differ in where a token may
 * start. A slash command opens a turn, so it must follow whitespace; an `@`
 * reference sits inside ordinary prose, including Chinese text that has no
 * whitespace, so it only needs to avoid being glued to a word or an email
 * address.
 */

export type CommandTokenBoundary = 'whitespace' | 'non-word'

export interface CommandTokenMatch {
  start: number
  end: number
  query: string
}

export interface CommandTokenInsertion {
  value: string
  caret: number
}

export interface CommandTokenDeletion {
  value: string
  caret: number
}

export interface CommandTokenSpan {
  name: string
  start: number
  end: number
}

const TOKEN_NAME = '[a-z0-9]+(?:-[a-z0-9]+)*'
const NAME_CHARACTER = /[A-Za-z0-9-]/

function escapePattern(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

function precedingBoundary(trigger: string, boundary: CommandTokenBoundary): string {
  return boundary === 'whitespace'
    ? '(?:^|\\s)'
    : `(?:^|[^A-Za-z0-9_${escapePattern(trigger)}/-])`
}

function tokenPattern(trigger: string, boundary: CommandTokenBoundary): RegExp {
  return new RegExp(`${precedingBoundary(trigger, boundary)}(${escapePattern(trigger)}${TOKEN_NAME})`, 'gi')
}

function namePattern(trigger: string, name: string): RegExp {
  return new RegExp(`(?:^|\\s)(${escapePattern(trigger)}${escapePattern(name)})(?=\\s|$)`)
}

function allowsStart(value: string, index: number, trigger: string, boundary: CommandTokenBoundary): boolean {
  if (index < 0) return true
  if (boundary === 'whitespace') return /\s/.test(value[index])
  return !/[A-Za-z0-9_]/.test(value[index]) && value[index] !== trigger && value[index] !== '/'
}

export function matchCommandToken(
  value: string,
  caret: number,
  trigger: string,
  boundary: CommandTokenBoundary,
): CommandTokenMatch | null {
  const end = Math.max(0, Math.min(caret, value.length))
  let nameStart = end
  while (nameStart > 0 && NAME_CHARACTER.test(value[nameStart - 1])) nameStart -= 1
  const start = nameStart - 1
  if (start < 0 || value[start] !== trigger) return null
  if (!allowsStart(value, start - 1, trigger, boundary)) return null
  const query = value.slice(nameStart, end)
  if (/\s/.test(query)) return null
  return { start, end, query }
}

export function insertCommandToken(
  value: string,
  match: CommandTokenMatch,
  name: string,
  trigger: string,
): CommandTokenInsertion {
  const token = `${trigger}${name}`
  const rest = value.slice(match.end)
  const needsSeparator = !/^\s/.test(rest)
  const insertion = needsSeparator ? `${token} ` : token
  // Keep the caret after the separator so the next keystroke starts the
  // request instead of gluing itself to the token name.
  const advance = needsSeparator ? insertion.length : token.length + (rest.match(/^\s+/)?.[0].length ?? 0)
  return {
    value: `${value.slice(0, match.start)}${insertion}${value.slice(match.end)}`,
    caret: match.start + advance,
  }
}

export function commandTokenSpans(
  value: string,
  trigger: string,
  boundary: CommandTokenBoundary,
): CommandTokenSpan[] {
  return [...value.matchAll(tokenPattern(trigger, boundary))].map((match) => {
    const token = match[1]
    const start = (match.index ?? 0) + match[0].length - token.length
    return { name: token.slice(trigger.length), start, end: start + token.length }
  })
}

export function commandTokenRange(
  value: string,
  name: string,
  trigger: string,
): { start: number; end: number } | null {
  const match = namePattern(trigger, name).exec(value)
  if (!match || match.index === undefined) return null
  const start = match.index + match[0].length - match[1].length
  return { start, end: start + match[1].length }
}

export function containsCommandToken(value: string, name: string, trigger: string): boolean {
  return commandTokenRange(value, name, trigger) !== null
}

export function deleteCommandToken(
  value: string,
  name: string,
  selectionStart: number,
  selectionEnd: number,
  key: 'Backspace' | 'Delete',
  trigger: string,
): CommandTokenDeletion | null {
  const range = commandTokenRange(value, name, trigger)
  if (!range) return null
  const selectedRangeIntersects = selectionStart !== selectionEnd
    && selectionStart <= range.end
    && selectionEnd >= range.start
  const caretInside = selectionStart === selectionEnd
    && selectionStart >= range.start
    && selectionStart <= range.end + 1
  const backwardBoundary = key === 'Backspace'
    && caretInside
  const forwardBoundary = key === 'Delete'
    && selectionStart >= range.start - 1
    && selectionStart <= range.end
  if (!selectedRangeIntersects && !backwardBoundary && !forwardBoundary) return null

  let end = range.end
  while (end < value.length && /\s/.test(value[end])) end += 1
  return {
    value: `${value.slice(0, range.start)}${value.slice(end)}`,
    caret: range.start,
  }
}
