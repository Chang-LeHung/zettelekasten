import { describe, expect, it } from 'vitest'
import { isEditorSaveShortcut } from './editorShortcuts'

describe('editor shortcuts', () => {
  it('recognizes Command+S by physical key code', () => {
    expect(isEditorSaveShortcut({ metaKey: true, code: 'KeyS' })).toBe(true)
  })

  it('ignores S without Command and unrelated Command shortcuts', () => {
    expect(isEditorSaveShortcut({ metaKey: false, code: 'KeyS' })).toBe(false)
    expect(isEditorSaveShortcut({ metaKey: true, code: 'KeyA' })).toBe(false)
  })
})
