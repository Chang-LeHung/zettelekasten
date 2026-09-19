<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from '../i18n'

defineProps<{
  command: string
  timeoutSeconds: number
  rememberSupported: boolean
  submitting: boolean
}>()

const emit = defineEmits<{
  execute: [remember: boolean]
  abort: []
}>()

const { t } = useI18n()
const remember = ref(false)
</script>

<template>
  <section class="shell-approval" aria-live="polite">
    <header>
      <div>
        <span>{{ t('shellApproval.title') }}</span>
        <small>{{ t('shellApproval.description', { seconds: timeoutSeconds }) }}</small>
      </div>
      <span class="waiting"><i />{{ t('shellApproval.waiting') }}</span>
    </header>
    <pre><code>{{ command }}</code></pre>
    <footer>
      <label v-if="rememberSupported" class="remember">
        <input v-model="remember" type="checkbox" />
        <span>{{ t('shellApproval.remember') }}</span>
      </label>
      <small v-else>{{ t('shellApproval.once') }}</small>
      <div>
        <button class="abort" type="button" :disabled="submitting" @click="emit('abort')">{{ t('shellApproval.abort') }}</button>
        <button class="execute" type="button" :disabled="submitting" @click="emit('execute', remember)">
          {{ submitting ? t('shellApproval.sending') : t('shellApproval.execute') }}
        </button>
      </div>
    </footer>
  </section>
</template>

<style scoped>
.shell-approval { margin: .55rem .8rem 0; padding: .9rem; border: 1px solid rgba(139,91,57,.18); border-radius: .9rem; background: #fbf8f4; box-shadow: 0 3px 14px rgba(76,52,36,.05); }
.shell-approval header, .shell-approval footer { display: flex; align-items: center; justify-content: space-between; gap: 1rem; }
.shell-approval header > div { display: grid; gap: .14rem; }
.shell-approval header span { color: #76543e; font-size: .67rem; font-weight: 740; letter-spacing: .025em; }
.shell-approval header small, .shell-approval footer small { color: #91857d; font-size: .59rem; }
.waiting { display: inline-flex; align-items: center; gap: .35rem; color: #7b716b; font-size: .58rem; }
.waiting i { width: .36rem; height: .36rem; border-radius: 50%; background: #c88955; box-shadow: 0 0 0 3px rgba(200,137,85,.12); }
pre { margin: .65rem 0; padding: .62rem .7rem; overflow-x: auto; border: 1px solid #eadfd5; border-radius: .62rem; color: #3e342e; background: rgba(255,255,255,.9); font: .67rem/1.55 "SFMono-Regular", Consolas, monospace; white-space: pre-wrap; overflow-wrap: anywhere; }
code { font: inherit; }
.remember { display: inline-flex; align-items: center; gap: .4rem; color: #665b54; font-size: .63rem; cursor: pointer; }
.remember input { accent-color: #7a5b43; }
.shell-approval footer > div { display: flex; gap: .42rem; }
.shell-approval footer button { min-height: 2rem; padding: 0 .75rem; border-radius: .58rem; cursor: pointer; font-size: .66rem; font-weight: 680; }
.shell-approval footer button:disabled { opacity: .5; cursor: default; }
.abort { border: 1px solid #dfd4cc; color: #715d51; background: #fff; }
.execute { border: 1px solid #6f513c; color: #fff; background: #72503a; }
.execute:hover:not(:disabled) { background: #5f402d; }
@media (max-width: 620px) {
  .shell-approval footer { align-items: flex-start; flex-direction: column; }
}
</style>
