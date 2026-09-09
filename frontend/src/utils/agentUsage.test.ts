import { describe, expect, it } from 'vitest'

import type { AnalysisMessage } from '../api/types'
import { addAgentUsage, formatTokenCount, summarizeAgentUsage } from './agentUsage'

const usage = (input: number, output: number, cached: number) => ({
  input_tokens: input,
  output_tokens: output,
  cache_read_tokens: cached,
  cache_write_tokens: 0,
  reasoning_tokens: 0,
})

describe('agent usage', () => {
  it('adds every model call, including assistant tool-call steps', () => {
    const messages: AnalysisMessage[] = [
      { role: 'assistant', content: '', usage: usage(100, 20, 50), generation_duration_ms: 500 },
      { role: 'assistant', content: '', usage: usage(180, 30, 90), generation_duration_ms: 1_000 },
      { role: 'assistant', content: 'Done', usage: usage(250, 50, 200), generation_duration_ms: 1_500 },
    ]

    expect(summarizeAgentUsage(messages)).toEqual({
      input_tokens: 530,
      output_tokens: 100,
      cache_read_tokens: 340,
      cache_write_tokens: 0,
      reasoning_tokens: 0,
      total_tokens: 630,
      cache_hit_rate: 340 / 530,
      tokens_per_second: 100 / 3,
    })
  })

  it('excludes untimed output only from the speed denominator calculation', () => {
    const messages: AnalysisMessage[] = [
      { role: 'assistant', content: 'Old', usage: usage(10, 100, 0) },
      { role: 'assistant', content: 'New', usage: usage(10, 20, 0), generation_duration_ms: 2_000 },
    ]
    const result = summarizeAgentUsage(messages)
    expect(result?.output_tokens).toBe(120)
    expect(result?.tokens_per_second).toBe(10)
  })

  it('returns no summary without provider usage', () => {
    expect(summarizeAgentUsage([{ role: 'assistant', content: 'No counters' }])).toBeNull()
  })

  it('formats token counts for compact composer metrics', () => {
    expect([formatTokenCount(999), formatTokenCount(1_250), formatTokenCount(25_000), formatTokenCount(2_500_000)])
      .toEqual(['999', '1.3K', '25K', '2.5M'])
  })

  it('adds usage from consecutive streamed model completions', () => {
    expect(addAgentUsage(usage(10, 2, 5), usage(20, 3, 10))).toEqual(usage(30, 5, 15))
  })
})
