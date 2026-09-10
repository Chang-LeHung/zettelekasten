<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import type { LibraryItem, LibraryItemUpdate } from '../api/types'
import { isEditorSaveShortcut } from '../utils/editorShortcuts'
import { linkedScrollTop } from '../utils/linkedScroll'
import MarkdownContent from './MarkdownContent.vue'

const props = defineProps<{
  item: LibraryItem
  saving: boolean
}>()

const emit = defineEmits<{
  close: [dirty: boolean]
  save: [payload: LibraryItemUpdate]
}>()

const sourceEditor = ref<HTMLTextAreaElement | null>(null)
const lineGutter = ref<HTMLElement | null>(null)
const previewDocument = ref<HTMLElement | null>(null)
const draft = reactive<LibraryItemUpdate>({ title: '', subtitle: null, summary: null, content: '' })
const initial = ref('')
let scrollOwner: 'source' | 'preview' | null = null
let scrollReleaseFrame: number | null = null

const serializedDraft = computed(() => JSON.stringify(draft))
const dirty = computed(() => serializedDraft.value !== initial.value)
const lineNumbers = computed(() => Array.from({ length: Math.max(1, draft.content.split('\n').length) }, (_, index) => index + 1))

function applyItem(item: LibraryItem): void {
  Object.assign(draft, {
    title: item.title,
    subtitle: item.subtitle,
    summary: item.summary,
    content: item.content,
  })
  void nextTick(() => {
    initial.value = serializedDraft.value
  })
}

function releaseScrollOwner(): void {
  if (scrollReleaseFrame !== null) window.cancelAnimationFrame(scrollReleaseFrame)
  scrollReleaseFrame = window.requestAnimationFrame(() => {
    scrollOwner = null
    scrollReleaseFrame = null
  })
}

function syncSourceScroll(): void {
  const source = sourceEditor.value
  const preview = previewDocument.value
  if (!source) return
  if (lineGutter.value) lineGutter.value.scrollTop = source.scrollTop
  if (!preview || scrollOwner === 'preview') return
  scrollOwner = 'source'
  preview.scrollTop = linkedScrollTop(source, preview)
  releaseScrollOwner()
}

function syncPreviewScroll(): void {
  const source = sourceEditor.value
  const preview = previewDocument.value
  if (!source || !preview || scrollOwner === 'source') return
  scrollOwner = 'preview'
  source.scrollTop = linkedScrollTop(preview, source)
  if (lineGutter.value) lineGutter.value.scrollTop = source.scrollTop
  releaseScrollOwner()
}

function insertIndent(event: KeyboardEvent): void {
  if (event.key !== 'Tab' || !sourceEditor.value) return
  event.preventDefault()
  const editor = sourceEditor.value
  editor.setRangeText('  ', editor.selectionStart, editor.selectionEnd, 'end')
  draft.content = editor.value
}

function submit(): void {
  if (!draft.title.trim() || !draft.content.trim() || props.saving) return
  emit('save', {
    title: draft.title.trim(),
    subtitle: draft.subtitle?.trim() || null,
    summary: draft.summary?.trim() || null,
    content: draft.content,
  })
}

function handleEditorShortcut(event: KeyboardEvent): void {
  if (isEditorSaveShortcut(event)) {
    event.preventDefault()
    if (dirty.value) submit()
    return
  }
  if (event.key === 'Escape') emit('close', dirty.value)
}

watch(() => props.item, applyItem, { immediate: true })
watch(serializedDraft, () => {
  void nextTick(syncSourceScroll)
})

onMounted(() => {
  document.body.classList.add('library-editor-open')
  window.addEventListener('keydown', handleEditorShortcut)
})

onBeforeUnmount(() => {
  document.body.classList.remove('library-editor-open')
  window.removeEventListener('keydown', handleEditorShortcut)
  if (scrollReleaseFrame !== null) window.cancelAnimationFrame(scrollReleaseFrame)
})
</script>

<template>
  <Teleport to="body">
    <section class="library-editor" role="dialog" aria-modal="true" :aria-label="`Edit ${item.title}`">
      <header class="editor-toolbar">
        <button class="back-button" type="button" @click="emit('close', dirty)">
          <span aria-hidden="true">‹</span> Back
        </button>
        <div class="resource-heading">
          <span class="resource-icon" aria-hidden="true">{{ item.item_type === 'article' ? 'A' : 'C' }}</span>
          <strong>{{ draft.title || 'Untitled' }}</strong>
          <span class="resource-type">{{ item.item_type }}</span>
        </div>
        <div class="editor-actions">
          <span class="save-state" :class="{ changed: dirty }"><i />{{ dirty ? 'Unsaved changes' : 'All changes saved' }}</span>
          <span class="live-indicator"><i />Live preview</span>
          <button class="save-button" :disabled="saving || !dirty || !draft.title.trim() || !draft.content.trim()" type="button" title="Save (⌘S)" @click="submit">
            {{ saving ? 'Saving…' : 'Save' }}
          </button>
        </div>
      </header>

      <div class="editor-columns">
        <section class="source-pane" aria-label="Markdown source editor">
          <header class="pane-heading"><span>Source (Markdown)</span><small>{{ lineNumbers.length }} lines</small></header>
          <div class="metadata-fields">
            <label><span>Title</span><input v-model="draft.title" maxlength="300" /></label>
            <label v-if="item.item_type === 'article'"><span>Subtitle</span><input v-model="draft.subtitle" maxlength="500" /></label>
            <label><span>Summary</span><textarea v-model="draft.summary" rows="3" /></label>
          </div>
          <div class="source-workspace">
            <pre ref="lineGutter" class="line-gutter" aria-hidden="true"><span v-for="line in lineNumbers" :key="line">{{ line }}</span></pre>
            <textarea
              ref="sourceEditor"
              v-model="draft.content"
              aria-label="Markdown content"
              autocomplete="off"
              autocorrect="off"
              spellcheck="false"
              @keydown="insertIndent"
              @scroll.passive="syncSourceScroll"
            />
          </div>
        </section>

        <section class="preview-pane" aria-label="Live Markdown preview">
          <header class="pane-heading"><span>Live preview</span><small><i />Live · scroll linked</small></header>
          <article ref="previewDocument" class="preview-document" @scroll.passive="syncPreviewScroll">
            <span class="preview-type">{{ item.item_type }}</span>
            <h1>{{ draft.title || 'Untitled' }}</h1>
            <p v-if="draft.subtitle" class="preview-subtitle">{{ draft.subtitle }}</p>
            <MarkdownContent v-if="draft.summary" class="preview-summary" :content="draft.summary" />
            <div v-if="draft.summary" class="preview-rule" />
            <MarkdownContent class="preview-content" :content="draft.content || '*Start writing to see a preview.*'" />
          </article>
        </section>
      </div>
    </section>
  </Teleport>
</template>

<style scoped>
.library-editor { position: fixed; inset: .65rem; z-index: 500; display: grid; grid-template-rows: 4.65rem minmax(0, 1fr); overflow: hidden; border: 1px solid rgba(29,29,31,.1); border-radius: 1.15rem; color: #202321; background: #fbfcfb; box-shadow: 0 30px 90px rgba(20,30,24,.2); }
.editor-toolbar { display: grid; grid-template-columns: minmax(8rem, auto) minmax(0, 1fr) auto; align-items: center; gap: 1rem; padding: 0 1.25rem; border-bottom: 1px solid #e1e5e2; background: rgba(255,255,255,.96); }
.back-button { display: inline-flex; align-items: center; gap: .45rem; width: max-content; padding: .55rem .7rem; border: 0; border-radius: .6rem; color: #455149; background: transparent; cursor: pointer; font-weight: 610; }
.back-button:hover { background: #eef2ef; }
.back-button span { font-size: 1.55rem; font-weight: 350; line-height: .7; }
.resource-heading { min-width: 0; display: flex; align-items: center; gap: .65rem; }
.resource-heading strong { overflow: hidden; font-size: .95rem; text-overflow: ellipsis; white-space: nowrap; }
.resource-icon { display: grid; place-items: center; width: 2rem; height: 2rem; flex: 0 0 auto; border-radius: .55rem; color: #43614f; background: #e8efeb; font-size: .72rem; font-weight: 760; }
.resource-type, .preview-type { padding: .26rem .48rem; border-radius: 2rem; color: #665139; background: #f3ebdf; font-size: .62rem; font-weight: 720; letter-spacing: .055em; text-transform: uppercase; }
.editor-actions { display: flex; align-items: center; justify-content: flex-end; gap: .8rem; }
.save-state, .live-indicator { display: inline-flex; align-items: center; gap: .4rem; color: #6e7671; font-size: .7rem; white-space: nowrap; }
.save-state i, .live-indicator i, .pane-heading small i { width: .45rem; height: .45rem; border-radius: 50%; background: #56a36d; box-shadow: 0 0 0 3px rgba(86,163,109,.1); }
.save-state.changed i { background: #e2a12b; box-shadow: 0 0 0 3px rgba(226,161,43,.1); }
.save-button { min-width: 5.5rem; height: 2.55rem; padding: 0 1rem; border: 0; border-radius: .68rem; color: #fff; background: linear-gradient(180deg, #537764, #3d604e); box-shadow: 0 4px 12px rgba(52,82,67,.18); cursor: pointer; font-weight: 650; }
.save-button:disabled { opacity: .42; cursor: not-allowed; }
.editor-columns { min-height: 0; display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); }
.source-pane, .preview-pane { min-width: 0; min-height: 0; display: grid; grid-template-rows: 3.45rem auto minmax(0, 1fr); overflow: hidden; }
.preview-pane { grid-template-rows: 3.45rem minmax(0, 1fr); border-left: 1px solid #dfe3e0; background: #fff; }
.pane-heading { display: flex; align-items: center; justify-content: space-between; padding: 0 1.45rem; border-bottom: 1px solid #e4e7e5; color: #6c736e; font-size: .68rem; font-weight: 720; letter-spacing: .065em; text-transform: uppercase; }
.pane-heading small { display: inline-flex; align-items: center; gap: .42rem; color: #76807a; font-size: .62rem; font-weight: 570; letter-spacing: 0; text-transform: none; }
.metadata-fields { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: .75rem; padding: .9rem 1.1rem; border-bottom: 1px solid #e2e5e3; background: #f7f9f7; }
.metadata-fields label { min-width: 0; display: grid; gap: .3rem; color: #6e7771; font-size: .61rem; font-weight: 680; letter-spacing: .04em; text-transform: uppercase; }
.metadata-fields label:last-child { grid-column: 1 / -1; }
.metadata-fields input, .metadata-fields textarea { width: 100%; padding: .58rem .65rem; resize: none; border: 1px solid #dce2de; border-radius: .55rem; outline: 0; color: #262b28; background: #fff; font: inherit; font-size: .76rem; font-weight: 450; letter-spacing: 0; line-height: 1.45; text-transform: none; }
.metadata-fields input:focus, .metadata-fields textarea:focus { border-color: #85a491; box-shadow: 0 0 0 3px rgba(71,105,87,.08); }
.source-workspace { min-height: 0; display: grid; grid-template-columns: 3.6rem minmax(0, 1fr); overflow: hidden; background: #f9faf9; }
.line-gutter { min-height: 0; margin: 0; padding: 1.1rem .8rem 3rem 0; overflow: hidden; border-right: 1px solid #e2e5e3; color: #9aa09c; background: #f2f4f2; font-family: "SFMono-Regular", Consolas, monospace; font-size: .76rem; line-height: 1.72; text-align: right; user-select: none; }
.line-gutter span { display: block; }
.source-workspace textarea { min-width: 0; min-height: 0; width: 100%; height: 100%; padding: 1.1rem 1.25rem 3rem; resize: none; border: 0; outline: 0; color: #252c28; background: transparent; font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace; font-size: .82rem; line-height: 1.72; tab-size: 2; white-space: pre; overflow: auto; }
.preview-document { min-height: 0; overflow: auto; padding: 2.4rem clamp(2rem, 5vw, 5rem) 5rem; }
.preview-document h1 { max-width: 54rem; margin: .85rem 0 .7rem; font-size: clamp(2rem, 3.1vw, 3.2rem); line-height: 1.12; letter-spacing: -.04em; }
.preview-subtitle { margin: 0 0 1rem; color: #777f7a; font-size: 1rem; line-height: 1.55; }
.preview-summary { max-width: 52rem; color: #59635d; font-size: .94rem; line-height: 1.72; }
.preview-rule { width: 3rem; height: .18rem; margin: 1.65rem 0; border-radius: 2rem; background: #9eb6a7; }
.preview-content { max-width: 54rem; color: #303632; font-size: .96rem; line-height: 1.8; }

@media (max-width: 900px) {
  .library-editor { inset: 0; border: 0; border-radius: 0; }
  .editor-toolbar { grid-template-columns: auto minmax(0, 1fr) auto; padding: 0 .75rem; }
  .resource-heading .resource-icon, .resource-heading .resource-type, .save-state, .live-indicator { display: none; }
  .editor-columns { grid-template-columns: 1fr; grid-template-rows: minmax(0, 1fr) minmax(0, 1fr); }
  .preview-pane { border-top: 1px solid #dfe3e0; border-left: 0; }
  .preview-document { padding: 1.5rem; }
}
</style>

<style>
body.library-editor-open { overflow: hidden; }
</style>
