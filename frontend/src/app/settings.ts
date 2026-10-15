import { computed, ref } from 'vue'
import { settingsClient } from '../api/client'
import type { AgentModelUsageActivitySeries, AgentUsageActivityDay, RuntimeSettings } from '../api/types'
import type { Locale } from '../i18n'
import { setLocale } from './i18n'
import { errorMessage, showNotice } from './notice'
import type { SettingsSection } from './types'

export const runtimeSettings = ref<RuntimeSettings>({
  agent_may_delete_artifacts: false,
  agent_may_delete_tags: false,
  max_message_images: 32,
  max_turn_iterations: 256,
  max_asset_size_bytes: 250 * 1024 * 1024,
  compaction_max_tokens: 800_000,
  compaction_keep_recent_tokens: 64_000,
})
export const maxAssetSizeMb = computed<number>({
  get: () => Math.round(runtimeSettings.value.max_asset_size_bytes / (1024 * 1024)),
  set: (value) => {
    const normalized = Number.isFinite(value) ? Math.max(1, Math.round(value)) : 1
    runtimeSettings.value.max_asset_size_bytes = normalized * 1024 * 1024
  },
})
export const runtimeSettingsSaving = ref(false)
export const agentPermissions = [
  {
    key: 'agent_may_delete_artifacts',
    title: 'Delete artifacts',
    description: 'Lets the Agent delete this conversation’s artifacts when you ask. Off, it has no delete tool at all.',
  },
  {
    key: 'agent_may_delete_tags',
    title: 'Delete tags',
    description: 'Lets the Agent delete tags from your library when you ask. Off, it has no delete tool at all.',
  },
] as const
/** What the server last confirmed, so a permission switch never saves half-edited limits with it. */
export const settingsScratch = {
  persistedRuntimeSettings: null as RuntimeSettings | null,
}
export const agentPermissionSaving = ref<'agent_may_delete_artifacts' | 'agent_may_delete_tags' | null>(null)
export const usageActivity = ref<AgentUsageActivityDay[]>([])
export const modelUsageActivity = ref<AgentModelUsageActivitySeries[]>([])
export const usageActivityLoading = ref(false)
export const settingsSection = ref<SettingsSection>('providers')
export const settingsOpen = ref(false)
export const settingsDialog = ref<HTMLElement | null>(null)
export async function selectSettingsSection(section: SettingsSection): Promise<void> {
  if (settingsSection.value === section) return
  settingsSection.value = section
  if (section !== 'usage') return
  usageActivityLoading.value = true
  try {
    const [usageActivityData, modelUsageActivityData] = await Promise.all([
      settingsClient.getUsageActivity(),
      settingsClient.getModelUsageActivity(30),
    ])
    usageActivity.value = usageActivityData
    modelUsageActivity.value = modelUsageActivityData
  } catch (error) {
    showNotice(errorMessage(error), 'error')
  } finally {
    usageActivityLoading.value = false
  }
}
export function closeSettings(): void {
  settingsOpen.value = false
}
export function changeLocale(event: Event): void {
  setLocale((event.target as HTMLSelectElement).value as Locale)
}
export async function saveRuntimeSettings(): Promise<void> {
  if (runtimeSettingsSaving.value) return
  runtimeSettingsSaving.value = true
  try {
    runtimeSettings.value = await settingsClient.update(runtimeSettings.value)
    settingsScratch.persistedRuntimeSettings = { ...runtimeSettings.value }
    showNotice('Runtime settings saved')
  } catch (error) {
    showNotice(errorMessage(error), 'error')
  } finally {
    runtimeSettingsSaving.value = false
  }
}
/**
 * Apply one Agent permission the moment its switch moves. It saves the last
 * confirmed settings plus this one change, so limits still being typed in the
 * form above are neither saved nor lost.
 */
export async function setAgentPermission(key: 'agent_may_delete_artifacts' | 'agent_may_delete_tags', enabled: boolean): Promise<void> {
  if (agentPermissionSaving.value) return
  agentPermissionSaving.value = key
  const base = settingsScratch.persistedRuntimeSettings ?? runtimeSettings.value
  try {
    const saved = await settingsClient.update({ ...base, [key]: enabled })
    settingsScratch.persistedRuntimeSettings = { ...saved }
    runtimeSettings.value = { ...runtimeSettings.value, [key]: saved[key] }
    showNotice(enabled ? 'The Agent can now delete here when you ask it to' : 'The Agent can no longer delete here')
  } catch (error) {
    showNotice(errorMessage(error), 'error')
  } finally {
    agentPermissionSaving.value = null
  }
}
