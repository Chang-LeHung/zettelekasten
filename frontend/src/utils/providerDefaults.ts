const providerBaseUrls: Readonly<Record<string, string>> = {
  anthropic: 'https://api.anthropic.com',
  deepseek: 'https://api.deepseek.com/v1',
  google: 'https://generativelanguage.googleapis.com',
  ollama: 'http://localhost:11434',
  openai: 'https://api.openai.com/v1',
  openai_compatible: '',
}

/** Return the conventional API endpoint for a provider, or an empty value when it cannot be inferred. */
export function defaultProviderBaseUrl(provider: string, response = false): string {
  if (provider === 'deepseek' && response) return 'https://api.deepseek.com'
  return providerBaseUrls[provider] ?? ''
}

/** Explain whether the selected endpoint is inferred or must be supplied by the user. */
export function providerBaseUrlHelp(provider: string): string {
  if (provider === 'openai_compatible') {
    return 'Enter the endpoint exposed by your compatible service.'
  }
  if (provider === 'ollama') {
    return 'Defaults to local Ollama; change it when the server runs elsewhere.'
  }
  return 'Filled with the provider\u2019s standard API endpoint; change it when using a proxy.'
}
