const providerBaseUrls: Readonly<Record<string, string>> = {
  anthropic: 'https://api.anthropic.com',
  anthropic_compatible: '',
  deepseek: 'https://api.deepseek.com/v1',
  google: 'https://generativelanguage.googleapis.com',
  ollama: 'http://localhost:11434',
  openai: 'https://api.openai.com/v1',
  openai_compatible: '',
  responses_compatible: '',
}

/** Return the conventional API endpoint for a provider, or an empty value when it cannot be inferred. */
export function defaultProviderBaseUrl(provider: string, response = false): string {
  if (provider === 'deepseek' && response) return 'https://api.deepseek.com'
  return providerBaseUrls[provider] ?? ''
}

/** Providers whose adapter takes no temperature, so a slider for it would do nothing. */
export function providerIgnoresTemperature(provider: string): boolean {
  return ['anthropic', 'anthropic_compatible', 'google', 'ollama'].includes(provider)
}

const anthropicProtocols = ['anthropic', 'anthropic_compatible']
const openaiStyle = ['openai', 'openai_compatible', 'responses_compatible', 'deepseek']
const isDeepSeekModel = (model: string): boolean => model.toLowerCase().includes('deepseek')

/**
 * Return the search tool type a provider uses when none is named, or '' when the protocol has none.
 * Mirrors `default_web_search_name` in the backend, which is what decides at request time.
 */
export function defaultWebSearchName(provider: string, model: string, response = false): string {
  if (anthropicProtocols.includes(provider)) return isDeepSeekModel(model) ? 'web_search_20250305' : 'web_search_20260318'
  if (provider === 'google') return 'google_search'
  if (openaiStyle.includes(provider)) return 'web_search'
  return ''
}

/**
 * Describe what this protocol's search answer holds, so the form names the tool a user will actually get.
 * Mirrors `web_search_hint` in the backend; the response's own hint wins when it is available.
 */
export function webSearchHint(provider: string, model: string, response = false): string {
  const name = defaultWebSearchName(provider, model, response)
  if (!name) return 'This endpoint has no search tool Zett knows; type the search tool name your service documents.'
  if (anthropicProtocols.includes(provider)) {
    if (isDeepSeekModel(model)) return 'DeepSeek flash models search through the Anthropic API with web_search_20250305. Results come back as page titles and links.'
    return 'Anthropic searches with web_search_20260318 and returns page titles and links. Page text stays on the provider, so a snippet may be missing.'
  }
  if (provider === 'google') return 'Gemini grounds with google_search and returns the queries it ran plus the pages it cited.'
  if (provider === 'responses_compatible' || response) {
    return 'The Responses API searches with web_search and returns the queries it ran plus the cited pages.'
  }
  return 'Chat Completions searches with web_search when the service supports a hosted search tool.'
}

/** Explain why web search cannot be switched on for a configuration, or return '' when it can. */
export function webSearchUnavailableReason(provider: string, model: string, response = false, name = ''): string {
  if (provider === 'ollama') return 'Ollama has no hosted web search.'
  if (isDeepSeekModel(model)) {
    if (!anthropicProtocols.includes(provider)) return 'DeepSeek models search the web only through the Anthropic API.'
    if (!model.toLowerCase().includes('flash')) return 'Only DeepSeek flash models support web search on the Anthropic API.'
  }
  if (!name.trim() && !defaultWebSearchName(provider, model, response)) {
    return 'This endpoint has no search tool Zett knows; type the search tool name your service documents.'
  }
  return ''
}

/** Explain whether the selected endpoint is inferred or must be supplied by the user. */
export function providerBaseUrlHelp(provider: string): string {
  if (provider === 'openai_compatible') {
    return 'Enter the Chat Completions endpoint exposed by your compatible service.'
  }
  if (provider === 'responses_compatible') {
    return 'Enter the Responses API root exposed by your compatible service.'
  }
  if (provider === 'anthropic_compatible') {
    return 'Enter the API root of your Anthropic-compatible service; the full …/v1/messages address works too.'
  }
  if (provider === 'ollama') {
    return 'Defaults to local Ollama; change it when the server runs elsewhere.'
  }
  return 'Filled with the provider\u2019s standard API endpoint; change it when using a proxy.'
}
