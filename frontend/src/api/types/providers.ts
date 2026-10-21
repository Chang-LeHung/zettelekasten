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
  /** The model reads images; when false the file tool returns text only. */
  multimodal: boolean
  /** Let the model endpoint run its own web search. */
  web_search: boolean
  /** Provider-side search tool type; null selects the protocol's default. */
  web_search_name: string | null
  enabled: boolean
}

export interface AIProvider extends Omit<AIProviderInput, 'api_key' | 'base_url'> {
  id: string
  base_url: string | null
  api_key_configured: boolean
  /** Tool type the protocol uses when the saved name is blank. */
  web_search_default_name: string | null
  /** What this protocol's search answer holds, from the backend. */
  web_search_hint: string
  created_at: string
  updated_at: string
}

export interface AIProviderDetail extends AIProvider {
  api_key: string | null
}
