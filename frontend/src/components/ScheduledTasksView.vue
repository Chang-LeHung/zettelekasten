<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { aiClient, scheduledTaskClient } from '../api/client'
import type { AIProvider, ReasoningEffort, ScheduledTask, ScheduledTaskInput, ScheduledTaskRun } from '../api/types'
import { message, validCronShape, validTimeZone, actionPrompt, formatDate } from '../utils/scheduledTaskPresentation'
import ScheduledRunDetail from './scheduledTasks/ScheduledRunDetail.vue'
import ScheduledRunsTable from './scheduledTasks/ScheduledRunsTable.vue'
import ScheduledTaskForm from './scheduledTasks/ScheduledTaskForm.vue'

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
      <button class="secondary-action refresh-scheduled-tasks" type="button" :disabled="loading" aria-label="Refresh" title="Refresh" @click="loadTasks()">
        <span v-if="loading" class="button-spinner" aria-hidden="true" />
        <svg v-else><use href="#icon-refresh" /></svg>
      </button>
      <button class="primary-action new-scheduled-task-button" type="button" @click="formOpen = true">
        <svg><use href="#icon-add" /></svg>
        New task
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
        <div v-else class="empty-hint">
          <svg><use href="#icon-schedule" /></svg>
          <strong>No scheduled tasks yet</strong>
          <p>Run a prompt on a schedule and read what it produced while you were away.</p>
          <button class="secondary-action" type="button" @click="formOpen = true">Create a task</button>
        </div>
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
          <ScheduledRunsTable
            v-else-if="runs.length"
            :runs="runs"
            :run-page="runPage"
            :run-page-size="runPageSize"
            :runs-have-next="runsHaveNext"
            @open="openRunDetail"
            @open-session="emit('openSession', $event)"
            @change-page="changeRunPage"
          />
          <div v-else class="empty-hint">
            <svg><use href="#icon-conversation" /></svg>
            <strong>No runs yet</strong>
            <p>Each time this task runs, its status and transcript appear here.</p>
          </div>
        </article>
      </div>
    </div>
  </section>

  <ScheduledTaskForm
    :open="formOpen"
    :form="form"
    :providers="enabledProviders"
    :saving="saving"
    :can-create="canCreateTask"
    :expression-valid="expressionValid"
    :timezone-valid="timezoneValid"
    :timeout-valid="timeoutValid"
    @close="formOpen = false"
    @submit="createTask"
  />

  <ScheduledRunDetail
    :open="runDetailOpen"
    :run="selectedRun"
    :task-name="selectedTask?.name"
    @close="closeRunDetail"
    @open-session="emit('openSession', $event)"
  />
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
.run-raw summary { color: #7c867f; cursor: pointer; font-size: .62rem; }
.run-raw pre { max-height: 14rem; margin: .45rem 0 0; padding: .7rem; overflow: auto; border-radius: .55rem; color: #5f6863; background: #f4f6f4; font-size: .62rem; line-height: 1.45; white-space: pre-wrap; }
@media (max-width: 1080px) {
  .scheduled-layout { height: auto; min-height: 0; grid-template-columns: 1fr; }
  .scheduled-list-panel { max-height: 20rem; }
  .scheduled-detail { height: auto; overflow: visible; padding-right: 0; }
}
@media (max-width: 820px) {
  .scheduled-layout { height: auto; min-height: 0; grid-template-columns: 1fr; }
  .scheduled-list-panel { max-height: 22rem; }
  .scheduled-detail { height: auto; overflow: visible; padding-right: 0; }
  .scheduled-card-header, .scheduled-create footer { align-items: stretch; flex-direction: column; }
  .scheduled-actions { justify-content: flex-start; }
  .scheduled-topbar-actions { align-items: stretch; flex-direction: column-reverse; }
}
</style>
