<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import DOMPurify from 'dompurify'
import hljs from 'highlight.js/lib/core'
import bash from 'highlight.js/lib/languages/bash'
import c from 'highlight.js/lib/languages/c'
import cpp from 'highlight.js/lib/languages/cpp'
import csharp from 'highlight.js/lib/languages/csharp'
import css from 'highlight.js/lib/languages/css'
import dart from 'highlight.js/lib/languages/dart'
import diff from 'highlight.js/lib/languages/diff'
import dockerfile from 'highlight.js/lib/languages/dockerfile'
import go from 'highlight.js/lib/languages/go'
import graphql from 'highlight.js/lib/languages/graphql'
import ini from 'highlight.js/lib/languages/ini'
import java from 'highlight.js/lib/languages/java'
import javascript from 'highlight.js/lib/languages/javascript'
import json from 'highlight.js/lib/languages/json'
import kotlin from 'highlight.js/lib/languages/kotlin'
import less from 'highlight.js/lib/languages/less'
import lua from 'highlight.js/lib/languages/lua'
import makefile from 'highlight.js/lib/languages/makefile'
import markdown from 'highlight.js/lib/languages/markdown'
import nginx from 'highlight.js/lib/languages/nginx'
import objectivec from 'highlight.js/lib/languages/objectivec'
import perl from 'highlight.js/lib/languages/perl'
import php from 'highlight.js/lib/languages/php'
import powershell from 'highlight.js/lib/languages/powershell'
import python from 'highlight.js/lib/languages/python'
import r from 'highlight.js/lib/languages/r'
import ruby from 'highlight.js/lib/languages/ruby'
import rust from 'highlight.js/lib/languages/rust'
import scala from 'highlight.js/lib/languages/scala'
import scss from 'highlight.js/lib/languages/scss'
import sql from 'highlight.js/lib/languages/sql'
import swift from 'highlight.js/lib/languages/swift'
import typescript from 'highlight.js/lib/languages/typescript'
import xml from 'highlight.js/lib/languages/xml'
import yaml from 'highlight.js/lib/languages/yaml'
import { katex } from '@mdit/plugin-katex'
import MarkdownIt from 'markdown-it'
import { markdownFigures } from '../utils/markdownFigures'
import { sanitizeMarkdown } from '../utils/sanitizeMarkdown'
import { changeDiagramZoom, clampDiagramZoom } from '../utils/diagramZoom'
import { renderMermaid } from '../utils/mermaidRenderer'
import 'highlight.js/styles/github.css'
import 'katex/dist/katex.min.css'

const props = defineProps<{ content: string }>()

const COPY_RESET_DELAY_MS = 1600
const markdownRoot = ref<HTMLElement | null>(null)
const mermaidDialogClose = ref<HTMLButtonElement | null>(null)
const mermaidPreview = ref<{ source: string; svg: string } | null>(null)
const mermaidZoom = ref(1)
const renderedMermaidSvgs = new Map<string, string>()
let mermaidPreviewTrigger: HTMLElement | null = null
let renderGeneration = 0
let renderFrame: number | null = null

hljs.registerLanguage('bash', bash)
hljs.registerLanguage('c', c)
hljs.registerLanguage('cpp', cpp)
hljs.registerLanguage('cuda', cpp)
hljs.registerLanguage('csharp', csharp)
hljs.registerLanguage('css', css)
hljs.registerLanguage('dart', dart)
hljs.registerLanguage('diff', diff)
hljs.registerLanguage('dockerfile', dockerfile)
hljs.registerLanguage('go', go)
hljs.registerLanguage('graphql', graphql)
hljs.registerLanguage('html', xml)
hljs.registerLanguage('ini', ini)
hljs.registerLanguage('java', java)
hljs.registerLanguage('javascript', javascript)
hljs.registerLanguage('js', javascript)
hljs.registerLanguage('json', json)
hljs.registerLanguage('kotlin', kotlin)
hljs.registerLanguage('less', less)
hljs.registerLanguage('lua', lua)
hljs.registerLanguage('makefile', makefile)
hljs.registerLanguage('markdown', markdown)
hljs.registerLanguage('md', markdown)
hljs.registerLanguage('nginx', nginx)
hljs.registerLanguage('objectivec', objectivec)
hljs.registerLanguage('perl', perl)
hljs.registerLanguage('php', php)
hljs.registerLanguage('powershell', powershell)
hljs.registerLanguage('python', python)
hljs.registerLanguage('py', python)
hljs.registerLanguage('r', r)
hljs.registerLanguage('ruby', ruby)
hljs.registerLanguage('rust', rust)
hljs.registerLanguage('scala', scala)
hljs.registerLanguage('scss', scss)
hljs.registerLanguage('sql', sql)
hljs.registerLanguage('swift', swift)
hljs.registerLanguage('typescript', typescript)
hljs.registerLanguage('ts', typescript)
hljs.registerLanguage('vue', xml)
hljs.registerLanguage('yaml', yaml)

const LANGUAGE_ALIASES: Record<string, string> = {
  'c++': 'cpp',
  'c#': 'csharp',
  console: 'bash',
  cu: 'cuda',
  docker: 'dockerfile',
  jsx: 'javascript',
  make: 'makefile',
  nvcc: 'cuda',
  objc: 'objectivec',
  'objective-c': 'objectivec',
  ps1: 'powershell',
  shell: 'bash',
  shellsession: 'bash',
  tsx: 'typescript',
  zsh: 'bash',
}

function resolveLanguage(language: string): string {
  const normalized = language.trim().toLowerCase()
  const resolved = LANGUAGE_ALIASES[normalized] || normalized
  return /^[a-z0-9_-]+$/u.test(resolved) && hljs.getLanguage(resolved) ? resolved : ''
}

const renderer = new MarkdownIt({
  breaks: true,
  html: true,
  linkify: true,
  typographer: true,
  highlight(code: string, language: string): string {
    const resolvedLanguage = resolveLanguage(language)
    if (resolvedLanguage) {
      return hljs.highlight(code, { language: resolvedLanguage, ignoreIllegals: true }).value
    }
    return renderer.utils.escapeHtml(code)
  },
})

renderer.use(katex, {
  delimiters: 'all',
  mathFence: true,
  throwOnError: false,
  strict: 'ignore',
})
renderer.use(markdownFigures)

renderer.renderer.rules.link_open = (tokens, index, options, _environment, self) => {
  tokens[index].attrSet('target', '_blank')
  tokens[index].attrSet('rel', 'noopener noreferrer')
  return self.renderToken(tokens, index, options)
}

renderer.renderer.rules.fence = (tokens, index) => {
  const token = tokens[index]
  const language = token.info.trim().split(/\s+/u)[0] ?? ''
  if (language.toLowerCase() === 'mermaid') {
    const source = renderer.utils.escapeHtml(token.content)
    const rendered = renderedMermaidSvgs.get(token.content)
    const canvas = rendered ?? '<span class="mermaid-loading">Rendering diagram…</span>'
    return `<div class="mermaid-block"><div class="mermaid-toolbar"><span>Diagram</span><div class="mermaid-actions"><button type="button" class="code-copy-button" data-mermaid-copy aria-label="Copy Mermaid source">Copy source</button><button type="button" class="code-copy-button" data-mermaid-open aria-label="Open Mermaid diagram preview">Expand</button></div></div><pre class="mermaid-source" aria-hidden="true">${source}</pre><div class="mermaid-canvas" data-mermaid-canvas>${canvas}</div></div>`
  }
  const resolvedLanguage = resolveLanguage(language)
  const highlighted = resolvedLanguage
    ? hljs.highlight(token.content, { language: resolvedLanguage, ignoreIllegals: true }).value
    : renderer.utils.escapeHtml(token.content)
  const languageClass = resolvedLanguage ? ` class="language-${resolvedLanguage}"` : ''

  return `<pre class="code-block"><code${languageClass}>${highlighted}</code></pre>`
}

async function handleMarkdownClick(event: MouseEvent): Promise<void> {
  const target = event.target
  if (!(target instanceof Element)) return

  const expandButton = target.closest<HTMLButtonElement>('[data-mermaid-open]')
  if (expandButton) {
    const block = expandButton.closest('.mermaid-block')
    const source = block?.querySelector('.mermaid-source')?.textContent
    const svg = block?.querySelector<HTMLElement>('[data-mermaid-canvas]')?.innerHTML
    if (source && svg) openMermaidPreview(source, svg, expandButton)
    return
  }

  const button = target.closest<HTMLButtonElement>('[data-mermaid-copy]')
  const code = button?.closest('.mermaid-block')?.querySelector('.mermaid-source')?.textContent
  if (!button || code === null || code === undefined) return

  try {
    await navigator.clipboard.writeText(code)
    button.textContent = 'Copied'
    button.classList.add('is-copied')
    window.setTimeout(() => {
      button.textContent = 'Copy'
      button.classList.remove('is-copied')
    }, COPY_RESET_DELAY_MS)
  } catch {
    button.textContent = 'Copy failed'
    window.setTimeout(() => {
      button.textContent = 'Copy'
    }, COPY_RESET_DELAY_MS)
  }
}

function openMermaidPreview(source: string, svg: string, trigger: HTMLElement): void {
  mermaidPreviewTrigger = trigger
  mermaidZoom.value = 1
  mermaidPreview.value = { source, svg }
  void nextTick(() => mermaidDialogClose.value?.focus())
}

function closeMermaidPreview(): void {
  mermaidPreview.value = null
  mermaidZoom.value = 1
  mermaidPreviewTrigger?.focus()
  mermaidPreviewTrigger = null
}

function zoomMermaid(direction: -1 | 1): void {
  mermaidZoom.value = changeDiagramZoom(mermaidZoom.value, direction)
}

function handleMermaidWheel(event: WheelEvent): void {
  if (!event.ctrlKey && !event.metaKey) return
  event.preventDefault()
  mermaidZoom.value = clampDiagramZoom(mermaidZoom.value + (event.deltaY < 0 ? 0.1 : -0.1))
}

function handlePreviewKeydown(event: KeyboardEvent): void {
  if (mermaidPreview.value && event.key === 'Escape') closeMermaidPreview()
}

function showMermaidError(canvas: HTMLElement, source: string): void {
  canvas.replaceChildren()
  canvas.classList.add('is-error')
  const message = document.createElement('p')
  message.className = 'mermaid-error-message'
  message.textContent = 'This Mermaid diagram could not be rendered.'
  const pre = document.createElement('pre')
  const code = document.createElement('code')
  code.textContent = source
  pre.append(code)
  canvas.append(message, pre)
}

function sanitizeMermaidSvg(svg: string): string {
  return DOMPurify.sanitize(svg, {
    ADD_TAGS: ['foreignObject'],
    FORBID_CONTENTS: [],
    HTML_INTEGRATION_POINTS: { foreignobject: true },
    USE_PROFILES: { html: true, svg: true, svgFilters: true },
  })
}

async function renderMermaidDiagrams(generation: number): Promise<void> {
  const root = markdownRoot.value
  if (root === null) return
  const diagrams = [...root.querySelectorAll<HTMLElement>('[data-mermaid-canvas]')]
  if (!diagrams.length) return

  for (const canvas of diagrams) {
    if (generation !== renderGeneration || !canvas.isConnected) return
    const source = canvas.closest('.mermaid-block')?.querySelector('.mermaid-source')?.textContent ?? ''
    const cachedSvg = renderedMermaidSvgs.get(source)
    if (cachedSvg !== undefined) {
      if (canvas.querySelector('svg') === null) canvas.innerHTML = cachedSvg
      continue
    }
    try {
      const { svg, bindFunctions } = await renderMermaid(source)
      // v-html replaces the Markdown subtree for every streamed token. Keeping
      // the last SVG by source lets the next render paint the finished diagram
      // immediately instead of flashing the loading placeholder each time.
      const sanitizedSvg = sanitizeMermaidSvg(svg)
      renderedMermaidSvgs.set(source, sanitizedSvg)
      if (generation !== renderGeneration || !canvas.isConnected) return
      canvas.classList.remove('is-error')
      canvas.innerHTML = sanitizedSvg
      bindFunctions?.(canvas)
    } catch {
      if (generation === renderGeneration && canvas.isConnected) showMermaidError(canvas, source)
    }
  }
}

function scheduleMermaidRender(): void {
  const generation = ++renderGeneration
  if (renderFrame !== null) window.cancelAnimationFrame(renderFrame)
  renderFrame = window.requestAnimationFrame(() => {
    renderFrame = null
    void renderMermaidDiagrams(generation)
  })
}

const html = computed(() => sanitizeMarkdown(renderer.render(props.content)))

onMounted(() => {
  scheduleMermaidRender()
  window.addEventListener('keydown', handlePreviewKeydown)
})
watch(
  () => props.content,
  scheduleMermaidRender,
  { flush: 'post' },
)
onBeforeUnmount(() => {
  renderGeneration += 1
  if (renderFrame !== null) window.cancelAnimationFrame(renderFrame)
  window.removeEventListener('keydown', handlePreviewKeydown)
})
</script>

<template>
  <div ref="markdownRoot" class="markdown-body" @click="handleMarkdownClick" v-html="html" />
  <Teleport to="body">
    <div v-if="mermaidPreview" class="mermaid-preview-backdrop" @click.self="closeMermaidPreview">
      <section class="mermaid-preview-dialog" role="dialog" aria-modal="true" aria-label="Mermaid diagram preview">
        <header class="mermaid-preview-header">
          <div>
            <strong>Diagram preview</strong>
            <span>Ctrl/⌘ + scroll to zoom</span>
          </div>
          <div class="mermaid-preview-controls">
            <button type="button" aria-label="Zoom out" @click="zoomMermaid(-1)">−</button>
            <button type="button" class="mermaid-zoom-value" aria-label="Reset zoom" @click="mermaidZoom = 1">
              {{ Math.round(mermaidZoom * 100) }}%
            </button>
            <button type="button" aria-label="Zoom in" @click="zoomMermaid(1)">+</button>
            <button ref="mermaidDialogClose" type="button" class="mermaid-preview-close" aria-label="Close diagram preview" @click="closeMermaidPreview">×</button>
          </div>
        </header>
        <div class="mermaid-preview-stage" @wheel="handleMermaidWheel">
          <div class="mermaid-preview-diagram" :style="{ width: `${mermaidZoom * 100}%` }" v-html="mermaidPreview.svg" />
        </div>
      </section>
    </div>
  </Teleport>
</template>

<style scoped>
.markdown-body { min-width: 0; color: inherit; font: inherit; line-height: 1.65; overflow-wrap: anywhere; isolation: isolate; contain: layout paint; }
.markdown-body :deep(> :first-child) { margin-top: 0; }
.markdown-body :deep(> :last-child) { margin-bottom: 0; }
.markdown-body :deep(p), .markdown-body :deep(ul), .markdown-body :deep(ol), .markdown-body :deep(blockquote), .markdown-body :deep(pre), .markdown-body :deep(table) { margin: .62em 0; }
.markdown-body :deep(h1), .markdown-body :deep(h2), .markdown-body :deep(h3), .markdown-body :deep(h4) { margin: 1.15em 0 .48em; color: inherit; line-height: 1.28; letter-spacing: -.015em; }
.markdown-body :deep(h1) { font-size: 1.55em; }
.markdown-body :deep(h2) { font-size: 1.32em; }
.markdown-body :deep(h3) { font-size: 1.15em; }
.markdown-body :deep(ul), .markdown-body :deep(ol) { padding-left: 1.45em; }
.markdown-body :deep(li + li) { margin-top: .25em; }
.markdown-body :deep(a) { color: #35684e; text-decoration: none; }
.markdown-body :deep(a:hover) { color: #214b35; text-decoration: none; }
.markdown-body :deep(a:focus-visible) { outline: 2px solid currentColor; outline-offset: 3px; border-radius: 2px; }
.markdown-body :deep(blockquote) {
  margin: 1em .65rem;
  padding: .9em 1.2em;
  border: 0;
  border-radius: .65em;
  color: inherit;
  background: #f4faf8;
  box-shadow: 0 4px 16px rgb(0 0 0 / 10%), 0 1px 4px rgb(0 0 0 / 4%);
  font-style: normal;
}
.markdown-body :deep(blockquote > :first-child) { margin-top: 0; }
.markdown-body :deep(blockquote > :last-child) { margin-bottom: 0; }
.markdown-body :deep(blockquote blockquote) { margin: .65em 0; background: #eaf3ee; box-shadow: 0 2px 8px rgb(0 0 0 / 6%); }
.markdown-body :deep(.markdown-figure) { display: block; margin: 1.4em 0; padding: 0; break-inside: avoid; text-align: center; }
.markdown-body :deep(.markdown-figure img) { display: block; width: auto; max-width: 100%; height: auto; margin: 0 auto; border: 0; border-radius: .2rem; object-fit: contain; box-shadow: none; }
.markdown-body :deep(figcaption) { max-width: 90%; margin: .65em auto 0; color: #68736c; font-size: .85em; line-height: 1.5; text-align: center; overflow-wrap: anywhere; }
.markdown-body :deep(.figure-number) { color: #404c44; font-weight: 650; font-variant-numeric: tabular-nums; }
.markdown-body :deep(code) { padding: .14em .34em; border-radius: .32em; color: #744b2e; background: #f1ece7; font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace; font-size: .88em; }
.markdown-body :deep(.code-block) { max-width: 100%; margin: .62em .65rem; padding: .9rem 1rem; overflow: auto; border: 1px solid transparent; border-radius: 1rem; background: #eeeeee; box-shadow: 0 4px 16px rgb(0 0 0 / 10%), 0 1px 4px rgb(0 0 0 / 4%); }
.markdown-body:has(> pre, > blockquote) { padding-block: .65rem; }
.markdown-body :deep(.code-copy-button) { min-width: 3.4rem; padding: .32rem .58rem; border: 1px solid transparent; border-radius: .42rem; color: #4f5c55; background: transparent; font: inherit; text-transform: none; cursor: pointer; transition: color .16s ease, background .16s ease, border-color .16s ease; }
.markdown-body :deep(.code-copy-button:hover) { border-color: #d4ddd7; color: #294d3b; background: #fff; }
.markdown-body :deep(.code-copy-button:focus-visible) { outline: 2px solid #719681; outline-offset: 1px; }
.markdown-body :deep(.code-copy-button.is-copied) { color: #2f6a4b; }
.markdown-body :deep(.mermaid-block) { max-width: 100%; margin: .75em 0; overflow: hidden; border: 1px solid #dfe5e1; border-radius: .8rem; background: #fbfcfb; }
.markdown-body :deep(.mermaid-toolbar) { display: flex; align-items: center; justify-content: space-between; min-height: 2.25rem; padding: .35rem .55rem .35rem .9rem; border-bottom: 1px solid #e3e8e5; color: #78817c; background: #f3f6f4; font-size: .72em; font-weight: 600; letter-spacing: .02em; }
.markdown-body :deep(.mermaid-actions) { display: flex; align-items: center; gap: .2rem; }
.markdown-body :deep(.mermaid-source) { display: none; }
.markdown-body :deep(.mermaid-canvas) { display: flex; width: 100%; min-height: 6rem; padding: 1rem; overflow: auto; align-items: center; justify-content: center; }
.markdown-body :deep(.mermaid-canvas svg) { display: block; width: 100% !important; max-width: none !important; height: auto; }
.markdown-body :deep(.mermaid-loading) { color: #89928d; font-size: .84em; }
.markdown-body :deep(.mermaid-canvas.is-error) { display: block; color: #875348; }
.markdown-body :deep(.mermaid-error-message) { margin: 0 0 .55rem; font-size: .86em; }
.markdown-body :deep(.mermaid-canvas.is-error pre) { margin: 0; }
.markdown-body :deep(pre) { max-width: 100%; margin-inline: .65rem; padding: .9rem 1rem; overflow: auto; border: 1px solid transparent; border-radius: 1rem; background: #eeeeee; box-shadow: 0 4px 16px rgb(0 0 0 / 10%), 0 1px 4px rgb(0 0 0 / 4%); }
.markdown-body :deep(pre code) { padding: 0; color: #242b27; background: transparent; font-size: .84em; line-height: 1.62; }
.markdown-body :deep(table) { display: block; max-width: 100%; overflow-x: auto; border-collapse: collapse; }
.markdown-body :deep(th), .markdown-body :deep(td) { padding: .45em .65em; border: 1px solid #dfe4e0; text-align: left; }
.markdown-body :deep(th) { background: #f3f6f4; font-weight: 650; }
.markdown-body :deep(hr) { margin: 1.2em 0; border: 0; border-top: 1px solid #e1e5e2; }
.markdown-body :deep(img) { max-width: 100%; height: auto; border-radius: .65rem; }
.markdown-body :deep(.katex-display) { max-width: 100%; margin: .8em 0; padding: .35em 0; overflow-x: auto; overflow-y: hidden; }

.mermaid-preview-backdrop { position: fixed; z-index: 1200; inset: 0; display: grid; place-items: center; padding: 2rem; background: rgba(35, 43, 38, .32); }
.mermaid-preview-dialog { display: grid; grid-template-rows: auto minmax(0, 1fr); width: min(94vw, 92rem); height: min(90vh, 64rem); overflow: hidden; border: 1px solid #d9e0dc; border-radius: 1.1rem; background: #fbfcfb; box-shadow: 0 1.5rem 4rem rgba(35, 48, 40, .2); }
.mermaid-preview-header { display: flex; min-height: 4.25rem; padding: .75rem 1rem .75rem 1.25rem; align-items: center; justify-content: space-between; gap: 1rem; border-bottom: 1px solid #e1e6e3; background: rgba(247, 249, 248, .96); }
.mermaid-preview-header > div:first-child { display: grid; gap: .12rem; }
.mermaid-preview-header strong { color: #2d3932; font-size: .95rem; font-weight: 680; }
.mermaid-preview-header span { color: #89928d; font-size: .75rem; }
.mermaid-preview-controls { display: flex; align-items: center; gap: .35rem; }
.mermaid-preview-controls button { display: grid; min-width: 2.25rem; height: 2.25rem; padding: 0 .55rem; place-items: center; border: 1px solid #d8dfdb; border-radius: .62rem; color: #45544c; background: #fff; font: inherit; font-size: 1rem; cursor: pointer; }
.mermaid-preview-controls button:hover { border-color: #b9c9c0; color: #28503b; background: #f5f8f6; }
.mermaid-preview-controls button:focus-visible { outline: 2px solid #719681; outline-offset: 2px; }
.mermaid-preview-controls .mermaid-zoom-value { min-width: 4.25rem; font-size: .78rem; font-variant-numeric: tabular-nums; }
.mermaid-preview-controls .mermaid-preview-close { margin-left: .3rem; font-size: 1.35rem; font-weight: 300; }
.mermaid-preview-stage { min-width: 0; min-height: 0; padding: 2rem; overflow: auto; overscroll-behavior: contain; background-color: #fff; background-image: radial-gradient(#dce4df 1px, transparent 1px); background-size: 22px 22px; }
.mermaid-preview-diagram { min-width: 28rem; margin: 0 auto; padding: 1.5rem; border-radius: .9rem; background: rgba(255, 255, 255, .92); }
.mermaid-preview-diagram :deep(svg) { display: block; width: 100% !important; max-width: none !important; height: auto !important; margin: auto; user-select: text; }

@media (max-width: 700px) {
  .mermaid-preview-backdrop { padding: .65rem; }
  .mermaid-preview-dialog { width: 100%; height: 94vh; border-radius: .85rem; }
  .mermaid-preview-header { padding: .65rem .7rem .65rem .9rem; }
  .mermaid-preview-header span { display: none; }
  .mermaid-preview-stage { padding: .75rem; }
  .mermaid-preview-diagram { min-width: 20rem; padding: .75rem; }
}
</style>
