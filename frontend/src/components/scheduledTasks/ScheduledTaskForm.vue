<script setup lang="ts">
import type { AIProvider, ReasoningEffort } from '../../api/types'
import { REASONING_EFFORTS } from '../../utils/reasoningEffort'

/** The fields of the new-task form. The parent owns the object; this dialog edits it in place. */
export interface ScheduledTaskFormState {
  name: string
  expression: string
  timezone: string
  providerId: string
  prompt: string
  reasoningEffort: ReasoningEffort
  enabled: boolean
  timeoutSeconds: number
}

defineProps<{
  open: boolean
  form: ScheduledTaskFormState
  providers: AIProvider[]
  saving: boolean
  canCreate: boolean
  expressionValid: boolean
  timezoneValid: boolean
  timeoutValid: boolean
}>()
const emit = defineEmits<{ close: []; submit: [] }>()
</script>

<template>
  <Teleport to="body">
    <Transition name="scheduled-dialog">
      <div v-if="open" class="scheduled-modal-backdrop" @click.self="emit('close')" @keydown.esc.stop.prevent="emit('close')">
        <form class="scheduled-modal scheduled-create" role="dialog" aria-modal="true" aria-labelledby="new-scheduled-task-title" @submit.prevent="emit('submit')">
          <header class="scheduled-modal-header">
            <div>
              <span>Automation</span>
              <h2 id="new-scheduled-task-title">New scheduled task</h2>
              <p>Run one Agent prompt in a new session on a Cron schedule.</p>
            </div>
            <button class="scheduled-modal-close" type="button" aria-label="Close" @click="emit('close')">×</button>
          </header>
          <div class="scheduled-form-grid">
            <label><span>Name</span><input v-model="form.name" maxlength="200" placeholder="Daily knowledge review" autofocus /></label>
            <label>
              <span>Cron expression</span>
              <input v-model="form.expression" maxlength="200" placeholder="0 9 * * *" :aria-invalid="!expressionValid" />
              <small v-if="!expressionValid" class="field-error">Use a 5- or 6-field Cron expression.</small>
            </label>
            <label>
              <span>Timezone</span>
              <input v-model="form.timezone" maxlength="100" spellcheck="false" placeholder="Asia/Shanghai" :aria-invalid="!timezoneValid" />
              <small v-if="!timezoneValid" class="field-error">Use a valid IANA timezone such as Asia/Shanghai.</small>
            </label>
            <label><span>Provider</span><select v-model="form.providerId"><option value="" disabled>Select a provider</option><option v-for="provider in providers" :key="provider.id" :value="provider.id">{{ provider.name }} · {{ provider.model }}</option></select></label>
            <label><span>Reasoning</span><select v-model="form.reasoningEffort"><option v-for="option in REASONING_EFFORTS" :key="option.value" :value="option.value">{{ option.label }}</option></select></label>
            <label>
              <span>Timeout seconds</span>
              <input v-model.number="form.timeoutSeconds" type="number" min="1" max="86400" step="1" :aria-invalid="!timeoutValid" />
              <small v-if="!timeoutValid" class="field-error">Use a whole number from 1 to 86400.</small>
            </label>
            <label class="full"><span>Prompt</span><textarea v-model="form.prompt" maxlength="100000" rows="6" placeholder="Review recent notes and create a concise summary artifact." /></label>
          </div>
          <footer>
            <label class="task-enabled"><input v-model="form.enabled" type="checkbox" /> Enable immediately</label>
            <div>
              <button class="secondary-action" type="button" @click="emit('close')">Cancel</button>
              <button class="primary-action" type="submit" :disabled="saving || !canCreate">
                <span v-if="saving" class="button-spinner" aria-hidden="true" />
                {{ saving ? 'Creating…' : 'Create task' }}
              </button>
            </div>
          </footer>
        </form>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.scheduled-topbar-actions .secondary-action { min-height: 2.45rem; }
.scheduled-modal-backdrop { position: fixed; inset: 0; z-index: 1000; display: grid; place-items: center; padding: 1.25rem; background: rgba(27,35,30,.28); backdrop-filter: blur(12px) saturate(115%); }
.scheduled-modal { width: min(100%, 42rem); max-height: min(48rem, calc(100vh - 2rem)); overflow-y: auto; border: 1px solid rgba(38,52,43,.14); border-radius: 1rem; background: #fff; box-shadow: 0 28px 80px rgba(28,39,32,.22); }
.scheduled-modal-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 1rem; padding: 1.25rem 1.35rem 1rem; border-bottom: 1px solid rgba(29,29,31,.07); }
.scheduled-modal-header span { color: #557662; font-size: .61rem; font-weight: 750; letter-spacing: .09em; text-transform: uppercase; }
.scheduled-modal-header h2 { margin: .25rem 0 .24rem; color: #2d342f; font-size: 1.2rem; }
.scheduled-modal-header p { margin: 0; color: #858d88; font-size: .7rem; }
.scheduled-modal-close { width: 2rem; height: 2rem; flex: 0 0 auto; border: 1px solid #e1e6e2; border-radius: .62rem; color: #69726c; background: #f8f9f8; cursor: pointer; font-size: 1.2rem; line-height: 1; }
.scheduled-modal-close:hover { color: #35453b; background: #f0f4f1; }
.scheduled-form-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: .8rem; padding: 1rem 1.1rem; }
.scheduled-form-grid label { min-width: 0; display: grid; gap: .35rem; }
.scheduled-form-grid label.full { grid-column: 1 / -1; }
.scheduled-form-grid label > span { color: #68716b; font-size: .66rem; font-weight: 680; }
.scheduled-form-grid input, .scheduled-form-grid select, .scheduled-form-grid textarea { width: 100%; min-width: 0; border: 1px solid #dce2de; border-radius: .62rem; outline: none; color: #343b36; background: #fbfcfb; font: inherit; font-size: .72rem; }
.scheduled-form-grid input, .scheduled-form-grid select { height: 2.55rem; padding: 0 .7rem; }
.scheduled-form-grid textarea { resize: vertical; padding: .65rem .7rem; line-height: 1.5; }
.scheduled-form-grid input:focus, .scheduled-form-grid select:focus, .scheduled-form-grid textarea:focus { border-color: #8fab99; box-shadow: 0 0 0 3px rgba(76,119,94,.1); background: #fff; }
.scheduled-form-grid .field-error { color: #a05050; font-size: .6rem; line-height: 1.35; }
.scheduled-form-grid [aria-invalid="true"] { border-color: #d8aaaa; background: #fffafa; }
.scheduled-create footer { display: flex; align-items: center; justify-content: space-between; gap: 1rem; padding: .9rem 1.1rem 1.05rem; border-top: 1px solid rgba(29,29,31,.07); }
.scheduled-create footer > div { display: flex; align-items: center; gap: .5rem; }
.task-enabled { display: flex; align-items: center; gap: .42rem; color: #69726c; font-size: .68rem; }
.scheduled-dialog-enter-active .scheduled-modal, .scheduled-dialog-leave-active .scheduled-modal { transition: transform 210ms cubic-bezier(.2,.8,.2,1), opacity 170ms ease; }
.scheduled-dialog-enter-from .scheduled-modal, .scheduled-dialog-leave-to .scheduled-modal { opacity: 0; transform: translateY(.55rem) scale(.985); }
@media (max-width: 820px) {
  .scheduled-form-grid { grid-template-columns: 1fr; }
  .scheduled-card-header, .scheduled-create footer { align-items: stretch; flex-direction: column; }
}
@media (max-width: 560px) {
  .scheduled-modal-backdrop { align-items: end; padding: .7rem; }
  .scheduled-modal { max-height: calc(100vh - 1.4rem); border-radius: .9rem; }
  .scheduled-form-grid { grid-template-columns: 1fr; }
  .scheduled-create footer { align-items: stretch; flex-direction: column; }
  .scheduled-create footer > div { justify-content: flex-end; }
}
.scheduled-dialog-enter-active, .scheduled-dialog-leave-active { transition: opacity 170ms ease; }
.scheduled-dialog-enter-from, .scheduled-dialog-leave-to { opacity: 0; }
</style>
