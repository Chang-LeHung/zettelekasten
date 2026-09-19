<script setup lang="ts">
import { computed } from 'vue'
import type { AgentContextComposition } from '../api/types'
import { formatTokenCount } from '../utils/agentUsage'

const MIN_VISIBLE_SHARE = 0.035
const SEGMENT_GAP = 0.8

const props = defineProps<{
  composition: AgentContextComposition | null
  currentTokens: number | null
  maxTokens: number
}>()

const parts = computed(() => [
  { key: 'system_prompt', label: 'System', color: '#008f5d', value: props.composition?.system_prompt || 0 },
  { key: 'tool_prompt', label: 'Tool prompt', color: '#f0a202', value: props.composition?.tool_prompt || 0 },
  { key: 'tool_output', label: 'Tool output', color: '#d1495b', value: props.composition?.tool_output || 0 },
  { key: 'user', label: 'User', color: '#006fb9', value: props.composition?.user || 0 },
  { key: 'assistant', label: 'Assistant', color: '#783db8', value: props.composition?.assistant || 0 },
].filter(part => part.value > 0))

const segments = computed(() => {
  const visibleTotal = parts.value.reduce((total, part) => total + Math.max(part.value, MIN_VISIBLE_SHARE), 0)
  let start = 0
  return parts.value.map((part) => {
    const visualValue = Math.max(part.value, MIN_VISIBLE_SHARE) / visibleTotal
    const segment = { ...part, offset: -start * 100 }
    start += visualValue
    return { ...segment, visualValue, dashLength: Math.max(0, visualValue * 100 - SEGMENT_GAP) }
  })
})

const fullness = computed(() => {
  if (props.currentTokens === null || props.maxTokens <= 0) return null
  return Math.max(0, props.currentTokens / props.maxTokens)
})
</script>

<template>
  <div
    class="context-ring-control"
    :class="{ empty: !composition }"
    tabindex="0"
    :aria-label="composition ? 'Current context composition' : 'Context composition is not available yet'"
  >
    <svg class="context-ring" viewBox="0 0 24 24" aria-hidden="true">
      <circle class="context-ring-track" cx="12" cy="12" r="9.5" pathLength="100" />
      <circle
        v-for="segment in segments"
        :key="segment.key"
        class="context-ring-segment"
        cx="12"
        cy="12"
        r="9.5"
        pathLength="100"
        :stroke="segment.color"
        :stroke-dasharray="`${segment.dashLength} ${100 - segment.dashLength}`"
        :stroke-dashoffset="segment.offset"
      />
    </svg>
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
      <p v-if="!parts.length" class="context-empty">Available after the first model request.</p>
      <small>Exact values are shown above; tiny ring slices are enlarged for visibility.</small>
    </div>
  </div>
</template>

<style scoped>
.context-ring-control { position: relative; flex: 0 0 auto; display: grid; place-items: center; margin-left: .42rem; padding: .25rem; border-radius: 50%; outline: none; cursor: default; transition: background 140ms ease, transform 140ms ease; }
.context-ring-control:hover, .context-ring-control:focus-visible { background: #f1f5f2; transform: scale(1.05); }
.context-ring-control:focus-visible { box-shadow: 0 0 0 3px rgba(71, 105, 87, .13); }
.context-ring { width: 1.72rem; height: 1.72rem; display: block; overflow: visible; filter: drop-shadow(0 1px 1px rgba(45, 62, 52, .12)); transform: rotate(-90deg); }
.context-ring-track, .context-ring-segment { fill: none; stroke-width: 3; }
.context-ring-track { stroke: #e4e9e6; }
.context-ring-segment { stroke-linecap: butt; }
.context-ring-control.empty .context-ring { opacity: .72; }
.context-popover { position: absolute; right: -.25rem; bottom: calc(100% - .1rem); z-index: 32; width: 13.5rem; padding: .68rem; border: 1px solid rgba(52, 70, 60, .12); border-radius: .8rem; background: rgba(255, 255, 255, .98); box-shadow: 0 14px 38px rgba(35, 49, 41, .14); opacity: 0; visibility: hidden; transform: translateY(.25rem); transition: 140ms ease; pointer-events: none; }
.context-ring-control:hover .context-popover, .context-ring-control:focus-within .context-popover { opacity: 1; visibility: visible; transform: none; pointer-events: auto; }
.context-popover header { display: flex; align-items: flex-start; justify-content: space-between; gap: .6rem; margin-bottom: .55rem; color: #465149; font-size: .62rem; }
.context-popover header > div, .context-popover header > span { display: grid; gap: .08rem; }
.context-popover header > span { color: #67726b; text-align: right; font-variant-numeric: tabular-nums; }
.context-popover header small { color: #969e99; font-size: .49rem; font-weight: 520; }
.context-part { display: grid; grid-template-columns: auto 1fr auto; align-items: center; gap: .42rem; padding: .18rem 0; color: #66716a; font-size: .57rem; }
.context-part i { width: .42rem; height: .42rem; border-radius: 50%; }
.context-part strong { color: #4f5a53; font-variant-numeric: tabular-nums; }
.context-empty { margin: .2rem 0 0; color: #8c9590; font-size: .56rem; line-height: 1.4; }
.context-popover small { display: block; margin-top: .48rem; padding-top: .48rem; border-top: 1px solid #edf0ee; color: #969e99; font-size: .5rem; line-height: 1.45; }
</style>
