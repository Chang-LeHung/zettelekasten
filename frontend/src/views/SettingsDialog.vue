<script setup lang="ts">
import { defineAsyncComponent } from 'vue'
import { locale } from '../app/i18n'
import { ai, apiKeyVisible, editingProviderId, newProvider, providerLoading, providerSaving, providers, removeProvider, saveAI, selectProvider, selectProviderKind, setResponseMode } from '../app/providers'
import { agentPermissionSaving, agentPermissions, changeLocale, closeSettings, maxAssetSizeMb, modelUsageActivity, runtimeSettings, runtimeSettingsSaving, saveRuntimeSettings, selectSettingsSection, setAgentPermission, settingsOpen, settingsSection, usageActivity, usageActivityLoading } from '../app/settings'
import UsageActivityGraph from '../components/UsageActivityGraph.vue'
import { providerBaseUrlHelp, providerIgnoresTemperature } from '../utils/providerDefaults'

const ModelUsageTrend = defineAsyncComponent(() => import('../components/ModelUsageTrend.vue'))
</script>

<template>
  <Teleport to="body">
    <div v-if="settingsOpen" class="settings-backdrop" @click.self="closeSettings">
    <section ref="settingsDialog" class="settings-dialog" role="dialog" aria-modal="true" :aria-label="$t('Settings')" tabindex="-1">
      <header class="settings-dialog-header">
        <h1>{{ $t('Settings') }}</h1>
        <button class="close-button" type="button" :aria-label="$t('Close')" @click="closeSettings">×</button>
      </header>
      <div class="settings-dialog-body">
      <nav class="settings-tabs" role="tablist" aria-label="Settings sections">
        <button :class="{ active: settingsSection === 'general' }" type="button" role="tab" :aria-selected="settingsSection === 'general'" @click="selectSettingsSection('general')">{{ $t('settings.general') }}</button>
        <button :class="{ active: settingsSection === 'usage' }" type="button" role="tab" :aria-selected="settingsSection === 'usage'" @click="selectSettingsSection('usage')">{{ $t('settings.usage') }}</button>
        <button :class="{ active: settingsSection === 'providers' }" type="button" role="tab" :aria-selected="settingsSection === 'providers'" @click="selectSettingsSection('providers')">{{ $t('settings.providers') }}</button>
        <button :class="{ active: settingsSection === 'limits' }" type="button" role="tab" :aria-selected="settingsSection === 'limits'" @click="selectSettingsSection('limits')">{{ $t('settings.limits') }}</button>
      </nav>
      <section class="content settings-view">
      <div v-if="settingsSection === 'general'" class="settings-section">
      <div class="settings-intro">
        <div><h2>{{ $t('Preferences') }}</h2><p>{{ $t('Choose how Zett reads on this computer.') }}</p></div>
      </div>
      <div class="settings-card">
        <div class="form-grid">
          <label class="field">
            <span>{{ $t('settings.language') }}</span>
            <select :value="locale" @change="changeLocale">
              <option value="en">{{ $t('settings.english') }}</option>
              <option value="zh">{{ $t('settings.chinese') }}</option>
            </select>
            <small>{{ $t('Applied right away, and remembered in this browser.') }}</small>
          </label>
        </div>
      </div>
      </div>
      <div v-else-if="settingsSection === 'providers'" class="settings-section">
      <div class="settings-intro"><div><h2>{{ $t('AI providers') }}</h2><p>{{ $t('Keep multiple model connections and choose one for each conversation.') }}</p></div></div>
      <div class="provider-toolbar">
        <div v-if="providers.length" class="provider-list">
          <button v-for="provider in providers" :key="provider.id" :class="{ active: editingProviderId === provider.id }" type="button" @click="selectProvider(provider)"><span class="status-dot" :class="{ online: provider.enabled }" /><span><strong>{{ provider.name }}</strong><small>{{ provider.provider }} · {{ provider.model }}</small></span></button>
        </div>
        <button class="secondary-action" type="button" @click="newProvider"><svg><use href="#icon-add" /></svg>{{ $t('New provider') }}</button>
      </div>
      <form class="settings-card" @submit.prevent="saveAI">
        <div class="form-grid">
          <label class="field"><span>{{ $t('Connection name') }}</span><input v-model="ai.name" placeholder="e.g. Fast OpenAI" /><small>Shown in the conversation provider picker.</small></label>
          <label class="field"><span>{{ $t('Provider') }}</span><select v-model="ai.provider" @change="selectProviderKind"><option value="openai_compatible">OpenAI compatible</option><option value="responses_compatible">Responses compatible</option><option value="openai">OpenAI</option><option value="deepseek">DeepSeek</option><option value="anthropic">Anthropic</option><option value="anthropic_compatible">Anthropic compatible</option><option value="google">Google Gemini</option><option value="ollama">Ollama</option></select><small>The API format used for model requests.</small></label>
          <label class="field"><span>{{ $t('Model') }}</span><input v-model="ai.model" placeholder="e.g. gpt-4.1-mini" /><small>Use the exact model identifier from your provider.</small></label>
          <label class="field full"><span>{{ $t('Base URL') }} <em>{{ ['openai_compatible', 'responses_compatible', 'anthropic_compatible'].includes(ai.provider) ? 'Custom' : 'Auto-filled' }}</em></span><input v-model="ai.base_url" :placeholder="ai.provider === 'responses_compatible' ? 'https://api.example.com' : 'https://api.example.com/v1'" /><small>{{ providerBaseUrlHelp(ai.provider) }}</small></label>
          <label class="field full"><span>{{ $t('API key') }} <em>{{ providerLoading ? 'Loading…' : editingProviderId === null ? 'New' : ai.api_key ? 'Loaded' : 'Not set' }}</em></span><div class="secret-input"><input v-model="ai.api_key" :type="apiKeyVisible ? 'text' : 'password'" autocomplete="off" placeholder="Leave blank to keep the saved key" /><button type="button" :aria-label="apiKeyVisible ? 'Hide API key' : 'Show API key'" :title="apiKeyVisible ? 'Hide API key' : 'Show API key'" @click="apiKeyVisible = !apiKeyVisible"><svg aria-hidden="true"><use :href="apiKeyVisible ? '#icon-eye-off' : '#icon-eye'" /></svg></button></div><small>Stored encrypted locally. Saving a blank value keeps the existing key.</small></label>
          <label v-if="!providerIgnoresTemperature(ai.provider)" class="field temperature-field"><span>{{ $t('Temperature') }} <output>{{ ai.temperature.toFixed(1) }}</output></span><input v-model.number="ai.temperature" type="range" min="0" max="2" step="0.1" /></label>
          <div v-if="ai.provider === 'responses_compatible'" class="field"><span>{{ $t('API mode') }}</span><strong>Responses API</strong><small>This compatible connection always uses the Responses protocol.</small></div>
          <div v-else-if="['openai', 'openai_compatible', 'deepseek'].includes(ai.provider)" class="field"><span>{{ $t('API mode') }}</span><div class="mode-options" role="group" :aria-label="$t('API mode')"><button type="button" :class="{ active: !ai.response }" @click="setResponseMode(false)">Chat Completions</button><button type="button" :class="{ active: ai.response }" @click="setResponseMode(true)">Responses API</button></div><small>Responses mode enables provider-hosted tools such as web search.</small></div>
        </div>
        <div class="settings-actions"><button v-if="editingProviderId !== null" class="danger-button" type="button" @click="removeProvider">Delete provider</button><span v-else>Credentials are encrypted in your local database.</span><div><label class="switch"><input v-model="ai.enabled" type="checkbox" /><span /><small>{{ ai.enabled ? 'Enabled' : 'Disabled' }}</small></label><button class="primary-action" :disabled="providerSaving || providerLoading || !ai.name || !ai.model" :aria-busy="providerSaving" type="submit"><span v-if="providerSaving" class="button-spinner" aria-hidden="true" /><span>{{ providerSaving ? 'Testing…' : editingProviderId === null ? 'Add provider' : 'Save provider' }}</span></button></div></div>
      </form>
      </div>
      <div v-else-if="settingsSection === 'limits'" class="settings-section">
      <div class="settings-intro runtime-settings-heading">
        <div><h2>{{ $t('Conversation limits') }}</h2><p>{{ $t('Control local limits applied to new Agent requests.') }}</p></div>
      </div>
      <form class="settings-card" @submit.prevent="saveRuntimeSettings">
        <div class="form-grid">
          <label class="field">
            <span>{{ $t('Images per message') }}</span>
            <input v-model.number="runtimeSettings.max_message_images" type="number" min="1" max="256" step="1" />
            <small>Maximum number of images that can be pasted into one user message.</small>
          </label>
          <label class="field">
            <span>{{ $t('Model steps per turn') }}</span>
            <input v-model.number="runtimeSettings.max_turn_iterations" type="number" min="1" max="512" step="1" />
            <small>Maximum model calls, including tool-loop continuations, allowed in one turn.</small>
          </label>
          <label class="field">
            <span>{{ $t('Max asset file size') }} <em>MB</em></span>
            <input v-model.number="maxAssetSizeMb" type="number" min="1" max="2048" step="1" />
            <small>{{ $t('Maximum size for an uploaded image or file in this conversation.') }}</small>
          </label>
          <label class="field">
            <span>{{ $t('Compact context at') }}</span>
            <input v-model.number="runtimeSettings.compaction_max_tokens" type="number" min="128000" max="800000" step="1000" />
            <small>Estimated active-context tokens that trigger a compact snapshot.</small>
          </label>
          <label class="field">
            <span>{{ $t('Keep recent context') }}</span>
            <input v-model.number="runtimeSettings.compaction_keep_recent_tokens" type="number" min="32000" max="256000" step="1000" />
            <small>Recent estimated tokens retained verbatim after compaction.</small>
          </label>
        </div>
        <div class="settings-actions">
          <span>Stored locally and applied without restarting Zett.</span>
          <div><button class="primary-action" :disabled="runtimeSettingsSaving" type="submit">{{ runtimeSettingsSaving ? 'Saving…' : $t('Save limits') }}</button></div>
        </div>
      </form>
      <div class="settings-intro runtime-settings-heading">
        <div><h2>{{ $t('Agent permissions') }}</h2><p>{{ $t('Things the Agent may do in a conversation only when you allow them.') }}</p></div>
      </div>
      <div class="settings-card permission-card">
        <label v-for="permission in agentPermissions" :key="permission.key" class="permission-row">
          <span class="permission-copy">
            <strong>{{ $t(permission.title) }}</strong>
            <small>{{ $t(permission.description) }}</small>
          </span>
          <span class="switch">
            <input
              type="checkbox"
              role="switch"
              :checked="runtimeSettings[permission.key]"
              :disabled="agentPermissionSaving !== null"
              @change="setAgentPermission(permission.key, ($event.target as HTMLInputElement).checked)"
            />
            <span />
          </span>
        </label>
      </div>
      </div>
      <div v-else class="settings-section">
      <div class="settings-intro runtime-settings-heading">
        <div><h2>{{ $t('Model activity') }}</h2><p>{{ $t('Daily token requests recorded from completed LLM calls.') }}</p></div>
      </div>
      <div class="settings-card">
        <div v-if="usageActivityLoading" class="settings-activity-state">Loading activity…</div>
        <UsageActivityGraph v-else :days="usageActivity" />
      </div>

      <div class="settings-intro runtime-settings-heading">
        <div><h2>{{ $t('By model') }}</h2><p>{{ $t('Request volume and token usage for every provider model.') }}</p></div>
      </div>
      <div v-if="usageActivityLoading" class="settings-activity-state">Loading model activity…</div>
      <div v-else-if="!modelUsageActivity.length" class="settings-card settings-activity-state">No model activity recorded yet.</div>
      <div v-else class="model-usage-list">
        <ModelUsageTrend
          v-for="series in modelUsageActivity"
          :key="`${series.provider || 'unknown'}:${series.model || 'unknown'}`"
          :provider="series.provider"
          :model="series.model"
          :days="series.days"
        />
      </div>
      </div>
      </section>
      </div>
    </section>
    </div>
  </Teleport>
</template>
