<script setup lang="ts">
import { onBeforeUnmount, ref } from 'vue'

const props = defineProps<{
  content: string
  label?: string
  compact?: boolean
  flush?: boolean
}>()

const copied = ref(false)
let resetTimer: number | null = null

async function copyContent(): Promise<void> {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(props.content)
  } else {
    const field = document.createElement('textarea')
    field.value = props.content
    field.style.position = 'fixed'
    field.style.opacity = '0'
    document.body.append(field)
    field.select()
    document.execCommand('copy')
    field.remove()
  }
  copied.value = true
  if (resetTimer !== null) window.clearTimeout(resetTimer)
  resetTimer = window.setTimeout(() => {
    copied.value = false
    resetTimer = null
  }, 1_500)
}

onBeforeUnmount(() => {
  if (resetTimer !== null) window.clearTimeout(resetTimer)
})
</script>

<template>
  <div class="trace-copy-block" :class="{ compact, flush }">
    <button
      class="trace-copy-button"
      type="button"
      :aria-label="`Copy ${label || 'content'}`"
      :title="`Copy ${label || 'content'}`"
      @click="copyContent"
    >
      <svg aria-hidden="true"><use href="#icon-copy" /></svg>
      <span>{{ copied ? 'Copied' : 'Copy' }}</span>
    </button>
    <pre>{{ content }}</pre>
  </div>
</template>

<style scoped>
.trace-copy-block { position: relative; margin-top: .5rem; }
.trace-copy-block.flush { margin-top: 0; }
.trace-copy-block pre { max-height: 16rem; margin: 0; padding: .6rem 4.15rem .6rem .68rem; overflow: auto; border-radius: .52rem; color: #3f4a43; background: #f5f7f5; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; font-size: .62rem; line-height: 1.52; white-space: pre-wrap; overflow-wrap: anywhere; scrollbar-width: thin; }
.trace-copy-block.compact pre { max-height: 12rem; }
.trace-copy-button { position: absolute; top: .32rem; right: .34rem; z-index: 1; min-height: 1.42rem; display: inline-flex; align-items: center; gap: .2rem; padding: 0 .36rem; border: 1px solid #d6dfd9; border-radius: .36rem; color: #67776c; background: rgba(255,255,255,.94); cursor: pointer; font-size: .5rem; font-weight: 650; }
.trace-copy-button:hover, .trace-copy-button:focus-visible { border-color: #aebfb4; color: #31523f; background: #edf3ef; outline: none; }
.trace-copy-button svg { width: .62rem; height: .62rem; fill: none; stroke: currentColor; stroke-width: 1.7; stroke-linecap: round; stroke-linejoin: round; }
</style>
