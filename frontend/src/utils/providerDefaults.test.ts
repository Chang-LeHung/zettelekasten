import { describe, expect, it } from 'vitest'
import { defaultProviderBaseUrl, providerBaseUrlHelp } from './providerDefaults'

describe('provider defaults', () => {
  it.each([
    ['openai', 'https://api.openai.com/v1'],
    ['deepseek', 'https://api.deepseek.com/v1'],
    ['anthropic', 'https://api.anthropic.com'],
    ['google', 'https://generativelanguage.googleapis.com'],
    ['ollama', 'http://localhost:11434'],
  ])('returns the standard endpoint for %s', (provider, endpoint) => {
    expect(defaultProviderBaseUrl(provider)).toBe(endpoint)
  })

  it('leaves compatible and unknown providers for manual configuration', () => {
    expect(defaultProviderBaseUrl('openai_compatible')).toBe('')
    expect(defaultProviderBaseUrl('responses_compatible')).toBe('')
    expect(defaultProviderBaseUrl('custom')).toBe('')
    expect(providerBaseUrlHelp('openai_compatible')).toContain('Chat Completions endpoint')
    expect(providerBaseUrlHelp('responses_compatible')).toContain('Responses API root')
  })

  it('uses the unversioned DeepSeek root for the Responses API', () => {
    expect(defaultProviderBaseUrl('deepseek', true)).toBe('https://api.deepseek.com')
    expect(defaultProviderBaseUrl('deepseek', false)).toBe('https://api.deepseek.com/v1')
  })

  it('describes the local Ollama default separately', () => {
    expect(providerBaseUrlHelp('ollama')).toContain('local Ollama')
    expect(providerBaseUrlHelp('openai')).toContain('standard API endpoint')
  })
})
