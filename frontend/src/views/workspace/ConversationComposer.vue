<script setup lang="ts">
import { openImagePreview } from '../../app/assets'
import { finishComposerComposition, followUpTokenHighlight, handleComposerSelection, initialTokenHighlight, removeMessageImage, selectAtCommand, selectSlashCommand, syncComposerHighlight, updateComposerText } from '../../app/composer/actions'
import { atCommandsLoaded, atCommandsLoading, atMenu, atMenuActiveIndex, atMenuItems, composerComposing, followUp, pendingMessageImages, raw, slashCommandsLoaded, slashCommandsLoading, slashMenu, slashMenuActiveIndex, slashMenuItems } from '../../app/composer/state'
import { updateShellApprovalMode } from '../../app/conversation/askUser'
import { dropQueuedFollowUp, endQueuedFollowUpDrag, queuedFollowUpText, removeQueuedFollowUp, startQueuedFollowUpDrag, steerQueuedFollowUp } from '../../app/conversation/queue'
import { canSubmitMessage, contextComposition, conversationStarted, conversationUsage, currentContextUsage, draggingQueuedFollowUpId, loading, queuedFollowUps, steeringQueuedFollowUpId } from '../../app/conversation/state'
import { handleComposerKeydown, stopGeneration, submitConversation } from '../../app/conversation/turns'
import { providers, reasoningEffort, selectedProviderId, shellApprovalMode } from '../../app/providers'
import { runtimeSettings } from '../../app/settings'
import { navigate } from '../../app/workspace'
import AgentComposerControls from '../../components/AgentComposerControls.vue'
import ComposerCommandMenu from '../../components/ComposerCommandMenu.vue'
</script>

<template>
  <div class="agent-composer-stack">
    <div v-if="queuedFollowUps.length" class="queued-followup-list" aria-label="Queued follow-up messages" aria-live="polite">
      <article
        v-for="item in queuedFollowUps"
        :key="item.id"
        class="queued-followup"
        :class="{ dragging: draggingQueuedFollowUpId === item.id }"
        @dragover.prevent
        @drop.prevent="dropQueuedFollowUp(item, $event)"
      >
        <button
          class="queued-followup-drag"
          type="button"
          draggable="true"
          title="Drag to reorder"
          aria-label="Drag to reorder"
          @dragstart.stop="startQueuedFollowUpDrag(item, $event)"
          @dragend.stop="endQueuedFollowUpDrag"
        >
          <svg viewBox="0 0 20 20" aria-hidden="true"><circle cx="7" cy="5" r="1" /><circle cx="13" cy="5" r="1" /><circle cx="7" cy="10" r="1" /><circle cx="13" cy="10" r="1" /><circle cx="7" cy="15" r="1" /><circle cx="13" cy="15" r="1" /></svg>
        </button>
        <span class="queued-followup-icon" aria-hidden="true"><svg><use href="#icon-conversation" /></svg></span>
        <div class="queued-followup-copy">
          <p>{{ queuedFollowUpText(item) }}</p>
          <div v-if="item.parts.some((part) => part.type === 'image')" class="queued-followup-images">
            <template v-for="(part, partIndex) in item.parts" :key="`${item.id}-${partIndex}`">
              <button
                v-if="part.type === 'image'"
                class="queued-followup-image-preview"
                type="button"
                :aria-label="`Preview ${part.name}`"
                @click="openImagePreview({ name: part.name, url: part.content_url })"
              >
                <img :src="part.content_url" :alt="part.name" />
              </button>
            </template>
          </div>
        </div>
        <button
          class="queued-followup-steer"
          type="button"
          :disabled="steeringQueuedFollowUpId === item.id || item.slashCommandId !== null || item.atCommandId !== null"
          :aria-label="`Steer with ${queuedFollowUpText(item)}`"
          title="Apply this follow-up to the active run now"
          @click="steerQueuedFollowUp(item)"
        >
          <svg aria-hidden="true" viewBox="0 0 24 24"><path d="m9 7-5 5 5 5M5 12h8a6 6 0 0 1 6 6" /></svg>
          <span>{{ steeringQueuedFollowUpId === item.id ? 'Sending…' : 'Steer' }}</span>
        </button>
        <button
          class="queued-followup-remove"
          type="button"
          :aria-label="`Remove ${queuedFollowUpText(item)}`"
          @click="removeQueuedFollowUp(item)"
        >
          <svg aria-hidden="true"><use href="#icon-trash" /></svg>
        </button>
      </article>
    </div>
    <form class="agent-input" @submit.prevent="submitConversation">
      <ComposerCommandMenu
        v-if="slashMenu"
        :items="slashMenuItems"
        :active-index="slashMenuActiveIndex"
        :loading="slashCommandsLoading && !slashCommandsLoaded"
        :heading="$t('composer.slashCommands')"
        :hint="$t('composer.selectOneCommand')"
        :empty-label="$t('composer.noSlashCommands')"
        @select="selectSlashCommand"
        @hover="slashMenu = slashMenu ? { ...slashMenu, activeIndex: $event } : null"
      />
      <ComposerCommandMenu
        v-if="atMenu"
        trigger="@"
        :items="atMenuItems"
        :active-index="atMenuActiveIndex"
        :loading="atCommandsLoading && !atCommandsLoaded"
        :heading="$t('composer.references')"
        :hint="$t('composer.selectOneReference')"
        :empty-label="$t('composer.noReferences')"
        @select="selectAtCommand"
        @hover="atMenu = atMenu ? { ...atMenu, activeIndex: $event } : null"
      />
      <div v-if="pendingMessageImages.length" class="message-image-drafts" aria-label="Images attached to this message">
        <figure v-for="image in pendingMessageImages" :key="image.id">
          <button
            class="message-image-preview"
            type="button"
            :aria-label="`Preview ${image.name}`"
            @click="openImagePreview({ name: image.name, url: image.content_url })"
          >
            <img :src="image.content_url" :alt="image.name" />
          </button>
          <button class="message-image-remove" type="button" :aria-label="`Remove ${image.name}`" @click="removeMessageImage(image.id)">×</button>
        </figure>
      </div>
      <div v-if="!conversationStarted" class="composer-textarea-wrap" :class="{ 'token-selected': initialTokenHighlight, composing: composerComposing }">
        <div ref="initialComposerHighlight" class="composer-input-mirror" aria-hidden="true"><template v-if="initialTokenHighlight"><template v-for="(segment, index) in initialTokenHighlight" :key="index"><mark v-if="segment.kind" :class="segment.kind === 'reference' ? 'reference' : ''">{{ segment.text }}</mark><span v-else>{{ segment.text }}</span></template></template><template v-else>{{ raw }}</template></div>
        <textarea
          ref="initialComposerInput"
          :value="raw"
          rows="3"
          autofocus
          :placeholder="$t('composer.messagePlaceholder')"
          @input="updateComposerText($event, 'initial')"
          @scroll.passive="syncComposerHighlight('initial')"
          @compositionstart="composerComposing = true"
          @compositionend="finishComposerComposition"
          @click="handleComposerSelection('initial', $event)"
          @keydown="handleComposerKeydown($event, 'initial')"
        />
      </div>
      <div v-else class="composer-textarea-wrap" :class="{ 'token-selected': followUpTokenHighlight, composing: composerComposing }">
        <div ref="followUpComposerHighlight" class="composer-input-mirror" aria-hidden="true"><template v-if="followUpTokenHighlight"><template v-for="(segment, index) in followUpTokenHighlight" :key="index"><mark v-if="segment.kind" :class="segment.kind === 'reference' ? 'reference' : ''">{{ segment.text }}</mark><span v-else>{{ segment.text }}</span></template></template><template v-else>{{ followUp }}</template></div>
        <textarea
          ref="followUpComposerInput"
          :value="followUp"
          rows="3"
          :placeholder="$t('composer.continuePlaceholder')"
          @input="updateComposerText($event, 'follow-up')"
          @scroll.passive="syncComposerHighlight('follow-up')"
          @compositionstart="composerComposing = true"
          @compositionend="finishComposerComposition"
          @click="handleComposerSelection('follow-up', $event)"
          @keydown="handleComposerKeydown($event, 'follow-up')"
        />
      </div>
      <div class="agent-input-footer">
        <div class="composer-leading">
          <AgentComposerControls
            :providers="providers"
            :selected-provider-id="selectedProviderId"
            :effort="reasoningEffort"
            :shell-approval="shellApprovalMode"
            :disabled="loading"
            :usage="conversationUsage"
            :current-usage="currentContextUsage"
            :context-composition="contextComposition"
            :compaction-max-tokens="runtimeSettings.compaction_max_tokens"
            @update:selected-provider-id="selectedProviderId = $event"
            @update:effort="reasoningEffort = $event"
            @update:shell-approval="updateShellApprovalMode"
            @add-provider="navigate('settings')"
          />
        </div>
        <div class="composer-submit">
          <small>{{ loading ? $t('composer.enterToQueue') : $t('composer.enterToSend') }}</small>
          <button
            class="send-button"
            :class="{ stop: loading }"
            :disabled="!loading && !canSubmitMessage"
            type="button"
            :aria-label="loading ? 'Stop generating' : 'Send message'"
            @click="loading ? stopGeneration() : submitConversation()"
          >
            <svg v-if="loading"><use href="#icon-stop" /></svg>
            <svg v-else><use href="#icon-arrow" /></svg>
          </button>
        </div>
      </div>
    </form>
  </div>
</template>
