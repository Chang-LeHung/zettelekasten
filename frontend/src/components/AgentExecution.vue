<script setup lang="ts">
import type { AgentTimelineEntry } from '../api/types'
import { serverToolView } from '../utils/toolPresentation'
import { toolSummary } from '../utils/toolSummary'
import { editArguments, editDiffRows, type EditDiffRow } from '../utils/editDiff'
import type { AgentToolActivity } from '../api/types'
import ToolResult from './ToolResult.vue'

/** One block of diff rows per before/after pair of an `edit` call; empty for any other tool. */
function editChanges(activity: AgentToolActivity): EditDiffRow[][] {
  if (activity.name !== 'edit') return []
  return editArguments(activity.arguments).map((change) => editDiffRows(change.before, change.after))
}

function formatDuration(ms: number): string {
  return ms < 1000 ? `${Math.round(ms)} ms` : `${(ms / 1000).toFixed(ms < 10000 ? 1 : 0)} s`
}

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
            <summary :title="toolSummary(entry.activity.name, entry.activity.arguments).target || undefined">
              <template v-for="view in [toolSummary(entry.activity.name, entry.activity.arguments)]" :key="'summary'">
                <i />
                <span class="tool-label">{{ view.label }}</span>
                <span v-if="view.target" class="tool-target" :class="`tool-target-${view.kind}`">
                  <span class="tool-target-name">{{ view.target }}</span>
                  <span v-if="view.context" class="tool-target-context">{{ view.context }}</span>
                </span>
                <small v-if="view.meta" class="tool-meta">{{ view.meta }}</small>
                <small class="tool-time">{{ entry.activity.duration_ms ? formatDuration(entry.activity.duration_ms) : '' }}</small>
              </template>
            </summary>
            <div class="tool-activity-details">
              <template v-if="editChanges(entry.activity).length">
                <div v-for="(rows, blockIndex) in editChanges(entry.activity)" :key="blockIndex" class="edit-diff-block">
                  <strong>{{ editChanges(entry.activity).length > 1 ? `Change ${blockIndex + 1} of ${editChanges(entry.activity).length}` : 'Changes' }}</strong>
                  <div class="edit-diff" role="group" aria-label="Edit diff">
                    <div v-for="(row, rowIndex) in rows" :key="rowIndex" class="edit-diff-row" :class="row.kind">
                      <span class="edit-diff-mark" aria-hidden="true">{{ row.kind === 'added' ? '+' : row.kind === 'removed' ? '−' : '' }}</span>
                      <code><template v-for="(segment, segmentIndex) in row.segments" :key="segmentIndex"><mark v-if="segment.strong">{{ segment.text }}</mark><template v-else>{{ segment.text }}</template></template></code>
                    </div>
                  </div>
                </div>
                <details class="edit-raw"><summary>Arguments</summary><pre>{{ formatToolValue(entry.activity.arguments || {}) }}</pre></details>
              </template>
              <div v-else><strong>Arguments</strong><pre>{{ formatToolValue(entry.activity.arguments || {}) }}</pre></div>
              <div><strong>{{ entry.activity.error_message ? 'Error' : 'Result' }}</strong><ToolResult :output="entry.activity.output" :error="entry.activity.error_message" @preview-image="emit('previewImage', $event)" /></div>
            </div>
          </details>
          <details v-else-if="entry.type === 'server_tool'" class="tool-activity server-tool-activity" :class="entry.activity.state">
            <template v-for="view in [serverToolView(entry.activity.name, entry.activity.output, entry.activity.error_code)]" :key="'view'">
              <summary>
                <i />
                <span>{{ view.label }}</span>
                <small v-if="view.summary" class="server-tool-summary">{{ view.summary }}</small>
                <small v-else>Provider tool · {{ entry.activity.state }}</small>
              </summary>
              <div class="tool-activity-details">
                <div v-if="entry.activity.input !== null || entry.activity.input_delta"><strong>Input</strong><pre>{{ entry.activity.input_delta || formatToolValue(entry.activity.input) }}</pre></div>
                <div v-if="view.pages.length">
                  <strong>Sources</strong>
                  <ul class="server-tool-pages">
                    <li v-for="page in view.pages" :key="page.url">
                      <a :href="page.url" target="_blank" rel="noreferrer noopener">{{ page.title || page.url }}</a>
                      <small v-if="page.title">{{ page.url }}</small>
                    </li>
                  </ul>
                </div>
                <div v-if="view.text"><strong>Result</strong><pre>{{ view.text }}</pre></div>
                <div v-if="view.error"><strong>Error</strong><pre class="error">{{ view.error }}</pre></div>
              </div>
            </template>
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
.running .turn-execution-copy strong { color: #355b45; }.turn-execution-copy small { color: #929995; font-size: .56rem; font-variant-numeric: tabular-nums; }
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
.tool-activity summary .tool-label { flex: 0 0 auto; color: #3f4a43; font-weight: 630; }
.tool-activity.failed summary .tool-label { color: #914d4d; }
.tool-target { min-width: 0; display: inline-flex; align-items: baseline; gap: .38rem; padding: .1rem .42rem; border-radius: .38rem; background: #f1f4f2; text-transform: none; }
.tool-target-name { min-width: 0; overflow: hidden; color: #36413a; text-overflow: ellipsis; white-space: nowrap; }
.tool-target-file .tool-target-name, .tool-target-command .tool-target-name { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; font-size: .6rem; }
.tool-target-context { flex: 0 1 auto; min-width: 0; overflow: hidden; color: #98a19b; font-size: .54rem; text-overflow: ellipsis; white-space: nowrap; }
.tool-activity summary small.tool-meta { margin-left: 0; flex: 0 0 auto; color: #7c8780; font-variant-numeric: tabular-nums; }
.tool-activity summary small.tool-time { flex: 0 0 auto; font-variant-numeric: tabular-nums; }
.tool-activity summary .tool-target + small.tool-time, .tool-activity summary .tool-label + small.tool-time { margin-left: auto; }
.tool-activity summary .tool-target { margin-right: auto; }
.tool-activity summary .tool-target ~ small.tool-time { margin-left: 0; }
.tool-activity-details { display: grid; gap: .55rem; margin: .08rem 0 .55rem; padding: .2rem 0 .12rem; }
.tool-activity-details strong { display: block; margin-bottom: .28rem; color: #78827c; font-size: .56rem; letter-spacing: .055em; text-transform: uppercase; }
.tool-activity-details pre { max-height: 11rem; margin: 0; padding: .32rem 0; overflow: auto; border: 0; color: #465049; background: transparent; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; font-size: .62rem; line-height: 1.48; text-transform: none; white-space: pre-wrap; overflow-wrap: anywhere; }
.edit-diff { max-height: 18rem; overflow: auto; border: 1px solid #e3e8e5; border-radius: .5rem; background: #fff; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; font-size: .62rem; line-height: 1.5; text-transform: none; }
.edit-diff-row { display: grid; grid-template-columns: 1.3rem minmax(0, 1fr); min-width: max-content; width: 100%; color: #5b665f; }
.edit-diff-row code { padding: 0 .5rem 0 0; font: inherit; white-space: pre; }
.edit-diff-mark { text-align: center; color: #98a19b; user-select: none; }
.edit-diff-row.added { background: #eef8f0; color: #24452f; }
.edit-diff-row.removed { background: #fbefef; color: #5b2b2b; }
.edit-diff-row.added .edit-diff-mark { color: #3d8a59; }
.edit-diff-row.removed .edit-diff-mark { color: #b05050; }
.edit-diff-row mark { padding: 0 .08rem; border-radius: .18rem; color: inherit; }
.edit-diff-row.added mark { background: #a8dcb7; }
.edit-diff-row.removed mark { background: #efb3b3; }
.edit-diff-block + .edit-diff-block { margin-top: .1rem; }
.edit-raw { margin-top: .1rem; }
.edit-raw > summary { min-height: 0; padding: .1rem 0; color: #78827c; font-size: .56rem; letter-spacing: .055em; text-transform: uppercase; }
.tool-activity-details pre.error { color: #8d4040; }
.tool-activity summary small.server-tool-summary { max-width: 60%; margin-left: auto; overflow: hidden; color: #6f7a73; text-overflow: ellipsis; white-space: nowrap; text-transform: none; }
.server-tool-pages { display: grid; gap: .28rem; margin: 0; padding: 0; list-style: none; }
.server-tool-pages li { display: grid; gap: .08rem; padding-left: .7rem; position: relative; }
.server-tool-pages li::before { content: '·'; position: absolute; left: .18rem; color: #92a099; }
.server-tool-pages a { overflow: hidden; color: #355b45; font-size: .64rem; text-decoration: none; text-overflow: ellipsis; white-space: nowrap; }
.server-tool-pages a:hover { text-decoration: underline; }
.server-tool-pages small { overflow: hidden; color: var(--tertiary); font-size: .56rem; text-overflow: ellipsis; white-space: nowrap; }
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
