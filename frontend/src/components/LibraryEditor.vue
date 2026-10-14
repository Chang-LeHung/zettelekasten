<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch, type Directive } from 'vue'
import { useI18n } from '../i18n'
import type { LibraryItem, LibraryItemUpdate } from '../api/types'
import { isEditorSaveShortcut } from '../utils/editorShortcuts'
import { readEditorLayout, writeEditorLayout, type EditorLayout } from '../utils/editorLayout'
import { linkedScrollTop } from '../utils/linkedScroll'
import BlockEditor from './BlockEditor.vue'
import MarkdownContent from './MarkdownContent.vue'
import SlidesPreview from './SlidesPreview.vue'

const props = defineProps<{
  item: LibraryItem
  saving: boolean
  /** Label for the primary action; conversation editors stage a draft. */
  saveLabel?: string
}>()

const emit = defineEmits<{
  close: [dirty: boolean]
  save: [payload: LibraryItemUpdate]
}>()

const { t } = useI18n()

const layout = ref<EditorLayout>(readEditorLayout())
const blockEditor = ref<InstanceType<typeof BlockEditor> | null>(null)
const titleField = ref<HTMLTextAreaElement | null>(null)
const subtitleField = ref<HTMLTextAreaElement | null>(null)
const summaryField = ref<HTMLTextAreaElement | null>(null)
const sourceEditor = ref<HTMLTextAreaElement | null>(null)
const lineGutter = ref<HTMLElement | null>(null)
const previewDocument = ref<HTMLElement | null>(null)
const draft = reactive<LibraryItemUpdate>({ title: '', subtitle: null, summary: null, content: '' })
const initial = ref('')
let scrollOwner: 'source' | 'preview' | null = null
let scrollReleaseFrame: number | null = null

const isSlides = computed(() => props.item.item_type === 'slides')
const hasSubtitle = computed(() => props.item.item_type === 'article' || props.item.item_type === 'slides')
const serializedDraft = computed(() => JSON.stringify(draft))
const dirty = computed(() => serializedDraft.value !== initial.value)
const lineNumbers = computed(() => Array.from({ length: Math.max(1, draft.content.split('\n').length) }, (_, index) => index + 1))
const canSave = computed(() => !props.saving && dirty.value && Boolean(draft.title.trim()) && Boolean(draft.content.trim()))

/** Grow a text field to fit what it holds, so titles wrap like page text instead of scrolling. */
const fit = (element: HTMLElement): void => {
  element.style.height = 'auto'
  element.style.height = `${element.scrollHeight}px`
}
const vAutosize: Directive<HTMLTextAreaElement> = { mounted: fit, updated: fit }

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

function setLayout(next: EditorLayout): void {
  if (layout.value === next) return
  layout.value = next
  writeEditorLayout(next)
  // A text field measured while hidden has no height, so it is measured again once shown.
  if (next === 'single') {
    void nextTick(() => {
      for (const field of [titleField.value, subtitleField.value, summaryField.value]) if (field) fit(field)
      blockEditor.value?.refit()
    })
  }
  else blockEditor.value?.blur()
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
  if (isSlides.value) return
  if (!preview || scrollOwner === 'preview') return
  scrollOwner = 'source'
  preview.scrollTop = linkedScrollTop(source, preview)
  releaseScrollOwner()
}

function syncPreviewScroll(): void {
  const source = sourceEditor.value
  const preview = previewDocument.value
  if (isSlides.value) return
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

// Moving through the page header with the keyboard, the way a document reads.
function focusAfterTitle(): void {
  const next = hasSubtitle.value ? subtitleField.value : summaryField.value
  if (next) next.focus()
  else blockEditor.value?.focusStart()
}

function onTitleKey(event: KeyboardEvent): void {
  if (event.isComposing || event.keyCode === 229) return
  if (event.key === 'Enter') {
    event.preventDefault()
    focusAfterTitle()
  } else if (event.key === 'ArrowDown' && titleField.value && titleField.value.selectionStart === titleField.value.value.length) {
    event.preventDefault()
    focusAfterTitle()
  }
}

function onFieldKey(event: KeyboardEvent, next: 'summary' | 'body'): void {
  if (event.isComposing || event.keyCode === 229) return
  const field = event.target as HTMLTextAreaElement
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    if (next === 'summary' && summaryField.value) summaryField.value.focus()
    else blockEditor.value?.focusStart()
  } else if (event.key === 'ArrowUp' && field.selectionStart === 0) {
    event.preventDefault()
    const previous = field === summaryField.value && hasSubtitle.value ? subtitleField.value : titleField.value
    previous?.focus()
  } else if (event.key === 'ArrowDown' && field.selectionStart === field.value.length) {
    event.preventDefault()
    if (next === 'summary' && summaryField.value) summaryField.value.focus()
    else blockEditor.value?.focusStart()
  }
}

function onEdge(direction: 'up' | 'down'): void {
  if (direction !== 'up') return
  const previous = summaryField.value ?? (hasSubtitle.value ? subtitleField.value : null) ?? titleField.value
  previous?.focus()
}

// A subtitle and summary are optional properties, stored as null when empty.
const subtitleModel = computed({ get: () => draft.subtitle ?? '', set: (value: string) => { draft.subtitle = value || null } })
const summaryModel = computed({ get: () => draft.summary ?? '', set: (value: string) => { draft.summary = value || null } })

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
    <section class="library-editor" :class="`layout-${layout}`" role="dialog" aria-modal="true" :aria-label="`Edit ${item.title}`">
      <header class="editor-toolbar">
        <button class="back-button" type="button" @click="emit('close', dirty)">
          <span aria-hidden="true">‹</span> {{ t('editor.back') }}
        </button>
        <div class="resource-heading">
          <span class="resource-icon" aria-hidden="true">{{ item.item_type === 'article' ? 'A' : item.item_type === 'slides' ? 'S' : 'C' }}</span>
          <strong>{{ draft.title || t('editor.untitled') }}</strong>
          <span class="resource-type">{{ item.item_type }}</span>
        </div>
        <div class="editor-actions">
          <span class="save-state" :class="{ changed: dirty }" role="status"><i />{{ dirty ? t('editor.unsaved') : t('editor.saved') }}</span>
          <span v-if="layout === 'split'" class="live-indicator"><i />{{ t('editor.preview') }}</span>
          <div class="layout-switch" role="group" :aria-label="t('editor.layout')">
            <button type="button" :class="{ active: layout === 'split' }" :aria-pressed="layout === 'split'" :title="t('editor.layout.split')" :aria-label="t('editor.layout.split')" @click="setLayout('split')">
              <svg viewBox="0 0 16 16" aria-hidden="true"><rect x="2" y="2.5" width="12" height="11" rx="2" /><path d="M8 2.5v11" /></svg>
            </button>
            <button type="button" :class="{ active: layout === 'single' }" :aria-pressed="layout === 'single'" :title="t('editor.layout.single')" :aria-label="t('editor.layout.single')" @click="setLayout('single')">
              <svg viewBox="0 0 16 16" aria-hidden="true"><rect x="3" y="2.5" width="10" height="11" rx="2" /></svg>
            </button>
          </div>
          <button class="save-button" :disabled="!canSave" type="button" :title="`${saveLabel ?? t('editor.save')} (⌘S)`" @click="submit">
            {{ saving ? t('editor.saving') : saveLabel ?? t('editor.save') }}
          </button>
        </div>
      </header>

      <!-- One column: the page, written as blocks. -->
      <!-- Hidden, not removed, in two-column mode: the block editor keeps its undo history across the switch. -->
      <main v-show="layout === 'single'" class="page-scroll">
        <article class="page">
          <span class="page-type">{{ item.item_type }}</span>
          <textarea
            ref="titleField"
            v-model="draft.title"
            v-autosize
            class="page-title"
            rows="1"
            maxlength="300"
            :placeholder="t('editor.titlePlaceholder')"
            :aria-label="t('editor.titlePlaceholder')"
            @keydown="onTitleKey"
          />
          <textarea
            v-if="hasSubtitle"
            ref="subtitleField"
            v-model="subtitleModel"
            v-autosize
            class="page-subtitle"
            rows="1"
            maxlength="500"
            :placeholder="t('editor.subtitlePlaceholder')"
            :aria-label="t('editor.subtitlePlaceholder')"
            @keydown="onFieldKey($event, 'summary')"
          />
          <textarea
            ref="summaryField"
            v-model="summaryModel"
            v-autosize
            class="page-summary"
            rows="1"
            :placeholder="t('editor.summaryPlaceholder')"
            :aria-label="t('editor.summaryPlaceholder')"
            @keydown="onFieldKey($event, 'body')"
          />
          <BlockEditor ref="blockEditor" v-model="draft.content" class="page-body" :slides="isSlides" @edge="onEdge" />
        </article>
      </main>

      <!-- Two columns: the Markdown source beside a live preview. -->
      <div v-if="layout === 'split'" class="editor-columns">
        <section class="source-pane" :aria-label="t('editor.source')">
          <header class="pane-heading"><span>{{ t('editor.source') }}</span><small>{{ t('editor.lines', { count: lineNumbers.length }) }}</small></header>
          <div class="metadata-fields">
            <label><span>Title</span><input v-model="draft.title" maxlength="300" /></label>
            <label v-if="hasSubtitle"><span>Subtitle</span><input v-model="draft.subtitle" maxlength="500" /></label>
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

        <section class="preview-pane" :aria-label="t('editor.preview')">
          <header class="pane-heading"><span>{{ isSlides ? t('editor.liveDeck') : t('editor.preview') }}</span><small><i />{{ isSlides ? 'Live · use arrows' : 'Live · scroll linked' }}</small></header>
          <article v-if="isSlides" ref="previewDocument" class="preview-document slides-preview-document">
            <SlidesPreview :title="draft.title" :content="draft.content" />
          </article>
          <article v-else ref="previewDocument" class="preview-document" @scroll.passive="syncPreviewScroll">
            <span class="preview-type">{{ item.item_type }}</span>
            <h1>{{ draft.title || t('editor.untitled') }}</h1>
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
.layout-switch { display: inline-flex; padding: .16rem; gap: .12rem; border-radius: .7rem; background: #eef2ef; }
.layout-switch button { display: grid; place-items: center; width: 2.1rem; height: 1.9rem; padding: 0; border: 0; border-radius: .55rem; color: #7b827d; background: transparent; cursor: pointer; }
.layout-switch button:hover { color: #2b312d; }
.layout-switch button.active { color: #3f604c; background: #fff; box-shadow: 0 1px 3px rgba(24,28,26,.14); }
.layout-switch svg { width: 1rem; height: 1rem; fill: none; stroke: currentColor; stroke-width: 1.5; stroke-linejoin: round; }

/* The page: a calm column, wide enough to read and narrow enough to scan. */
.page-scroll { min-height: 0; overflow-y: auto; overscroll-behavior: contain; scrollbar-width: thin; }
.page { width: min(100%, 50rem); margin: 0 auto; padding: 4.5rem clamp(1.25rem, 6vw, 4.5rem) 3rem; }
.page-type { display: inline-block; margin-bottom: .8rem; padding: .26rem .48rem; border-radius: 2rem; color: #665139; background: #f3ebdf; font-size: .62rem; font-weight: 720; letter-spacing: .055em; text-transform: uppercase; }
.page-title, .page-subtitle, .page-summary { display: block; width: 100%; padding: 0; resize: none; overflow: hidden; border: 0; outline: 0; color: inherit; background: transparent; font: inherit; }
.page-title { font-size: 2.5rem; font-weight: 700; line-height: 1.2; letter-spacing: -.03em; }
.page-subtitle { margin-top: .35rem; color: #6c746e; font-size: 1.2rem; line-height: 1.45; }
.page-summary { margin: 1rem 0 1.4rem; padding: .7rem .95rem; border-radius: .82rem; color: #4b544e; background: #f6f7f6; font-size: .95rem; line-height: 1.65; }
.page-title::placeholder, .page-subtitle::placeholder, .page-summary::placeholder { color: #c0c5c1; }
.page-summary:not(:placeholder-shown) { background: #f6f7f6; }
.page-summary:placeholder-shown { margin-bottom: 1rem; background: transparent; padding-left: 0; }
.page-summary:placeholder-shown:focus { padding-left: .95rem; background: #f6f7f6; }
.page-body { margin-top: .4rem; padding-left: 0; }

.preview-document { min-height: 0; overflow: auto; padding: 2.4rem clamp(2rem, 5vw, 5rem) 5rem; }
.slides-preview-document { display: grid; align-items: center; padding: clamp(1rem, 3vw, 2.5rem); background: #f4f7f5; }
.preview-document h1 { max-width: 54rem; margin: .85rem 0 .7rem; font-size: clamp(2rem, 3.1vw, 3.2rem); line-height: 1.12; letter-spacing: -.04em; }
.preview-subtitle { margin: 0 0 1rem; color: #777f7a; font-size: 1rem; line-height: 1.55; }
.preview-summary { max-width: 52rem; color: #59635d; font-size: .94rem; line-height: 1.72; }
.preview-rule { width: 3rem; height: .18rem; margin: 1.65rem 0; border-radius: 2rem; background: #9eb6a7; }
.preview-content { max-width: 54rem; color: #303632; font-size: .96rem; line-height: 1.8; }

@media (max-width: 900px) {
  .library-editor { inset: 0; border: 0; border-radius: 0; }
  .editor-toolbar { grid-template-columns: auto minmax(0, 1fr) auto; padding: 0 .75rem; }
  .resource-heading .resource-icon, .resource-heading .resource-type, .save-state, .live-indicator, .layout-switch { display: none; }
  .page { padding: 2.5rem 1rem 2rem; }
  .page-title { font-size: 2rem; }
  .editor-columns { grid-template-columns: 1fr; grid-template-rows: minmax(0, 1fr) minmax(0, 1fr); }
  .preview-pane { border-top: 1px solid #dfe3e0; border-left: 0; }
  .preview-document { padding: 1.5rem; }
}
@media (max-width: 560px) {
  .editor-toolbar { gap: .4rem; padding: 0 .5rem; }
  .resource-heading strong { font-size: .82rem; }
  .metadata-fields { grid-template-columns: 1fr; padding: .75rem; }
  .metadata-fields label:last-child { grid-column: auto; }
  .pane-heading { padding: 0 .8rem; }
  .preview-document { padding: 1rem; }
}
</style>

<style>
body.library-editor-open { overflow: hidden; }
</style>
