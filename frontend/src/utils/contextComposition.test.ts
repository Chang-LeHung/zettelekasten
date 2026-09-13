import { describe, expect, it } from 'vitest'

import { asContextComposition } from './contextComposition'

describe('context composition', () => {
  it('accepts a normalized backend ratio payload', () => {
    const payload = {
      system_prompt: 0.1,
      tool_prompt: 0.2,
      tool_output: 0.3,
      user: 0.15,
      assistant: 0.25,
    }
    expect(asContextComposition(payload)).toEqual(payload)
  })

  it('rejects missing, unbounded, and non-normalized values', () => {
    expect(asContextComposition({})).toBeNull()
    expect(asContextComposition({
      system_prompt: 2,
      tool_prompt: 0,
      tool_output: 0,
      user: 0,
      assistant: 0,
    })).toBeNull()
    expect(asContextComposition({
      system_prompt: 0.1,
      tool_prompt: 0.1,
      tool_output: 0.1,
      user: 0.1,
      assistant: 0.1,
    })).toBeNull()
  })
})
