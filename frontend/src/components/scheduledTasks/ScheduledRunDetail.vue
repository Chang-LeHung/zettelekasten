<script setup lang="ts">
import type { ScheduledTaskRun } from '../../api/types'
import { statusLabel, formatDate, duration, outputModel, outputProvider, outputSessionId, rawOutput, runPreview, shortId } from '../../utils/scheduledTaskPresentation'

defineProps<{ open: boolean; run: ScheduledTaskRun | null; taskName?: string }>()
const emit = defineEmits<{ close: []; openSession: [sessionId: string] }>()
</script>

<template>
  <Teleport to="body">
    <Transition name="scheduled-dialog">
      <div v-if="open && run" class="scheduled-modal-backdrop" @click.self="emit('close')" @keydown.esc.stop.prevent="emit('close')">
        <section class="scheduled-modal run-detail-modal" role="dialog" aria-modal="true" aria-labelledby="run-detail-title">
          <header class="scheduled-modal-header">
            <div>
              <span>Execution detail</span>
              <div class="run-detail-heading">
                <span class="run-status" :class="run.status">{{ statusLabel(run.status) }}</span>
                <h2 id="run-detail-title">{{ taskName || 'Scheduled run' }}</h2>
              </div>
              <p>{{ shortId(run.id) }} · {{ formatDate(run.scheduled_for) }}</p>
            </div>
            <button class="scheduled-modal-close" type="button" aria-label="Close" @click="emit('close')">×</button>
          </header>

          <div class="run-detail-body">
            <div v-if="run.error_message" class="run-error" role="alert">
              <strong>{{ run.error_type || 'Execution failed' }}</strong>
              <p>{{ run.error_message }}</p>
            </div>

            <dl class="run-detail-grid">
              <div><dt>Trigger</dt><dd>{{ run.trigger_kind }}</dd></div>
              <div><dt>Duration</dt><dd>{{ duration(run) }}</dd></div>
              <div><dt>Started</dt><dd>{{ formatDate(run.started_at) }}</dd></div>
              <div><dt>Completed</dt><dd>{{ formatDate(run.completed_at) }}</dd></div>
              <div><dt>Model</dt><dd>{{ outputModel(run) || '—' }}</dd></div>
              <div><dt>Provider</dt><dd :title="outputProvider(run) || ''">{{ outputProvider(run) ? shortId(outputProvider(run) || '') : '—' }}</dd></div>
            </dl>

            <section class="run-detail-section">
              <h3>Preview</h3>
              <p class="run-preview">{{ runPreview(run) }}</p>
            </section>

            <section class="run-detail-section">
              <h3>Output</h3>
              <pre v-if="rawOutput(run)" class="run-output-block">{{ rawOutput(run) }}</pre>
              <p v-else class="run-output-empty">No output was produced for this run.</p>
            </section>
          </div>

          <footer class="scheduled-create-footer run-detail-footer">
            <button class="secondary-action" type="button" @click="emit('close')">Close</button>
            <button
              v-if="outputSessionId(run)"
              class="primary-action"
              type="button"
              @click="emit('openSession', outputSessionId(run) || '')"
            >
              Open session
            </button>
          </footer>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.scheduled-topbar-actions .secondary-action { min-height: 2.45rem; }
.run-status { justify-self: start; padding: .22rem .48rem; border-radius: 999px; color: #3c6b4d; background: #e9f4ed; font-size: .62rem; font-weight: 700; }
.run-status.failed, .run-status.interrupted { color: #984646; background: #faeceb; }
.run-status.pending, .run-status.running { color: #786126; background: #f7f0d9; }
.run-status.skipped, .run-status.cancelled { color: #6d7270; background: #eeeeec; }
.run-preview { max-height: 13rem; margin: 0; padding: .75rem .85rem; overflow: auto; border-left: 3px solid #8caf99; border-radius: .2rem .58rem .58rem .2rem; color: #3e4842; background: #f7faf8; font: inherit; font-size: .69rem; line-height: 1.55; white-space: pre-wrap; }
.run-error { padding: .7rem .8rem; border: 1px solid #efd7d5; border-radius: .6rem; color: #8f4141; background: #fff8f7; }
.run-error strong { display: block; font-size: .68rem; }
.run-error p { margin: .28rem 0 0; font-size: .66rem; line-height: 1.5; white-space: pre-wrap; }
.scheduled-modal-backdrop { position: fixed; inset: 0; z-index: 1000; display: grid; place-items: center; padding: 1.25rem; background: rgba(27,35,30,.28); backdrop-filter: blur(12px) saturate(115%); }
.scheduled-modal { width: min(100%, 42rem); max-height: min(48rem, calc(100vh - 2rem)); overflow-y: auto; border: 1px solid rgba(38,52,43,.14); border-radius: 1rem; background: #fff; box-shadow: 0 28px 80px rgba(28,39,32,.22); }
.scheduled-modal-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 1rem; padding: 1.25rem 1.35rem 1rem; border-bottom: 1px solid rgba(29,29,31,.07); }
.scheduled-modal-header span { color: #557662; font-size: .61rem; font-weight: 750; letter-spacing: .09em; text-transform: uppercase; }
.scheduled-modal-header h2 { margin: .25rem 0 .24rem; color: #2d342f; font-size: 1.2rem; }
.scheduled-modal-header p { margin: 0; color: #858d88; font-size: .7rem; }
.scheduled-modal-close { width: 2rem; height: 2rem; flex: 0 0 auto; border: 1px solid #e1e6e2; border-radius: .62rem; color: #69726c; background: #f8f9f8; cursor: pointer; font-size: 1.2rem; line-height: 1; }
.scheduled-modal-close:hover { color: #35453b; background: #f0f4f1; }
.run-detail-modal { width: min(100%, 58rem); }
.run-detail-heading { display: flex; align-items: center; gap: .55rem; margin-top: .3rem; }
.run-detail-heading h2 { margin: 0; }
.run-detail-body { display: grid; gap: .9rem; padding: 1rem 1.2rem; }
.run-detail-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: .75rem; margin: 0; }
.run-detail-grid div { min-width: 0; padding: .62rem .7rem; border: 1px solid rgba(29,29,31,.07); border-radius: .58rem; background: #fafcfb; }
.run-detail-grid dt { color: #8b938e; font-size: .58rem; font-weight: 700; letter-spacing: .04em; text-transform: uppercase; }
.run-detail-grid dd { overflow: hidden; margin: .24rem 0 0; color: #3f4842; font-size: .68rem; text-overflow: ellipsis; white-space: nowrap; }
.run-detail-section { display: grid; gap: .42rem; }
.run-detail-section h3 { margin: 0; color: #606a64; font-size: .64rem; font-weight: 720; letter-spacing: .04em; text-transform: uppercase; }
.run-output-block { margin: 0; padding: .78rem .85rem; border: 1px solid rgba(29,29,31,.07); border-radius: .58rem; color: #4e5a53; background: #f7faf8; font: inherit; font-size: .66rem; line-height: 1.55; overflow-wrap: anywhere; white-space: pre-wrap; }
.run-output-empty { margin: 0; padding: .72rem .8rem; border: 1px dashed #dce4de; border-radius: .58rem; color: #8b938e; background: #fafcfb; font-size: .66rem; }
.run-detail-footer { display: flex; align-items: center; justify-content: flex-end; gap: .5rem; padding: .85rem 1.2rem 1rem; border-top: 1px solid rgba(29,29,31,.07); }
.scheduled-dialog-enter-active .scheduled-modal, .scheduled-dialog-leave-active .scheduled-modal { transition: transform 210ms cubic-bezier(.2,.8,.2,1), opacity 170ms ease; }
.scheduled-dialog-enter-from .scheduled-modal, .scheduled-dialog-leave-to .scheduled-modal { opacity: 0; transform: translateY(.55rem) scale(.985); }
@media (max-width: 820px) {
  .run-detail-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 560px) {
  .scheduled-modal-backdrop { align-items: end; padding: .7rem; }
  .scheduled-modal { max-height: calc(100vh - 1.4rem); border-radius: .9rem; }
  .run-detail-grid { grid-template-columns: 1fr; }
}
.scheduled-dialog-enter-active, .scheduled-dialog-leave-active { transition: opacity 170ms ease; }
.scheduled-dialog-enter-from, .scheduled-dialog-leave-to { opacity: 0; }
</style>
