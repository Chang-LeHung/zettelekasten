import { describe, expect, it } from 'vitest'

import { TurnDetailsVisibility } from './turnDetails'

describe('turn details visibility', () => {
  it('stays open while a turn streams and collapses when its final answer arrives', () => {
    const visibility = new TurnDetailsVisibility()

    expect(visibility.isOpen('turn-0', true)).toBe(true)
    expect(visibility.isOpen('turn-0', false)).toBe(false)
  })

  it('collapses the running turn as soon as it stops streaming', () => {
    const visibility = new TurnDetailsVisibility()

    expect(visibility.isOpen('turn-2', true)).toBe(true)
    expect(visibility.isOpen('turn-2', false)).toBe(false)
    expect(visibility.isOpen('turn-3', true)).toBe(true)
  })

  it('lets one reader toggle win over the streaming default', () => {
    const visibility = new TurnDetailsVisibility()

    visibility.setOpen('turn-0', true)
    expect(visibility.isOpen('turn-0', false)).toBe(true)

    visibility.setOpen('turn-1', false)
    expect(visibility.isOpen('turn-1', true)).toBe(false)
    expect(visibility.isOpen('turn-2', true)).toBe(true)
  })

  it('forgets overrides when the conversation changes', () => {
    const visibility = new TurnDetailsVisibility()
    visibility.setOpen('turn-0', true)

    visibility.clear()

    expect(visibility.isOpen('turn-0', false)).toBe(false)
    expect(visibility.isOpen('turn-0', true)).toBe(true)
  })
})
