<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { aiClient, scheduledTaskClient } from '../api/client'
import type {
  AIProvider,
  ReasoningEffort,
  ScheduledTask,
  ScheduledTaskInput,
  ScheduledTaskRun,
  ScheduledTaskRunStatus,
} from '../api/types'

const emit = defineEmits<{
  openSession: [sessionId: string]
}>()

const tasks = ref<ScheduledTask[]>([])
const providers = ref<AIProvider[]>([])
const runs = ref<ScheduledTaskRun[]>([])
const selectedTaskId = ref<string | null>(null)
const loading = ref(false)
const runsLoading = ref(false)
const saving = ref(false)
const busyTaskId = ref<string | null>(null)
const error = ref('')
const form = reactive({
  name: '',
  expression: '0 9 * * *',
  timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC',
  providerId: '',
  prompt: '',
  reasoningEffort: 'medium' as ReasoningEffort,
  enabled: true,
  timeoutSeconds: 600,
})

const selectedTask = computed(() => tasks.value.find((task) => task.id === selectedTaskId.value) ?? null)
const enabledProviders = computed(() => providers.value.filter((provider) => provider.enabled))

function message(errorValue: unknown): string {
  return errorValue instanceof Error ? errorValue.message : 'Scheduled task request failed'
}

function actionPayload(task: ScheduledTask): Record<string, unknown> {
  return task.action.payload
}

function actionPrompt(task: ScheduledTask): string {
  const prompt = actionPayload(task).message
  return typeof prompt === 'string' ? prompt : 'No prompt'
}

function statusLabel(status: ScheduledTaskRunStatus): string {
  return status.charAt(0).toUpperCase() + status.slice(1)
}

function formatDate(value: string | null): string {
  if (!value) return 'Not yet'
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value))
}

function duration(run: ScheduledTaskRun): string {
  if (!run.started_at || !run.completed_at) return '—'
  const milliseconds = new Date(run.completed_at).getTime() - new Date(run.started_at).getTime()
  if (milliseconds < 1000) return `${milliseconds} ms`
  return `${(milliseconds / 1000).toFixed(1)} s`
}

function outputValue(run: ScheduledTaskRun, key: string): string | null {
  const value = run.output?.[key]
  return typeof value === 'string' && value ? value : null
}

function outputPreview(run: ScheduledTaskRun): string | null {
  return outputValue(run, 'content_preview')
}

function outputModel(run: ScheduledTaskRun): string | null {
  return outputValue(run, 'model')
}

function outputProvider(run: ScheduledTaskRun): string | null {
  return outputValue(run, 'provider_id')
}

function outputSessionId(run: ScheduledTaskRun): string | null {
  return outputValue(run, 'session_id')
}

function rawOutput(run: ScheduledTaskRun): string | null {
  if (!run.output) return null
  return JSON.stringify(run.output, null, 2)
}

function shortId(value: string): string {
  return value.length > 16 ? `${value.slice(0, 8)}…${value.slice(-5)}` : value
}

async function loadTasks(preferredTaskId?: string): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    const [taskData, providerData] = await Promise.all([
      scheduledTaskClient.list(),
      aiClient.listProviders(),
    ])
    tasks.value = taskData
    providers.value = providerData
    if (!form.providerId && enabledProviders.value[0]) form.providerId = enabledProviders.value[0].id
    const requested = preferredTaskId ?? selectedTaskId.value
    const nextTask = taskData.find((task) => task.id === requested) ?? taskData[0] ?? null
    selectedTaskId.value = nextTask?.id ?? null
    if (nextTask) await loadRuns(nextTask.id)
    else runs.value = []
  } catch (errorValue) {
    error.value = message(errorValue)
  } finally {
    loading.value = false
  }
}

async function loadRuns(taskId: string): Promise<void> {
  runsLoading.value = true
  try {
    runs.value = await scheduledTaskClient.listRuns(taskId)
  } catch (errorValue) {
    error.value = message(errorValue)
  } finally {
    runsLoading.value = false
  }
}

async function selectTask(task: ScheduledTask): Promise<void> {
  selectedTaskId.value = task.id
  await loadRuns(task.id)
}

async function createTask(): Promise<void> {
  if (saving.value) return
  if (!form.name.trim() || !form.providerId || !form.prompt.trim()) return
  saving.value = true
  error.value = ''
  try {
    const payload: ScheduledTaskInput = {
      name: form.name.trim(),
      enabled: form.enabled,
      timeout_seconds: form.timeoutSeconds,
      schedule: {
        expression: form.expression.trim(),
        timezone: form.timezone.trim(),
      },
      action: {
        kind: 'agent_prompt',
        payload: {
          provider_id: form.providerId,
          message: form.prompt.trim(),
          reasoning_effort: form.reasoningEffort,
        },
      },
    }
    const created = await scheduledTaskClient.create(payload)
    form.name = ''
    form.prompt = ''
    await loadTasks(created.id)
  } catch (errorValue) {
    error.value = message(errorValue)
  } finally {
    saving.value = false
  }
}

async function toggleTask(task: ScheduledTask): Promise<void> {
  busyTaskId.value = task.id
  try {
    const updated = await scheduledTaskClient.setEnabled(task.id, !task.enabled)
    tasks.value = tasks.value.map((item) => item.id === updated.id ? updated : item)
  } catch (errorValue) {
    error.value = message(errorValue)
  } finally {
    busyTaskId.value = null
  }
}

async function runNow(task: ScheduledTask): Promise<void> {
  busyTaskId.value = task.id
  try {
    await scheduledTaskClient.runNow(task.id)
    await loadRuns(task.id)
  } catch (errorValue) {
    error.value = message(errorValue)
  } finally {
    busyTaskId.value = null
  }
}

async function removeTask(task: ScheduledTask): Promise<void> {
  if (!window.confirm(`Delete scheduled task “${task.name}”?`)) return
  busyTaskId.value = task.id
  try {
    await scheduledTaskClient.delete(task.id)
    await loadTasks()
  } catch (errorValue) {
    error.value = message(errorValue)
  } finally {
    busyTaskId.value = null
  }
}

onMounted(() => {
  void loadTasks()
})
</script>

<template>
  <header class="topbar compact">
    <div><p class="eyebrow">Automation</p><h1>Scheduled tasks</h1></div>
    <button class="primary-action" type="button" :disabled="loading" @click="loadTasks()">
      <span v-if="loading" class="button-spinner" aria-hidden="true" />
      Refresh
    </button>
  </header>

  <section class="content scheduled-view">
    <p v-if="error" class="scheduled-error" role="alert">{{ error }}</p>

    <div class="scheduled-layout">
      <aside class="scheduled-list-panel">
        <header>
          <div><strong>Tasks</strong><small>{{ tasks.length }} configured</small></div>
        </header>
        <div v-if="loading" class="scheduled-loading">Loading tasks…</div>
        <div v-else-if="tasks.length" class="scheduled-list">
          <button
            v-for="task in tasks"
            :key="task.id"
            class="scheduled-list-item"
            :class="{ active: selectedTaskId === task.id }"
            type="button"
            @click="selectTask(task)"
          >
            <span class="scheduled-status-dot" :class="{ disabled: !task.enabled }" />
            <span class="scheduled-list-copy">
              <strong>{{ task.name }}</strong>
              <small>{{ task.schedule.expression }} · {{ task.schedule.timezone }}</small>
              <time>Next {{ formatDate(task.next_run_at) }}</time>
            </span>
          </button>
        </div>
        <div v-else class="scheduled-empty">No scheduled tasks yet.</div>
      </aside>

      <div class="scheduled-detail">
        <article v-if="selectedTask" class="scheduled-card">
          <header class="scheduled-card-header">
            <div>
              <span class="scheduled-status" :class="{ disabled: !selectedTask.enabled }">
                {{ selectedTask.enabled ? 'Enabled' : 'Disabled' }}
              </span>
              <h2>{{ selectedTask.name }}</h2>
              <p>{{ actionPrompt(selectedTask) }}</p>
            </div>
            <div class="scheduled-actions">
              <button type="button" :disabled="busyTaskId === selectedTask.id" @click="toggleTask(selectedTask)">
                {{ selectedTask.enabled ? 'Disable' : 'Enable' }}
              </button>
              <button type="button" :disabled="busyTaskId === selectedTask.id" @click="runNow(selectedTask)">
                {{ busyTaskId === selectedTask.id ? 'Working…' : 'Run now' }}
              </button>
              <button class="danger" type="button" :disabled="busyTaskId === selectedTask.id" @click="removeTask(selectedTask)">
                Delete
              </button>
            </div>
          </header>
          <dl class="scheduled-facts">
            <div><dt>Schedule</dt><dd>{{ selectedTask.schedule.expression }}</dd></div>
            <div><dt>Timezone</dt><dd>{{ selectedTask.schedule.timezone }}</dd></div>
            <div><dt>Next run</dt><dd>{{ formatDate(selectedTask.next_run_at) }}</dd></div>
            <div><dt>Timeout</dt><dd>{{ selectedTask.timeout_seconds }} seconds</dd></div>
            <div><dt>Action</dt><dd>{{ selectedTask.action.kind }}</dd></div>
            <div><dt>Lease</dt><dd>{{ selectedTask.lease_run_id ? 'Running or queued' : 'Idle' }}</dd></div>
          </dl>
        </article>

        <article class="scheduled-card">
          <header class="scheduled-card-header">
            <div><h2>Recent runs</h2><p>Execution status written by scheduler workers.</p></div>
          </header>
          <div v-if="runsLoading" class="scheduled-loading">Loading runs…</div>
          <div v-else-if="runs.length" class="scheduled-runs">
            <article v-for="run in runs" :key="run.id" class="scheduled-run" :class="run.status">
              <header class="run-header">
                <span class="run-status" :class="run.status">{{ statusLabel(run.status) }}</span>
                <div class="run-timing">
                  <strong>{{ formatDate(run.scheduled_for) }}</strong>
                  <small>{{ run.trigger_kind }} · {{ duration(run) }}</small>
                </div>
              </header>

              <div v-if="run.error_message" class="run-error" role="alert">
                <strong>{{ run.error_type || 'Execution failed' }}</strong>
                <p>{{ run.error_message }}</p>
              </div>

              <div v-else-if="run.output" class="run-output">
                <div class="run-output-meta">
                  <span v-if="outputModel(run)" class="run-chip">Model {{ outputModel(run) }}</span>
                  <span v-if="outputProvider(run)" class="run-chip" :title="outputProvider(run) || ''">Provider {{ shortId(outputProvider(run) || '') }}</span>
                  <button
                    v-if="outputSessionId(run)"
                    class="run-session-button"
                    type="button"
                    :title="outputSessionId(run) || ''"
                    @click="emit('openSession', outputSessionId(run) || '')"
                  >
                    Open session
                  </button>
                </div>
                <p v-if="outputPreview(run)" class="run-preview">{{ outputPreview(run) }}</p>
                <details v-if="rawOutput(run)" class="run-raw">
                  <summary>Raw output</summary>
                  <pre>{{ rawOutput(run) }}</pre>
                </details>
              </div>

              <div v-else class="run-waiting">Waiting for a worker to produce a result.</div>
            </article>
          </div>
          <div v-else class="scheduled-empty">No runs recorded for this task.</div>
        </article>

        <form class="scheduled-card scheduled-create" @submit.prevent="createTask">
          <header class="scheduled-card-header">
            <div><h2>New scheduled task</h2><p>Run one Agent prompt in a new session on a Cron schedule.</p></div>
          </header>
          <div class="scheduled-form-grid">
            <label><span>Name</span><input v-model="form.name" placeholder="Daily knowledge review" /></label>
            <label><span>Cron expression</span><input v-model="form.expression" placeholder="0 9 * * *" /></label>
            <label><span>Timezone</span><input v-model="form.timezone" placeholder="Asia/Shanghai" /></label>
            <label><span>Provider</span><select v-model="form.providerId"><option value="" disabled>Select a provider</option><option v-for="provider in enabledProviders" :key="provider.id" :value="provider.id">{{ provider.name }} · {{ provider.model }}</option></select></label>
            <label><span>Reasoning</span><select v-model="form.reasoningEffort"><option value="off">Off</option><option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option></select></label>
            <label><span>Timeout seconds</span><input v-model.number="form.timeoutSeconds" type="number" min="1" max="86400" /></label>
            <label class="full"><span>Prompt</span><textarea v-model="form.prompt" rows="5" placeholder="Review recent notes and create a concise summary artifact." /></label>
          </div>
          <footer>
            <label class="task-enabled"><input v-model="form.enabled" type="checkbox" /> Enable immediately</label>
            <button class="primary-action" type="submit" :disabled="saving || !form.name.trim() || !form.providerId || !form.prompt.trim()">
              <span v-if="saving" class="button-spinner" aria-hidden="true" />
              {{ saving ? 'Creating…' : 'Create task' }}
            </button>
          </footer>
        </form>
      </div>
    </div>
  </section>
</template>

<style scoped>
.scheduled-view { max-width: 74rem; }
.scheduled-error { margin: 0 0 1rem; padding: .75rem .9rem; border-radius: .7rem; color: #963f3f; background: #faeded; font-size: .72rem; }
.scheduled-layout { display: grid; grid-template-columns: minmax(14rem, 18rem) minmax(0, 1fr); align-items: start; gap: 1rem; }
.scheduled-list-panel, .scheduled-card { border: 1px solid rgba(29,29,31,.08); border-radius: .85rem; background: rgba(255,255,255,.9); box-shadow: 0 2px 12px rgba(0,0,0,.025); }
.scheduled-list-panel { position: sticky; top: 5.5rem; overflow: hidden; }
.scheduled-list-panel > header, .scheduled-card-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 1rem; padding: 1rem 1.1rem; border-bottom: 1px solid rgba(29,29,31,.07); }
.scheduled-list-panel header div, .scheduled-card-header > div { min-width: 0; }
.scheduled-list-panel strong, .scheduled-card h2 { margin: 0; color: #303632; }
.scheduled-list-panel small, .scheduled-card-header p { display: block; margin: .2rem 0 0; color: #8a918d; font-size: .68rem; line-height: 1.5; }
.scheduled-list { max-height: 34rem; overflow-y: auto; padding: .4rem; }
.scheduled-list-item { width: 100%; display: flex; align-items: flex-start; gap: .65rem; padding: .7rem; border: 0; border-radius: .7rem; color: #39413c; background: transparent; cursor: pointer; text-align: left; }
.scheduled-list-item:hover, .scheduled-list-item.active { background: #f0f5f1; }
.scheduled-status-dot { width: .5rem; height: .5rem; flex: 0 0 auto; margin-top: .28rem; border-radius: 50%; background: #4f8a64; box-shadow: 0 0 0 3px #e3f0e7; }
.scheduled-status-dot.disabled { background: #aaa; box-shadow: 0 0 0 3px #eee; }
.scheduled-list-copy { min-width: 0; display: grid; gap: .18rem; }
.scheduled-list-copy strong { overflow: hidden; font-size: .76rem; text-overflow: ellipsis; white-space: nowrap; }
.scheduled-list-copy small, .scheduled-list-copy time { overflow: hidden; color: #8c938f; font-size: .62rem; text-overflow: ellipsis; white-space: nowrap; }
.scheduled-detail { min-width: 0; display: grid; gap: 1rem; }
.scheduled-card { overflow: hidden; }
.scheduled-card h2 { font-size: 1rem; }
.scheduled-card-header > div > p { max-width: 38rem; }
.scheduled-status { display: inline-flex; margin-bottom: .4rem; padding: .2rem .45rem; border-radius: 999px; color: #3d6d4e; background: #e9f4ed; font-size: .62rem; font-weight: 700; }
.scheduled-status.disabled { color: #777; background: #eee; }
.scheduled-actions { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: .4rem; }
.scheduled-actions button { min-height: 2rem; padding: 0 .65rem; border: 1px solid #dce4de; border-radius: .58rem; color: #43534a; background: #fff; cursor: pointer; font-size: .66rem; font-weight: 650; }
.scheduled-actions button:hover:not(:disabled) { background: #f2f6f3; }
.scheduled-actions button.danger { color: #9d4545; border-color: #ecd8d6; background: #fffafa; }
.scheduled-actions button:disabled { cursor: default; opacity: .55; }
.scheduled-facts { display: grid; grid-template-columns: repeat(auto-fit, minmax(9rem, 1fr)); gap: .75rem; margin: 0; padding: 1rem 1.1rem 1.15rem; }
.scheduled-facts div { min-width: 0; }
.scheduled-facts dt { color: #929994; font-size: .62rem; text-transform: uppercase; letter-spacing: .045em; }
.scheduled-facts dd { overflow: hidden; margin: .25rem 0 0; color: #3e4741; font-size: .72rem; text-overflow: ellipsis; white-space: nowrap; }
.scheduled-loading, .scheduled-empty { padding: 2rem 1rem; color: #8b938e; font-size: .72rem; text-align: center; }
.scheduled-runs { display: grid; gap: .7rem; padding: .8rem; background: #f7f9f7; }
.scheduled-run { display: grid; gap: .75rem; padding: .9rem 1rem; border: 1px solid rgba(29,29,31,.075); border-radius: .72rem; background: #fff; box-shadow: 0 1px 3px rgba(25,34,29,.025); }
.scheduled-run.failed, .scheduled-run.interrupted { border-color: rgba(175,85,85,.2); }
.run-header { display: flex; align-items: center; justify-content: space-between; gap: .8rem; }
.run-status { justify-self: start; padding: .22rem .48rem; border-radius: 999px; color: #3c6b4d; background: #e9f4ed; font-size: .62rem; font-weight: 700; }
.run-status.failed, .run-status.interrupted { color: #984646; background: #faeceb; }
.run-status.pending, .run-status.running { color: #786126; background: #f7f0d9; }
.run-status.skipped, .run-status.cancelled { color: #6d7270; background: #eeeeec; }
.run-timing { min-width: 0; text-align: right; }
.run-timing strong, .run-timing small { display: block; }
.run-timing strong { color: #414943; font-size: .7rem; }
.run-timing small { margin-top: .14rem; color: #949a96; font-size: .62rem; }
.run-output { display: grid; gap: .6rem; }
.run-output-meta { display: flex; flex-wrap: wrap; align-items: center; gap: .4rem; }
.run-chip { display: inline-flex; max-width: 18rem; padding: .24rem .48rem; overflow: hidden; border-radius: 999px; color: #617068; background: #f0f4f1; font-size: .61rem; text-overflow: ellipsis; white-space: nowrap; }
.run-session-button { min-height: 1.75rem; margin-left: auto; padding: 0 .58rem; border: 1px solid #cedbd2; border-radius: .52rem; color: #3f6850; background: #f7fbf8; cursor: pointer; font-size: .62rem; font-weight: 680; }
.run-session-button:hover { background: #eaf4ed; }
.run-preview { max-height: 13rem; margin: 0; padding: .75rem .85rem; overflow: auto; border-left: 3px solid #8caf99; border-radius: .2rem .58rem .58rem .2rem; color: #3e4842; background: #f7faf8; font: inherit; font-size: .69rem; line-height: 1.55; white-space: pre-wrap; }
.run-error { padding: .7rem .8rem; border: 1px solid #efd7d5; border-radius: .6rem; color: #8f4141; background: #fff8f7; }
.run-error strong { display: block; font-size: .68rem; }
.run-error p { margin: .28rem 0 0; font-size: .66rem; line-height: 1.5; white-space: pre-wrap; }
.run-raw summary { color: #7c867f; cursor: pointer; font-size: .62rem; }
.run-raw pre { max-height: 14rem; margin: .45rem 0 0; padding: .7rem; overflow: auto; border-radius: .55rem; color: #5f6863; background: #f4f6f4; font-size: .62rem; line-height: 1.45; white-space: pre-wrap; }
.run-waiting { color: #8b938e; font-size: .66rem; }
.scheduled-create { padding-bottom: .2rem; }
.scheduled-form-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: .8rem; padding: 1rem 1.1rem; }
.scheduled-form-grid label { min-width: 0; display: grid; gap: .35rem; }
.scheduled-form-grid label.full { grid-column: 1 / -1; }
.scheduled-form-grid label > span { color: #68716b; font-size: .66rem; font-weight: 680; }
.scheduled-form-grid input, .scheduled-form-grid select, .scheduled-form-grid textarea { width: 100%; min-width: 0; border: 1px solid #dce2de; border-radius: .62rem; outline: none; color: #343b36; background: #fbfcfb; font: inherit; font-size: .72rem; }
.scheduled-form-grid input, .scheduled-form-grid select { height: 2.55rem; padding: 0 .7rem; }
.scheduled-form-grid textarea { resize: vertical; padding: .65rem .7rem; line-height: 1.5; }
.scheduled-form-grid input:focus, .scheduled-form-grid select:focus, .scheduled-form-grid textarea:focus { border-color: #8fab99; box-shadow: 0 0 0 3px rgba(76,119,94,.1); background: #fff; }
.scheduled-create footer { display: flex; align-items: center; justify-content: space-between; gap: 1rem; padding: .9rem 1.1rem 1.05rem; border-top: 1px solid rgba(29,29,31,.07); }
.task-enabled { display: flex; align-items: center; gap: .42rem; color: #69726c; font-size: .68rem; }
@media (max-width: 820px) {
  .scheduled-layout { grid-template-columns: 1fr; }
  .scheduled-list-panel { position: static; }
  .scheduled-list { max-height: 18rem; }
  .run-header { align-items: flex-start; }
  .run-session-button { margin-left: 0; }
  .scheduled-form-grid { grid-template-columns: 1fr; }
  .scheduled-card-header, .scheduled-create footer { align-items: stretch; flex-direction: column; }
  .scheduled-actions { justify-content: flex-start; }
}
</style>
