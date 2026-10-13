/**
 * The arithmetic behind selecting several cards with the mouse.
 *
 * Kept free of the DOM and of Vue so each rule is a plain function a test can
 * pin: what a drag rectangle covers, what Shift-click spans, and how a batch of
 * requests runs without opening a connection per card.
 */

export interface Box {
  left: number
  top: number
  right: number
  bottom: number
}

/** A pointer drag shorter than this is a click, so a stray tremor never starts a marquee. */
export const MARQUEE_THRESHOLD = 4

export function boxFromPoints(ax: number, ay: number, bx: number, by: number): Box {
  return { left: Math.min(ax, bx), top: Math.min(ay, by), right: Math.max(ax, bx), bottom: Math.max(ay, by) }
}

export function exceedsThreshold(dx: number, dy: number, threshold = MARQUEE_THRESHOLD): boolean {
  return Math.hypot(dx, dy) >= threshold
}

/** Touching edges do not count: the rectangle has to actually cover some of the card. */
export function boxesIntersect(a: Box, b: Box): boolean {
  return a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top
}

export function idsInBox(box: Box, targets: ReadonlyArray<{ id: string; box: Box }>): string[] {
  return targets.filter((target) => boxesIntersect(box, target.box)).map((target) => target.id)
}

/**
 * Every id from the anchor to the target, in list order and inclusive. Without an
 * anchor, or when the anchor has left the list, only the target is selected.
 */
export function rangeBetween(order: readonly string[], anchor: string | null, target: string): string[] {
  const to = order.indexOf(target)
  if (to < 0) return []
  const from = anchor === null ? -1 : order.indexOf(anchor)
  if (from < 0) return [target]
  return order.slice(Math.min(from, to), Math.max(from, to) + 1)
}

export function toggled(selection: ReadonlySet<string>, id: string): Set<string> {
  const next = new Set(selection)
  if (!next.delete(id)) next.add(id)
  return next
}

/** Keep only ids still in the list: a card deleted or filtered away cannot stay selected. */
export function pruned(selection: ReadonlySet<string>, order: readonly string[]): Set<string> {
  const present = new Set(order)
  return new Set([...selection].filter((id) => present.has(id)))
}

/**
 * Run `worker` over every item with at most `limit` in flight, never rejecting:
 * each outcome is reported, so one failure cannot hide the others' results.
 */
export async function settleLimited<T, R>(
  items: readonly T[],
  limit: number,
  worker: (item: T) => Promise<R>,
): Promise<Array<PromiseSettledResult<R>>> {
  const results = new Array<PromiseSettledResult<R>>(items.length)
  let next = 0
  async function lane(): Promise<void> {
    while (next < items.length) {
      const index = next++
      try {
        results[index] = { status: 'fulfilled', value: await worker(items[index]) }
      } catch (reason) {
        results[index] = { status: 'rejected', reason }
      }
    }
  }
  await Promise.all(Array.from({ length: Math.min(Math.max(limit, 1), items.length) }, lane))
  return results
}
