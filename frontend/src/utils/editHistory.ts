/**
 * Undo and redo for the block editor.
 *
 * A textarea keeps its own undo stack, but splitting, merging, and moving blocks
 * swap the textarea out, so the browser's stack would undo the wrong thing or
 * nothing. The editor therefore records whole-document snapshots itself. Typing
 * in one block is coalesced into a single step, so Undo takes back a sentence
 * rather than a letter, while any structural change is a step of its own.
 */

export interface EditSnapshot {
  /** The whole document. */
  text: string
  /** Index of the block that had the caret, and the caret inside it. */
  block: number
  caret: number
}

/** How long a pause ends one run of typing. */
export const TYPING_WINDOW_MS = 900

export class EditHistory {
  private past: EditSnapshot[] = []
  private future: EditSnapshot[] = []
  private present: EditSnapshot
  private lastTypingAt = 0
  private typingBlock = -1

  constructor(
    initial: EditSnapshot,
    private readonly limit = 200,
    private readonly now: () => number = () => Date.now(),
  ) {
    this.present = initial
  }

  get canUndo(): boolean {
    return this.past.length > 0
  }

  get canRedo(): boolean {
    return this.future.length > 0
  }

  /**
   * Record a new state. `typing` edits in the same block within the window
   * replace the last step instead of adding one.
   */
  record(next: EditSnapshot, typing: boolean): void {
    if (next.text === this.present.text) {
      this.present = next
      return
    }
    const time = this.now()
    const merges = typing
      && this.past.length > 0
      && this.typingBlock === next.block
      && time - this.lastTypingAt <= TYPING_WINDOW_MS
    if (!merges) {
      this.past.push(this.present)
      if (this.past.length > this.limit) this.past.shift()
    }
    this.present = next
    this.future = []
    this.lastTypingAt = time
    this.typingBlock = typing ? next.block : -1
  }

  /** Update where the caret is without making a step, so Undo returns to it. */
  moveCaret(block: number, caret: number): void {
    this.present = { ...this.present, block, caret }
    // Moving away ends a run of typing: the next keystroke is a new step.
    this.typingBlock = -1
  }

  undo(): EditSnapshot | null {
    const previous = this.past.pop()
    if (!previous) return null
    this.future.push(this.present)
    this.present = previous
    this.typingBlock = -1
    return previous
  }

  redo(): EditSnapshot | null {
    const next = this.future.pop()
    if (!next) return null
    this.past.push(this.present)
    this.present = next
    this.typingBlock = -1
    return next
  }

  /** Forget every step, for a document that was replaced from outside. */
  reset(initial: EditSnapshot): void {
    this.past = []
    this.future = []
    this.present = initial
    this.typingBlock = -1
  }
}
