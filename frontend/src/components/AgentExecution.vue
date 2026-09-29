<script setup lang="ts">
import type { AgentTimelineEntry } from '../api/types'
import ToolResult from './ToolResult.vue'

defineProps<{
  timeline: readonly AgentTimelineEntry[]
  running: boolean
  open: boolean
  task: string
  duration: string
}>()
const emit = defineEmits<{
  toggle: [event: MouseEvent]
  previewImage: [image: { name: string; url: string }]
}>()

function formatToolValue(value: unknown): string {
  if (value === undefined) return 'Waiting for result…'
  if (typeof value === 'string') return value
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}
</script>

<template>
  <!-- Shared by the web conversation and the Chrome panel. Markdown is a slot
       so each host keeps its renderer without duplicating execution UI. -->
  <details class="turn-execution" :class="{ running }" :open="open">
    <summary @click="emit('toggle', $event)">
      <span class="turn-state-icon" aria-hidden="true"><i /></span>
      <span class="turn-execution-copy">
        <strong>{{ running ? task : `Processed in ${duration}` }}</strong>
        <small>{{ running ? `Running · ${duration}` : 'Show thinking, tools, and task details' }}</small>
      </span>
      <span class="turn-execution-metrics"><slot name="metrics" /></span>
      <span class="turn-chevron" aria-hidden="true">›</span>
    </summary>
    <div class="turn-execution-details">
      <slot name="tasks" />
      <div v-if="timeline.length" class="agent-event-timeline">
        <template v-for="entry in timeline" :key="entry.id">
          <details v-if="entry.type === 'reasoning'" class="reasoning-panel" :class="{ 'streaming-reasoning': running }">
            <summary><i aria-hidden="true" /><span>Thinking</span><small>{{ running ? 'Live' : 'Completed' }}</small></summary>
            <div class="reasoning-content"><slot name="markdown" :content="entry.content" /></div>
          </details>
          <div v-else-if="entry.type === 'message'" class="intermediate-response">
            <slot name="markdown" :content="entry.content" />
          </div>
          <details v-else-if="entry.type === 'compaction'" class="reasoning-panel compaction-panel">
            <summary><span>Context compaction</span><small>{{ entry.activity.state }}</small></summary>
            <div class="compaction-content">
              <div v-if="entry.activity.reasoning" class="reasoning-content"><slot name="markdown" :content="entry.activity.reasoning" /></div>
              <div v-if="entry.activity.content" class="reasoning-content"><slot name="markdown" :content="entry.activity.content" /></div>
              <small v-if="entry.activity.compressed_from">Compressed {{ entry.activity.compressed_from }}–{{ entry.activity.compressed_to }} · kept {{ entry.activity.kept_from }}–{{ entry.activity.kept_to }}</small>
            </div>
          </details>
          <details v-else-if="entry.type === 'tool'" class="tool-activity" :class="entry.activity.state">
            <summary><i /><span>{{ entry.activity.name.replaceAll('_', ' ') }}</span><small v-if="entry.activity.duration_ms">{{ Math.round(entry.activity.duration_ms) }} ms</small></summary>
            <div class="tool-activity-details">
              <div><strong>Arguments</strong><pre>{{ formatToolValue(entry.activity.arguments || {}) }}</pre></div>
              <div><strong>{{ entry.activity.error_message ? 'Error' : 'Result' }}</strong><ToolResult :output="entry.activity.output" :error="entry.activity.error_message" @preview-image="emit('previewImage', $event)" /></div>
            </div>
          </details>
          <details v-else-if="entry.type === 'server_tool'" class="tool-activity server-tool-activity" :class="entry.activity.state">
            <summary><i /><span>{{ entry.activity.name.replaceAll('_', ' ') }}</span><small>Provider tool · {{ entry.activity.state }}</small></summary>
            <div class="tool-activity-details">
              <div><strong>Input</strong><pre>{{ entry.activity.input_delta || (entry.activity.input === null ? 'Waiting for streamed input…' : formatToolValue(entry.activity.input)) }}</pre></div>
              <div v-if="entry.activity.output !== undefined || entry.activity.error_code"><strong>{{ entry.activity.error_code ? 'Error' : 'Result' }}</strong><pre :class="{ error: entry.activity.error_code }">{{ entry.activity.error_code || formatToolValue(entry.activity.output) }}</pre></div>
            </div>
          </details>
        </template>
      </div>
      <p v-else-if="running" class="turn-empty-detail">Waiting for execution details…</p>
    </div>
  </details>
</template>

<style scoped>
.turn-execution { min-width: 0; margin-right: 7%; }
.turn-execution > summary { min-height: 3.1rem; display: grid; grid-template-columns: auto minmax(0,1fr) auto auto; align-items: center; gap: .62rem; padding: .55rem .1rem; border-bottom: 1px solid #e7ebe8; cursor: pointer; list-style: none; user-select: none; }
.turn-execution > summary::-webkit-details-marker { display: none; }
.turn-state-icon { width: 1.55rem; height: 1.55rem; display: grid; place-items: center; border: 1px solid #d9e1dc; border-radius: 50%; background: #f5f8f6; }
.turn-state-icon i { width: .43rem; height: .43rem; border-radius: 50%; background: #72907d; }
.running .turn-state-icon { border-color: #b8ccbf; background: #edf4ef; box-shadow: 0 0 0 .22rem rgba(96,139,112,.07); }
.running .turn-state-icon i { animation: activity-pulse 1.15s ease-in-out infinite; }
.turn-execution-copy { min-width: 0; display: grid; gap: .16rem; }
.turn-execution-copy strong { overflow: hidden; color: #59635d; font-size: .68rem; font-weight: 620; text-overflow: ellipsis; white-space: nowrap; }
.running .turn-execution-copy strong { color: #355b45; }
.turn-execution-copy small { color: #929995; font-size: .56rem; font-variant-numeric: tabular-nums; }
.turn-execution-metrics { min-width: 0; display: flex; align-items: center; justify-content: flex-end; }
.turn-chevron { color: #8e9892; font-size: 1.05rem; line-height: 1; transition: transform 160ms ease; }
.turn-execution[open] > summary .turn-chevron { transform: rotate(90deg); }
.turn-execution-details { display: grid; gap: .28rem; padding: .48rem 0 .2rem; animation: turn-reveal 160ms ease-out; }
.turn-empty-detail { margin: 0; color: #979e99; font-size: .62rem; }
.agent-event-timeline { width: 100%; min-width: 0; display: grid; gap: .12rem; }
.agent-event-timeline > .reasoning-panel, .agent-event-timeline > .tool-activity { margin: 0; }
.intermediate-response { margin: .18rem 0 .3rem; padding: .12rem 0; color: #4f5b54; font-size: .68rem; line-height: 1.58; }
.tool-activity { min-width: 0; color: #657068; font-size: .64rem; }
.tool-activity summary { display: flex; align-items: center; gap: .42rem; min-height: 1.7rem; padding: .12rem .08rem; cursor: pointer; list-style: none; text-transform: capitalize; user-select: none; }
.tool-activity summary::-webkit-details-marker { display: none; }
.tool-activity summary::after { content: '›'; margin-left: .12rem; color: #8b948f; font-size: .82rem; transition: transform 150ms ease; }
.tool-activity[open] summary::after { transform: rotate(90deg); }
.tool-activity summary i { width: .38rem; height: .38rem; flex: 0 0 auto; border-radius: 50%; background: #d59b45; animation: activity-pulse 1.1s ease-in-out infinite; }
.tool-activity.succeeded summary i { background: #4b9867; animation: none; }
.tool-activity.failed { color: #914d4d; }
.tool-activity.failed summary i { background: #bd5656; animation: none; }
.tool-activity.cancelled summary i { background: #929995; animation: none; }
.tool-activity summary small { margin-left: auto; color: var(--tertiary); font-size: .58rem; text-transform: none; }
.tool-activity-details { display: grid; gap: .55rem; margin: .08rem 0 .55rem; padding: .2rem 0 .12rem; }
.tool-activity-details strong { display: block; margin-bottom: .28rem; color: #78827c; font-size: .56rem; letter-spacing: .055em; text-transform: uppercase; }
.tool-activity-details pre { max-height: 11rem; margin: 0; padding: .32rem 0; overflow: auto; border: 0; color: #465049; background: transparent; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; font-size: .62rem; line-height: 1.48; text-transform: none; white-space: pre-wrap; overflow-wrap: anywhere; }
.tool-activity-details pre.error { color: #8d4040; }
.reasoning-panel { width: 100%; min-width: 0; margin: 0; color: #5d6961; background: transparent; }
.reasoning-panel summary { display: flex; align-items: center; gap: .42rem; min-height: 1.7rem; padding: .12rem .08rem; cursor: pointer; list-style: none; font-size: .68rem; font-weight: 630; user-select: none; }
.reasoning-panel summary::-webkit-details-marker { display: none; }
.reasoning-panel summary::after { content: '›'; margin-left: .12rem; color: #8b948f; font-size: .82rem; transition: transform 150ms ease; }
.reasoning-panel[open] summary::after { transform: rotate(90deg); }
.reasoning-panel summary > i { width: .38rem; height: .38rem; flex: 0 0 auto; border-radius: 50%; background: #789383; }
.reasoning-panel summary small { margin-left: auto; color: var(--tertiary); font-size: .58rem; font-weight: 500; }
.streaming-reasoning > summary { color: #466554; }
.streaming-reasoning > summary > i { animation: activity-pulse 1.1s ease-in-out infinite; }
.reasoning-content { max-height: 14rem; margin: .08rem 0 .55rem; padding: .25rem 0; overflow: auto; color: #657068; font-size: .68rem; line-height: 1.58; }
.compaction-panel { color: #6d658b; }
.compaction-content > small { display: block; padding: .32rem 0 .45rem; color: var(--tertiary); font-size: .61rem; }
@keyframes activity-pulse { 50% { opacity: .4; } }
@keyframes turn-reveal { from { opacity: 0; transform: translateY(-3px); } to { opacity: 1; transform: translateY(0); } }
@media (prefers-reduced-motion: reduce) {
  *, *::after { animation: none !important; transition: none !important; }
}
</style>
