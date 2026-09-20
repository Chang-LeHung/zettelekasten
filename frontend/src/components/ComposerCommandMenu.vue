<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'

/**
 * One composer capability row. Slash commands and `@` references share this
 * menu; only the trigger and the badge text differ.
 */
interface ComposerCommandItem {
  id: string
  name: string
  description: string
  badge: string
}

const props = withDefaults(defineProps<{
  items: ComposerCommandItem[]
  activeIndex: number
  loading: boolean
  heading: string
  hint: string
  emptyLabel: string
  trigger?: string
}>(), { trigger: '/' })

defineEmits<{
  select: [index: number]
  hover: [index: number]
}>()

const list = ref<HTMLElement | null>(null)

function revealActiveItem(): void {
  const rows = list.value?.querySelectorAll<HTMLButtonElement>('button')
  rows?.[props.activeIndex]?.scrollIntoView?.({ block: 'nearest' })
}

watch(() => props.activeIndex, () => { void nextTick(revealActiveItem) })
watch(() => props.items.length, () => { void nextTick(revealActiveItem) })
</script>

<template>
  <div class="command-menu" role="listbox">
    <header>
      <span>{{ heading }}</span>
      <small>{{ hint }}</small>
    </header>
    <div v-if="loading" class="command-menu-empty">Loading…</div>
    <div v-else-if="!items.length" class="command-menu-empty">{{ emptyLabel }}</div>
    <div v-else ref="list" class="command-menu-list" @wheel.stop>
      <button
        v-for="(item, index) in items"
        :key="item.id"
        type="button"
        role="option"
        :aria-selected="index === activeIndex"
        :class="{ active: index === activeIndex }"
        @mouseenter="$emit('hover', index)"
        @mousedown.prevent="$emit('select', index)"
      >
        <code>{{ trigger }}{{ item.name }}</code>
        <span>{{ item.description }}</span>
        <small>{{ item.badge }}</small>
      </button>
    </div>
  </div>
</template>

<style scoped>
.command-menu { --command-menu-row: 2.3rem; position: absolute; left: .45rem; right: .45rem; bottom: calc(100% + .45rem); z-index: 40; min-height: 0; display: flex; flex-direction: column; max-height: min(28rem, 60vh); overflow: hidden; border: 1px solid rgba(29,29,31,.12); border-radius: .78rem; background: rgba(255,255,255,.98); box-shadow: 0 14px 38px rgba(24,35,28,.16); backdrop-filter: blur(12px); }
.command-menu > header { display: flex; align-items: baseline; justify-content: space-between; gap: 1rem; padding: .55rem .72rem .42rem; border-bottom: 1px solid #edf0ee; color: #5f6b64; font-size: .65rem; font-weight: 720; letter-spacing: .045em; text-transform: uppercase; }
.command-menu > header small { color: #919a95; font-size: .58rem; font-weight: 560; letter-spacing: 0; text-transform: none; }
.command-menu-list { min-height: 0; flex: 1 1 auto; max-height: calc(var(--command-menu-row) * 5 + .6rem); overflow-y: auto; overscroll-behavior: contain; padding: .3rem .15rem .3rem .3rem; scrollbar-color: #8fa397 #edf1ee; scrollbar-gutter: stable; scrollbar-width: auto; }
.command-menu-list::-webkit-scrollbar { width: .58rem; }
.command-menu-list::-webkit-scrollbar-track { border-radius: 999px; background: #edf1ee; }
.command-menu-list::-webkit-scrollbar-thumb { border: 2px solid #edf1ee; border-radius: 999px; background: #8fa397; }
.command-menu-list button { width: 100%; min-width: 0; min-height: var(--command-menu-row); display: grid; grid-template-columns: auto minmax(0, 1fr) auto; align-items: center; gap: .55rem; padding: .4rem .55rem; border: 0; border-radius: .55rem; color: #493f35; background: transparent; text-align: left; cursor: pointer; }
.command-menu-list button.active { background: #edf4ef; }
.command-menu-list code { max-width: 10rem; overflow: hidden; color: #2e6046; font-family: "SFMono-Regular", Consolas, monospace; font-size: .64rem; text-overflow: ellipsis; white-space: nowrap; }
.command-menu-list span { min-width: 0; overflow: hidden; color: #69736d; font-size: .64rem; text-overflow: ellipsis; white-space: nowrap; }
.command-menu-list small { padding: .18rem .35rem; border-radius: 999px; color: #64766b; background: #e7eee9; font-size: .54rem; font-weight: 680; text-transform: uppercase; }
.command-menu-empty { padding: 1rem .8rem; color: #8b948e; font-size: .68rem; text-align: center; }
@container composer-footer (max-width: 520px) {
  .command-menu { --command-menu-row: 3.35rem; left: .2rem; right: .2rem; bottom: calc(100% + .3rem); max-height: min(24rem, 60vh); }
  .command-menu-list button { grid-template-columns: 1fr auto; gap: .2rem .45rem; }
  .command-menu-list code, .command-menu-list span { grid-column: 1; }
  .command-menu-list small { grid-column: 2; grid-row: 1 / span 2; }
}
</style>
