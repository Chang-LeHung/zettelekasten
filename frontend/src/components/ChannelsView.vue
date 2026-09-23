<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { aiClient, channelClient } from '../api/client'
import type { AIProvider, Channel, ChannelLogin, ChannelPluginInfo, ChannelType, ReasoningEffort } from '../api/types'
import { useI18n } from '../i18n'

const { t } = useI18n()

const channels = ref<Channel[]>([])
const providers = ref<AIProvider[]>([])
const plugins = ref<ChannelPluginInfo[]>([])
const loading = ref(false)
const connecting = ref(false)
const busyId = ref<string | null>(null)
const error = ref('')
const setupOpen = ref(false)
const loginOpen = ref(false)
const login = ref<ChannelLogin | null>(null)
const verifyCode = ref('')
const selectedType = ref<ChannelType>('')
let loginPoll: number | null = null

const form = reactive({
  name: '',
  providerId: '',
  reasoningEffort: 'medium' as ReasoningEffort,
  allowCoding: false,
})

const enabledProviders = computed(() => providers.value.filter((provider) => provider.enabled))
const canConnect = computed(() => (
  selectedType.value.length > 0
  && form.providerId.length > 0
  && enabledProviders.value.some((provider) => provider.id === form.providerId)
))
const providerName = (providerId: string): string => (
  providers.value.find((provider) => provider.id === providerId)?.name || providerId
)
const botId = (channel: Channel): string => {
  const value = channel.config.ilink_bot_id ?? channel.config.bot_id
  return typeof value === 'string' && value ? value : t('channels.value.unknown')
}

function message(errorValue: unknown): string {
  return errorValue instanceof Error ? errorValue.message : t('channels.error')
}

function typeLabel(channelType: ChannelType): string {
  const known = plugins.value.find((plugin) => plugin.channel_type === channelType)?.label
  if (known) return known
  const key = `channels.type.${channelType}`
  const localized = t(key)
  return localized === key ? channelType : localized
}

function loginStatusText(value: ChannelLogin): string {
  const key = `channels.login.status.${value.status}`
  const localized = t(key)
  return localized === key ? (value.message ?? '') : localized
}

async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    const [channelData, providerData, pluginData] = await Promise.all([
      channelClient.list(),
      aiClient.listProviders(),
      channelClient.plugins(),
    ])
    channels.value = channelData
    providers.value = providerData
    plugins.value = pluginData
    if (!form.providerId && enabledProviders.value[0]) form.providerId = enabledProviders.value[0].id
    if (!selectedType.value && pluginData[0]) selectedType.value = pluginData[0].channel_type
  } catch (errorValue) {
    error.value = message(errorValue)
  } finally {
    loading.value = false
  }
}

async function connectChannel(): Promise<void> {
  if (!canConnect.value || connecting.value) return
  connecting.value = true
  error.value = ''
  try {
    const created = await channelClient.startLogin({
      channel_type: selectedType.value,
      provider_id: form.providerId,
      name: form.name.trim() || undefined,
    })
    login.value = {
      ...created,
      channel_type: selectedType.value,
      provider_id: form.providerId,
      name: form.name.trim() || created.name,
    }
    setupOpen.value = false
    loginOpen.value = true
    startLoginPoll()
  } catch (errorValue) {
    error.value = message(errorValue)
  } finally {
    connecting.value = false
  }
}

function startLoginPoll(): void {
  stopLoginPoll()
  void pollLogin()
}

async function pollLogin(): Promise<void> {
  if (!login.value) return
  try {
    const next = await channelClient.pollLogin(login.value.id, verifyCode.value || undefined)
    login.value = next
    if (['connected', 'failed', 'expired'].includes(next.status)) {
      stopLoginPoll()
      if (next.status === 'connected') {
        await load()
        const created = channels.value.find((item) => item.id === next.channel_id)
        if (created) {
          await channelClient.update(created.id, {
            reasoning_effort: form.reasoningEffort,
            allow_coding: form.allowCoding,
          })
          await load()
        }
      }
    } else {
      loginPoll = window.setTimeout(() => {
        void pollLogin()
      }, 1_000)
    }
  } catch (errorValue) {
    error.value = message(errorValue)
    stopLoginPoll()
  }
}

function stopLoginPoll(): void {
  if (loginPoll !== null) {
    window.clearInterval(loginPoll)
    loginPoll = null
  }
}

function closeLogin(): void {
  stopLoginPoll()
  loginOpen.value = false
  login.value = null
}

async function toggleChannel(channel: Channel): Promise<void> {
  busyId.value = channel.id
  error.value = ''
  try {
    const updated = await channelClient.update(channel.id, { enabled: !channel.enabled })
    channels.value = channels.value.map((item) => item.id === updated.id ? updated : item)
  } catch (errorValue) {
    error.value = message(errorValue)
  } finally {
    busyId.value = null
  }
}

async function removeChannel(channel: Channel): Promise<void> {
  if (!window.confirm(t('channels.action.deleteConfirm', { name: channel.name }))) return
  busyId.value = channel.id
  error.value = ''
  try {
    await channelClient.delete(channel.id)
    channels.value = channels.value.filter((item) => item.id !== channel.id)
  } catch (errorValue) {
    error.value = message(errorValue)
  } finally {
    busyId.value = null
  }
}

function handleEscape(event: KeyboardEvent): void {
  if (event.key !== 'Escape') return
  if (loginOpen.value) closeLogin()
  else setupOpen.value = false
}

onMounted(() => {
  void load()
  window.addEventListener('keydown', handleEscape)
})

onBeforeUnmount(() => {
  stopLoginPoll()
  window.removeEventListener('keydown', handleEscape)
})
</script>

<template>
  <header class="topbar compact">
    <div><p class="eyebrow">{{ t('channels.eyebrow') }}</p><h1>{{ t('channels.title') }}</h1></div>
    <div class="channel-topbar-actions">
      <button class="primary-action" type="button" @click="setupOpen = true">
        <svg><use href="#icon-add" /></svg>
        {{ t('channels.connect') }}
      </button>
      <button class="secondary-action" type="button" :disabled="loading" @click="load">
        {{ loading ? t('channels.loading') : t('channels.refresh') }}
      </button>
    </div>
  </header>

  <section class="content channels-view">
    <p v-if="error" class="channel-error" role="alert">{{ error }}</p>

    <section class="wechat-connect">
      <div class="wechat-mark" aria-hidden="true"><svg><use href="#icon-channels" /></svg></div>
      <div>
        <span>{{ t('channels.hero.eyebrow') }}</span>
        <h2>{{ t('channels.hero.title') }}</h2>
        <p>{{ t('channels.hero.body') }}</p>
      </div>
      <button class="primary-action" type="button" @click="setupOpen = true">{{ t('channels.hero.action') }}</button>
    </section>

    <div v-if="loading" class="channel-empty">{{ t('channels.loadingList') }}</div>
    <div v-else-if="channels.length" class="channel-grid">
      <article v-for="channel in channels" :key="channel.id" class="channel-card">
        <header>
          <div>
            <span class="channel-type">{{ typeLabel(channel.channel_type) }}</span>
            <h2>{{ channel.name }}</h2>
            <p>{{ providerName(channel.provider_id) }}</p>
          </div>
          <span class="channel-status" :class="{ disabled: !channel.enabled }">
            {{ channel.enabled ? t('channels.state.connected') : t('channels.state.disabled') }}
          </span>
        </header>
        <dl>
          <div><dt>{{ t('channels.field.botId') }}</dt><dd :title="botId(channel)">{{ botId(channel) }}</dd></div>
          <div><dt>{{ t('channels.field.reasoning') }}</dt><dd>{{ channel.reasoning_effort }}</dd></div>
          <div>
            <dt>{{ t('channels.field.coding') }}</dt>
            <dd>{{ channel.allow_coding ? t('channels.value.enabled') : t('channels.value.disabled') }}</dd>
          </div>
        </dl>
        <footer>
          <button type="button" :disabled="busyId === channel.id" @click="toggleChannel(channel)">
            {{ channel.enabled ? t('channels.action.disable') : t('channels.action.enable') }}
          </button>
          <button class="danger" type="button" :disabled="busyId === channel.id" @click="removeChannel(channel)">
            {{ t('channels.action.delete') }}
          </button>
        </footer>
      </article>
    </div>
    <div v-else class="channel-empty">
      <h2>{{ t('channels.empty.title') }}</h2>
      <p>{{ t('channels.empty.body') }}</p>
    </div>
  </section>

  <Teleport to="body">
    <div v-if="setupOpen" class="channel-modal-backdrop" @click.self="setupOpen = false">
      <form class="channel-modal setup-modal" role="dialog" aria-modal="true" aria-labelledby="connect-title" @submit.prevent="connectChannel">
        <header>
          <div>
            <span>{{ plugins.length > 1 || !selectedType ? t('channels.title') : typeLabel(selectedType) }}</span>
            <h2 id="connect-title">{{ t('channels.setup.title') }}</h2>
            <p>{{ t('channels.setup.body') }}</p>
          </div>
          <button type="button" :aria-label="t('channels.login.close')" @click="setupOpen = false">×</button>
        </header>
        <div class="channel-form">
          <label v-if="plugins.length > 1">
            <span>{{ t('channels.field.type') }}</span>
            <select v-model="selectedType" required>
              <option v-for="plugin in plugins" :key="plugin.channel_type" :value="plugin.channel_type">
                {{ plugin.label }}
              </option>
            </select>
          </label>
          <label>
            <span>{{ t('channels.setup.name') }}</span>
            <input v-model="form.name" maxlength="100" :placeholder="t('channels.setup.namePlaceholder')" />
          </label>
          <label>
            <span>{{ t('channels.setup.provider') }}</span>
            <select v-model="form.providerId" required>
              <option value="" disabled>{{ t('channels.setup.providerPlaceholder') }}</option>
              <option v-for="provider in enabledProviders" :key="provider.id" :value="provider.id">
                {{ provider.name }} · {{ provider.model }}
              </option>
            </select>
          </label>
          <label>
            <span>Reasoning</span>
            <select v-model="form.reasoningEffort">
              <option value="off">Off</option>
              <option value="low">Low</option>
              <option value="medium">Medium</option>
              <option value="high">High</option>
            </select>
          </label>
          <label class="channel-coding">
            <input v-model="form.allowCoding" type="checkbox" />
            {{ t('channels.setup.allowCoding') }}
          </label>
        </div>
        <footer>
          <button class="secondary-action" type="button" @click="setupOpen = false">{{ t('channels.setup.cancel') }}</button>
          <button class="primary-action" type="submit" :disabled="connecting || !canConnect">
            {{ connecting ? t('channels.setup.submitting') : t('channels.setup.submit') }}
          </button>
        </footer>
      </form>
    </div>
  </Teleport>

  <Teleport to="body">
    <div v-if="loginOpen && login" class="channel-modal-backdrop" @click.self="closeLogin">
      <section class="channel-modal onboarding-modal" role="dialog" aria-modal="true" aria-labelledby="login-title">
        <header>
          <div>
            <span>{{ t('channels.login.eyebrow') }}</span>
            <h2 id="login-title">{{ t('channels.login.title', { platform: typeLabel(login.channel_type) }) }}</h2>
            <p>{{ loginStatusText(login) }}</p>
          </div>
          <button type="button" :aria-label="t('channels.login.close')" @click="closeLogin">×</button>
        </header>
        <div class="onboarding-body">
          <img
            v-if="login.qr_data_url"
            :src="login.qr_data_url"
            :alt="t('channels.login.qrAlt', { platform: typeLabel(login.channel_type) })"
          />
          <div v-else class="onboarding-placeholder">{{ t('channels.login.qrUnavailable') }}</div>
          <label v-if="login.status === 'verify_required'" class="wechat-verify">
            <span>{{ t('channels.login.pairingLabel') }}</span>
            <input
              v-model="verifyCode"
              inputmode="numeric"
              maxlength="100"
              :placeholder="t('channels.login.pairingPlaceholder')"
            />
          </label>
          <div class="onboarding-status" :class="login.status">
            <strong>{{ login.status }}</strong>
            <span>{{ loginStatusText(login) }}</span>
          </div>
          <a v-if="login.qr_url" :href="login.qr_url" target="_blank" rel="noopener noreferrer">
            {{ t('channels.login.openLink') }}
          </a>
        </div>
        <footer>
          <button class="primary-action" type="button" @click="closeLogin">{{ t('channels.login.close') }}</button>
        </footer>
      </section>
    </div>
  </Teleport>
</template>

<style scoped>
.channels-view { max-width: 84rem; }
.channel-topbar-actions { display: flex; align-items: center; gap: .5rem; }
.channel-error { margin: 0 0 1rem; padding: .75rem .9rem; border-radius: .65rem; color: #963f3f; background: #faeded; font-size: .72rem; }
.wechat-connect { display: grid; grid-template-columns: auto minmax(0, 1fr) auto; align-items: center; gap: 1rem; margin-bottom: 1.1rem; padding: 1.1rem; border: 1px solid rgba(29,29,31,.08); border-radius: .85rem; background: rgba(255,255,255,.94); }
.wechat-mark { display: grid; width: 3rem; height: 3rem; place-items: center; border-radius: .75rem; color: #1a7f5a; background: #e8f5ee; }
.wechat-mark svg { width: 1.55rem; height: 1.55rem; }
.wechat-connect > div:nth-child(2) > span { color: #3d6d4e; font-size: .6rem; font-weight: 760; letter-spacing: .08em; text-transform: uppercase; }
.wechat-connect h2 { margin: .2rem 0 0; color: #303632; font-size: 1rem; }
.wechat-connect p { max-width: 54rem; margin: .3rem 0 0; color: #7b857f; font-size: .68rem; line-height: 1.55; }
.channel-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(20rem, 1fr)); gap: 1rem; }
.channel-card { overflow: hidden; border: 1px solid rgba(29,29,31,.08); border-radius: .8rem; background: rgba(255,255,255,.92); box-shadow: 0 2px 12px rgba(0,0,0,.025); }
.channel-card > header { display: flex; align-items: flex-start; justify-content: space-between; gap: 1rem; padding: 1rem 1.1rem; border-bottom: 1px solid rgba(29,29,31,.07); }
.channel-card h2 { margin: .28rem 0 0; color: #303632; font-size: .96rem; }
.channel-card header p { margin: .2rem 0 0; color: #8a918d; font-size: .66rem; }
.channel-type { color: #52705d; font-size: .59rem; font-weight: 750; letter-spacing: .06em; text-transform: uppercase; }
.channel-status { padding: .22rem .48rem; border-radius: 999px; color: #3d6d4e; background: #e9f4ed; font-size: .6rem; font-weight: 700; }
.channel-status.disabled { color: #777; background: #eee; }
.channel-card dl { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: .6rem; margin: 0; padding: .9rem 1.1rem; }
.channel-card dt { color: #929994; font-size: .58rem; text-transform: uppercase; }
.channel-card dd { margin: .22rem 0 0; overflow: hidden; color: #3e4741; font-size: .66rem; text-overflow: ellipsis; white-space: nowrap; }
.channel-card footer { display: flex; justify-content: flex-end; gap: .45rem; padding: .75rem 1.1rem; border-top: 1px solid rgba(29,29,31,.07); }
.channel-card footer button { min-height: 1.9rem; padding: 0 .65rem; border: 1px solid #dce4de; border-radius: .55rem; color: #43534a; background: #fff; cursor: pointer; font-size: .64rem; font-weight: 650; }
.channel-card footer button.danger { color: #9d4545; border-color: #ecd8d6; background: #fffafa; }
.channel-empty { padding: 4rem 1rem; text-align: center; color: #858d88; }
.channel-empty h2 { margin: 0; color: #3e4741; font-size: 1.05rem; }
.channel-empty p { margin: .35rem 0 0; font-size: .72rem; }
.channel-modal-backdrop { position: fixed; inset: 0; z-index: 1200; display: grid; place-items: center; padding: 1rem; background: rgba(27,35,30,.3); backdrop-filter: blur(10px); }
.channel-modal { width: min(100%, 48rem); max-height: calc(100vh - 2rem); overflow-y: auto; border-radius: 1rem; background: #fff; box-shadow: 0 28px 80px rgba(28,39,32,.22); }
.channel-modal > header { display: flex; justify-content: space-between; gap: 1rem; padding: 1.15rem 1.3rem; border-bottom: 1px solid rgba(29,29,31,.07); }
.channel-modal header span { color: #557662; font-size: .6rem; font-weight: 750; letter-spacing: .08em; text-transform: uppercase; }
.channel-modal h2 { margin: .22rem 0 .2rem; color: #2d342f; font-size: 1.15rem; }
.channel-modal header p { margin: 0; color: #858d88; font-size: .68rem; }
.channel-modal header > button { width: 2rem; height: 2rem; border: 1px solid #e1e6e2; border-radius: .55rem; color: #69726c; background: #f8f9f8; cursor: pointer; font-size: 1.1rem; }
.setup-modal { width: min(100%, 34rem); }
.channel-form { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: .8rem; padding: 1rem 1.3rem; }
.channel-form label { display: grid; gap: .34rem; min-width: 0; }
.channel-form label span { color: #68716b; font-size: .64rem; font-weight: 680; }
.channel-form input, .channel-form select { width: 100%; height: 2.5rem; padding: 0 .7rem; border: 1px solid #dce2de; border-radius: .6rem; outline: none; color: #343b36; background: #fbfcfb; font: inherit; font-size: .7rem; }
.channel-form .channel-coding { display: flex; align-items: center; grid-column: 1 / -1; gap: .45rem; color: #69726c; font-size: .68rem; }
.channel-form .channel-coding input { width: auto; height: auto; }
.channel-modal > footer { display: flex; justify-content: flex-end; gap: .5rem; padding: .9rem 1.3rem 1rem; border-top: 1px solid rgba(29,29,31,.07); }
.channel-modal footer button { min-height: 2.2rem; padding: 0 .8rem; }
.onboarding-modal { width: min(100%, 30rem); }
.onboarding-body { display: grid; justify-items: center; gap: .8rem; padding: 1.2rem; }
.onboarding-body > img { width: min(100%, 18rem); aspect-ratio: 1; padding: .7rem; border: 1px solid rgba(29,29,31,.08); border-radius: .75rem; background: #fff; }
.onboarding-placeholder { width: 100%; padding: 2rem 1rem; border: 1px dashed #dce4de; border-radius: .7rem; color: #858d88; font-size: .68rem; text-align: center; }
.onboarding-status { width: 100%; display: grid; gap: .2rem; padding: .65rem .75rem; border-radius: .6rem; color: #6b746e; background: #f5f7f5; text-align: center; }
.onboarding-status strong { font-size: .68rem; text-transform: capitalize; }
.onboarding-status span { font-size: .62rem; }
.onboarding-status.connected { color: #3d6d4e; background: #e9f4ed; }
.onboarding-status.failed, .onboarding-status.expired { color: #984646; background: #faeceb; }
.onboarding-body a { color: #3f6850; font-size: .66rem; font-weight: 680; }
.wechat-verify { width: 100%; display: grid; gap: .35rem; }
.wechat-verify span { color: #68716b; font-size: .64rem; font-weight: 680; }
.wechat-verify input { width: 100%; height: 2.5rem; padding: 0 .7rem; border: 1px solid #dce2de; border-radius: .6rem; outline: none; color: #343b36; background: #fbfcfb; font: inherit; font-size: .76rem; text-align: center; }
@media (max-width: 720px) {
  .channel-topbar-actions { align-items: stretch; flex-direction: column-reverse; }
  .wechat-connect { grid-template-columns: auto minmax(0, 1fr); }
  .wechat-connect > button { grid-column: 1 / -1; }
  .channel-grid, .channel-form { grid-template-columns: 1fr; }
  .channel-card dl { grid-template-columns: 1fr; }
}
</style>
