<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
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
const selectedRun = ref<ScheduledTaskRun | null>(null)
const loading = ref(false)
const runsLoading = ref(false)
const saving = ref(false)
const formOpen = ref(false)
const runDetailOpen = ref(false)
const busyTaskId = ref<string | null>(null)
const runPage = ref(1)
const runPageSize = 10
const runsHaveNext = ref(false)
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
const nameValid = computed(() => form.name.trim().length > 0 && form.name.trim().length <= 200)
const expressionValid = computed(() => validCronShape(form.expression))
const timezoneValid = computed(() => validTimeZone(form.timezone))
const timeoutValid = computed(() => Number.isInteger(form.timeoutSeconds) && form.timeoutSeconds >= 1 && form.timeoutSeconds <= 86_400)
const promptValid = computed(() => form.prompt.trim().length > 0 && form.prompt.length <= 100_000)
const canCreateTask = computed(() => (
  nameValid.value
  && expressionValid.value
  && timezoneValid.value
  && timeoutValid.value
  && promptValid.value
  && enabledProviders.value.some((provider) => provider.id === form.providerId)
))

function message(errorValue: unknown): string {
  return errorValue instanceof Error ? errorValue.message : 'Scheduled task request failed'
}

function validCronShape(value: string): boolean {
  const fields = value.trim().split(/\s+/).filter(Boolean)
  if (fields.length === 1 && fields[0]!.startsWith('@')) return /^@[a-z]+$/i.test(fields[0]!)
  if (fields.length !== 5 && fields.length !== 6) return false
  return fields.every((field) => /^[0-9A-Za-z*?/,\-#]+$/.test(field))
}

function validTimeZone(value: string): boolean {
  const normalized = value.trim()
  if (!normalized) return false
  try {
    new Intl.DateTimeFormat(undefined, { timeZone: normalized })
    return true
  } catch {
    return false
  }
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

function runPreview(run: ScheduledTaskRun): string {
  return outputPreview(run) || run.error_message || (run.status === 'pending' || run.status === 'running'
    ? 'Waiting for execution result.'
    : 'No output preview.')
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
    if (nextTask) await loadRuns(nextTask.id, 1)
    else runs.value = []
  } catch (errorValue) {
    error.value = message(errorValue)
  } finally {
    loading.value = false
  }
}

async function loadRuns(taskId: string, page = runPage.value): Promise<void> {
  runsLoading.value = true
  error.value = ''
  try {
    const offset = Math.max(0, page - 1) * runPageSize
    const pageData = await scheduledTaskClient.listRuns(taskId, {
      limit: runPageSize + 1,
      offset,
    })
    runsHaveNext.value = pageData.length > runPageSize
    runs.value = pageData.slice(0, runPageSize)
    runPage.value = page
  } catch (errorValue) {
    error.value = message(errorValue)
  } finally {
    runsLoading.value = false
  }
}

async function selectTask(task: ScheduledTask): Promise<void> {
  selectedTaskId.value = task.id
  selectedRun.value = null
  runDetailOpen.value = false
  await loadRuns(task.id, 1)
}

async function createTask(): Promise<void> {
  if (saving.value) return
  if (!canCreateTask.value) return
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
    formOpen.value = false
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
    await loadRuns(task.id, 1)
  } catch (errorValue) {
    error.value = message(errorValue)
  } finally {
    busyTaskId.value = null
  }
}

function openRunDetail(run: ScheduledTaskRun): void {
  selectedRun.value = run
  runDetailOpen.value = true
}

function closeRunDetail(): void {
  runDetailOpen.value = false
  selectedRun.value = null
}

function handleModalKeydown(event: KeyboardEvent): void {
  if (event.key !== 'Escape') return
  if (runDetailOpen.value) {
    event.preventDefault()
    closeRunDetail()
    return
  }
  if (formOpen.value) {
    event.preventDefault()
    formOpen.value = false
  }
}

function changeRunPage(page: number): void {
  if (!selectedTask.value) return
  if (page < 1 || (page > runPage.value && !runsHaveNext.value)) return
  void loadRuns(selectedTask.value.id, page)
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
  window.addEventListener('keydown', handleModalKeydown)
  void loadTasks()
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', handleModalKeydown)
})
</script>

<template>
  <header class="topbar compact">
    <div><p class="eyebrow">Automation</p><h1>Scheduled tasks</h1></div>
    <div class="scheduled-topbar-actions">
      <button class="secondary-action new-scheduled-task-button" type="button" @click="formOpen = true">
        <svg><use href="#icon-add" /></svg>
        New task
      </button>
      <button class="primary-action" type="button" :disabled="loading" @click="loadTasks()">
        <span v-if="loading" class="button-spinner" aria-hidden="true" />
        Refresh
      </button>
    </div>
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

        <article class="scheduled-card scheduled-runs-card">
          <header class="scheduled-card-header">
            <div><h2>Run history</h2><p>Execution status written by scheduler workers.</p></div>
            <span v-if="selectedTask" class="runs-page-label">Page {{ runPage }}</span>
          </header>
          <div v-if="runsLoading" class="scheduled-loading">Loading runs…</div>
          <div v-else-if="runs.length" class="runs-table-wrap">
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
                  @click="openRunDetail(run)"
                  @keydown.enter.prevent="openRunDetail(run)"
                  @keydown.space.prevent="openRunDetail(run)"
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
                  <td data-label="Details"><button class="run-view-button" type="button" @click.stop="openRunDetail(run)">View</button></td>
                </tr>
              </tbody>
            </table>
            <footer class="runs-pagination">
              <span>{{ runPageSize }} runs per page</span>
              <div>
                <button type="button" :disabled="runPage <= 1" @click="changeRunPage(runPage - 1)">Previous</button>
                <button type="button" :disabled="!runsHaveNext" @click="changeRunPage(runPage + 1)">Next</button>
              </div>
            </footer>
          </div>
          <div v-else class="scheduled-empty">No runs recorded for this task.</div>
        </article>
      </div>
    </div>
  </section>

  <Teleport to="body">
    <Transition name="scheduled-dialog">
      <div v-if="formOpen" class="scheduled-modal-backdrop" @click.self="formOpen = false" @keydown.esc.stop.prevent="formOpen = false">
        <form class="scheduled-modal scheduled-create" role="dialog" aria-modal="true" aria-labelledby="new-scheduled-task-title" @submit.prevent="createTask">
          <header class="scheduled-modal-header">
            <div>
              <span>Automation</span>
              <h2 id="new-scheduled-task-title">New scheduled task</h2>
              <p>Run one Agent prompt in a new session on a Cron schedule.</p>
            </div>
            <button class="scheduled-modal-close" type="button" aria-label="Close" @click="formOpen = false">×</button>
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
            <label><span>Provider</span><select v-model="form.providerId"><option value="" disabled>Select a provider</option><option v-for="provider in enabledProviders" :key="provider.id" :value="provider.id">{{ provider.name }} · {{ provider.model }}</option></select></label>
            <label><span>Reasoning</span><select v-model="form.reasoningEffort"><option value="off">Off</option><option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option></select></label>
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
              <button class="secondary-action" type="button" @click="formOpen = false">Cancel</button>
              <button class="primary-action" type="submit" :disabled="saving || !canCreateTask">
                <span v-if="saving" class="button-spinner" aria-hidden="true" />
                {{ saving ? 'Creating…' : 'Create task' }}
              </button>
            </div>
          </footer>
        </form>
      </div>
    </Transition>
  </Teleport>

  <Teleport to="body">
    <Transition name="scheduled-dialog">
      <div v-if="runDetailOpen && selectedRun" class="scheduled-modal-backdrop" @click.self="closeRunDetail" @keydown.esc.stop.prevent="closeRunDetail">
        <section class="scheduled-modal run-detail-modal" role="dialog" aria-modal="true" aria-labelledby="run-detail-title">
          <header class="scheduled-modal-header">
            <div>
              <span>Execution detail</span>
              <div class="run-detail-heading">
                <span class="run-status" :class="selectedRun.status">{{ statusLabel(selectedRun.status) }}</span>
                <h2 id="run-detail-title">{{ selectedTask?.name || 'Scheduled run' }}</h2>
              </div>
              <p>{{ shortId(selectedRun.id) }} · {{ formatDate(selectedRun.scheduled_for) }}</p>
            </div>
            <button class="scheduled-modal-close" type="button" aria-label="Close" @click="closeRunDetail">×</button>
          </header>

          <div class="run-detail-body">
            <div v-if="selectedRun.error_message" class="run-error" role="alert">
              <strong>{{ selectedRun.error_type || 'Execution failed' }}</strong>
              <p>{{ selectedRun.error_message }}</p>
            </div>

            <dl class="run-detail-grid">
              <div><dt>Trigger</dt><dd>{{ selectedRun.trigger_kind }}</dd></div>
              <div><dt>Duration</dt><dd>{{ duration(selectedRun) }}</dd></div>
              <div><dt>Started</dt><dd>{{ formatDate(selectedRun.started_at) }}</dd></div>
              <div><dt>Completed</dt><dd>{{ formatDate(selectedRun.completed_at) }}</dd></div>
              <div><dt>Model</dt><dd>{{ outputModel(selectedRun) || '—' }}</dd></div>
              <div><dt>Provider</dt><dd :title="outputProvider(selectedRun) || ''">{{ outputProvider(selectedRun) ? shortId(outputProvider(selectedRun) || '') : '—' }}</dd></div>
            </dl>

            <section class="run-detail-section">
              <h3>Preview</h3>
              <p class="run-preview">{{ runPreview(selectedRun) }}</p>
            </section>

            <section class="run-detail-section">
              <h3>Output</h3>
              <pre v-if="rawOutput(selectedRun)" class="run-output-block">{{ rawOutput(selectedRun) }}</pre>
              <p v-else class="run-output-empty">No output was produced for this run.</p>
            </section>
          </div>

          <footer class="scheduled-create-footer run-detail-footer">
            <button class="secondary-action" type="button" @click="closeRunDetail">Close</button>
            <button
              v-if="outputSessionId(selectedRun)"
              class="primary-action"
              type="button"
              @click="emit('openSession', outputSessionId(selectedRun) || '')"
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
.scheduled-view { max-width: 90rem; }
.scheduled-topbar-actions { display: flex; align-items: center; gap: .55rem; }
.scheduled-topbar-actions .secondary-action { min-height: 2.45rem; }
.scheduled-error { margin: 0 0 1rem; padding: .75rem .9rem; border-radius: .7rem; color: #963f3f; background: #faeded; font-size: .72rem; }
.scheduled-layout { height: calc(100vh - 9rem); min-height: 36rem; display: grid; grid-template-columns: clamp(13rem, 20vw, 18rem) minmax(0, 1fr); align-items: stretch; gap: 1rem; }
.scheduled-list-panel, .scheduled-card { border: 1px solid rgba(29,29,31,.08); border-radius: .85rem; background: rgba(255,255,255,.9); box-shadow: 0 2px 12px rgba(0,0,0,.025); }
.scheduled-list-panel { min-height: 0; display: flex; flex-direction: column; overflow: hidden; }
.scheduled-list-panel > header, .scheduled-card-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 1rem; padding: 1rem 1.1rem; border-bottom: 1px solid rgba(29,29,31,.07); }
.scheduled-list-panel header div, .scheduled-card-header > div { min-width: 0; }
.scheduled-list-panel strong, .scheduled-card h2 { margin: 0; color: #303632; }
.scheduled-list-panel small, .scheduled-card-header p { display: block; margin: .2rem 0 0; color: #8a918d; font-size: .68rem; line-height: 1.5; }
.scheduled-list { min-height: 0; flex: 1; overflow-y: auto; padding: .4rem; }
.scheduled-list-item { width: 100%; display: flex; align-items: flex-start; gap: .65rem; padding: .7rem; border: 0; border-radius: .7rem; color: #39413c; background: transparent; cursor: pointer; text-align: left; }
.scheduled-list-item:hover, .scheduled-list-item.active { background: #f0f5f1; }
.scheduled-status-dot { width: .5rem; height: .5rem; flex: 0 0 auto; margin-top: .28rem; border-radius: 50%; background: #4f8a64; box-shadow: 0 0 0 3px #e3f0e7; }
.scheduled-status-dot.disabled { background: #aaa; box-shadow: 0 0 0 3px #eee; }
.scheduled-list-copy { min-width: 0; display: grid; gap: .18rem; }
.scheduled-list-copy strong { overflow: hidden; font-size: .76rem; text-overflow: ellipsis; white-space: nowrap; }
.scheduled-list-copy small, .scheduled-list-copy time { overflow: hidden; color: #8c938f; font-size: .62rem; text-overflow: ellipsis; white-space: nowrap; }
.scheduled-detail { min-width: 0; height: 100%; display: grid; align-content: start; gap: 1rem; overflow-y: auto; padding-right: .18rem; }
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
.runs-page-label { color: #8a918d; font-size: .62rem; font-weight: 650; }
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
.run-preview { max-height: 13rem; margin: 0; padding: .75rem .85rem; overflow: auto; border-left: 3px solid #8caf99; border-radius: .2rem .58rem .58rem .2rem; color: #3e4842; background: #f7faf8; font: inherit; font-size: .69rem; line-height: 1.55; white-space: pre-wrap; }
.run-error { padding: .7rem .8rem; border: 1px solid #efd7d5; border-radius: .6rem; color: #8f4141; background: #fff8f7; }
.run-error strong { display: block; font-size: .68rem; }
.run-error p { margin: .28rem 0 0; font-size: .66rem; line-height: 1.5; white-space: pre-wrap; }
.run-raw summary { color: #7c867f; cursor: pointer; font-size: .62rem; }
.run-raw pre { max-height: 14rem; margin: .45rem 0 0; padding: .7rem; overflow: auto; border-radius: .55rem; color: #5f6863; background: #f4f6f4; font-size: .62rem; line-height: 1.45; white-space: pre-wrap; }
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
.sr-only { position: absolute; width: 1px; height: 1px; padding: 0; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0; }
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
.scheduled-dialog-enter-active, .scheduled-dialog-leave-active { transition: opacity 170ms ease; }
.scheduled-dialog-enter-active .scheduled-modal, .scheduled-dialog-leave-active .scheduled-modal { transition: transform 210ms cubic-bezier(.2,.8,.2,1), opacity 170ms ease; }
.scheduled-dialog-enter-from, .scheduled-dialog-leave-to { opacity: 0; }
.scheduled-dialog-enter-from .scheduled-modal, .scheduled-dialog-leave-to .scheduled-modal { opacity: 0; transform: translateY(.55rem) scale(.985); }
@media (max-width: 1080px) {
  .scheduled-layout { height: auto; min-height: 0; grid-template-columns: 1fr; }
  .scheduled-list-panel { max-height: 20rem; }
  .scheduled-detail { height: auto; overflow: visible; padding-right: 0; }
  .runs-table thead { display: none; }
  .runs-table, .runs-table tbody, .runs-table tr, .runs-table td { display: block; width: 100%; }
  .runs-table tbody { display: grid; gap: .7rem; padding: .75rem; background: #f7f9f7; }
  .runs-table tr { padding: .72rem .8rem; border: 1px solid rgba(29,29,31,.075); border-radius: .72rem; background: #fff; box-shadow: 0 1px 3px rgba(25,34,29,.025); }
  .runs-table td { display: grid; grid-template-columns: 6.5rem minmax(0, 1fr); gap: .65rem; align-items: start; max-width: none; padding: .42rem 0; border: 0; }
  .runs-table td::before { color: #909792; content: attr(data-label); font-size: .58rem; font-weight: 720; letter-spacing: .04em; text-transform: uppercase; }
  .runs-table td:last-child { display: flex; align-items: center; justify-content: space-between; padding-top: .55rem; }
  .runs-pagination { background: #fff; }
}
@media (max-width: 820px) {
  .scheduled-layout { height: auto; min-height: 0; grid-template-columns: 1fr; }
  .scheduled-list-panel { max-height: 22rem; }
  .scheduled-detail { height: auto; overflow: visible; padding-right: 0; }
  .run-detail-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .scheduled-form-grid { grid-template-columns: 1fr; }
  .scheduled-card-header, .scheduled-create footer { align-items: stretch; flex-direction: column; }
  .scheduled-actions { justify-content: flex-start; }
  .scheduled-topbar-actions { align-items: stretch; flex-direction: column-reverse; }
}
@media (max-width: 560px) {
  .scheduled-modal-backdrop { align-items: end; padding: .7rem; }
  .scheduled-modal { max-height: calc(100vh - 1.4rem); border-radius: .9rem; }
  .run-detail-grid { grid-template-columns: 1fr; }
  .scheduled-form-grid { grid-template-columns: 1fr; }
  .scheduled-create footer { align-items: stretch; flex-direction: column; }
  .scheduled-create footer > div { justify-content: flex-end; }
}
</style>
