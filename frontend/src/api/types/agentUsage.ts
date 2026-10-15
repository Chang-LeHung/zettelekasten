export interface AgentUsageActivityDay {
  date: string
  requests: number
  input_tokens: number
  output_tokens: number
  cache_read_tokens: number
  cache_write_tokens: number
  reasoning_tokens: number
  total_tokens: number
}

export interface AgentModelUsageActivitySeries {
  provider: string | null
  model: string | null
  days: AgentUsageActivityDay[]
}

export interface AgentContextComposition {
  system_prompt: number
  tool_prompt: number
  tool_output: number
  user: number
  assistant: number
}
