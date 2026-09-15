<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, watch } from 'vue'
import type { Tag } from '../api/types'
import { visibleTagRows } from '../utils/tagTree'

const props = defineProps<{
  tags: Tag[]
  busy: boolean
  feedback?: string
  feedbackKind?: 'success' | 'error'
}>()

const emit = defineEmits<{
  close: []
  create: [path: string]
  delete: [tag: Tag]
}>()

const path = ref('')
const pathInput = ref<HTMLInputElement | null>(null)
const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null

void nextTick(() => pathInput.value?.focus())
onBeforeUnmount(() => previousFocus?.focus())
watch(
  () => props.feedback,
  (feedback) => {
    if (feedback && props.feedbackKind === 'success') path.value = ''
  },
)

function submit(): void {
  const value = path.value.trim()
  if (!value || props.busy) return
  emit('create', value)
}
</script>

<template>
  <Teleport to="body">
    <Transition name="tag-manager">
      <div class="tag-manager-backdrop" @click.self="emit('close')" @keydown.esc.stop.prevent="emit('close')">
        <section class="tag-manager-panel" role="dialog" aria-modal="true" aria-labelledby="tag-manager-title">
          <header>
            <div>
              <span>Library taxonomy</span>
              <h2 id="tag-manager-title">Manage collections</h2>
              <p>Create a path with <strong>/</strong> to build nested tags.</p>
            </div>
            <button class="close-button" type="button" aria-label="Close tag manager" @click="emit('close')">×</button>
          </header>

          <form class="tag-create-form" @submit.prevent="submit">
            <label for="tag-path">Tag path</label>
            <div>
              <input id="tag-path" ref="pathInput" v-model="path" :disabled="busy" autocomplete="off" placeholder="Engineering / Python / Asyncio" />
              <button type="submit" :disabled="busy || !path.trim()">
                <svg viewBox="0 0 24 24"><path d="M12 5v14M5 12h14" /></svg>
                {{ busy ? 'Saving…' : 'Add tag' }}
              </button>
            </div>
            <p v-if="feedback" class="tag-manager-feedback" :class="feedbackKind" :role="feedbackKind === 'error' ? 'alert' : 'status'">
              <svg v-if="feedbackKind !== 'error'" viewBox="0 0 24 24"><path d="m5 12 4 4L19 6" /></svg>
              <span>{{ feedback }}</span>
            </p>
          </form>

          <div class="tag-manager-list" aria-live="polite">
            <div v-if="tags.length" class="tag-list-heading"><span>Tags</span><small>{{ visibleTagRows(tags).length }} total</small></div>
            <div
              v-for="tag in visibleTagRows(tags)"
              :key="tag.id"
              class="managed-tag"
              :style="{ '--tag-depth': tag.depth }"
            >
              <span class="managed-tag-branch" aria-hidden="true" />
              <span class="managed-tag-dot" :style="tag.color ? { background: tag.color } : undefined" />
              <span class="managed-tag-copy"><strong>{{ tag.name }}</strong><small>{{ tag.path }}</small></span>
              <span class="managed-tag-count">{{ tag.total_count }} {{ tag.total_count === 1 ? 'item' : 'items' }}</span>
              <button class="delete-tag-button" type="button" :disabled="busy" :aria-label="`Delete ${tag.path}`" :title="`Delete ${tag.path}`" @click="emit('delete', tag)">
                <svg viewBox="0 0 24 24"><path d="M4 7h16M9 7V4h6v3m3 0-1 13H7L6 7m4 4v5m4-5v5" /></svg>
              </button>
            </div>
            <div v-if="!tags.length" class="tag-manager-empty">
              <span>#</span>
              <strong>No tags yet</strong>
              <p>Add a path above to create your first collection.</p>
            </div>
          </div>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.tag-manager-backdrop { position: fixed; inset: 0; z-index: 900; display: grid; place-items: center; padding: 1.25rem; background: rgba(35, 42, 38, .22); backdrop-filter: blur(12px) saturate(115%); }
.tag-manager-panel { width: min(100%, 38rem); max-height: min(46rem, calc(100vh - 2.5rem)); overflow: hidden; border: 1px solid rgba(60, 72, 65, .12); border-radius: 1.35rem; background: rgba(255, 255, 255, .98); box-shadow: 0 30px 90px rgba(31, 42, 35, .2), 0 2px 8px rgba(31, 42, 35, .08); }
.tag-manager-panel > header { display: flex; align-items: flex-start; justify-content: space-between; gap: 1rem; padding: 1.45rem 1.5rem 1.1rem; }
.tag-manager-panel header span { color: #557662; font-size: .64rem; font-weight: 750; letter-spacing: .09em; text-transform: uppercase; }
.tag-manager-panel h2 { margin: .28rem 0 .3rem; color: #262c28; font-size: 1.35rem; line-height: 1.2; letter-spacing: -.025em; }
.tag-manager-panel header p { margin: 0; color: #858c87; font-size: .76rem; }
.tag-manager-panel header strong { color: #5c6f63; }
.close-button { width: 2.15rem; height: 2.15rem; flex: 0 0 auto; border: 1px solid #e1e6e2; border-radius: .72rem; color: #69726c; background: #f8f9f8; cursor: pointer; font-size: 1.35rem; line-height: 1; }
.close-button:hover { color: #35453b; background: #f0f4f1; }
.tag-create-form { padding: 0 1.5rem 1.3rem; border-bottom: 1px solid #e8ebe9; }
.tag-create-form > label { display: block; margin-bottom: .45rem; color: #69726c; font-size: .68rem; font-weight: 700; }
.tag-create-form > div { display: flex; gap: .55rem; }
.tag-create-form input { min-width: 0; flex: 1; height: 2.7rem; padding: 0 .85rem; border: 1px solid #dfe4e1; border-radius: .78rem; outline: none; color: #303632; background: #fafbfa; font: inherit; font-size: .8rem; }
.tag-create-form input:focus { border-color: #8fab99; box-shadow: 0 0 0 3px rgba(76, 119, 94, .1); background: #fff; }
.tag-create-form button { display: inline-flex; align-items: center; justify-content: center; gap: .4rem; min-width: 6.7rem; border: 1px solid #466f58; border-radius: .78rem; color: #fff; background: #4b755d; cursor: pointer; font-size: .73rem; font-weight: 700; box-shadow: 0 5px 14px rgba(50, 91, 67, .16); }
.tag-create-form button:hover:not(:disabled) { background: #41694f; }
.tag-create-form button:disabled { cursor: default; opacity: .55; }
.tag-create-form svg { width: .92rem; height: .92rem; fill: none; stroke: currentColor; stroke-width: 1.8; stroke-linecap: round; }
.tag-manager-feedback { display: flex; align-items: center; gap: .42rem; margin: .65rem 0 0; color: #477159; font-size: .7rem; line-height: 1.4; }
.tag-manager-feedback.error { color: #a14949; }
.tag-manager-feedback svg { width: .9rem; height: .9rem; flex: 0 0 auto; }
.tag-manager-list { max-height: min(27rem, calc(100vh - 15rem)); overflow-y: auto; padding: .75rem 1rem 1rem; }
.tag-list-heading { display: flex; align-items: center; justify-content: space-between; padding: .15rem .5rem .55rem; color: #7b837e; font-size: .66rem; font-weight: 700; letter-spacing: .035em; text-transform: uppercase; }
.tag-list-heading small { color: #a0a6a2; font-size: .62rem; font-weight: 600; letter-spacing: 0; text-transform: none; }
.managed-tag { --tag-depth: 0; display: grid; grid-template-columns: calc(var(--tag-depth) * .85rem) .5rem minmax(0, 1fr) auto 2rem; align-items: center; gap: .62rem; min-height: 3.25rem; padding: .38rem .42rem; border-radius: .78rem; }
.managed-tag:hover { background: #f5f7f5; }
.managed-tag-branch { height: 100%; border-right: calc(var(--tag-depth) * 1px) solid #dce3de; }
.managed-tag-dot { width: .48rem; height: .48rem; border-radius: 50%; background: #7ea08b; box-shadow: 0 0 0 3px #edf3ef; }
.managed-tag-copy { min-width: 0; display: flex; flex-direction: column; gap: .12rem; }
.managed-tag-copy strong { overflow: hidden; color: #414944; font-size: .78rem; font-weight: 680; text-overflow: ellipsis; white-space: nowrap; }
.managed-tag-copy small { overflow: hidden; color: #969d98; font-size: .64rem; text-overflow: ellipsis; white-space: nowrap; }
.managed-tag-count { color: #858d88; font-size: .65rem; white-space: nowrap; }
.delete-tag-button { display: grid; place-items: center; width: 1.9rem; height: 1.9rem; padding: 0; border: 1px solid #ece4e3; border-radius: .58rem; color: #a76868; background: #fffafa; cursor: pointer; opacity: .82; }
.managed-tag:hover .delete-tag-button, .delete-tag-button:focus-visible { color: #a64949; border-color: #eed5d3; opacity: 1; }
.delete-tag-button:hover { color: #a64949; background: #faeceb; }
.delete-tag-button:disabled { cursor: default; opacity: .35; }
.delete-tag-button svg { width: .95rem; height: .95rem; fill: none; stroke: currentColor; stroke-width: 1.75; stroke-linecap: round; stroke-linejoin: round; }
.tag-manager-empty { display: grid; justify-items: center; padding: 3.2rem 1rem; color: #8b938e; text-align: center; }
.tag-manager-empty > span { display: grid; place-items: center; width: 2.5rem; height: 2.5rem; margin-bottom: .7rem; border-radius: .8rem; color: #668572; background: #edf3ef; font-size: 1.15rem; }
.tag-manager-empty strong { color: #515a54; font-size: .82rem; }
.tag-manager-empty p { margin: .25rem 0 0; font-size: .7rem; }
.tag-manager-panel button:focus-visible { outline: 3px solid rgba(71, 105, 87, .18); outline-offset: 2px; }
.tag-manager-enter-active, .tag-manager-leave-active { transition: opacity 170ms ease; }
.tag-manager-enter-active .tag-manager-panel, .tag-manager-leave-active .tag-manager-panel { transition: transform 220ms cubic-bezier(.2, .8, .2, 1), opacity 170ms ease; }
.tag-manager-enter-from, .tag-manager-leave-to { opacity: 0; }
.tag-manager-enter-from .tag-manager-panel, .tag-manager-leave-to .tag-manager-panel { opacity: 0; transform: translateY(.55rem) scale(.98); }
@media (max-width: 560px) {
  .tag-manager-backdrop { align-items: end; padding: .7rem; }
  .tag-manager-panel { max-height: calc(100vh - 1.4rem); border-radius: 1.15rem; }
  .tag-create-form > div { align-items: stretch; flex-direction: column; }
  .tag-create-form button { min-height: 2.7rem; }
  .managed-tag { grid-template-columns: calc(var(--tag-depth) * .55rem) .5rem minmax(0, 1fr) 2rem; }
  .managed-tag-count { display: none; }
  .delete-tag-button { opacity: 1; }
}
@media (prefers-reduced-motion: reduce) {
  .tag-manager-enter-active, .tag-manager-leave-active, .tag-manager-enter-active .tag-manager-panel, .tag-manager-leave-active .tag-manager-panel { transition-duration: 1ms; }
}
</style>
