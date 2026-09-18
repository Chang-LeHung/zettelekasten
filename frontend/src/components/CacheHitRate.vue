<script setup lang="ts">
import { computed } from 'vue'
import type { AgentModelUsage } from '../api/types'
import { cacheHitLevel, calculateCacheHitRate, formatCacheHitRate } from '../utils/agentUsage'

const props = withDefaults(defineProps<{
  usage?: AgentModelUsage | null
  rate?: number | null
  label?: string
}>(), {
  usage: null,
  rate: null,
  label: 'Cache hit',
})

const value = computed(() => props.rate ?? calculateCacheHitRate(props.usage))
const level = computed(() => cacheHitLevel(value.value))
const display = computed(() => value.value === null ? null : formatCacheHitRate(value.value))
</script>

<template>
  <span
    v-if="display !== null && level !== null"
    class="cache-hit-rate"
    :class="level"
    :title="`Cached input tokens divided by all input tokens (${display})`"
    :aria-label="`${label}: ${display}`"
  >{{ label }} {{ display }}</span>
</template>

<style scoped>
.cache-hit-rate { display: inline; width: fit-content; padding: 0; border: 0; background: transparent; font-size: .56rem; font-weight: 680; font-variant-numeric: tabular-nums; line-height: 1.2; white-space: nowrap; }
.cache-hit-rate.high { color: #285f3e; }
.cache-hit-rate.medium { color: #7b5a1e; }
.cache-hit-rate.low { color: #824c45; }
</style>
