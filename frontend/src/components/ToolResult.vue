<script setup lang="ts">
import { computed } from 'vue'
import { toolOutputParts } from '../utils/toolPresentation'

const props = defineProps<{
  output?: unknown
  error?: string | null
}>()
const emit = defineEmits<{
  previewImage: [image: { name: string; url: string }]
}>()

const parts = computed(() => props.error ? null : toolOutputParts(props.output))

function formatValue(value: unknown): string {
  if (value === undefined) return 'Waiting for result…'
  if (typeof value === 'string') return value
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}
</script>

<template>
  <pre v-if="error" class="tool-result-text error">{{ error }}</pre>
  <div v-else-if="parts" class="tool-result-parts">
    <template v-for="(part, index) in parts" :key="`${part.type}-${index}`">
      <pre v-if="part.type === 'text'" class="tool-result-text">{{ part.text }}</pre>
      <figure v-else class="tool-result-image">
        <button
          class="tool-result-image-button"
          type="button"
          :aria-label="`Preview ${part.alt_text || 'tool result image'}`"
          @click="emit('previewImage', { name: part.alt_text || 'Tool result image', url: part.url })"
        >
          <img :src="part.url" :alt="part.alt_text || 'Tool result image'" />
        </button>
        <figcaption v-if="part.alt_text">{{ part.alt_text }}</figcaption>
      </figure>
    </template>
  </div>
  <pre v-else class="tool-result-text">{{ formatValue(output) }}</pre>
</template>

<style scoped>
.tool-result-text { max-height: 11rem; margin: 0; padding: .32rem 0; overflow: auto; border: 0; color: #465049; background: transparent; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; font-size: .62rem; line-height: 1.48; white-space: pre-wrap; overflow-wrap: anywhere; }
.tool-result-text.error { color: #8d4040; }
.tool-result-parts { display: grid; gap: .45rem; }
.tool-result-image { display: grid; gap: .25rem; justify-items: start; margin: 0; }
.tool-result-image-button { display: block; max-width: 100%; padding: 0; border: 0; border-radius: .55rem; background: transparent; cursor: zoom-in; }
.tool-result-image-button:hover img { box-shadow: 0 0 0 2px rgba(71,105,87,.22); }
.tool-result-image-button:focus-visible { outline: 3px solid rgba(71,105,87,.24); outline-offset: 2px; }
.tool-result-image img { display: block; max-width: min(100%, 34rem); max-height: 24rem; border: 1px solid #dfe5e1; border-radius: .55rem; object-fit: contain; background: #f5f7f5; }
.tool-result-image figcaption { color: #8b948f; font-size: .56rem; overflow-wrap: anywhere; }
</style>
