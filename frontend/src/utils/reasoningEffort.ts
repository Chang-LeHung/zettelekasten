import type { ReasoningEffort } from '../api/types'

/**
 * Every thinking level the runtime defines, weakest first. A provider maps the
 * levels it cannot express onto its closest supported value, so offering all of
 * them is safe: choosing one the model lacks never fails the turn.
 */
export const REASONING_EFFORTS: ReadonlyArray<{ value: ReasoningEffort; label: string; description: string }> = [
  { value: 'off', label: 'Off', description: 'Answer directly' },
  { value: 'minimal', label: 'Minimal', description: 'A moment of thought' },
  { value: 'low', label: 'Low', description: 'Light thinking' },
  { value: 'medium', label: 'Medium', description: 'Balanced depth' },
  { value: 'high', label: 'High', description: 'Deep analysis' },
  { value: 'xhigh', label: 'Extra high', description: 'Very deep analysis' },
  { value: 'max', label: 'Max', description: 'The most the model offers' },
  { value: 'ultra', label: 'Ultra', description: 'Longest, slowest, costliest' },
]

export function isReasoningEffort(value: unknown): value is ReasoningEffort {
  return REASONING_EFFORTS.some((option) => option.value === value)
}
