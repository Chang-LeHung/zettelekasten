import { ref } from 'vue'
import { aiClient } from '../api/client'
import type { AIProvider, AIProviderInput, ReasoningEffort, ShellApprovalMode } from '../api/types'
import { defaultProviderBaseUrl } from '../utils/providerDefaults'
import { errorMessage, requestConfirmation, showNotice } from './notice'

export const providers = ref<AIProvider[]>([])
export const selectedProviderId = ref<string | null>(null)
export const reasoningEffort = ref<ReasoningEffort>('medium')
export const shellApprovalMode = ref<ShellApprovalMode>('review')
export const editingProviderId = ref<string | null>(null)
export const providerLoading = ref(false)
export const providerSaving = ref(false)
export const apiKeyVisible = ref(true)
export const ai = ref<AIProviderInput>({
  name: '',
  provider: 'openai_compatible',
  model: '',
  base_url: '',
  api_key: '',
  temperature: 0.2,
  response: false,
  enabled: true,
})
let providerSelectionGeneration = 0
export async function saveAI(): Promise<void> {
  if (providerLoading.value || providerSaving.value) return
  providerSaving.value = true
  try {
    const providerId = editingProviderId.value
    const isNew = providerId === null
    const saved = isNew
      ? await aiClient.createProvider(ai.value)
      : await aiClient.updateProvider(providerId, ai.value)
    providers.value = await aiClient.listProviders()
    selectedProviderId.value = saved.id
    await selectProvider(saved)
    showNotice(isNew ? 'Provider verified and added' : 'Provider verified and saved')
  } catch (error) {
    showNotice(errorMessage(error), 'error')
  } finally {
    providerSaving.value = false
  }
}
export async function selectProvider(provider: AIProvider): Promise<void> {
  const generation = ++providerSelectionGeneration
  providerLoading.value = true
  try {
    const detail = await aiClient.getProvider(provider.id)
    if (generation !== providerSelectionGeneration) return
    editingProviderId.value = detail.id
    selectedProviderId.value = detail.id
    apiKeyVisible.value = true
    ai.value = {
      name: detail.name,
      provider: detail.provider,
      model: detail.model,
      base_url: detail.base_url || '',
      api_key: detail.api_key || '',
      temperature: detail.temperature,
      response: detail.response,
      enabled: detail.enabled,
    }
  } catch (error) {
    if (generation === providerSelectionGeneration) showNotice(errorMessage(error), 'error')
  } finally {
    if (generation === providerSelectionGeneration) providerLoading.value = false
  }
}
export function newProvider(): void {
  providerSelectionGeneration += 1
  providerLoading.value = false
  editingProviderId.value = null
  apiKeyVisible.value = true
  ai.value = { name: '', provider: 'openai_compatible', model: '', base_url: '', api_key: '', temperature: 0.2, response: false, enabled: true }
}
export function selectProviderKind(): void {
  if (ai.value.provider === 'responses_compatible') ai.value.response = true
  ai.value.base_url = defaultProviderBaseUrl(ai.value.provider, ai.value.response)
}
export function setResponseMode(enabled: boolean): void {
  ai.value.response = enabled
  ai.value.base_url = defaultProviderBaseUrl(ai.value.provider, ai.value.response)
}
export async function removeProvider(): Promise<void> {
  if (editingProviderId.value === null) return
  const confirmed = await requestConfirmation(
    'Delete this provider?',
    `“${ai.value.name || ai.value.model}” and its locally stored credentials will be permanently removed.`,
    'Delete provider',
  )
  if (!confirmed) return
  await aiClient.deleteProvider(editingProviderId.value)
  providers.value = await aiClient.listProviders()
  const next = providers.value[0]
  selectedProviderId.value = next?.id ?? null
  if (next) await selectProvider(next)
  else newProvider()
  showNotice('Provider removed')
}
