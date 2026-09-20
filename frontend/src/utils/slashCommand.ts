export interface SlashCommandMatch {
  start: number
  end: number
  query: string
}

export interface SlashCommandInsertion {
  value: string
  caret: number
}

export interface SlashCommandDeletion {
  value: string
  caret: number
}

export interface SlashCommandToken {
  name: string
  start: number
  end: number
}

export class SlashCommandInput {
  static readonly trigger = '/'

  static match(value: string, caret: number): SlashCommandMatch | null {
    const end = Math.max(0, Math.min(caret, value.length))
    let start = end - 1
    while (start >= 0 && !/\s/.test(value[start])) start -= 1
    start += 1
    if (value[start] !== SlashCommandInput.trigger) return null
    if (start > 0 && !/\s/.test(value[start - 1])) return null
    const query = value.slice(start + 1, end)
    if (/\s/.test(query)) return null
    return { start, end, query }
  }

  static insert(value: string, match: SlashCommandMatch, name: string): SlashCommandInsertion {
    const token = `/${name}`
    const rest = value.slice(match.end)
    const needsSeparator = !/^\s/.test(rest)
    const insertion = needsSeparator ? `${token} ` : token
    // Keep the caret after the separator so the next keystroke starts the
    // request instead of gluing itself to the command name.
    const advance = needsSeparator ? insertion.length : token.length + (rest.match(/^\s+/)?.[0].length ?? 0)
    return {
      value: `${value.slice(0, match.start)}${insertion}${value.slice(match.end)}`,
      caret: match.start + advance,
    }
  }

  static contains(value: string, name: string): boolean {
    return SlashCommandInput.range(value, name) !== null
  }

  /**
   * Locate every `/name` token that starts a word. Unlike `range`, a token does
   * not need whitespace after it, so a command stays highlighted while the rest
   * of the sentence is typed right behind it.
   */
  static tokens(value: string): SlashCommandToken[] {
    return [...value.matchAll(/(?:^|\s)\/([a-z0-9]+(?:-[a-z0-9]+)*)/gi)].map((match) => {
      const name = match[1]
      const start = (match.index ?? 0) + match[0].length - name.length - 1
      return { name, start, end: start + name.length + 1 }
    })
  }

  static tokenNames(value: string): string[] {
    return SlashCommandInput.tokens(value).map(token => token.name)
  }

  static range(value: string, name: string): { start: number; end: number } | null {
    const escaped = name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
    const match = new RegExp(`(?:^|\\s)(/${escaped})(?=\\s|$)`).exec(value)
    if (!match || match.index === undefined) return null
    const start = match.index + match[0].length - match[1].length
    return { start, end: start + match[1].length }
  }

  static deleteAtomically(
    value: string,
    name: string,
    selectionStart: number,
    selectionEnd: number,
    key: 'Backspace' | 'Delete',
  ): SlashCommandDeletion | null {
    const range = SlashCommandInput.range(value, name)
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
}
