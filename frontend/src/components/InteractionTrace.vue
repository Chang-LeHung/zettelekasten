<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import type { AgentPersistedMessage } from '../api/types'
import { calculateCacheHitRate, formatTokenCount } from '../utils/agentUsage'
import CacheHitRate from './CacheHitRate.vue'
import TraceCopyBlock from './TraceCopyBlock.vue'
import {
  buildInteractionTrace,
  interactionTraceEventKind,
  interactionTraceEventLabel,
  interactionTraceModelRequest,
  interactionTraceTurnAnchor,
  interactionTraceUsage,
  type InteractionTraceTurn,
} from '../utils/interactionTrace'

const props = defineProps<{
  messages: AgentPersistedMessage[]
  loading: boolean
  error: string
  selectedTurnId?: string | null
}>()
const emit = defineEmits<{
  refresh: []
  previewImage: [image: { name: string; url: string }]
  'update:selectedTurnId': [turnId: string]
}>()

const turns = computed(() => buildInteractionTrace(props.messages))
const selectedTurnId = ref<string | null>(props.selectedTurnId || null)
//: A turn named by the caller at mount, such as a trace link, is a location to open at.
const mountedTurnId = props.selectedTurnId || null
const traceDetail = ref<HTMLElement | null>(null)
const selectedTurn = computed(
  () => turns.value.find((turn) => turn.id === selectedTurnId.value) || turns.value.at(-1) || null,
)
//: Every stored message, oldest first: the trace is one transcript, not a filter.
const transcript = computed(() => [...props.messages].sort((left, right) => left.sequence - right.sequence))
//: The message that begins each turn, so the transcript can label the boundary.
const turnStarts = computed(() => {
  const starts = new Map<string, InteractionTraceTurn>()
  for (const turn of turns.value) {
    const first = turn.messages[0]
    if (first) starts.set(first.id, turn)
  }
  return starts
})
//: Every request re-appends the same system instructions, so later copies fold
//: into a collapsed step that still shows the text on demand.
const systemRepeats = computed(() => {
  const firstByText = new Map<string, AgentPersistedMessage>()
  const repeats = new Map<string, AgentPersistedMessage>()
  for (const message of transcript.value) {
    if (message.role !== 'system' || !message.content) continue
    const first = firstByText.get(message.content)
    if (first) repeats.set(message.id, first)
    else firstByText.set(message.content, message)
  }
  return repeats
})

watch(() => props.selectedTurnId, (turnId) => {
  if (!turnId) return
  selectedTurnId.value = turnId
  // A turn selected from outside the rail, such as a trace link, is a location too.
  void scrollToTurn(turnId)
})

onMounted(() => {
  if (mountedTurnId) void scrollToTurn(mountedTurnId)
})

watch(turns, (nextTurns) => {
  if (!nextTurns.some((turn) => turn.id === selectedTurnId.value)) {
    selectedTurnId.value = nextTurns.at(-1)?.id || null
    if (selectedTurnId.value) emit('update:selectedTurnId', selectedTurnId.value)
  }
}, { immediate: true })

function selectTurn(turnId: string): void {
  selectedTurnId.value = turnId
  emit('update:selectedTurnId', turnId)
  void scrollToTurn(turnId)
}

/** Scroll the transcript to the user message that started one turn. */
async function scrollToTurn(turnId: string): Promise<void> {
  const turn = turns.value.find((candidate) => candidate.id === turnId)
  const anchor = turn && interactionTraceTurnAnchor(turn)
  await nextTick()
  if (!anchor) return
  const element = traceDetail.value?.querySelector<HTMLElement>(`[data-message-id="${anchor.id}"]`)
  element?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

function turnTitle(turn: InteractionTraceTurn): string {
  const prompt = turn.messages.find((message) => message.role === 'user')?.content
  const normalized = prompt?.replace(/\s+/g, ' ').trim()
  return normalized ? (normalized.length > 54 ? `${normalized.slice(0, 53)}…` : normalized) : `Turn ${turn.index}`
}

function turnModelLabel(turn: InteractionTraceTurn): string {
  return turn.models.map((identity) => identity.model || 'Unknown model').join(' → ') || 'Model call'
}

/** Return the first identical system instruction, when this one repeats it. */
function repeatedSystemMessage(message: AgentPersistedMessage): AgentPersistedMessage | null {
  return systemRepeats.value.get(message.id) || null
}

function turnProviderLabel(turn: InteractionTraceTurn): string {
  return [...new Set(turn.models.map((identity) => identity.provider).filter((provider) => provider))]
    .join(' → ')
}

function formatDuration(milliseconds: number): string {
  if (milliseconds < 1_000) return `${Math.round(milliseconds)} ms`
  return `${(milliseconds / 1_000).toFixed(milliseconds < 10_000 ? 2 : 1)} s`
}

function formatTime(value: string): string {
  const normalized = value.includes('T') ? value : value.replace(' ', 'T')
  const includesTimezone = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(normalized)
  const date = new Date(includesTimezone ? normalized : `${normalized}Z`)
  return new Intl.DateTimeFormat(undefined, {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  }).format(date)
}

function formatJson(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}

function formatTraceText(message: AgentPersistedMessage, value: string): string {
  if (message.role !== 'tool' || !value.trim()) return value
  try {
    return JSON.stringify(JSON.parse(value), null, 2)
  } catch {
    return value
  }
}

function cacheHitRate(message: AgentPersistedMessage): number | null {
  if (message.role !== 'assistant') return null
  if (message.cache_hit_rate !== null) return message.cache_hit_rate
  return calculateCacheHitRate(interactionTraceUsage(message))
}
</script>

<template>
  <section class="interaction-trace" aria-label="LLM interaction trace">
    <header class="trace-header">
      <div>
        <p>Raw message storage</p>
        <h1>LLM interaction trace</h1>
        <span>{{ turns.length }} {{ turns.length === 1 ? 'turn' : 'turns' }}</span>
      </div>
      <button
        class="trace-refresh"
        type="button"
        :disabled="loading"
        :title="loading ? 'Refreshing…' : 'Refresh'"
        :aria-label="loading ? 'Refreshing…' : 'Refresh'"
        @click="emit('refresh')"
      >
        <svg :class="{ spinning: loading }" aria-hidden="true"><use href="#icon-refresh" /></svg>
      </button>
    </header>

    <div v-if="loading && !turns.length" class="trace-state">Loading interaction trace…</div>
    <div v-else-if="error" class="trace-state error" role="alert">
      <strong>Trace unavailable</strong>
      <span>{{ error }}</span>
      <button type="button" @click="emit('refresh')">Try again</button>
    </div>
    <div v-else-if="!turns.length" class="trace-state">
      <strong>No interaction trace yet</strong>
      <span>Send a message to record the first model request.</span>
    </div>

    <div v-else class="trace-layout">
      <aside class="trace-turn-list" aria-label="Conversation turns">
        <button
          v-for="turn in turns"
          :key="turn.id"
          type="button"
          :class="{ active: selectedTurn?.id === turn.id }"
          @click="selectTurn(turn.id)"
        >
          <span class="trace-turn-top">
            <span class="trace-turn-index">Turn {{ turn.index }}</span>
            <CacheHitRate
              v-if="turn.usage"
              class="trace-turn-cache"
              label="Cache"
              :rate="calculateCacheHitRate(turn.usage)"
            />
          </span>
          <strong>{{ turnTitle(turn) }}</strong>
          <small>{{ turn.messages.length }} events · {{ formatDuration(turn.duration_ms) }}</small>
        </button>
      </aside>

      <div ref="traceDetail" class="trace-detail">
        <ol class="trace-events">
          <template v-for="message in transcript" :key="message.id">
          <li
            v-if="turnStarts.get(message.id)"
            class="trace-turn-divider"
          >
            <span class="trace-turn-index">Turn {{ turnStarts.get(message.id)?.index }}</span>
            <strong>{{ turnModelLabel(turnStarts.get(message.id)!) }}</strong>
            <small v-if="turnProviderLabel(turnStarts.get(message.id)!)">{{ turnProviderLabel(turnStarts.get(message.id)!) }}</small>
            <em>{{ turnStarts.get(message.id)?.messages.length }} events · {{ formatDuration(turnStarts.get(message.id)?.duration_ms || 0) }}</em>
          </li>
          <li
            class="trace-event"
            :class="interactionTraceEventKind(message)"
            :data-message-id="message.id"
          >
            <div class="trace-event-rail" aria-hidden="true"><i /></div>
            <div class="trace-event-content">
              <header>
                <div>
                  <strong>{{ interactionTraceEventLabel(message) }}</strong>
                  <small>#{{ message.sequence }} · {{ formatTime(message.started_at) }}</small>
                </div>
                <div class="trace-event-meta">
                  <span v-if="message.duration_ns">{{ formatDuration(message.duration_ns / 1_000_000) }}</span>
                  <span v-if="message.tool_name">{{ message.tool_name }}</span>
                </div>
              </header>

              <div v-if="message.parts.length" class="trace-message-parts">
                <template v-for="(part, partIndex) in message.parts" :key="`${message.id}-part-${partIndex}`">
                  <TraceCopyBlock v-if="part.type === 'text'" flush :content="formatTraceText(message, part.text)" />
                  <button
                    v-else
                    class="trace-message-image-button"
                    type="button"
                    :aria-label="`Preview ${part.name}`"
                    @click="emit('previewImage', { name: part.name, url: part.content_url })"
                  >
                    <img :src="part.content_url" :alt="part.name" />
                  </button>
                </template>
              </div>
              <details
                v-else-if="message.content && repeatedSystemMessage(message)"
                class="trace-payload trace-system-repeat"
              >
                <summary>
                  System instruction
                  <small>{{ message.content.length.toLocaleString() }} chars · same as #{{ repeatedSystemMessage(message)?.sequence }}</small>
                </summary>
                <TraceCopyBlock :content="formatTraceText(message, message.content)" />
              </details>
              <TraceCopyBlock
                v-else-if="message.content"
                class="trace-message-content"
                :content="formatTraceText(message, message.content)"
              />

              <details v-if="message.reasoning_content" class="trace-payload">
                <summary>Reasoning</summary>
                <TraceCopyBlock :content="message.reasoning_content" />
              </details>

              <details v-if="message.tool_calls.length" class="trace-payload">
                <summary>{{ message.tool_calls.length }} tool {{ message.tool_calls.length === 1 ? 'call' : 'calls' }}</summary>
                <div v-for="call in message.tool_calls" :key="call.id" class="trace-tool-call">
                  <strong>{{ call.name }}</strong>
                  <small>{{ call.id }}</small>
                  <TraceCopyBlock compact label="arguments" :content="formatJson(call.arguments)" />
                </div>
              </details>

              <details v-if="interactionTraceModelRequest(message)" class="trace-payload trace-tool-definitions">
                <summary>
                  Tool definitions
                  <small>
                    {{ interactionTraceModelRequest(message)?.tools.length || 0 }} local ·
                    {{ interactionTraceModelRequest(message)?.server_tools.length || 0 }} provider
                  </small>
                </summary>
                <section v-if="interactionTraceModelRequest(message)?.tools.length" class="trace-tool-section">
                  <h3>Local tools</h3>
                  <article
                    v-for="tool in interactionTraceModelRequest(message)?.tools || []"
                    :key="tool.name"
                    class="trace-tool-definition"
                  >
                    <header>
                      <strong>{{ tool.name }}</strong>
                      <span v-if="tool.deferred">Deferred</span>
                    </header>
                    <p>{{ tool.description }}</p>
                    <TraceCopyBlock compact label="parameters" :content="formatJson(tool.parameters)" />
                  </article>
                </section>
                <section v-if="interactionTraceModelRequest(message)?.server_tools.length" class="trace-tool-section">
                  <h3>Provider tools</h3>
                  <article
                    v-for="tool in interactionTraceModelRequest(message)?.server_tools || []"
                    :key="tool.type"
                    class="trace-tool-definition"
                  >
                    <header><strong>{{ tool.type }}</strong><span>Provider</span></header>
                    <TraceCopyBlock compact label="configuration" :content="formatJson(tool.configuration)" />
                  </article>
                </section>
              </details>

              <div v-if="interactionTraceUsage(message)" class="trace-event-usage">
                <span>Input {{ formatTokenCount(interactionTraceUsage(message)!.input_tokens) }}</span>
                <span>Output {{ formatTokenCount(interactionTraceUsage(message)!.output_tokens) }}</span>
                <span>Cache {{ formatTokenCount(interactionTraceUsage(message)!.cache_read_tokens) }}</span>
                <span>Reasoning {{ formatTokenCount(interactionTraceUsage(message)!.reasoning_tokens) }}</span>
                <CacheHitRate class="trace-cache-rate" :rate="cacheHitRate(message)" />
              </div>
            </div>
          </li>
          </template>
        </ol>
      </div>
    </div>
  </section>
</template>

<style scoped>
.interaction-trace { height: 100%; min-height: 0; display: grid; grid-template-rows: auto minmax(0, 1fr); overflow: hidden; border: 1px solid rgba(29,29,31,.08); border-radius: .8rem; background: rgba(255,255,255,.9); box-shadow: var(--shadow); }
.trace-header { position: sticky; top: 0; z-index: 2; display: flex; align-items: center; justify-content: space-between; gap: 1rem; padding: 1rem 1.15rem; border-bottom: 1px solid var(--line); background: rgba(250,251,250,.95); backdrop-filter: blur(16px); }
.trace-header p { margin: 0 0 .2rem; color: var(--accent); font-size: .58rem; font-weight: 720; letter-spacing: .07em; text-transform: uppercase; }
.trace-header h1 { margin: 0; color: #343a36; font-size: 1.05rem; letter-spacing: -.02em; }
.trace-header span { display: block; margin-top: .18rem; color: var(--tertiary); font-size: .62rem; }
.trace-header button, .trace-state button { min-height: 2rem; padding: 0 .7rem; border: 1px solid #cfd8d2; border-radius: .52rem; color: #355442; background: #f7f9f8; cursor: pointer; font-size: .64rem; font-weight: 650; }
.trace-header button:disabled { opacity: .5; cursor: wait; }
.trace-header button.trace-refresh { width: 2rem; min-height: 2rem; display: grid; place-items: center; padding: 0; color: #4f5c55; }
.trace-header button.trace-refresh:hover:not(:disabled) { color: #31523f; background: #edf3ef; }
.trace-header button.trace-refresh svg { width: .95rem; height: .95rem; }
.trace-header button.trace-refresh svg.spinning { animation: trace-refresh-spin 900ms linear infinite; }
@keyframes trace-refresh-spin { to { transform: rotate(360deg); } }
.trace-layout { min-height: 0; display: grid; grid-template-columns: minmax(11rem, 14rem) minmax(0, 1fr); }
.trace-turn-list { min-height: 0; display: grid; align-content: start; gap: .42rem; padding: .65rem; overflow-y: auto; border-right: 1px solid #e4e9e6; background: #f6f8f6; scrollbar-width: thin; }
.trace-turn-list button { width: 100%; display: grid; gap: .3rem; padding: .68rem .72rem .66rem; border: 1px solid rgba(68,88,76,.08); border-radius: .58rem; color: #66716a; background: rgba(255,255,255,.55); cursor: pointer; text-align: left; transition: border-color 150ms ease, background 150ms ease, box-shadow 150ms ease; }
.trace-turn-list button:hover { border-color: rgba(76,112,91,.2); background: #fff; }
.trace-turn-list button.active { border-color: rgba(76,112,91,.2); color: #31523f; background: #fff; box-shadow: 0 2px 8px rgba(39,57,47,.08); }
.trace-turn-top { min-width: 0; display: flex; align-items: center; justify-content: space-between; gap: .45rem; }
.trace-turn-index { color: #849188; font-size: .5rem; font-weight: 740; letter-spacing: .075em; text-transform: uppercase; }
.trace-turn-list button strong { overflow: hidden; color: #3f4a43; font-size: .72rem; font-weight: 670; line-height: 1.38; text-overflow: ellipsis; white-space: nowrap; }
.trace-turn-list button.active strong { color: #2f4c3b; }
.trace-turn-list button small { overflow: hidden; color: #9aa19d; font-size: .5rem; font-variant-numeric: tabular-nums; text-overflow: ellipsis; white-space: nowrap; }
.trace-turn-cache { flex: 0 0 auto; opacity: .72; font-size: .48rem; }
.trace-detail { min-height: 0; padding: 1rem; overflow-y: auto; scrollbar-width: thin; }
.trace-turn-index { color: #54705f; font-size: .56rem; font-weight: 720; letter-spacing: .06em; text-transform: uppercase; }
.trace-turn-divider { position: sticky; top: 0; z-index: 1; display: flex; flex-wrap: wrap; align-items: center; gap: .42rem; margin: .35rem 0 .05rem; padding: .55rem .62rem; border: 1px solid rgba(56,74,64,.12); border-radius: .6rem; background: rgba(247,249,247,.96); backdrop-filter: blur(10px); scroll-margin-top: .8rem; }
.trace-turn-divider strong { color: #354039; font-size: .72rem; }
.trace-turn-divider small { color: #848c87; font-size: .56rem; }
.trace-turn-divider em { margin-left: auto; color: #7b847f; font-size: .56rem; font-style: normal; font-variant-numeric: tabular-nums; }
.trace-event-meta span, .trace-event-usage span { padding: .22rem .42rem; border-radius: 1rem; color: #627068; background: #e9efeb; font-size: .56rem; font-variant-numeric: tabular-nums; }
.trace-events { display: grid; gap: .52rem; margin: 0; padding: .65rem .8rem .8rem; list-style: none; }
.trace-event { position: relative; display: grid; grid-template-columns: 1.15rem minmax(0, 1fr); gap: .55rem; scroll-margin-top: 3.2rem; }
.trace-event-rail { position: relative; display: flex; justify-content: center; }
.trace-event-rail::after { content: ""; position: absolute; top: 1.1rem; bottom: -.68rem; width: 1px; background: #dfe5e1; }
.trace-event:last-child .trace-event-rail::after { display: none; }
.trace-event-rail i { position: relative; z-index: 1; width: .55rem; height: .55rem; margin-top: .85rem; border: 2px solid #fff; border-radius: 50%; background: #7d9284; box-shadow: 0 0 0 1px #cfd8d2; }
.trace-event.user .trace-event-rail i { background: #4d7dac; }
.trace-event.model .trace-event-rail i { background: #557b65; }
.trace-event.tool .trace-event-rail i { background: #c08b45; }
.trace-event.system .trace-event-rail i, .trace-event.agent .trace-event-rail i { background: #78818b; }
.trace-event-content { min-width: 0; padding: .72rem .56rem .76rem; border-bottom: 1px solid #edf0ee; border-radius: .48rem; }
.trace-event:last-child .trace-event-content { border-bottom: 0; }
.trace-event-content > header { display: flex; align-items: flex-start; justify-content: space-between; gap: .8rem; }
.trace-event-content > header strong, .trace-event-content > header small { display: block; }
.trace-event-content > header strong { color: #3d4841; font-size: .68rem; }
.trace-event-content > header small { margin-top: .13rem; color: #909892; font-size: .55rem; }
.trace-event.user .trace-event-content { background: rgba(65, 112, 158, .055); }
.trace-event.user .trace-event-content > header strong { color: #3f6f9e; }
.trace-event.model .trace-event-content { background: rgba(79, 123, 99, .055); }
.trace-event.model .trace-event-content > header strong { color: #3f6d55; }
.trace-event.tool .trace-event-content { background: rgba(181, 126, 53, .06); }
.trace-event.tool .trace-event-content > header strong { color: #9a682a; }
.trace-event.system .trace-event-content, .trace-event.agent .trace-event-content { background: rgba(103, 112, 121, .045); }
.trace-event.system .trace-event-content > header strong, .trace-event.agent .trace-event-content > header strong { color: #65707a; }
.trace-event-meta { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: .28rem; }
.trace-message-parts { display: grid; gap: .42rem; margin-top: .5rem; }
.trace-message-image-button { width: fit-content; max-width: 100%; display: block; padding: 0; border: 0; border-radius: .55rem; background: transparent; cursor: zoom-in; }
.trace-message-image-button:hover img { box-shadow: 0 0 0 2px rgba(71,105,87,.22); }
.trace-message-image-button:focus-visible { outline: 3px solid rgba(71,105,87,.24); outline-offset: 2px; }
.trace-message-parts img { max-width: min(100%, 28rem); max-height: 20rem; border: 1px solid #dfe5e1; border-radius: .55rem; object-fit: contain; background: #eef1ef; }
.trace-payload { margin-top: .48rem; }
.trace-payload > summary { width: fit-content; min-height: 1.8rem; display: inline-flex; align-items: center; gap: .34rem; padding: 0 .48rem; border: 1px solid #dce4df; border-radius: .42rem; color: #52645a; background: #f7f9f7; cursor: pointer; font-size: .6rem; font-weight: 650; list-style: none; transition: border-color 140ms ease, background 140ms ease, color 140ms ease; }
.trace-payload > summary::-webkit-details-marker { display: none; }
.trace-payload > summary::before { content: "›"; color: #89958e; font-size: .82rem; line-height: 1; transform: translateY(-.02rem) rotate(0); transition: transform 140ms ease; }
.trace-payload[open] > summary { border-color: #cbd8d0; color: #355442; background: #edf3ef; }
.trace-payload[open] > summary::before { transform: translateY(-.02rem) rotate(90deg); }
.trace-payload > summary:hover, .trace-payload > summary:focus-visible { border-color: #b9cbc0; color: #31523f; background: #edf3ef; outline: none; }
.trace-tool-call { display: grid; gap: .2rem; margin-top: .45rem; }
.trace-tool-call strong { color: #4e6355; font-size: .62rem; }
.trace-tool-call small { color: #929a95; font-size: .53rem; }
.trace-tool-definitions > summary { display: flex; align-items: center; gap: .4rem; }
.trace-tool-definitions > summary small { color: #929a95; font-size: .53rem; font-weight: 500; }
.trace-tool-section { margin-top: .58rem; }
.trace-tool-section h3 { margin: 0 0 .34rem; color: #66736b; font-size: .55rem; font-weight: 720; letter-spacing: .055em; text-transform: uppercase; }
.trace-tool-definition { display: grid; gap: .32rem; margin-top: .38rem; padding: .55rem .6rem; border: 1px solid #e1e7e3; border-radius: .52rem; background: #fafbfa; }
.trace-tool-definition header { display: flex; align-items: center; justify-content: space-between; gap: .5rem; }
.trace-tool-definition header strong { color: #3f5046; font-size: .64rem; }
.trace-tool-definition header span { padding: .12rem .3rem; border-radius: .3rem; color: #5f6c64; background: #e9efeb; font-size: .48rem; font-weight: 680; text-transform: uppercase; }
.trace-tool-definition p { margin: 0; color: #68736c; font-size: .59rem; line-height: 1.45; }
.trace-event-usage { display: flex; flex-wrap: wrap; gap: .28rem; margin-top: .5rem; }
.trace-state { min-height: 18rem; display: grid; place-items: center; align-content: center; gap: .35rem; padding: 2rem; color: #818983; text-align: center; }
.trace-state strong { color: #4b554f; font-size: .82rem; }
.trace-state span { max-width: 26rem; font-size: .68rem; line-height: 1.5; }
.trace-state.error strong, .trace-state.error span { color: #8a504b; }
@media (max-width: 760px) {
  .trace-layout { grid-template-columns: 1fr; grid-template-rows: auto minmax(0, 1fr); }
  .trace-turn-list { grid-auto-flow: column; grid-auto-columns: minmax(11rem, 70vw); overflow-x: auto; overflow-y: hidden; border-right: 0; border-bottom: 1px solid #e4e9e6; }
  .trace-detail { padding: .7rem; }
}
</style>
