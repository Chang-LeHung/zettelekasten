<script setup lang="ts">
import { defineAsyncComponent } from 'vue'
import { workspaceRestoring } from '../../app/artifacts/state'
import { openImagePreview, openMessageImage } from '../../app/assets'
import { raw } from '../../app/composer/state'
import { activeTodos, conversationStarted, conversationTurns } from '../../app/conversation/state'
import { handleAgentThreadScroll, handleAgentThreadWheel, isRunningTurn, isSteeredTurn, isTurnDetailsOpen, toggleTurnExecution, turnAnswerTimeline, turnCacheHitRate, turnDuration, turnExecutionTimeline, turnTask } from '../../app/conversation/stream'
import { conversationId, switchingSessionId } from '../../app/sessions'
import AgentExecution from '../../components/AgentExecution.vue'
import CacheHitRate from '../../components/CacheHitRate.vue'

const MarkdownContent = defineAsyncComponent(() => import('../../components/MarkdownContent.vue'))

/** What Zett produces, each with the sentence that starts it; the user finishes the sentence. */
const STARTERS = [
  { kind: 'card', icon: '◇', title: 'Knowledge card', hint: 'Capture one idea, task or reference.', prompt: 'Make a card about: ' },
  { kind: 'article', icon: '¶', title: 'Article', hint: 'Turn notes or sources into a structured piece.', prompt: 'Write an article about: ' },
  { kind: 'slides', icon: '▤', title: 'Slides', hint: 'A concise deck you can present.', prompt: 'Make a slide deck about: ' },
  { kind: 'latex', icon: '∑', title: 'LaTeX paper', hint: 'A typeset PDF you can compare after every edit.', prompt: 'Write a LaTeX paper about: ' },
  { kind: 'image', icon: '▧', title: 'Image', hint: 'A visual from a short brief.', prompt: 'Create an image of: ' },
] as const
</script>

<template>
  <div ref="agentThread" class="agent-thread" :class="{ empty: !conversationStarted && switchingSessionId === null }" aria-live="polite" @scroll.passive="handleAgentThreadScroll" @wheel.passive="handleAgentThreadWheel">
    <Transition name="session-content" mode="out-in">
      <div v-if="switchingSessionId || workspaceRestoring" key="switching" class="session-switch-state" aria-live="polite">
        <span class="session-switch-spinner" aria-hidden="true" />
        <strong>{{ workspaceRestoring ? 'Restoring conversation' : 'Switching conversation' }}</strong>
        <small>Loading messages and workspace…</small>
      </div>
      <div v-else-if="!conversationStarted" key="welcome" class="agent-welcome starter">
        <span class="feature-icon"><svg><use href="#icon-spark" /></svg></span>
        <h2>{{ $t('What should we make?') }}</h2>
        <p>{{ $t('Describe what you want. Zett turns it into an artifact you can read, edit and keep.') }}</p>
        <div class="starter-grid">
          <button v-for="card in STARTERS" :key="card.kind" type="button" class="starter-card" :class="card.kind" @click="raw = card.prompt"><i aria-hidden="true">{{ card.icon }}</i><strong>{{ $t(card.title) }}</strong><span>{{ $t(card.hint) }}</span></button>
        </div>
        <p class="starter-note">{{ $t('Pick a starting point, or just type. You review every change before it is saved.') }}</p>
      </div>
      <div v-else ref="agentTurnStack" :key="conversationId || 'conversation'" class="turn-stack">
      <article
        v-for="(turn, index) in conversationTurns"
        :key="turn.id"
        class="conversation-turn"
        :class="{ running: isRunningTurn(index) }"
      >
        <section class="turn-prompt" aria-label="User message">
          <div class="turn-prompt-content">
            <div v-if="turn.prompt.steering_status === 'waiting'" class="turn-steering-status">
              <i aria-hidden="true" />
              <span>Will respond immediately after the current tool call or turn finishes.</span>
            </div>
            <template v-if="turn.prompt.parts?.length">
              <template v-for="(part, partIndex) in turn.prompt.parts" :key="`${turn.id}-part-${partIndex}`">
                <div
                  v-if="part.type === 'text' && part.text"
                  class="message-content"
                >
                  <MarkdownContent :content="part.text" />
                </div>
                <button
                  v-else-if="part.type === 'image'"
                  class="turn-prompt-image-button"
                  type="button"
                  :aria-label="`Preview ${part.name}`"
                  @click="openMessageImage(part)"
                >
                  <img class="turn-prompt-image" :src="part.content_url" :alt="part.name" />
                </button>
              </template>
            </template>
            <div v-else-if="turn.prompt.content" class="message-content">
              <MarkdownContent :content="turn.prompt.content" />
            </div>
          </div>
        </section>

        <div class="turn-content">
          <AgentExecution
            :timeline="turnExecutionTimeline(turn, index)"
            :running="isRunningTurn(index)"
            :open="isTurnDetailsOpen(turn, index)"
            :task="turnTask(index)"
            :duration="turnDuration(turn, index)"
            @toggle="toggleTurnExecution(turn, $event)"
            @preview-image="openImagePreview"
          >
            <template #metrics>
              <CacheHitRate class="turn-execution-cache" label="Cache" :rate="turnCacheHitRate(turn, index)" />
            </template>
            <template #tasks>
              <div v-if="isRunningTurn(index) && activeTodos?.todos.length" class="turn-task-list">
                <div><strong>Task progress</strong><small>{{ activeTodos.completed ? 'Completed' : `${(activeTodos.processing_index ?? 0) + 1} of ${activeTodos.todos.length}` }}</small></div>
                <ol>
                  <li v-for="todo in activeTodos.todos" :key="todo.content" :class="todo.status">
                    <i aria-hidden="true">{{ todo.status === 'completed' ? '✓' : todo.status === 'processing' ? '•' : '' }}</i>
                    <span>{{ todo.content }}</span>
                  </li>
                </ol>
              </div>
            </template>
            <template #markdown="{ content }"><MarkdownContent :content="content" /></template>
          </AgentExecution>

          <section class="turn-response" aria-label="Agent response">
            <div class="agent-response-content">
              <template v-for="entry in turnAnswerTimeline(turn, index)" :key="entry.id">
                <MarkdownContent class="final-response" :content="entry.content" />
              </template>
              <span v-if="isRunningTurn(index)" class="streaming-dots compact" aria-label="Generating"><i /><i /><i /></span>
              <p v-else-if="isSteeredTurn(index)" class="turn-steered-note">This turn was steered by a follow-up message.</p>
              <p v-else-if="!turnAnswerTimeline(turn, index).length && !turn.response?.error" class="turn-empty-response">No response was recorded for this turn.</p>
              <div v-if="turn.response?.error" class="turn-error" role="alert">
                <strong>Request failed</strong>
                <span>{{ turn.response.error }}</span>
              </div>
            </div>
          </section>
        </div>
      </article>
      </div>
    </Transition>
  </div>
</template>
