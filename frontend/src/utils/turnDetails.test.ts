import { describe, expect, it } from 'vitest'

import { TurnDetailsVisibility } from './turnDetails'

describe('turn details visibility', () => {
  it('opens the running turn and collapses it when the final response arrives', () => {
    const visibility = new TurnDetailsVisibility()

    expect(visibility.isOpen('turn-0', true)).toBe(true)
    expect(visibility.isOpen('turn-0', false)).toBe(false)
  })

  it('applies the same default independently to every turn', () => {
    const visibility = new TurnDetailsVisibility()

    expect(visibility.isOpen('turn-2', true)).toBe(true)
    expect(visibility.isOpen('turn-2', false)).toBe(false)
    expect(visibility.isOpen('turn-3', true)).toBe(true)
  })

  it('lets an explicit reader toggle override the streaming default', () => {
    const visibility = new TurnDetailsVisibility()

    visibility.setOpen('turn-0', true)
    expect(visibility.isOpen('turn-0', false)).toBe(true)

    visibility.setOpen('turn-1', false)
    expect(visibility.isOpen('turn-1', true)).toBe(false)
    expect(visibility.isOpen('turn-2', true)).toBe(true)
  })

  it('clears all overrides when the conversation changes', () => {
    const visibility = new TurnDetailsVisibility()
    visibility.setOpen('turn-0', true)

    visibility.clear()

    expect(visibility.isOpen('turn-0', false)).toBe(false)
    expect(visibility.isOpen('turn-0', true)).toBe(true)
  })
})
