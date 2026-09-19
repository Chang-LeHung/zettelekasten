/**
 * Follow-the-run expansion state for one conversation's turn details.
 *
 * The latest running turn expands by default so live thinking, tools, and task
 * details stay visible while the model works. Once the final assistant message
 * arrives, that default flips to collapsed so the answer becomes the primary
 * content. A manual toggle is recorded per turn and wins over both defaults so
 * a reader can keep inspecting a running or completed turn.
 */
export class TurnDetailsVisibility {
  private readonly overrides = new Map<string, boolean>()

  /** Return the effective open state for one turn. */
  isOpen(turnId: string, running: boolean): boolean {
    return this.overrides.get(turnId) ?? running
  }

  /** Record a reader's explicit choice for one turn. */
  setOpen(turnId: string, open: boolean): void {
    this.overrides.set(turnId, open)
  }

  /** Forget all overrides when switching or clearing a conversation. */
  clear(): void {
    this.overrides.clear()
  }
}
