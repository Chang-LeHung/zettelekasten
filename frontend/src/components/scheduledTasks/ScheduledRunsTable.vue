<script setup lang="ts">
import type { ScheduledTaskRun } from '../../api/types'
import { statusLabel, formatDate, duration, outputModel, outputSessionId } from '../../utils/scheduledTaskPresentation'

defineProps<{ runs: ScheduledTaskRun[]; runPage: number; runPageSize: number; runsHaveNext: boolean }>()
const emit = defineEmits<{ open: [run: ScheduledTaskRun]; openSession: [sessionId: string]; changePage: [page: number] }>()
</script>

<template>
  <div class="runs-table-wrap">
    <table class="runs-table">
      <thead>
        <tr>
          <th>Status</th>
          <th>Reason</th>
          <th>Scheduled</th>
          <th>Trigger</th>
          <th>Duration</th>
          <th>Model</th>
          <th>Session</th>
          <th><span class="sr-only">Actions</span></th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="run in runs"
          :key="run.id"
          class="run-table-row"
          tabindex="0"
          @click="emit('open', run)"
          @keydown.enter.prevent="emit('open', run)"
          @keydown.space.prevent="emit('open', run)"
        >
          <td data-label="Status">
            <span class="run-status" :class="run.status">{{ statusLabel(run.status) }}</span>
          </td>
          <td data-label="Reason" class="run-reason-cell">{{ run.error_type || '—' }}</td>
          <td data-label="Scheduled"><time>{{ formatDate(run.scheduled_for) }}</time></td>
          <td data-label="Trigger" class="run-trigger">{{ run.trigger_kind }}</td>
          <td data-label="Duration">{{ duration(run) }}</td>
          <td data-label="Model">{{ outputModel(run) || '—' }}</td>
          <td data-label="Session">
            <button
              v-if="outputSessionId(run)"
              class="run-session-button"
              type="button"
              :title="outputSessionId(run) || ''"
              @click.stop="emit('openSession', outputSessionId(run) || '')"
            >
              Open session
            </button>
            <span v-else class="table-muted">—</span>
          </td>
          <td data-label="Details"><button class="run-view-button" type="button" @click.stop="emit('open', run)">View</button></td>
        </tr>
      </tbody>
    </table>
    <footer class="runs-pagination">
      <span>{{ runPageSize }} runs per page</span>
      <div>
        <button type="button" :disabled="runPage <= 1" @click="emit('changePage', runPage - 1)">Previous</button>
        <button type="button" :disabled="!runsHaveNext" @click="emit('changePage', runPage + 1)">Next</button>
      </div>
    </footer>
  </div>
</template>

<style scoped>
.runs-table-wrap { min-width: 0; }
.runs-table { width: 100%; table-layout: auto; border-collapse: collapse; color: #465049; font-size: .67rem; }
.runs-table th { padding: .62rem .72rem; border-bottom: 1px solid rgba(29,29,31,.08); color: #7c857f; background: #f7f9f7; font-size: .6rem; font-weight: 720; letter-spacing: .04em; text-align: left; text-transform: uppercase; }
.runs-table td { padding: .72rem; border-bottom: 1px solid rgba(29,29,31,.065); vertical-align: top; }
.runs-table tbody tr { cursor: pointer; transition: background 130ms ease; }
.runs-table tbody tr:hover, .runs-table tbody tr:focus-visible { outline: none; background: #f6faf7; }
.runs-table tbody tr:last-child td { border-bottom: 0; }
.run-table-row time { color: #626c65; white-space: nowrap; }
.run-trigger { color: #7a837d; text-transform: capitalize; }
.run-reason-cell { max-width: 11rem; overflow: hidden; color: #8a5b5b; font-size: .62rem; text-overflow: ellipsis; white-space: nowrap; }
.table-muted { color: #a1a7a3; }
.run-view-button { min-height: 1.75rem; padding: 0 .55rem; border: 1px solid #dce4de; border-radius: .5rem; color: #496052; background: #fff; cursor: pointer; font-size: .6rem; font-weight: 680; }
.run-view-button:hover { background: #eef5f0; }
.runs-pagination { display: flex; align-items: center; justify-content: space-between; gap: 1rem; padding: .72rem .85rem; border-top: 1px solid rgba(29,29,31,.07); color: #89918c; font-size: .62rem; }
.runs-pagination > div { display: flex; gap: .4rem; }
.runs-pagination button { min-height: 1.9rem; padding: 0 .62rem; border: 1px solid #dce4de; border-radius: .52rem; color: #4b5c52; background: #fff; cursor: pointer; font-size: .62rem; font-weight: 650; }
.runs-pagination button:hover:not(:disabled) { background: #f1f6f3; }
.runs-pagination button:disabled { cursor: default; opacity: .45; }
.run-status { justify-self: start; padding: .22rem .48rem; border-radius: 999px; color: #3c6b4d; background: #e9f4ed; font-size: .62rem; font-weight: 700; }
.run-status.failed, .run-status.interrupted { color: #984646; background: #faeceb; }
.run-status.pending, .run-status.running { color: #786126; background: #f7f0d9; }
.run-status.skipped, .run-status.cancelled { color: #6d7270; background: #eeeeec; }
.run-session-button { min-height: 1.75rem; padding: 0 .58rem; border: 1px solid #cedbd2; border-radius: .52rem; color: #3f6850; background: #f7fbf8; cursor: pointer; font-size: .62rem; font-weight: 680; white-space: nowrap; }
.run-session-button:hover { background: #eaf4ed; }
.sr-only { position: absolute; width: 1px; height: 1px; padding: 0; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0; }
@media (max-width: 1080px) {
  .runs-table thead { display: none; }
  .runs-table, .runs-table tbody, .runs-table tr, .runs-table td { display: block; width: 100%; }
  .runs-table tbody { display: grid; gap: .7rem; padding: .75rem; background: #f7f9f7; }
  .runs-table tr { padding: .72rem .8rem; border: 1px solid rgba(29,29,31,.075); border-radius: .72rem; background: #fff; box-shadow: 0 1px 3px rgba(25,34,29,.025); }
  .runs-table td { display: grid; grid-template-columns: 6.5rem minmax(0, 1fr); gap: .65rem; align-items: start; max-width: none; padding: .42rem 0; border: 0; }
  .runs-table td::before { color: #909792; content: attr(data-label); font-size: .58rem; font-weight: 720; letter-spacing: .04em; text-transform: uppercase; }
  .runs-table td:last-child { display: flex; align-items: center; justify-content: space-between; padding-top: .55rem; }
  .runs-pagination { background: #fff; }
}
</style>
