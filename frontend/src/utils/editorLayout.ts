/**
 * How the Markdown editor lays itself out: the source and a live preview side by
 * side (the default), or one column of blocks. The choice is remembered, so an
 * author who prefers one column is not asked again every time an editor opens.
 */

export type EditorLayout = 'single' | 'split'

export const EDITOR_LAYOUT_KEY = 'zett.editor-layout'

function defaultStorage(): Storage | null {
  if (typeof window === 'undefined') return null
  return window.localStorage ?? null
}

/** Only the non-default value is stored, so an unreadable value means "split". */
export function readEditorLayout(storage: Storage | null = defaultStorage()): EditorLayout {
  try {
    return storage?.getItem(EDITOR_LAYOUT_KEY) === 'single' ? 'single' : 'split'
  } catch {
    return 'split'
  }
}

export function writeEditorLayout(layout: EditorLayout, storage: Storage | null = defaultStorage()): void {
  try {
    if (layout === 'single') storage?.setItem(EDITOR_LAYOUT_KEY, 'single')
    else storage?.removeItem(EDITOR_LAYOUT_KEY)
  } catch {
    // A blocked localStorage must never stop the editor from switching layout.
  }
}
