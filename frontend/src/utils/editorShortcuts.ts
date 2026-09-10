export interface EditorShortcutEvent {
  metaKey: boolean
  code: string
}

/** Match the physical S key used by the macOS Command+S save shortcut. */
export function isEditorSaveShortcut(event: EditorShortcutEvent): boolean {
  return event.metaKey && event.code === 'KeyS'
}
