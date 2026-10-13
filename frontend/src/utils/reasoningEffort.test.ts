import { expect, it } from 'vitest'
import { isReasoningEffort, REASONING_EFFORTS } from './reasoningEffort'

it('lists every level once, from off to ultra, and recognises only those', () => {
  const values = REASONING_EFFORTS.map((option) => option.value)
  expect(new Set(values).size).toBe(values.length)
  expect(values[0]).toBe('off')
  expect(values.at(-1)).toBe('ultra')
  expect(isReasoningEffort('xhigh')).toBe(true)
  expect(isReasoningEffort('extreme')).toBe(false)
  expect(isReasoningEffort(undefined)).toBe(false)
})
