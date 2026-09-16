/**
 * Follow-the-run expansion state for one conversation's turn details.
 *
 * Each turn keeps its thinking, tools, and task timeline behind a disclosure
 * summary. The panel follows the run by default: it stays open while the turn
 * is still streaming and collapses once the final assistant message arrives.
 * A reader who toggles the summary overrides that default for that turn, so
 * inspecting a finished turn is still possible.
 */
export class TurnDetailsVisibility {
  private readonly overrides = new Map<string, boolean>()

  /** Report whether one turn's execution details should be open. */
  isOpen(turnId: string, running: boolean): boolean {
    return this.overrides.get(turnId) ?? running
  }

  /** Record one reader toggle, which then wins over the streaming default. */
  setOpen(turnId: string, open: boolean): void {
    this.overrides.set(turnId, open)
  }

  /** Forget every override, for example after switching conversations. */
  clear(): void {
    this.overrides.clear()
  }
}
