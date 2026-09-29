<!--
  One rendered answer, styled like the browser app's thread content.

  The styles are the app's `.markdown-body` rules, minus the pieces the panel has
  no use for: no figures, no diagrams, no KaTeX (those need the app's heavier
  renderers), and no copy button chrome.
-->

<script setup lang="ts">
import { computed } from 'vue'

import { renderMarkdown } from './markdown'

const props = defineProps<{ content: string }>()

const html = computed(() => renderMarkdown(props.content))
</script>

<template>
  <!-- eslint-disable-next-line vue/no-v-html -- sanitized by renderMarkdown -->
  <div class="markdown-body" v-html="html" />
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
.markdown-body pre.code-block {
  max-width: 100%;
  margin: .72em 0;
  padding: .7rem .8rem;
  overflow-x: auto;
  border-radius: 1.05rem;
  background: #f1f1f1;
  box-shadow: 0 5px 18px rgb(0 0 0 / 9%), 0 1px 4px rgb(0 0 0 / 4%);
}
.markdown-body pre.code-block code { padding: 0; color: inherit; background: transparent; font-size: .78em; }
.markdown-body table { width: 100%; border-collapse: collapse; font-size: .92em; }
.markdown-body th, .markdown-body td { padding: .38em .5em; border: 1px solid #e2e7e3; text-align: left; }
.markdown-body th { background: #f5f7f5; font-weight: 620; }
.markdown-body hr { margin: 1.1em 0; border: 0; border-top: 1px solid #e4e8e5; }
.markdown-body img { max-width: 100%; height: auto; border-radius: .5rem; }
</style>
