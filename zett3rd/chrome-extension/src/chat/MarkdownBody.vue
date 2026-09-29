<!--
  One rendered answer, styled like the browser app's thread content.

  The styles are the app's `.markdown-body` rules, minus the pieces the panel has
  no use for: no figures, no diagrams, no KaTeX (those need the app's heavier
  renderers). Code blocks keep the app's toolbar and copy button.
-->

<script setup lang="ts">
import { computed } from 'vue'

import { renderMarkdown } from './markdown'

const props = defineProps<{ content: string }>()

const html = computed(() => renderMarkdown(props.content))
const COPY_RESET_DELAY_MS = 1600

/** The copy button a rendered block carries is the only control in an answer,
 * so one delegated handler covers every block on the page. */
async function handleClick(event: MouseEvent): Promise<void> {
  const target = event.target
  if (!(target instanceof Element)) return
  const button = target.closest<HTMLButtonElement>('[data-code-copy]')
  const code = button?.closest('.code-block')?.querySelector('code')?.textContent
  if (!button || code === null || code === undefined) return
  const originalLabel = button.getAttribute('aria-label') ?? 'Copy'
  const label = await navigator.clipboard.writeText(code).then(
    () => {
      button.classList.add('is-copied')
      return 'Copied'
    },
    () => 'Copy failed',
  )
  button.setAttribute('aria-label', label)
  button.setAttribute('title', label)
  window.setTimeout(() => {
    button.setAttribute('aria-label', originalLabel)
    button.setAttribute('title', originalLabel)
    button.classList.remove('is-copied')
  }, COPY_RESET_DELAY_MS)
}
</script>

<template>
  <!-- eslint-disable-next-line vue/no-v-html -- sanitized by renderMarkdown -->
  <div class="markdown-body" v-html="html" @click="handleClick" />
</template>

<style>
.markdown-body {
  min-width: 0;
  color: inherit;
  font: inherit;
  line-height: 1.65;
  overflow-wrap: anywhere;
}
.markdown-body > :first-child { margin-top: 0; }
.markdown-body > :last-child { margin-bottom: 0; }
.markdown-body p, .markdown-body ul, .markdown-body ol, .markdown-body blockquote, .markdown-body pre, .markdown-body table { margin: .62em 0; }
.markdown-body h1, .markdown-body h2, .markdown-body h3, .markdown-body h4 { margin: 1.15em 0 .48em; color: inherit; line-height: 1.28; letter-spacing: -.015em; }
.markdown-body h1 { font-size: 1.55em; }
.markdown-body h2 { font-size: 1.32em; }
.markdown-body h3 { font-size: 1.15em; }
.markdown-body ul, .markdown-body ol { padding-left: 1.45em; }
.markdown-body li + li { margin-top: .25em; }
.markdown-body a { color: #35684e; text-decoration: none; }
.markdown-body a:hover { color: #214b35; }
.markdown-body a:focus-visible { outline: 2px solid currentColor; outline-offset: 3px; border-radius: 2px; }
.markdown-body blockquote { margin-left: 0; padding: .1em 0 .1em 1em; border-left: 3px solid #d7e2da; color: #5d6a62; }
.markdown-body code {
  padding: .14em .34em;
  border-radius: .32em;
  color: #744b2e;
  background: #f1ece7;
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
  font-size: .88em;
}
.markdown-body .code-block { max-width: 100%; margin: .72em 0; overflow: hidden; border: 0; border-radius: 1.05rem; background: #f1f1f1; box-shadow: 0 5px 18px rgb(0 0 0 / 9%), 0 1px 4px rgb(0 0 0 / 4%); }
.markdown-body .code-block-toolbar { display: flex; align-items: center; justify-content: space-between; min-height: 2.75rem; padding: .5rem .72rem .3rem 1rem; color: #393d3a; font-size: .78em; font-weight: 620; }
.markdown-body .code-language { display: flex; align-items: center; gap: .55rem; }
.markdown-body .code-language svg { width: 1rem; height: 1rem; fill: none; stroke: currentColor; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; }
.markdown-body .code-copy-button { display: inline-grid; place-items: center; min-width: 2rem; height: 2rem; padding: .3rem; border: 1px solid transparent; border-radius: .55rem; color: #555c58; background: transparent; font: inherit; text-transform: none; cursor: pointer; transition: color .16s ease, background .16s ease, border-color .16s ease; }
.markdown-body .code-copy-button svg { width: 1.08rem; height: 1.08rem; fill: none; stroke: currentColor; stroke-width: 1.7; stroke-linecap: round; stroke-linejoin: round; }
.markdown-body .code-copy-button:hover { border-color: #d5d8d6; color: #294d3b; background: rgb(255 255 255 / 72%); }
.markdown-body .code-copy-button:focus-visible { outline: 2px solid #719681; outline-offset: 1px; }
.markdown-body .code-copy-button.is-copied { color: #2f6a4b; }
.markdown-body .code-block pre { max-width: 100%; margin: 0; padding: .35rem 1.15rem 1.15rem; overflow: auto; border: 0; border-radius: 0; background: transparent; box-shadow: none; }
.markdown-body pre { max-width: 100%; padding: .9rem 1rem; overflow: auto; border: 1px solid #dfe5e1; border-radius: .72rem; background: #f6f8f7; box-shadow: inset 0 1px rgba(255,255,255,.72); }
.markdown-body pre code { padding: 0; color: #242b27; background: transparent; font-size: .84em; line-height: 1.62; }
.markdown-body table { width: 100%; border-collapse: collapse; font-size: .92em; }
.markdown-body th, .markdown-body td { padding: .38em .5em; border: 1px solid #e2e7e3; text-align: left; }
.markdown-body th { background: #f5f7f5; font-weight: 620; }
.markdown-body hr { margin: 1.1em 0; border: 0; border-top: 1px solid #e4e8e5; }
.markdown-body img { max-width: 100%; height: auto; border-radius: .5rem; }
</style>
