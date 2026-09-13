import type { AgentModelUsage, AnalysisMessage } from '../api/types'

export interface AgentUsageSummary extends AgentModelUsage {
  total_tokens: number
  cache_hit_rate: number | null
  tokens_per_second: number | null
}

const EMPTY_USAGE: AgentModelUsage = {
  input_tokens: 0,
  output_tokens: 0,
  cache_read_tokens: 0,
  cache_write_tokens: 0,
  reasoning_tokens: 0,
}

/** Add provider counters without double-counting cache or reasoning subsets. */
export function addAgentUsage(
  current: AgentModelUsage | null,
  next: AgentModelUsage,
): AgentModelUsage {
  const left = current || EMPTY_USAGE
  return {
    input_tokens: left.input_tokens + next.input_tokens,
    output_tokens: left.output_tokens + next.output_tokens,
    cache_read_tokens: left.cache_read_tokens + next.cache_read_tokens,
    cache_write_tokens: left.cache_write_tokens + next.cache_write_tokens,
    reasoning_tokens: left.reasoning_tokens + next.reasoning_tokens,
  }
}

/** Aggregate every Assistant model step selected by the caller. */
export function summarizeAgentUsage(messages: readonly AnalysisMessage[]): AgentUsageSummary | null {
  let usage: AgentModelUsage | null = null
  let timedOutputTokens = 0
  let generationDurationMs = 0
  for (const message of messages) {
    if (!message.usage) continue
    usage = addAgentUsage(usage, message.usage)
    if ((message.generation_duration_ms || 0) > 0) {
      timedOutputTokens += message.usage.output_tokens
      generationDurationMs += message.generation_duration_ms || 0
    }
  }
  if (!usage) return null

  return {
    ...usage,
    total_tokens: usage.input_tokens + usage.output_tokens,
    cache_hit_rate: usage.input_tokens ? usage.cache_read_tokens / usage.input_tokens : null,
    tokens_per_second: generationDurationMs ? timedOutputTokens / (generationDurationMs / 1000) : null,
  }
}

/** Return the provider counters for the latest completed model step. */
export function latestAgentUsage(messages: readonly AnalysisMessage[]): AgentModelUsage | null {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const usage = messages[index]?.usage
    if (usage) return usage
  }
  return null
}

/** Render large token counters compactly without hiding their magnitude. */
export function formatTokenCount(value: number): string {
  if (value < 1_000) return String(value)
  if (value < 1_000_000) return `${(value / 1_000).toFixed(value < 10_000 ? 1 : 0)}K`
  return `${(value / 1_000_000).toFixed(value < 10_000_000 ? 1 : 0)}M`
}
