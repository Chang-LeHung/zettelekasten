<script setup lang="ts">
import { nextTick, ref } from 'vue'

const props = defineProps<{ name: string; save: (name: string) => Promise<void> }>()
const editing = ref(false)
const saving = ref(false)
const draft = ref('')
const error = ref('')
const input = ref<HTMLInputElement | null>(null)

async function start() {
  draft.value = props.name
  error.value = ''
  editing.value = true
  await nextTick()
  input.value?.focus()
  input.value?.select()
}
function cancel() {
  if (!saving.value) editing.value = false
}
async function submit() {
  if (saving.value) return
  const name = draft.value.trim()
  if (!name || /[\x00-\x1f\x7f]/u.test(name)) {
    error.value = 'Enter a valid asset name.'
    return
  }
  if (name === props.name) { cancel(); return }
  saving.value = true
  error.value = ''
  try {
    await props.save(name)
    editing.value = false
  } catch {
    error.value = 'Could not rename the asset. Please retry.'
    await nextTick()
    input.value?.focus()
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <form v-if="editing" class="asset-rename-form" @submit.prevent="submit" @keydown.esc.stop.prevent="cancel">
    <input ref="input" v-model="draft" maxlength="500" aria-label="Asset name" :readonly="saving" @blur="cancel" />
    <small v-if="error" role="alert">{{ error }}</small>
    <span v-else>{{ saving ? 'Saving…' : 'Enter to save · Esc to cancel' }}</span>
  </form>
  <button v-else class="asset-rename-button" type="button" :aria-label="`Rename ${name}`" title="Rename asset" @click.stop="start">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="m15 4 5 5M4 20l5-1L20 8a2 2 0 0 0-5-5L4 14z" /></svg>
  </button>
</template>

<style scoped>
.asset-rename-button { position: absolute; right: 1.9rem; top: .25rem; display: grid; place-items: center; width: 1.45rem; height: 1.45rem; padding: .3rem; border: 0; border-radius: .4rem; color: #67716b; background: #f7f8f7; cursor: pointer; }
.asset-rename-button:hover { color: #345442; background: #e5ebe7; }
.asset-rename-button svg { width: 100%; height: 100%; }
.asset-rename-form { position: absolute; inset: 0; display: flex; flex-direction: column; justify-content: center; gap: .3rem; padding: .5rem; background: #f7f9f7; }
.asset-rename-form input { width: 100%; min-width: 0; box-sizing: border-box; padding: .4rem .5rem; border: 1px solid #8da997; border-radius: .4rem; font: inherit; font-size: .7rem; }
.asset-rename-form span, .asset-rename-form small { font-size: .55rem; color: #66736b; }
.asset-rename-form small { color: #9b4545; }
</style>
