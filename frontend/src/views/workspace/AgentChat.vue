<script setup lang="ts">
import { assetsPaneHidden, openImagePreview, toggleAssetsPane } from '../../app/assets'
import { answerAgentQuestion, attachAskUserImages, removeAskUserImage, respondToShellApproval, toggleAskOption, updateAskAnswer } from '../../app/conversation/askUser'
import { answeringQuestion, askAnswer, askUserImages, pendingQuestion, pendingShellApprovals, queuedQuestions, selectedAskOptions, shellApprovalSubmittingIds } from '../../app/conversation/state'
import { switchingSessionId } from '../../app/sessions'
import AskUserPrompt from '../../components/AskUserPrompt.vue'
import ShellApprovalPrompt from '../../components/ShellApprovalPrompt.vue'
import ConversationComposer from './ConversationComposer.vue'
import ConversationThread from './ConversationThread.vue'
</script>

<template>
  <section class="agent-chat" :class="{ 'session-switching': switchingSessionId !== null }" aria-label="Knowledge card conversation" :aria-busy="switchingSessionId !== null">
    <div class="agent-chat-header">
      <div class="agent-identity"><img src="/logo.png" alt="" /><div><strong>{{ $t('Zettelkasten Agent') }}</strong><small>{{ $t('Turn a conversation into knowledge') }}</small></div></div>
      <button v-if="assetsPaneHidden" class="asset-show-action" type="button" :title="$t('Show assets')" :aria-label="$t('Show assets')" @click="toggleAssetsPane(false)">
        <svg><use href="#icon-eye" /></svg>
        <span>{{ $t('Assets') }}</span>
      </button>
      <span class="streaming-status"><i />{{ $t('Zettelkasten Agent online') }}</span>
    </div>

    <ConversationThread />

    <AskUserPrompt
      v-if="pendingQuestion"
      :question="pendingQuestion.question"
      :options="pendingQuestion.options"
      :allow-multiple="pendingQuestion.allowMultiple"
      :selected-options="selectedAskOptions"
      :answer="askAnswer"
      :images="askUserImages"
      :queued-count="queuedQuestions.length"
      :submitting="answeringQuestion"
      @toggle="toggleAskOption"
      @update:answer="updateAskAnswer"
      @add-images="attachAskUserImages"
      @preview-image="openImagePreview"
      @remove-image="removeAskUserImage"
      @submit="answerAgentQuestion"
    />

    <ShellApprovalPrompt
      v-for="approval in pendingShellApprovals"
      :key="approval.toolCallId"
      :command="approval.command"
      :timeout-seconds="approval.timeoutSeconds"
      :remember-supported="approval.rememberSupported"
      :submitting="shellApprovalSubmittingIds.includes(approval.toolCallId)"
      @execute="remember => respondToShellApproval(approval.toolCallId, 'execute', remember)"
      @abort="respondToShellApproval(approval.toolCallId, 'abort')"
    />

    <ConversationComposer />
  </section>
</template>
