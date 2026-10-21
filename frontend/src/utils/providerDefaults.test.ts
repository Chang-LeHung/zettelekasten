import { describe, expect, it } from 'vitest'
import {
  defaultProviderBaseUrl,
  defaultWebSearchName,
  providerBaseUrlHelp,
  providerIgnoresTemperature,
  webSearchHint,
  webSearchUnavailableReason,
} from './providerDefaults'

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

it('knows Anthropic-compatible services need an address, and which adapters ignore temperature', () => {
  expect(defaultProviderBaseUrl('anthropic')).toBe('https://api.anthropic.com')
  expect(defaultProviderBaseUrl('anthropic_compatible')).toBe('')
  expect(providerBaseUrlHelp('anthropic_compatible')).toContain('Anthropic-compatible')
  expect(providerIgnoresTemperature('anthropic')).toBe(true)
  expect(providerIgnoresTemperature('anthropic_compatible')).toBe(true)
  expect(providerIgnoresTemperature('openai')).toBe(false)
})

describe('web search defaults', () => {
  it('picks the search tool each protocol understands', () => {
    expect(defaultWebSearchName('openai', 'gpt-4.1', true)).toBe('web_search')
    // OpenAI-style adapters send a hosted tool on Chat Completions too.
    expect(defaultWebSearchName('openai', 'gpt-4.1', false)).toBe('web_search')
    expect(defaultWebSearchName('openai_compatible', 'm')).toBe('web_search')
    expect(defaultWebSearchName('anthropic', 'claude-sonnet')).toBe('web_search_20260318')
    expect(defaultWebSearchName('anthropic_compatible', 'deepseek-flash')).toBe('web_search_20250305')
    expect(defaultWebSearchName('google', 'gemini')).toBe('google_search')
    expect(defaultWebSearchName('ollama', 'llama')).toBe('')
  })

  it('lets DeepSeek search only through the Anthropic API on a flash model', () => {
    expect(webSearchUnavailableReason('anthropic_compatible', 'deepseek-flash')).toBe('')
    expect(webSearchUnavailableReason('responses_compatible', 'deepseek-flash')).toContain('Anthropic API')
    expect(webSearchUnavailableReason('deepseek', 'deepseek-v4-flash', true)).toContain('Anthropic API')
    expect(webSearchUnavailableReason('anthropic_compatible', 'deepseek-pro')).toContain('flash')
  })

  it('explains protocols that cannot search unless a tool is named', () => {
    expect(webSearchUnavailableReason('ollama', 'llama')).toContain('Ollama')
    expect(webSearchUnavailableReason('openai_compatible', 'm')).toBe('')
    expect(webSearchUnavailableReason('openai_compatible', 'm', false, 'gateway:search')).toBe('')
    expect(webSearchUnavailableReason('anthropic_compatible', 'gateway-model')).toBe('')
  })

  it('names the tool and the result shape each protocol uses', () => {
    expect(webSearchHint('anthropic', 'claude-sonnet')).toContain('web_search_20260318')
    expect(webSearchHint('anthropic_compatible', 'deepseek-flash')).toContain('web_search_20250305')
    expect(webSearchHint('openai', 'gpt-4.1', true)).toContain('Responses API')
    expect(webSearchHint('google', 'gemini')).toContain('google_search')
    expect(webSearchHint('ollama', 'llama')).toContain('no search tool')
  })
})
