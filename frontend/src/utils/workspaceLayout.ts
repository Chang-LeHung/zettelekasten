/** How the workspace divides its width between the conversation and the artifact. */

export type WorkspaceMode = 'split' | 'artifact' | 'chat'

export const MODES: readonly WorkspaceMode[] = ['chat', 'split', 'artifact']
export const MIN_CHAT_SHARE = 0.24
export const MAX_CHAT_SHARE = 0.76
export const DEFAULT_CHAT_SHARE = 0.4
/** One keyboard step on the divider. */
export const SHARE_STEP = 0.02

export function clampShare(value: number): number {
  if (!Number.isFinite(value)) return DEFAULT_CHAT_SHARE
  return Math.min(MAX_CHAT_SHARE, Math.max(MIN_CHAT_SHARE, value))
}

export function parseMode(value: string | null): WorkspaceMode {
  return MODES.find((mode) => mode === value) ?? 'split'
}

export function parseShare(value: string | null): number {
  if (value === null || value.trim() === '') return DEFAULT_CHAT_SHARE
  return clampShare(Number(value))
}

/** Share of the chat + artifact region that lies left of the pointer. */
export function shareFromPointer(pointerX: number, regionLeft: number, regionWidth: number): number {
  if (regionWidth <= 0) return DEFAULT_CHAT_SHARE
  return clampShare((pointerX - regionLeft) / regionWidth)
}

export function readStored(key: string, storage: Storage | null = defaultStorage()): string | null {
  try {
    return storage?.getItem(key) ?? null
  } catch {
    return null
  }
}

export function writeStored(key: string, value: string, storage: Storage | null = defaultStorage()): void {
  try {
    storage?.setItem(key, value)
  } catch {
    // A blocked localStorage must never break the layout itself.
  }
}

function defaultStorage(): Storage | null {
  if (typeof window === 'undefined') return null
  return window.localStorage ?? null
}
