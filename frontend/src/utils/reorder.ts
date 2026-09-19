/** Move one item relative to another item while preserving all identities. */
export function moveItemBeforeOrAfter<T>(
  items: readonly T[],
  sourceId: string | number,
  targetId: string | number,
  placeAfter: boolean,
  getId: (item: T) => string | number,
): T[] {
  if (sourceId === targetId) return [...items]
  const sourceIndex = items.findIndex((item) => getId(item) === sourceId)
  if (sourceIndex < 0) return [...items]

  const next = [...items]
  const [moved] = next.splice(sourceIndex, 1)
  if (moved === undefined) return [...items]
  const targetIndex = next.findIndex((item) => getId(item) === targetId)
  if (targetIndex < 0) return [...items]
  next.splice(placeAfter ? targetIndex + 1 : targetIndex, 0, moved)
  return next
}
