import { describe, expect, it } from 'vitest'
import { EDITOR_LAYOUT_KEY, readEditorLayout, writeEditorLayout } from './editorLayout'

function memoryStorage(): Storage {
  const values = new Map<string, string>()
  return {
    get length() { return values.size },
    clear: () => values.clear(),
    getItem: (key: string) => values.get(key) ?? null,
    key: (index: number) => [...values.keys()][index] ?? null,
    removeItem: (key: string) => void values.delete(key),
    setItem: (key: string, value: string) => void values.set(key, value),
  }
}

describe('editor layout', () => {
  it('opens in a single column until two columns are chosen', () => {
    const storage = memoryStorage()
    expect(readEditorLayout(storage)).toBe('single')

    writeEditorLayout('split', storage)
    expect(readEditorLayout(storage)).toBe('split')
    expect(storage.getItem(EDITOR_LAYOUT_KEY)).toBe('split')

    writeEditorLayout('single', storage)
    expect(readEditorLayout(storage)).toBe('single')
    expect(storage.length).toBe(0)
  })

  it('treats an unknown stored value as the default', () => {
    const storage = memoryStorage()
    storage.setItem(EDITOR_LAYOUT_KEY, 'wide')
    expect(readEditorLayout(storage)).toBe('single')
  })

  it('survives a storage that throws', () => {
    const broken = { getItem() { throw new Error('blocked') }, setItem() { throw new Error('blocked') }, removeItem() { throw new Error('blocked') } } as unknown as Storage
    expect(readEditorLayout(broken)).toBe('single')
    expect(() => writeEditorLayout('split', broken)).not.toThrow()
  })
})
