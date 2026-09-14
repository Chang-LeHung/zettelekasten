<script setup lang="ts">
import MarkdownContent from './MarkdownContent.vue'

defineProps<{ content: string }>()
</script>

<template>
  <div class="slides-markdown">
    <MarkdownContent :content="content" allow-html presentation />
  </div>
</template>

<style scoped>
.slides-markdown { min-width: 0; color: inherit; font: inherit; }

/* Presentation callouts are intentionally scoped here. Normal chat, card and
   article Markdown keeps its original restrained left-rule quotation style. */
.slides-markdown :deep(.presentation-markdown blockquote) {
  margin: .7em .4rem;
  padding: .78em 1em;
  border: 0;
  border-radius: .75em;
  color: inherit;
  background: #f4faf8;
  box-shadow: 0 4px 16px rgb(0 0 0 / 9%), 0 1px 4px rgb(0 0 0 / 4%);
  font-style: normal;
}
.slides-markdown :deep(.presentation-markdown blockquote > :first-child) { margin-top: 0; }
.slides-markdown :deep(.presentation-markdown blockquote > :last-child) { margin-bottom: 0; }
.slides-markdown :deep(.presentation-markdown blockquote blockquote) {
  margin: .6em 0;
  background: #eaf3ee;
  box-shadow: 0 2px 8px rgb(0 0 0 / 6%);
}
</style>
