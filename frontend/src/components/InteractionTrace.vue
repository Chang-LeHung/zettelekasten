<script setup lang="ts">
import { computed } from 'vue'
import type { AgentPersistedMessage } from '../api/types'
import { formatTokenCount } from '../utils/agentUsage'
import {
  buildInteractionTrace,
  interactionTraceEventKind,
  interactionTraceEventLabel,
  interactionTraceUsage,
} from '../utils/interactionTrace'

const props = defineProps<{
  messages: AgentPersistedMessage[]
  loading: boolean
  error: string
}>()
const emit = defineEmits<{ refresh: [] }>()

const turns = computed(() => buildInteractionTrace(props.messages))

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
</script>

<template>
  <section class="interaction-trace" aria-label="LLM interaction trace">
    <header class="trace-header">
      <div>
        <p>Raw message storage</p>
        <h1>LLM interaction trace</h1>
        <span>{{ turns.length }} {{ turns.length === 1 ? 'turn' : 'turns' }}</span>
      </div>
      <button type="button" :disabled="loading" @click="emit('refresh')">
        {{ loading ? 'Refreshing…' : 'Refresh' }}
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

    <div v-else class="trace-turns">
      <article v-for="turn in turns" :key="turn.id" class="trace-turn">
        <header class="trace-turn-header">
          <div>
            <span class="trace-turn-index">Turn {{ turn.index }}</span>
            <strong>{{ turn.model || 'Model call' }}</strong>
            <small v-if="turn.provider">{{ turn.provider }}</small>
          </div>
          <div class="trace-turn-summary">
            <span>{{ turn.messages.length }} events</span>
            <span>{{ formatDuration(turn.duration_ms) }}</span>
            <span v-if="turn.usage">Input {{ formatTokenCount(turn.usage.input_tokens) }}</span>
            <span v-if="turn.usage">Output {{ formatTokenCount(turn.usage.output_tokens) }}</span>
            <span v-if="turn.usage?.reasoning_tokens">Reasoning {{ formatTokenCount(turn.usage.reasoning_tokens) }}</span>
          </div>
        </header>

        <ol class="trace-events">
          <li
            v-for="message in turn.messages"
            :key="message.id"
            class="trace-event"
            :class="interactionTraceEventKind(message)"
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
                  <span v-if="message.model">{{ message.model }}</span>
                  <span v-if="message.tool_name">{{ message.tool_name }}</span>
                </div>
              </header>

              <div v-if="message.parts.length" class="trace-message-parts">
                <template v-for="(part, partIndex) in message.parts" :key="`${message.id}-part-${partIndex}`">
                  <pre v-if="part.type === 'text'">{{ part.text }}</pre>
                  <img v-else :src="part.content_url" :alt="part.name" />
                </template>
              </div>
              <pre v-else-if="message.content" class="trace-message-content">{{ message.content }}</pre>

              <details v-if="message.reasoning_content" class="trace-payload">
                <summary>Reasoning</summary>
                <pre>{{ message.reasoning_content }}</pre>
              </details>

              <details v-if="message.tool_calls.length" class="trace-payload">
                <summary>{{ message.tool_calls.length }} tool {{ message.tool_calls.length === 1 ? 'call' : 'calls' }}</summary>
                <div v-for="call in message.tool_calls" :key="call.id" class="trace-tool-call">
                  <strong>{{ call.name }}</strong>
                  <small>{{ call.id }}</small>
                  <pre>{{ formatJson(call.arguments) }}</pre>
                </div>
              </details>

              <div v-if="interactionTraceUsage(message)" class="trace-event-usage">
                <span>Input {{ formatTokenCount(interactionTraceUsage(message)!.input_tokens) }}</span>
                <span>Output {{ formatTokenCount(interactionTraceUsage(message)!.output_tokens) }}</span>
                <span>Cache {{ formatTokenCount(interactionTraceUsage(message)!.cache_read_tokens) }}</span>
                <span>Reasoning {{ formatTokenCount(interactionTraceUsage(message)!.reasoning_tokens) }}</span>
              </div>
            </div>
          </li>
        </ol>
      </article>
    </div>
  </section>
</template>

<style scoped>
.interaction-trace { height: 100%; min-height: 0; overflow: auto; border: 1px solid rgba(29,29,31,.08); border-radius: .8rem; background: rgba(255,255,255,.9); box-shadow: var(--shadow); scrollbar-width: thin; }
.trace-header { position: sticky; top: 0; z-index: 2; display: flex; align-items: center; justify-content: space-between; gap: 1rem; padding: 1rem 1.15rem; border-bottom: 1px solid var(--line); background: rgba(250,251,250,.95); backdrop-filter: blur(16px); }
.trace-header p { margin: 0 0 .2rem; color: var(--accent); font-size: .58rem; font-weight: 720; letter-spacing: .07em; text-transform: uppercase; }
.trace-header h1 { margin: 0; color: #343a36; font-size: 1.05rem; letter-spacing: -.02em; }
.trace-header span { display: block; margin-top: .18rem; color: var(--tertiary); font-size: .62rem; }
.trace-header button, .trace-state button { min-height: 2rem; padding: 0 .7rem; border: 1px solid #cfd8d2; border-radius: .52rem; color: #355442; background: #f7f9f8; cursor: pointer; font-size: .64rem; font-weight: 650; }
.trace-header button:disabled { opacity: .5; cursor: wait; }
.trace-turns { display: grid; gap: .8rem; padding: 1rem; }
.trace-turn { overflow: hidden; border: 1px solid rgba(56,74,64,.1); border-radius: .72rem; background: #fff; }
.trace-turn-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 1rem; padding: .8rem .9rem; border-bottom: 1px solid #e8ece9; background: #f7f9f7; }
.trace-turn-header strong, .trace-turn-header small { display: block; }
.trace-turn-header strong { margin-top: .18rem; color: #354039; font-size: .76rem; }
.trace-turn-header small { margin-top: .12rem; color: #848c87; font-size: .58rem; }
.trace-turn-index { color: #54705f; font-size: .56rem; font-weight: 720; letter-spacing: .06em; text-transform: uppercase; }
.trace-turn-summary { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: .3rem; }
.trace-turn-summary span, .trace-event-meta span, .trace-event-usage span { padding: .22rem .42rem; border-radius: 1rem; color: #627068; background: #e9efeb; font-size: .56rem; font-variant-numeric: tabular-nums; }
.trace-events { display: grid; margin: 0; padding: .65rem .8rem .8rem; list-style: none; }
.trace-event { position: relative; display: grid; grid-template-columns: 1.15rem minmax(0, 1fr); gap: .55rem; }
.trace-event-rail { position: relative; display: flex; justify-content: center; }
.trace-event-rail::after { content: ""; position: absolute; top: 1.1rem; bottom: -.2rem; width: 1px; background: #dfe5e1; }
.trace-event:last-child .trace-event-rail::after { display: none; }
.trace-event-rail i { position: relative; z-index: 1; width: .55rem; height: .55rem; margin-top: .85rem; border: 2px solid #fff; border-radius: 50%; background: #7d9284; box-shadow: 0 0 0 1px #cfd8d2; }
.trace-event.model .trace-event-rail i { background: #557b65; }
.trace-event.tool .trace-event-rail i { background: #c08b45; }
.trace-event.system .trace-event-rail i, .trace-event.agent .trace-event-rail i { background: #78818b; }
.trace-event-content { min-width: 0; padding: .65rem 0 .6rem; border-bottom: 1px solid #edf0ee; }
.trace-event:last-child .trace-event-content { border-bottom: 0; }
.trace-event-content > header { display: flex; align-items: flex-start; justify-content: space-between; gap: .8rem; }
.trace-event-content > header strong, .trace-event-content > header small { display: block; }
.trace-event-content > header strong { color: #3d4841; font-size: .68rem; }
.trace-event-content > header small { margin-top: .13rem; color: #909892; font-size: .55rem; }
.trace-event-meta { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: .28rem; }
.trace-message-content, .trace-message-parts pre, .trace-payload pre, .trace-tool-call pre { margin: .5rem 0 0; padding: .6rem .68rem; overflow: auto; border-radius: .52rem; color: #3f4a43; background: #f5f7f5; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; font-size: .62rem; line-height: 1.52; white-space: pre-wrap; overflow-wrap: anywhere; }
.trace-message-parts { display: grid; gap: .42rem; margin-top: .5rem; }
.trace-message-parts pre { margin: 0; }
.trace-message-parts img { max-width: min(100%, 28rem); max-height: 20rem; border: 1px solid #dfe5e1; border-radius: .55rem; object-fit: contain; background: #eef1ef; }
.trace-payload { margin-top: .48rem; }
.trace-payload summary { color: #5d6a62; cursor: pointer; font-size: .6rem; font-weight: 650; }
.trace-tool-call { display: grid; gap: .2rem; margin-top: .45rem; }
.trace-tool-call strong { color: #4e6355; font-size: .62rem; }
.trace-tool-call small { color: #929a95; font-size: .53rem; }
.trace-event-usage { display: flex; flex-wrap: wrap; gap: .28rem; margin-top: .5rem; }
.trace-state { min-height: 18rem; display: grid; place-items: center; align-content: center; gap: .35rem; padding: 2rem; color: #818983; text-align: center; }
.trace-state strong { color: #4b554f; font-size: .82rem; }
.trace-state span { max-width: 26rem; font-size: .68rem; line-height: 1.5; }
.trace-state.error strong, .trace-state.error span { color: #8a504b; }
</style>
