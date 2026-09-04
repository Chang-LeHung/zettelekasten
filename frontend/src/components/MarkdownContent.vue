<script setup lang="ts">
import { computed } from 'vue'
import DOMPurify from 'dompurify'
import hljs from 'highlight.js/lib/core'
import bash from 'highlight.js/lib/languages/bash'
import css from 'highlight.js/lib/languages/css'
import javascript from 'highlight.js/lib/languages/javascript'
import json from 'highlight.js/lib/languages/json'
import markdown from 'highlight.js/lib/languages/markdown'
import python from 'highlight.js/lib/languages/python'
import sql from 'highlight.js/lib/languages/sql'
import typescript from 'highlight.js/lib/languages/typescript'
import xml from 'highlight.js/lib/languages/xml'
import { katex } from '@mdit/plugin-katex'
import MarkdownIt from 'markdown-it'
import 'highlight.js/styles/github.css'
import 'katex/dist/katex.min.css'

const props = defineProps<{ content: string }>()

const COPY_RESET_DELAY_MS = 1600

hljs.registerLanguage('bash', bash)
hljs.registerLanguage('css', css)
hljs.registerLanguage('html', xml)
hljs.registerLanguage('javascript', javascript)
hljs.registerLanguage('js', javascript)
hljs.registerLanguage('json', json)
hljs.registerLanguage('markdown', markdown)
hljs.registerLanguage('md', markdown)
hljs.registerLanguage('python', python)
hljs.registerLanguage('py', python)
hljs.registerLanguage('sql', sql)
hljs.registerLanguage('typescript', typescript)
hljs.registerLanguage('ts', typescript)
hljs.registerLanguage('vue', xml)

const renderer = new MarkdownIt({
  breaks: true,
  html: false,
  linkify: true,
  typographer: true,
  highlight(code: string, language: string): string {
    if (language && hljs.getLanguage(language)) {
      return hljs.highlight(code, { language, ignoreIllegals: true }).value
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

renderer.renderer.rules.link_open = (tokens, index, options, _environment, self) => {
  tokens[index].attrSet('target', '_blank')
  tokens[index].attrSet('rel', 'noopener noreferrer')
  return self.renderToken(tokens, index, options)
}

renderer.renderer.rules.fence = (tokens, index) => {
  const token = tokens[index]
  const language = token.info.trim().split(/\s+/u)[0] ?? ''
  const safeLanguage = /^[\w-]+$/u.test(language) ? language : ''
  const highlighted = safeLanguage && hljs.getLanguage(safeLanguage)
    ? hljs.highlight(token.content, { language: safeLanguage, ignoreIllegals: true }).value
    : renderer.utils.escapeHtml(token.content)
  const languageClass = safeLanguage ? ` class="language-${safeLanguage}"` : ''
  const languageLabel = safeLanguage || 'code'

  return `<div class="code-block"><div class="code-block-toolbar"><span>${languageLabel}</span><button type="button" class="code-copy-button" data-code-copy aria-label="Copy code">Copy</button></div><pre><code${languageClass}>${highlighted}</code></pre></div>`
}

async function handleMarkdownClick(event: MouseEvent): Promise<void> {
  const target = event.target
  if (!(target instanceof Element)) return

  const button = target.closest<HTMLButtonElement>('[data-code-copy]')
  const code = button?.closest('.code-block')?.querySelector('code')?.textContent
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

const html = computed(() => DOMPurify.sanitize(renderer.render(props.content)))
</script>

<template>
  <div class="markdown-body" @click="handleMarkdownClick" v-html="html" />
</template>

<style scoped>
.markdown-body { min-width: 0; color: inherit; font: inherit; line-height: 1.65; overflow-wrap: anywhere; }
.markdown-body :deep(> :first-child) { margin-top: 0; }
.markdown-body :deep(> :last-child) { margin-bottom: 0; }
.markdown-body :deep(p), .markdown-body :deep(ul), .markdown-body :deep(ol), .markdown-body :deep(blockquote), .markdown-body :deep(pre), .markdown-body :deep(table) { margin: .62em 0; }
.markdown-body :deep(h1), .markdown-body :deep(h2), .markdown-body :deep(h3), .markdown-body :deep(h4) { margin: 1.15em 0 .48em; color: inherit; line-height: 1.28; letter-spacing: -.015em; }
.markdown-body :deep(h1) { font-size: 1.55em; }
.markdown-body :deep(h2) { font-size: 1.32em; }
.markdown-body :deep(h3) { font-size: 1.15em; }
.markdown-body :deep(ul), .markdown-body :deep(ol) { padding-left: 1.45em; }
.markdown-body :deep(li + li) { margin-top: .25em; }
.markdown-body :deep(a) { color: #35684e; text-decoration-thickness: .08em; text-underline-offset: .16em; }
.markdown-body :deep(blockquote) { padding: .15em 0 .15em .9em; border-left: .22em solid #9bb5a5; color: #5f6963; }
.markdown-body :deep(code) { padding: .14em .34em; border-radius: .32em; color: #744b2e; background: #f1ece7; font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace; font-size: .88em; }
.markdown-body :deep(.code-block) { max-width: 100%; margin: .62em 0; overflow: hidden; border: 1px solid #dfe5e1; border-radius: .72rem; background: #f6f8f7; box-shadow: inset 0 1px rgba(255,255,255,.72); }
.markdown-body :deep(.code-block-toolbar) { display: flex; align-items: center; justify-content: space-between; min-height: 2.25rem; padding: .35rem .55rem .35rem .9rem; border-bottom: 1px solid #e3e8e5; color: #78817c; background: #f0f3f1; font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace; font-size: .72em; text-transform: lowercase; }
.markdown-body :deep(.code-copy-button) { min-width: 3.4rem; padding: .32rem .58rem; border: 1px solid transparent; border-radius: .42rem; color: #4f5c55; background: transparent; font: inherit; text-transform: none; cursor: pointer; transition: color .16s ease, background .16s ease, border-color .16s ease; }
.markdown-body :deep(.code-copy-button:hover) { border-color: #d4ddd7; color: #294d3b; background: #fff; }
.markdown-body :deep(.code-copy-button:focus-visible) { outline: 2px solid #719681; outline-offset: 1px; }
.markdown-body :deep(.code-copy-button.is-copied) { color: #2f6a4b; }
.markdown-body :deep(.code-block pre) { margin: 0; border: 0; border-radius: 0; box-shadow: none; }
.markdown-body :deep(pre) { max-width: 100%; padding: .9rem 1rem; overflow: auto; border: 1px solid #dfe5e1; border-radius: .72rem; background: #f6f8f7; box-shadow: inset 0 1px rgba(255,255,255,.72); }
.markdown-body :deep(pre code) { padding: 0; color: #242b27; background: transparent; font-size: .84em; line-height: 1.62; }
.markdown-body :deep(table) { display: block; max-width: 100%; overflow-x: auto; border-collapse: collapse; }
.markdown-body :deep(th), .markdown-body :deep(td) { padding: .45em .65em; border: 1px solid #dfe4e0; text-align: left; }
.markdown-body :deep(th) { background: #f3f6f4; font-weight: 650; }
.markdown-body :deep(hr) { margin: 1.2em 0; border: 0; border-top: 1px solid #e1e5e2; }
.markdown-body :deep(img) { max-width: 100%; height: auto; border-radius: .65rem; }
.markdown-body :deep(.katex-display) { max-width: 100%; margin: .8em 0; padding: .35em 0; overflow-x: auto; overflow-y: hidden; }
</style>
