<script setup lang="ts">
import { computed } from 'vue'
import { BarChart, LineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent } from 'echarts/components'
import { use } from 'echarts/core'
import type { EChartsOption } from 'echarts'
import { CanvasRenderer } from 'echarts/renderers'
import VChart from 'vue-echarts'
import type { AgentUsageActivityDay } from '../api/types'
import { formatTokenCount } from '../utils/agentUsage'

use([CanvasRenderer, LineChart, BarChart, GridComponent, TooltipComponent])

const props = defineProps<{
  provider: string | null
  model: string | null
  days: AgentUsageActivityDay[]
}>()

const providerLabel = computed(() => props.provider || 'Unknown provider')
const modelLabel = computed(() => props.model || 'Unknown model')
const modelIcon = computed(() => (props.provider || props.model || '?').slice(0, 1).toUpperCase())
const chartDays = computed(() => focusActivityRange(props.days))
const dates = computed(() => chartDays.value.map(day => day.date))
const totalRequests = computed(() => chartDays.value.reduce((total, day) => total + day.requests, 0))
const totalTokens = computed(() => chartDays.value.reduce((total, day) => total + day.total_tokens, 0))
const sparseRequestData = computed(() => chartDays.value.filter(day => day.requests > 0).length < 4)

const requestOption = computed<EChartsOption>(() => ({
  animationDuration: 320,
  animationEasing: 'cubicOut',
  grid: chartGrid(),
  tooltip: requestTooltip(),
  xAxis: chartXAxis(dates.value, sparseRequestData.value),
  yAxis: chartYAxis(formatRequestTick),
  series: [
    sparseRequestData.value
      ? {
          type: 'bar',
          data: chartDays.value.map(day => day.requests),
          barMaxWidth: 16,
          itemStyle: { color: '#7fa58b', borderRadius: [3, 3, 0, 0] },
          emphasis: { itemStyle: { color: '#5d8a70' } },
        }
      : {
          type: 'line',
          data: chartDays.value.map(day => day.requests),
          smooth: 0.32,
          smoothMonotone: 'x',
          symbol: 'none',
          lineStyle: { color: '#5d8a70', width: 2.4 },
          areaStyle: {
            color: {
              type: 'linear',
              x: 0,
              y: 0,
              x2: 0,
              y2: 1,
              colorStops: [
                { offset: 0, color: 'rgba(93,138,112,.34)' },
                { offset: 1, color: 'rgba(93,138,112,.035)' },
              ],
            },
          },
          emphasis: { focus: 'series' },
        },
  ],
}))

const tokenOption = computed<EChartsOption>(() => ({
  animationDuration: 320,
  animationEasing: 'cubicOut',
  grid: chartGrid(),
  tooltip: chartTooltip(formatInteger),
  xAxis: chartXAxis(dates.value, true),
  yAxis: chartYAxis(formatTokenCount),
  series: [
    {
      type: 'bar',
      data: chartDays.value.map(day => day.total_tokens),
      barMaxWidth: 16,
      itemStyle: { color: '#8fb59b', borderRadius: [3, 3, 0, 0] },
      emphasis: { itemStyle: { color: '#5d8a70' } },
    },
  ],
}))

function focusActivityRange(days: AgentUsageActivityDay[]): AgentUsageActivityDay[] {
  const activeIndexes = days
    .map((day, index) => day.requests > 0 || day.total_tokens > 0 ? index : -1)
    .filter(index => index >= 0)
  if (!activeIndexes.length) return days
  let start = Math.max(0, activeIndexes[0]! - 4)
  let end = Math.min(days.length - 1, activeIndexes.at(-1)! + 2)
  if (end - start + 1 < 7) start = Math.max(0, end - 6)
  return days.slice(start, end + 1)
}

function chartGrid() {
  return {
    left: 44,
    right: 16,
    top: 18,
    bottom: 38,
    containLabel: false,
  }
}

function chartTooltip(valueFormatter: (value: number) => string) {
  return {
    trigger: 'axis' as const,
    valueFormatter: (value: unknown) => valueFormatter(Number(value)),
    backgroundColor: 'rgba(255,255,255,.98)',
    borderColor: 'rgba(66,91,75,.16)',
    borderWidth: 1,
    padding: [8, 10],
    textStyle: { color: '#3e4842', fontSize: 12 },
    axisPointer: {
      type: 'line' as const,
      lineStyle: { color: 'rgba(84,116,95,.44)', type: 'dashed' as const },
    },
  }
}

function requestTooltip() {
  return {
    ...chartTooltip(formatInteger),
    formatter: (params: unknown) => {
      const first = Array.isArray(params) ? params[0] : params
      const index = Number((first as { dataIndex?: number } | undefined)?.dataIndex ?? -1)
      const day = chartDays.value[index]
      if (!day) return ''
      return `<div style="font-weight:650;margin-bottom:.2rem">${day.date}</div><div style="color:#58665e">${formatInteger(day.requests)} requests</div>`
    },
  }
}

function chartXAxis(datesValue: string[], boundaryGap: boolean) {
  return {
    type: 'category' as const,
    data: datesValue,
    boundaryGap,
    axisLine: { lineStyle: { color: 'rgba(80,90,84,.3)' } },
    axisTick: { show: false },
    axisLabel: {
      color: '#68736d',
      fontSize: 12,
      fontWeight: 400,
      margin: 14,
      hideOverlap: true,
      formatter: (value: string) => formatDateLabel(value),
    },
  }
}

function chartYAxis(formatter: (value: number) => string) {
  return {
    type: 'value' as const,
    splitNumber: 2,
    axisLine: { show: false },
    axisTick: { show: false },
    axisLabel: {
      color: '#7d8781',
      fontSize: 10,
      fontWeight: 400,
      formatter: (value: number) => formatter(value),
    },
    splitLine: { lineStyle: { color: 'rgba(80,90,84,.25)' } },
  }
}

function formatInteger(value: number): string {
  return new Intl.NumberFormat('en-US').format(value)
}

function formatRequestTick(value: number): string {
  return Number.isInteger(value) ? formatInteger(value) : value.toFixed(1)
}

function formatDateLabel(value: string): string {
  const date = new Date(`${value}T00:00:00Z`)
  return `${date.getUTCMonth() + 1}/${date.getUTCDate()}`
}
</script>

<template>
  <section class="model-usage-trend">
    <header>
      <span class="model-usage-icon" aria-hidden="true">{{ modelIcon }}</span>
      <div><strong>{{ modelLabel }}</strong><small>{{ providerLabel }}</small></div>
    </header>
    <div class="model-trend-grid">
      <article class="model-trend-card">
        <div class="model-trend-heading"><strong>API requests</strong><span>{{ formatInteger(totalRequests) }}</span></div>
        <VChart class="model-trend-chart" :option="requestOption" autoresize />
      </article>
      <article class="model-trend-card">
        <div class="model-trend-heading"><strong>Tokens</strong><span>{{ formatInteger(totalTokens) }}</span></div>
        <VChart class="model-trend-chart" :option="tokenOption" autoresize />
      </article>
    </div>
  </section>
</template>

<style scoped>
.model-usage-trend { display: grid; gap: .75rem; }
.model-usage-trend > header { display: flex; align-items: center; gap: .58rem; }
.model-usage-icon { width: 2rem; height: 2rem; display: grid; place-items: center; border-radius: .58rem; color: #315b43; background: #e3eee7; font-size: .78rem; font-weight: 760; box-shadow: inset 0 0 0 1px rgba(59,96,75,.08); }
.model-usage-trend header strong, .model-usage-trend header small { display: block; }
.model-usage-trend header strong { color: #26332c; font-size: .82rem; }
.model-usage-trend header small { margin-top: .12rem; color: #87918b; font-size: .6rem; text-transform: capitalize; }
.model-trend-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: .8rem; }
.model-trend-card { min-width: 0; padding: .8rem .8rem .35rem; overflow: hidden; border: 1px solid rgba(35,45,39,.06); border-radius: .95rem; background: #f3f5f3; }
.model-trend-heading { display: flex; align-items: baseline; gap: .45rem; margin-bottom: .18rem; color: #3c4540; }
.model-trend-heading strong { font-size: .72rem; }
.model-trend-heading span { color: #59635d; font-size: .72rem; font-weight: 720; font-variant-numeric: tabular-nums; }
.model-trend-chart { width: 100%; height: 16rem; }
@media (max-width: 760px) {
  .model-trend-grid { grid-template-columns: 1fr; }
}
</style>
