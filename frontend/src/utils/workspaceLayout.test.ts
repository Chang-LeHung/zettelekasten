import { describe, expect, it } from 'vitest'
import { DEFAULT_CHAT_SHARE, MAX_CHAT_SHARE, MIN_CHAT_SHARE, clampShare, parseMode, parseShare, shareFromPointer } from './workspaceLayout'

describe('workspace layout', () => {
  it('falls back to split for an unknown stored mode', () => {
    expect(parseMode(null)).toBe('split')
    expect(parseMode('weird')).toBe('split')
    expect(parseMode('artifact')).toBe('artifact')
  })

  it('keeps the share inside the usable range', () => {
    expect(clampShare(0)).toBe(MIN_CHAT_SHARE)
    expect(clampShare(1)).toBe(MAX_CHAT_SHARE)
    expect(clampShare(Number.NaN)).toBe(DEFAULT_CHAT_SHARE)
    expect(parseShare('')).toBe(DEFAULT_CHAT_SHARE)
    expect(parseShare('0.5')).toBe(0.5)
  })

  it('maps the pointer to a share of the region', () => {
    expect(shareFromPointer(500, 100, 800)).toBe(0.5)
    expect(shareFromPointer(0, 100, 800)).toBe(MIN_CHAT_SHARE)
    expect(shareFromPointer(10, 0, 0)).toBe(DEFAULT_CHAT_SHARE)
  })
})
