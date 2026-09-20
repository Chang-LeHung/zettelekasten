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

export type SlashCommandMatch = CommandTokenMatch
export type SlashCommandInsertion = CommandTokenInsertion
export type SlashCommandDeletion = CommandTokenDeletion
export type SlashCommandToken = CommandTokenSpan

/**
 * One `/command` token inside the composer.
 *
 * A slash command opens a turn, so it must start the input or follow
 * whitespace. `AtCommandInput` shares the same grammar with an `@` trigger.
 */
export class SlashCommandInput {
  static readonly trigger = '/'

  static match(value: string, caret: number): SlashCommandMatch | null {
    return matchCommandToken(value, caret, SlashCommandInput.trigger, 'whitespace')
  }

  static insert(value: string, match: SlashCommandMatch, name: string): SlashCommandInsertion {
    return insertCommandToken(value, match, name, SlashCommandInput.trigger)
  }

  static contains(value: string, name: string): boolean {
    return containsCommandToken(value, name, SlashCommandInput.trigger)
  }

  /**
   * Locate every `/name` token that starts a word. Unlike `range`, a token does
   * not need whitespace after it, so a command stays highlighted while the rest
   * of the sentence is typed right behind it.
   */
  static tokens(value: string): SlashCommandToken[] {
    return commandTokenSpans(value, SlashCommandInput.trigger, 'whitespace')
  }

  static tokenNames(value: string): string[] {
    return SlashCommandInput.tokens(value).map(token => token.name)
  }

  static range(value: string, name: string): { start: number; end: number } | null {
    return commandTokenRange(value, name, SlashCommandInput.trigger)
  }

  static deleteAtomically(
    value: string,
    name: string,
    selectionStart: number,
    selectionEnd: number,
    key: 'Backspace' | 'Delete',
  ): SlashCommandDeletion | null {
    return deleteCommandToken(value, name, selectionStart, selectionEnd, key, SlashCommandInput.trigger)
  }
}
