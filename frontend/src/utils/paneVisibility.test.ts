import { describe, expect, it, vi } from 'vitest'

import { readPaneHidden, writePaneHidden } from './paneVisibility'

function memoryStorage(): Storage {
  const values = new Map<string, string>()
  return {
    get length() {
      return values.size
    },
    clear: () => values.clear(),
    getItem: (key: string) => values.get(key) ?? null,
    key: (index: number) => [...values.keys()][index] ?? null,
    removeItem: (key: string) => void values.delete(key),
    setItem: (key: string, value: string) => void values.set(key, value),
  }
}

describe('pane visibility', () => {
  it('reads a missing flag as visible and remembers a hidden column', () => {
    const storage = memoryStorage()

    expect(readPaneHidden('zett.assets-pane', storage)).toBe(false)

    writePaneHidden('zett.assets-pane', true, storage)
    expect(readPaneHidden('zett.assets-pane', storage)).toBe(true)
    expect(storage.length).toBe(1)

    writePaneHidden('zett.assets-pane', false, storage)
    expect(readPaneHidden('zett.assets-pane', storage)).toBe(false)
    expect(storage.length).toBe(0)
  })

  it('treats an unavailable or blocked storage as visible', () => {
    const blocked = memoryStorage()
    blocked.setItem = vi.fn(() => {
      throw new Error('blocked')
    })
    blocked.getItem = vi.fn(() => {
      throw new Error('blocked')
    })

    expect(readPaneHidden('zett.assets-pane', null)).toBe(false)
    expect(readPaneHidden('zett.assets-pane', blocked)).toBe(false)
    expect(() => writePaneHidden('zett.assets-pane', true, blocked)).not.toThrow()
  })
})
