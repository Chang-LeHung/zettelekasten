<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import type { AgentSlashCommand } from '../api/types'

const props = defineProps<{
  commands: AgentSlashCommand[]
  activeIndex: number
  loading: boolean
  heading: string
  hint: string
  emptyLabel: string
}>()

defineEmits<{
  select: [index: number]
  hover: [index: number]
}>()

const list = ref<HTMLElement | null>(null)

function revealActiveCommand(): void {
  const rows = list.value?.querySelectorAll<HTMLButtonElement>('button')
  rows?.[props.activeIndex]?.scrollIntoView?.({ block: 'nearest' })
}

watch(() => props.activeIndex, () => { void nextTick(revealActiveCommand) })
watch(() => props.commands.length, () => { void nextTick(revealActiveCommand) })
</script>

<template>
  <div class="slash-menu" role="listbox">
    <header>
      <span>{{ heading }}</span>
      <small>{{ hint }}</small>
    </header>
    <div v-if="loading" class="slash-menu-empty">Loading…</div>
    <div v-else-if="!commands.length" class="slash-menu-empty">{{ emptyLabel }}</div>
    <div v-else ref="list" class="slash-menu-list" @wheel.stop>
      <button
        v-for="(command, index) in commands"
        :key="command.id"
        type="button"
        role="option"
        :aria-selected="index === activeIndex"
        :class="{ active: index === activeIndex }"
        @mouseenter="$emit('hover', index)"
        @mousedown.prevent="$emit('select', index)"
      >
        <code>/{{ command.name }}</code>
        <span>{{ command.description }}</span>
        <small>{{ command.type }}</small>
      </button>
    </div>
  </div>
</template>

<style scoped>
.slash-menu { --slash-menu-row: 2.3rem; position: absolute; left: .45rem; right: .45rem; bottom: calc(100% + .45rem); z-index: 40; min-height: 0; display: flex; flex-direction: column; max-height: min(28rem, 60vh); overflow: hidden; border: 1px solid rgba(29,29,31,.12); border-radius: .78rem; background: rgba(255,255,255,.98); box-shadow: 0 14px 38px rgba(24,35,28,.16); backdrop-filter: blur(12px); }
.slash-menu > header { display: flex; align-items: baseline; justify-content: space-between; gap: 1rem; padding: .55rem .72rem .42rem; border-bottom: 1px solid #edf0ee; color: #5f6b64; font-size: .65rem; font-weight: 720; letter-spacing: .045em; text-transform: uppercase; }
.slash-menu > header small { color: #919a95; font-size: .58rem; font-weight: 560; letter-spacing: 0; text-transform: none; }
.slash-menu-list { min-height: 0; flex: 1 1 auto; max-height: calc(var(--slash-menu-row) * 5 + .6rem); overflow-y: auto; overscroll-behavior: contain; padding: .3rem .15rem .3rem .3rem; scrollbar-color: #8fa397 #edf1ee; scrollbar-gutter: stable; scrollbar-width: auto; }
.slash-menu-list::-webkit-scrollbar { width: .58rem; }
.slash-menu-list::-webkit-scrollbar-track { border-radius: 999px; background: #edf1ee; }
.slash-menu-list::-webkit-scrollbar-thumb { border: 2px solid #edf1ee; border-radius: 999px; background: #8fa397; }
.slash-menu-list button { width: 100%; min-width: 0; min-height: var(--slash-menu-row); display: grid; grid-template-columns: auto minmax(0, 1fr) auto; align-items: center; gap: .55rem; padding: .4rem .55rem; border: 0; border-radius: .55rem; color: #493f35; background: transparent; text-align: left; cursor: pointer; }
.slash-menu-list button.active { background: #edf4ef; }
.slash-menu-list code { max-width: 10rem; overflow: hidden; color: #2e6046; font-family: "SFMono-Regular", Consolas, monospace; font-size: .64rem; text-overflow: ellipsis; white-space: nowrap; }
.slash-menu-list span { min-width: 0; overflow: hidden; color: #69736d; font-size: .64rem; text-overflow: ellipsis; white-space: nowrap; }
.slash-menu-list small { padding: .18rem .35rem; border-radius: 999px; color: #64766b; background: #e7eee9; font-size: .54rem; font-weight: 680; text-transform: uppercase; }
.slash-menu-empty { padding: 1rem .8rem; color: #8b948e; font-size: .68rem; text-align: center; }
@container composer-footer (max-width: 520px) {
  .slash-menu { --slash-menu-row: 3.35rem; left: .2rem; right: .2rem; bottom: calc(100% + .3rem); max-height: min(24rem, 60vh); }
  .slash-menu-list button { grid-template-columns: 1fr auto; gap: .2rem .45rem; }
  .slash-menu-list code, .slash-menu-list span { grid-column: 1; }
  .slash-menu-list small { grid-column: 2; grid-row: 1 / span 2; }
}
</style>
