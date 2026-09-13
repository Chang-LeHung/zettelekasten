<script setup lang="ts">
import { computed } from 'vue'
import type { AgentContextComposition } from '../api/types'
import { formatTokenCount } from '../utils/agentUsage'

const props = defineProps<{
  composition: AgentContextComposition | null
  currentTokens: number | null
  maxTokens: number
}>()

const parts = computed(() => [
  { key: 'system_prompt', label: 'System', color: '#416b54', value: props.composition?.system_prompt || 0 },
  { key: 'tool_prompt', label: 'Tool prompt', color: '#76917f', value: props.composition?.tool_prompt || 0 },
  { key: 'tool_output', label: 'Tool output', color: '#b58a5f', value: props.composition?.tool_output || 0 },
  { key: 'user', label: 'User', color: '#668ba0', value: props.composition?.user || 0 },
  { key: 'assistant', label: 'Assistant', color: '#9d80a8', value: props.composition?.assistant || 0 },
].filter(part => part.value > 0))

const gradient = computed(() => {
  if (!parts.value.length) return 'conic-gradient(#e4e9e6 0 100%)'
  let start = 0
  const stops = parts.value.map((part) => {
    const end = start + part.value * 100
    const stop = `${part.color} ${start}% ${end}%`
    start = end
    return stop
  })
  return `conic-gradient(${stops.join(',')})`
})

const fullness = computed(() => {
  if (props.currentTokens === null || props.maxTokens <= 0) return null
  return Math.max(0, props.currentTokens / props.maxTokens)
})
</script>

<template>
  <div class="context-ring-control" tabindex="0" aria-label="Current context composition">
    <span class="context-ring" :style="{ background: gradient }" aria-hidden="true" />
    <div class="context-popover" role="tooltip">
      <header>
        <div><strong>Context composition</strong><small>Latest model context</small></div>
        <span v-if="currentTokens !== null">
          {{ formatTokenCount(currentTokens) }} / {{ formatTokenCount(maxTokens) }}
          <small v-if="fullness !== null">{{ Math.round(fullness * 100) }}%</small>
        </span>
      </header>
      <div v-for="part in parts" :key="part.key" class="context-part">
        <i :style="{ background: part.color }" />
        <span>{{ part.label }}</span>
        <strong>{{ (part.value * 100).toFixed(1) }}%</strong>
      </div>
      <small>Estimated uniformly with tiktoken. Provider billing may differ.</small>
    </div>
  </div>
</template>

<style scoped>
.context-ring-control { position: relative; flex: 0 0 auto; display: grid; place-items: center; margin-left: .42rem; padding: .25rem; border-radius: 50%; outline: none; cursor: help; transition: background 140ms ease, transform 140ms ease; }
.context-ring-control:hover, .context-ring-control:focus-visible { background: #f1f5f2; transform: scale(1.05); }
.context-ring-control:focus-visible { box-shadow: 0 0 0 3px rgba(71, 105, 87, .13); }
.context-ring { width: 1.48rem; height: 1.48rem; display: block; border-radius: 50%; filter: drop-shadow(0 1px 1px rgba(45, 62, 52, .12)); -webkit-mask: radial-gradient(circle, transparent calc(100% - 2.5px), #000 calc(100% - 2px)); mask: radial-gradient(circle, transparent calc(100% - 2.5px), #000 calc(100% - 2px)); }
.context-popover { position: absolute; right: -.25rem; bottom: calc(100% + .62rem); z-index: 32; width: 13.5rem; padding: .68rem; border: 1px solid rgba(52, 70, 60, .12); border-radius: .8rem; background: rgba(255, 255, 255, .98); box-shadow: 0 14px 38px rgba(35, 49, 41, .14); opacity: 0; visibility: hidden; transform: translateY(.25rem); transition: 140ms ease; pointer-events: none; }
.context-ring-control:hover .context-popover, .context-ring-control:focus-within .context-popover { opacity: 1; visibility: visible; transform: none; }
.context-popover header { display: flex; align-items: flex-start; justify-content: space-between; gap: .6rem; margin-bottom: .55rem; color: #465149; font-size: .62rem; }
.context-popover header > div, .context-popover header > span { display: grid; gap: .08rem; }
.context-popover header > span { color: #67726b; text-align: right; font-variant-numeric: tabular-nums; }
.context-popover header small { color: #969e99; font-size: .49rem; font-weight: 520; }
.context-part { display: grid; grid-template-columns: auto 1fr auto; align-items: center; gap: .42rem; padding: .18rem 0; color: #66716a; font-size: .57rem; }
.context-part i { width: .42rem; height: .42rem; border-radius: 50%; }
.context-part strong { color: #4f5a53; font-variant-numeric: tabular-nums; }
.context-popover small { display: block; margin-top: .48rem; padding-top: .48rem; border-top: 1px solid #edf0ee; color: #969e99; font-size: .5rem; line-height: 1.45; }
</style>
