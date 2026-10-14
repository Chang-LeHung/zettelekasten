export type AIProviderKind =
  | 'openai_compatible'
  | 'responses_compatible'
  | 'openai'
  | 'deepseek'
  | 'anthropic'
  | 'anthropic_compatible'
  | 'google'
  | 'ollama'

export interface AIProviderInput {
  name: string
  provider: AIProviderKind
  model: string
  base_url: string
  api_key: string
  temperature: number
  response: boolean
  enabled: boolean
}

export interface AIProvider extends Omit<AIProviderInput, 'api_key' | 'base_url'> {
  id: string
  base_url: string | null
  api_key_configured: boolean
  created_at: string
  updated_at: string
}

export interface AIProviderDetail extends AIProvider {
  api_key: string | null
}
