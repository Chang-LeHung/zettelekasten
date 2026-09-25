/** Remember whether a workspace column is hidden so the layout survives a reload. */

const HIDDEN_VALUE = 'hidden'

function defaultStorage(): Storage | null {
  if (typeof window === 'undefined') return null
  return window.localStorage ?? null
}

export function readPaneHidden(storageKey: string, storage: Storage | null = defaultStorage()): boolean {
  try {
    return storage?.getItem(storageKey) === HIDDEN_VALUE
  } catch {
    return false
  }
}

export function writePaneHidden(
  storageKey: string,
  hidden: boolean,
  storage: Storage | null = defaultStorage(),
): void {
  try {
    if (hidden) storage?.setItem(storageKey, HIDDEN_VALUE)
    else storage?.removeItem(storageKey)
  } catch {
    // A blocked localStorage must never break the layout toggle itself.
  }
}
