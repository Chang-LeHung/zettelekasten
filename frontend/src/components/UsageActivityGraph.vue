<script setup lang="ts">
import { computed, ref } from 'vue'
import type { AgentUsageActivityDay } from '../api/types'
import { calculateCacheHitRate, formatTokenCount } from '../utils/agentUsage'
import { useI18n } from '../i18n'

const props = defineProps<{
  days: AgentUsageActivityDay[]
}>()

const { locale, t } = useI18n()
const graphRoot = ref<HTMLElement | null>(null)
const hoveredCell = ref<DayCell | null>(null)
const tooltipPosition = ref({ left: 0, top: 0 })

interface DayCell {
  date: string
  requests: number
  inputTokens: number
  outputTokens: number
  cacheReadTokens: number
  cacheWriteTokens: number
  reasoningTokens: number
  cacheHitRate: number | null
  totalTokens: number
  level: number
}

const cells = computed<Array<DayCell | null>>(() => {
  if (!props.days.length) return []
  const first = new Date(`${props.days[0]!.date}T00:00:00Z`)
  const padding = Array.from({ length: first.getUTCDay() }, () => null as DayCell | null)
  const maxTokens = Math.max(...props.days.map(day => day.total_tokens), 0)
  return [
    ...padding,
    ...props.days.map((day) => ({
      date: day.date,
      requests: day.requests,
      inputTokens: day.input_tokens,
      outputTokens: day.output_tokens,
      cacheReadTokens: day.cache_read_tokens,
      cacheWriteTokens: day.cache_write_tokens,
      reasoningTokens: day.reasoning_tokens,
      cacheHitRate: calculateCacheHitRate(day),
      totalTokens: day.total_tokens,
      level: activityLevel(day.total_tokens, maxTokens),
    })),
  ]
})

const weeks = computed(() => {
  const rows: Array<Array<DayCell | null>> = []
  for (let index = 0; index < cells.value.length; index += 7) {
    const week = cells.value.slice(index, index + 7)
    // The final week is usually incomplete. Empty slots must still occupy
    // rows, otherwise CSS Grid stretches its few populated days vertically.
    rows.push([...week, ...Array.from({ length: 7 - week.length }, () => null)])
  }
  return rows
})

const monthLabels = computed(() => {
  let previousMonth = ''
  return weeks.value.map((week) => {
    const first = week.find((cell): cell is DayCell => cell !== null)
    if (!first) return ''
    const month = first.date.slice(0, 7)
    if (month === previousMonth) return ''
    previousMonth = month
    return new Intl.DateTimeFormat(locale.value === 'zh' ? 'zh-CN' : 'en-US', { month: 'short', timeZone: 'UTC' })
      .format(new Date(`${first.date}T00:00:00Z`))
  })
})

const totalTokens = computed(() => props.days.reduce((total, day) => total + day.total_tokens, 0))
const totalRequests = computed(() => props.days.reduce((total, day) => total + day.requests, 0))
const activeDays = computed(() => props.days.filter(day => day.requests > 0).length)

function activityLevel(tokens: number, maximum: number): number {
  if (tokens <= 0 || maximum <= 0) return 0
  const ratio = tokens / maximum
  if (ratio <= 0.2) return 1
  if (ratio <= 0.45) return 2
  if (ratio <= 0.75) return 3
  return 4
}

function displayDate(value: string): string {
  return new Intl.DateTimeFormat(locale.value === 'zh' ? 'zh-CN' : 'en-US', {
    weekday: 'short',
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    timeZone: 'UTC',
  }).format(new Date(`${value}T00:00:00Z`))
}

function formatCacheHitRatePercent(rate: number): string {
  return `${(rate * 100).toFixed(2)}%`
}

function showTooltip(cell: DayCell | null, event: MouseEvent): void {
  if (!cell || !graphRoot.value) return
  const root = graphRoot.value.getBoundingClientRect()
  const target = (event.currentTarget as HTMLElement).getBoundingClientRect()
  hoveredCell.value = cell
  tooltipPosition.value = {
    left: target.left - root.left + target.width / 2,
    top: target.top - root.top,
  }
}

function hideTooltip(): void {
  hoveredCell.value = null
}
</script>

<template>
  <section ref="graphRoot" class="usage-activity">
    <header>
      <div>
        <strong>{{ t('Last 12 months') }}</strong>
        <small>{{ activeDays === 1 ? t('{count} requests · {days} active day', { count: totalRequests, days: activeDays }) : t('{count} requests · {days} active days', { count: totalRequests, days: activeDays }) }}</small>
      </div>
      <span>{{ t('{count} tokens', { count: formatTokenCount(totalTokens) }) }}</span>
    </header>
    <div class="activity-calendar">
      <div class="activity-months" :style="{ gridTemplateColumns: `repeat(${weeks.length}, minmax(0, 1fr))` }" aria-hidden="true">
        <span v-for="(month, index) in monthLabels" :key="`${month}-${index}`" class="activity-month">
          <span v-if="month" class="month-full">{{ month }}</span>
          <span v-if="month" class="month-short">{{ month.slice(0, 1) }}</span>
        </span>
      </div>
      <div class="activity-grid" :style="{ gridTemplateColumns: `repeat(${weeks.length}, minmax(0, 1fr))` }" :aria-label="t('Daily model token activity')">
        <div v-for="(week, weekIndex) in weeks" :key="weekIndex" class="activity-week">
          <span
            v-for="(cell, dayIndex) in week"
            :key="cell?.date || `${weekIndex}-${dayIndex}`"
            class="activity-cell"
            :class="cell ? `level-${cell.level}` : 'empty'"
            @mouseenter="showTooltip(cell, $event)"
            @mouseleave="hideTooltip"
          />
        </div>
      </div>
    </div>
    <footer>
      <span>{{ t('Less') }}</span>
      <i class="level-0" />
      <i class="level-1" />
      <i class="level-2" />
      <i class="level-3" />
      <i class="level-4" />
      <span>{{ t('More') }}</span>
    </footer>
    <div
      v-if="hoveredCell"
      class="activity-tooltip"
      :style="{ left: `${tooltipPosition.left}px`, top: `${tooltipPosition.top}px` }"
      role="tooltip"
    >
      <strong>{{ displayDate(hoveredCell.date) }}</strong>
      <span>{{ hoveredCell.requests }} {{ hoveredCell.requests === 1 ? t('request') : t('requests') }}</span>
      <dl>
        <div><dt>{{ t('Input') }}</dt><dd>{{ formatTokenCount(hoveredCell.inputTokens) }}</dd></div>
        <div><dt>{{ t('Output') }}</dt><dd>{{ formatTokenCount(hoveredCell.outputTokens) }}</dd></div>
        <div><dt>{{ t('Total') }}</dt><dd>{{ formatTokenCount(hoveredCell.totalTokens) }}</dd></div>
        <div><dt>{{ t('Cache read') }}</dt><dd>{{ formatTokenCount(hoveredCell.cacheReadTokens) }}</dd></div>
        <div><dt>{{ t('Cache hit rate') }}</dt><dd>{{ hoveredCell.cacheHitRate === null ? '—' : formatCacheHitRatePercent(hoveredCell.cacheHitRate) }}</dd></div>
        <div><dt>{{ t('Cache write') }}</dt><dd>{{ formatTokenCount(hoveredCell.cacheWriteTokens) }}</dd></div>
        <div><dt>{{ t('Reasoning') }}</dt><dd>{{ formatTokenCount(hoveredCell.reasoningTokens) }}</dd></div>
      </dl>
    </div>
  </section>
</template>

<style scoped>
.usage-activity { --activity-gap: clamp(1px, .2vw, .2rem); position: relative; display: grid; gap: .9rem; min-width: 0; container-type: inline-size; }
.usage-activity > header { display: flex; align-items: flex-start; justify-content: space-between; gap: 1rem; }
.usage-activity > header strong, .usage-activity > header small { display: block; }
.usage-activity > header strong { color: #3c4740; font-size: .86rem; }
.usage-activity > header small { margin-top: .16rem; color: #828c86; font-size: .64rem; }
.usage-activity > header > span { color: #496353; font-size: .74rem; font-weight: 700; font-variant-numeric: tabular-nums; }
.activity-calendar { min-width: 0; width: 100%; }
.activity-grid { display: grid; gap: var(--activity-gap); width: 100%; min-width: 0; }
.activity-months { height: 1rem; display: grid; gap: var(--activity-gap); width: 100%; min-width: 0; margin-bottom: .02rem; }
.activity-month { position: relative; min-width: 0; }
.activity-month > span { position: absolute; left: 0; bottom: .2rem; color: #68756d; font-size: .58rem; font-weight: 640; line-height: 1; white-space: nowrap; }
.activity-month .month-short { display: none; }
.activity-week { min-width: 0; display: grid; grid-template-rows: repeat(7, minmax(0, 1fr)); gap: var(--activity-gap); }
.activity-cell { width: 100%; height: auto; aspect-ratio: 1; border-radius: clamp(1px, .18vw, .2rem); background: #edf0ee; }
.activity-cell.empty { visibility: hidden; }
.activity-cell.level-0, .usage-activity footer .level-0 { background: #edf0ee; }
.activity-cell.level-1, .usage-activity footer .level-1 { background: #cce5d5; }
.activity-cell.level-2, .usage-activity footer .level-2 { background: #94c9a7; }
.activity-cell.level-3, .usage-activity footer .level-3 { background: #4d9870; }
.activity-cell.level-4, .usage-activity footer .level-4 { background: #236041; }
.usage-activity footer { display: flex; align-items: center; justify-content: flex-end; gap: .24rem; color: #8a948e; font-size: .59rem; }
.usage-activity footer i { width: .68rem; height: .68rem; border-radius: .18rem; }
.activity-tooltip { position: absolute; z-index: 20; width: 12rem; display: grid; gap: .28rem; padding: .55rem .62rem; border: 1px solid rgba(255,255,255,.12); border-radius: .55rem; color: #f7faf8; background: #26332c; box-shadow: 0 10px 28px rgba(24,35,29,.2); pointer-events: none; transform: translate(-50%, calc(-100% - .42rem)); }
.activity-tooltip::after { content: ""; position: absolute; left: 50%; bottom: -.28rem; width: .48rem; height: .48rem; background: #26332c; transform: translateX(-50%) rotate(45deg); }
.activity-tooltip strong { font-size: .61rem; }
.activity-tooltip > span { color: #bdc9c1; font-size: .53rem; }
.activity-tooltip dl { display: grid; gap: .16rem; margin: .08rem 0 0; }
.activity-tooltip dl > div { display: flex; align-items: center; justify-content: space-between; gap: .6rem; }
.activity-tooltip dt { color: #b8c5bd; font-size: .51rem; font-weight: 500; }
.activity-tooltip dd { margin: 0; color: #fff; font-size: .54rem; font-weight: 680; font-variant-numeric: tabular-nums; }
@container (max-width: 42rem) {
  .activity-month .month-full { display: none; }
  .activity-month .month-short { display: inline; }
}
</style>
