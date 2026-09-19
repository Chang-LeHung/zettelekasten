<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import type { AgentContextComposition, AgentModelUsage, AIProvider, ReasoningEffort, ShellApprovalMode } from '../api/types'
import { formatTokenCount, type AgentUsageSummary } from '../utils/agentUsage'
import { useI18n } from '../i18n'
import ContextCompositionRing from './ContextCompositionRing.vue'

const props = defineProps<{
  providers: AIProvider[]
  selectedProviderId: string | null
  effort: ReasoningEffort
  shellApproval: ShellApprovalMode
  disabled: boolean
  usage: AgentUsageSummary | null
  currentUsage: AgentModelUsage | null
  contextComposition: AgentContextComposition | null
  compactionMaxTokens: number
}>()

const emit = defineEmits<{
  'update:selectedProviderId': [value: string]
  'update:effort': [value: ReasoningEffort]
  'update:shellApproval': [value: ShellApprovalMode]
  addProvider: []
}>()

const root = ref<HTMLElement | null>(null)
const { t } = useI18n()
const openMenu = ref<'model' | 'effort' | 'shell' | null>(null)
const enabledProviders = computed(() => props.providers.filter((provider) => provider.enabled))
const selectedProvider = computed(() => (
  enabledProviders.value.find((provider) => provider.id === props.selectedProviderId) || enabledProviders.value[0] || null
))
const currentContextTokens = computed(() => (
  props.currentUsage
    ? props.currentUsage.input_tokens + props.currentUsage.output_tokens
    : null
))

const effortOptions = computed<Array<{ value: ReasoningEffort; label: string; description: string }>>(() => [
  { value: 'off', label: t('composer.off'), description: 'Answer directly' },
  { value: 'low', label: t('composer.low'), description: 'Light thinking' },
  { value: 'medium', label: t('composer.medium'), description: 'Balanced depth' },
  { value: 'high', label: t('composer.high'), description: 'Deep analysis' },
])

const selectedEffort = computed(() => effortOptions.value.find((option) => option.value === props.effort) || effortOptions.value[2])
const shellApprovalOptions = computed<Array<{ value: ShellApprovalMode; label: string; description: string }>>(() => [
  { value: 'review', label: t('composer.review'), description: t('composer.reviewDescription') },
  { value: 'allow_all', label: t('composer.allowAll'), description: t('composer.allowAllDescription') },
])
const selectedShellApproval = computed(() => (
  shellApprovalOptions.value.find((option) => option.value === props.shellApproval) || shellApprovalOptions.value[0]
))

function toggleMenu(menu: 'model' | 'effort' | 'shell'): void {
  if (props.disabled && menu !== 'shell') return
  openMenu.value = openMenu.value === menu ? null : menu
}

function selectProvider(id: string): void {
  emit('update:selectedProviderId', id)
  openMenu.value = null
}

function selectEffort(effort: ReasoningEffort): void {
  emit('update:effort', effort)
  openMenu.value = null
}

function selectShellApproval(value: ShellApprovalMode): void {
  emit('update:shellApproval', value)
  openMenu.value = null
}

function handleDocumentPointerDown(event: PointerEvent): void {
  if (root.value && event.target instanceof Node && !root.value.contains(event.target)) openMenu.value = null
}

function handleDocumentKeydown(event: KeyboardEvent): void {
  if (event.key === 'Escape') openMenu.value = null
}

onMounted(() => {
  document.addEventListener('pointerdown', handleDocumentPointerDown)
  document.addEventListener('keydown', handleDocumentKeydown)
})

onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', handleDocumentPointerDown)
  document.removeEventListener('keydown', handleDocumentKeydown)
})
</script>

<template>
  <div ref="root" class="agent-composer-controls">
    <div class="control-menu model-menu">
      <button
        class="control-trigger model-trigger"
        type="button"
        :disabled="disabled"
        :aria-expanded="openMenu === 'model'"
        aria-haspopup="listbox"
        @click="toggleMenu('model')"
      >
        <span class="control-icon" aria-hidden="true">
          <svg viewBox="0 0 24 24"><path d="m12 3 1.2 4.8L18 9.5l-4.8 1.7L12 16l-1.2-4.8L6 9.5l4.8-1.7zM18.5 15l.6 2.1 2.1.6-2.1.6-.6 2.1-.6-2.1-2.1-.6 2.1-.6z" /></svg>
        </span>
        <span class="control-copy">
          <small>{{ t('composer.model') }}</small>
          <strong>{{ selectedProvider?.model || 'Add a provider' }}</strong>
        </span>
        <svg class="control-chevron" viewBox="0 0 20 20" aria-hidden="true"><path d="m6 8 4 4 4-4" /></svg>
      </button>

      <div v-if="openMenu === 'model'" class="control-popover model-popover" role="listbox" aria-label="Model">
        <header><strong>Choose model</strong><small>{{ enabledProviders.length }} available</small></header>
        <button
          v-for="provider in enabledProviders"
          :key="provider.id"
          class="model-option"
          :class="{ selected: provider.id === selectedProvider?.id }"
          type="button"
          role="option"
          :aria-selected="provider.id === selectedProvider?.id"
          @click="selectProvider(provider.id)"
        >
          <span class="provider-mark" aria-hidden="true">{{ provider.name.slice(0, 1).toUpperCase() }}</span>
          <span><strong>{{ provider.model }}</strong><small>{{ provider.name }} · {{ provider.provider.replaceAll('_', ' ') }}</small></span>
          <svg v-if="provider.id === selectedProvider?.id" viewBox="0 0 20 20" aria-hidden="true"><path d="m5 10 3 3 7-7" /></svg>
        </button>
        <button v-if="!enabledProviders.length" class="empty-provider" type="button" @click="emit('addProvider')">Configure your first provider</button>
      </div>
    </div>

    <div class="control-menu effort-menu">
      <button
        class="control-trigger effort-trigger"
        type="button"
        :disabled="disabled"
        :aria-expanded="openMenu === 'effort'"
        aria-haspopup="listbox"
        @click="toggleMenu('effort')"
      >
        <span class="effort-dot" :class="effort" aria-hidden="true" />
        <span class="control-copy"><small>{{ t('composer.thinking') }}</small><strong>{{ selectedEffort.label }}</strong></span>
        <svg class="control-chevron" viewBox="0 0 20 20" aria-hidden="true"><path d="m6 8 4 4 4-4" /></svg>
      </button>

      <div v-if="openMenu === 'effort'" class="control-popover effort-popover" role="listbox" aria-label="Thinking effort">
        <header><strong>Thinking effort</strong><small>For the next message</small></header>
        <button
          v-for="option in effortOptions"
          :key="option.value"
          class="effort-option"
          :class="{ selected: option.value === effort }"
          type="button"
          role="option"
          :aria-selected="option.value === effort"
          @click="selectEffort(option.value)"
        >
          <span class="effort-dot" :class="option.value" aria-hidden="true" />
          <span><strong>{{ option.label }}</strong><small>{{ option.description }}</small></span>
          <svg v-if="option.value === effort" viewBox="0 0 20 20" aria-hidden="true"><path d="m5 10 3 3 7-7" /></svg>
        </button>
      </div>
    </div>

    <div class="control-menu shell-menu">
      <button
        class="control-trigger shell-trigger"
        type="button"
        :aria-expanded="openMenu === 'shell'"
        aria-haspopup="listbox"
        @click="toggleMenu('shell')"
      >
        <span class="control-icon shell-icon" aria-hidden="true">
          <svg viewBox="0 0 24 24"><path d="M12 3 5 6v5c0 4.4 2.8 8.3 7 10 4.2-1.7 7-5.6 7-10V6z" /><path d="m9 12 2 2 4-4" /></svg>
        </span>
        <span class="control-copy"><small>{{ t('composer.shell') }}</small><strong>{{ selectedShellApproval.label }}</strong></span>
        <svg class="control-chevron" viewBox="0 0 20 20" aria-hidden="true"><path d="m6 8 4 4 4-4" /></svg>
      </button>

      <div v-if="openMenu === 'shell'" class="control-popover shell-popover" role="listbox" aria-label="Shell approval">
        <header><strong>Shell approval</strong><small>{{ t('composer.nextMessage') }}</small></header>
        <button
          v-for="option in shellApprovalOptions"
          :key="option.value"
          class="shell-option"
          :class="{ selected: option.value === shellApproval }"
          type="button"
          role="option"
          :aria-selected="option.value === shellApproval"
          @click="selectShellApproval(option.value)"
        >
          <span class="shell-mode-mark" :class="option.value" aria-hidden="true" />
          <span><strong>{{ option.label }}</strong><small>{{ option.description }}</small></span>
          <svg v-if="option.value === shellApproval" viewBox="0 0 20 20" aria-hidden="true"><path d="m5 10 3 3 7-7" /></svg>
        </button>
      </div>
    </div>

    <dl v-if="usage" class="usage-strip" aria-label="Conversation token usage">
      <div title="Input tokens accumulated across every model step"><dt>{{ t('composer.totalIn') }}</dt><dd>{{ formatTokenCount(usage.input_tokens) }}</dd></div>
      <div title="Output tokens accumulated across every model step"><dt>{{ t('composer.totalOut') }}</dt><dd>{{ formatTokenCount(usage.output_tokens) }}</dd></div>
      <div title="Cached input tokens divided by all input tokens"><dt>{{ t('composer.cache') }}</dt><dd>{{ usage.cache_hit_rate === null ? '—' : `${(usage.cache_hit_rate * 100).toFixed(1)}%` }}</dd></div>
      <div title="Output tokens per second of model generation"><dt>{{ t('composer.speed') }}</dt><dd>{{ usage.tokens_per_second === null ? '—' : `${usage.tokens_per_second.toFixed(1)} tok/s` }}</dd></div>
    </dl>
    <span v-if="usage" class="compact-cache" tabindex="0" :aria-label="t('composer.cache')">
      <span class="compact-stat">{{ t('composer.cache') }} <strong>{{ usage.cache_hit_rate === null ? '—' : `${(usage.cache_hit_rate * 100).toFixed(1)}%` }}</strong></span>
      <span class="compact-stat compact-speed">{{ t('composer.speed') }} <strong>{{ usage.tokens_per_second === null ? '—' : `${usage.tokens_per_second.toFixed(1)} tok/s` }}</strong></span>
      <span class="cache-popover" role="tooltip">
        <strong>{{ t('composer.cache') }}</strong>
        <span><small>{{ t('Input') }}</small><em>{{ formatTokenCount(usage.input_tokens) }}</em></span>
        <span><small>{{ t('Output') }}</small><em>{{ formatTokenCount(usage.output_tokens) }}</em></span>
        <span><small>{{ t('Cache read') }}</small><em>{{ formatTokenCount(usage.cache_read_tokens) }}</em></span>
        <span><small>{{ t('Cache write') }}</small><em>{{ formatTokenCount(usage.cache_write_tokens) }}</em></span>
        <span><small>{{ t('Cache hit rate') }}</small><em>{{ usage.cache_hit_rate === null ? '—' : `${(usage.cache_hit_rate * 100).toFixed(2)}%` }}</em></span>
        <span><small>{{ t('composer.speed') }}</small><em>{{ usage.tokens_per_second === null ? '—' : `${usage.tokens_per_second.toFixed(1)} tok/s` }}</em></span>
      </span>
    </span>
    <ContextCompositionRing
      :composition="contextComposition"
      :current-tokens="currentContextTokens"
      :max-tokens="compactionMaxTokens"
    />
  </div>
</template>

<style scoped>
.agent-composer-controls { min-width: 0; display: flex; align-items: center; gap: .2rem; }
.control-menu { position: relative; flex: 0 0 auto; }
.control-trigger { min-width: 0; height: 2.5rem; display: flex; align-items: center; gap: .48rem; padding: .25rem .5rem; border: 1px solid transparent; border-radius: .7rem; color: #4e5952; background: transparent; cursor: pointer; text-align: left; transition: border-color 150ms ease, background 150ms ease, box-shadow 150ms ease; }
.control-trigger:hover, .control-trigger[aria-expanded='true'] { border-color: #dfe6e1; background: #f5f8f6; }
.control-trigger[aria-expanded='true'] { box-shadow: 0 1px 5px rgba(42, 63, 51, .06); }
.control-trigger:focus-visible { outline: 3px solid rgba(71, 105, 87, .14); outline-offset: 1px; }
.control-trigger:disabled { opacity: .6; cursor: default; }
.model-trigger { width: clamp(8.5rem, 11vw, 10.5rem); }
.effort-trigger { width: 7.2rem; }
.shell-trigger { width: 8.35rem; }
.control-icon { width: 1.65rem; height: 1.65rem; flex: 0 0 auto; display: grid; place-items: center; border-radius: .52rem; color: #42614f; background: #e9f0eb; }
.control-icon svg { width: .88rem; height: .88rem; fill: none; stroke: currentColor; stroke-width: 1.65; stroke-linecap: round; stroke-linejoin: round; }
.control-copy { min-width: 0; flex: 1; display: grid; gap: .05rem; }
.control-copy small, .control-copy strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.control-copy small { color: #929a95; font-size: .5rem; font-weight: 560; line-height: 1.15; }
.control-copy strong { color: #4c5650; font-size: .66rem; font-weight: 650; line-height: 1.2; }
.control-chevron { width: .72rem; height: .72rem; flex: 0 0 auto; fill: none; stroke: #8c9690; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; transition: transform 150ms ease; }
.control-trigger[aria-expanded='true'] .control-chevron { transform: rotate(180deg); }
.effort-dot { width: .48rem; height: .48rem; flex: 0 0 auto; border: 1px solid #a8b3ac; border-radius: 50%; background: #fff; box-shadow: 0 0 0 .2rem #f0f3f1; }
.effort-dot.low { background: #a8bbae; }
.effort-dot.medium { border-color: #668573; background: #71917d; }
.effort-dot.high { border-color: #3f684f; background: #416d53; box-shadow: 0 0 0 .2rem #e6eee9; }
.control-popover { position: absolute; left: 0; bottom: calc(100% + .55rem); z-index: 30; padding: .42rem; border: 1px solid rgba(52, 70, 60, .12); border-radius: .86rem; background: rgba(255, 255, 255, .98); box-shadow: 0 16px 42px rgba(35, 49, 41, .14), 0 2px 8px rgba(35, 49, 41, .06); backdrop-filter: blur(18px); animation: popover-enter 150ms ease-out; }
.model-popover { width: min(19rem, calc(100vw - 2rem)); }
.effort-popover { width: 14rem; }
.shell-popover { width: 15rem; }
.control-popover header { display: flex; align-items: baseline; justify-content: space-between; gap: .5rem; padding: .45rem .52rem .52rem; }
.control-popover header strong { color: #38423c; font-size: .66rem; }
.control-popover header small { color: #969d98; font-size: .53rem; }
.control-popover button { width: 100%; min-height: 2.8rem; display: grid; grid-template-columns: auto minmax(0, 1fr) auto; align-items: center; gap: .55rem; padding: .42rem .5rem; border: 0; border-radius: .62rem; color: #535d57; background: transparent; cursor: pointer; text-align: left; }
.control-popover button:hover { background: #f3f6f4; }
.control-popover button.selected { color: #31543f; background: #edf4ef; }
.control-popover button > span:nth-child(2) { min-width: 0; }
.control-popover button strong, .control-popover button small { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.control-popover button strong { font-size: .65rem; font-weight: 650; }
.control-popover button small { margin-top: .1rem; color: #8d9590; font-size: .53rem; text-transform: capitalize; }
.control-popover button > svg { width: .8rem; height: .8rem; fill: none; stroke: currentColor; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; }
.provider-mark { width: 1.65rem; height: 1.65rem; display: grid; place-items: center; border-radius: .5rem; color: #3d624c; background: #e5eee8; font-size: .62rem; font-weight: 720; }
.shell-mode-mark { width: .5rem; height: .5rem; border-radius: 50%; background: #d6a36d; box-shadow: 0 0 0 .2rem #f7efe6; }
.shell-mode-mark.allow_all { background: #5e8f70; box-shadow: 0 0 0 .2rem #e5efe8; }
.empty-provider { grid-template-columns: 1fr !important; color: #42614f !important; text-align: center !important; }
.usage-strip { min-width: 0; display: flex; align-items: stretch; margin: 0 0 0 .35rem; padding: .15rem 0 .15rem .48rem; border-left: 1px solid #e4e8e5; font-variant-numeric: tabular-nums; }
.usage-strip div { min-width: 3.25rem; display: grid; align-content: center; gap: .04rem; padding: 0 .52rem; }
.usage-strip div + div { border-left: 1px solid #edf0ee; }
.usage-strip dt, .usage-strip dd { margin: 0; white-space: nowrap; }
.usage-strip dt { color: #a0a6a2; font-size: .48rem; font-weight: 580; line-height: 1.1; }
.usage-strip dd { color: #657069; font-size: .57rem; font-weight: 630; line-height: 1.25; }
.compact-cache { display: none; }
@keyframes popover-enter { from { opacity: 0; transform: translateY(.3rem) scale(.985); } }
@container composer-footer (max-width: 860px) {
  .agent-composer-controls { flex-wrap: wrap; }
  .usage-strip { display: none; }
  .compact-cache { position: relative; order: 1; display: inline-flex; align-items: baseline; gap: .48rem; margin-left: auto; color: #7b857f; white-space: nowrap; font-size: .54rem; cursor: default; }
  .compact-stat { display: inline-flex; gap: .22rem; }
  .compact-cache strong { color: #4f5a53; font-variant-numeric: tabular-nums; }
  .context-ring-control { order: 2; margin-left: auto; }
}
@container composer-footer (max-width: 760px) {
  .agent-composer-controls { display: grid; grid-template-columns: minmax(0, 1.15fr) minmax(0, 1fr) minmax(0, 1.08fr) auto auto; align-items: center; column-gap: .25rem; row-gap: .25rem; }
  .control-menu { min-width: 0; }
  .model-trigger, .effort-trigger, .shell-trigger { width: 100%; }
  .control-icon { display: none; }
  .compact-cache { grid-column: 4; margin-left: 0; }
  .context-ring-control { grid-column: 5; margin-left: 0; }
}
@container composer-footer (max-width: 560px) {
  .control-trigger { gap: .2rem; padding: .2rem .3rem; }
  .control-copy small, .control-chevron { display: none; }
  .context-ring { width: 1.9rem; height: 1.9rem; }
}
@container composer-footer (max-width: 430px) {
  .agent-composer-controls { grid-template-columns: repeat(2, minmax(0, 1fr)) auto; }
  .model-menu { grid-column: 1 / 3; }
  .effort-menu { grid-column: 1; }
  .shell-menu { grid-column: 2; }
  .compact-cache { grid-column: 1 / 3; grid-row: 3; justify-self: start; }
  .context-ring-control { grid-column: 3; grid-row: 1 / span 3; align-self: center; }
}
.cache-popover { position: absolute; right: 0; bottom: calc(100% + .45rem); z-index: 35; width: 12.5rem; display: grid; gap: .3rem; padding: .55rem .62rem; border: 1px solid rgba(52, 70, 60, .12); border-radius: .72rem; color: #4f5a53; background: rgba(255, 255, 255, .98); box-shadow: 0 12px 34px rgba(35, 49, 41, .14); opacity: 0; visibility: hidden; transform: translateY(.2rem); transition: 140ms ease; pointer-events: none; }
.compact-cache:hover .cache-popover, .compact-cache:focus .cache-popover, .compact-cache:focus-within .cache-popover { opacity: 1; visibility: visible; transform: none; }
.cache-popover > strong { color: #3f4a43; font-size: .6rem; }
.cache-popover > span { display: flex; align-items: center; justify-content: space-between; gap: .5rem; }
.cache-popover small { color: #8d9590; font-size: .5rem; font-weight: 500; }
.cache-popover em { color: #4f5a53; font-size: .54rem; font-style: normal; font-weight: 680; font-variant-numeric: tabular-nums; }
@media (prefers-reduced-motion: reduce) {
  .control-popover { animation-duration: 1ms; }
}
</style>
