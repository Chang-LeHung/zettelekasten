import {
  commandTokenRange,
  commandTokenSpans,
  containsCommandToken,
  deleteCommandToken,
  insertCommandToken,
  matchCommandToken,
  type CommandTokenDeletion,
  type CommandTokenInsertion,
  type CommandTokenMatch,
  type CommandTokenSpan,
} from './commandToken'

export type AtCommandMatch = CommandTokenMatch
export type AtCommandInsertion = CommandTokenInsertion
export type AtCommandDeletion = CommandTokenDeletion
export type AtCommandToken = CommandTokenSpan

/**
 * One `@reference` token inside the composer.
 *
 * Unlike a slash command, a reference belongs to the sentence the user is
 * writing, so it may follow any character that is not part of a word, which
 * keeps Chinese prose like `总结一下@report` working.
 */
export class AtCommandInput {
  static readonly trigger = '@'

  static match(value: string, caret: number): AtCommandMatch | null {
    return matchCommandToken(value, caret, AtCommandInput.trigger, 'non-word')
  }

  static insert(value: string, match: AtCommandMatch, name: string): AtCommandInsertion {
    return insertCommandToken(value, match, name, AtCommandInput.trigger)
  }

  static contains(value: string, name: string): boolean {
    return containsCommandToken(value, name, AtCommandInput.trigger)
  }

  static tokens(value: string): AtCommandToken[] {
    return commandTokenSpans(value, AtCommandInput.trigger, 'non-word')
  }

  static tokenNames(value: string): string[] {
    return AtCommandInput.tokens(value).map(token => token.name)
  }

  static range(value: string, name: string): { start: number; end: number } | null {
    return commandTokenRange(value, name, AtCommandInput.trigger)
  }

  static deleteAtomically(
    value: string,
    name: string,
    selectionStart: number,
    selectionEnd: number,
    key: 'Backspace' | 'Delete',
  ): AtCommandDeletion | null {
    return deleteCommandToken(value, name, selectionStart, selectionEnd, key, AtCommandInput.trigger)
  }
}
