<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref } from 'vue'
import { useI18n } from '../i18n'
import type { CardStatus } from '../api/types'
import { cardStatusLabel, isActive, statusOptions, statusTone } from '../utils/cardStatus'
import '../styles/cardStatusTone.css'

const props = defineProps<{ status: CardStatus; busy?: boolean }>()
const emit = defineEmits<{ select: [status: CardStatus] }>()
const { t } = useI18n()

// Only the statuses of this card's own type: a reference is read, never done.
const options = computed(() => statusOptions(props.status))

// A status that has not started, or that ended without success, is drawn as a hollow dot.
function isHollow(status: CardStatus): boolean {
  return status === 'on_hold' || status === 'cancelled' || status === 'dropped' || status === 'captured'
}

const open = ref(false)
const trigger = ref<HTMLButtonElement | null>(null)
const menu = ref<HTMLElement | null>(null)
const position = ref<Record<string, string>>({})

// The menu is teleported to <body>: a library card clips its own overflow, so a
// menu rendered inside it would be cut off at the card edge.
function place(): void {
  const anchor = trigger.value?.getBoundingClientRect()
  if (!anchor) return
  const height = menu.value?.offsetHeight ?? options.value.length * 34 + 12
  const below = window.innerHeight - anchor.bottom
  const top = below >= height + 8 || anchor.top < height + 8 ? anchor.bottom + 6 : anchor.top - height - 6
  const left = Math.min(Math.max(8, anchor.left), Math.max(8, window.innerWidth - 188))
  position.value = { top: `${top}px`, left: `${left}px` }
}

function close(restoreFocus = false): void {
  if (!open.value) return
  open.value = false
  document.removeEventListener('pointerdown', onOutside, true)
  window.removeEventListener('resize', onViewportChange)
  window.removeEventListener('scroll', onViewportChange, true)
  if (restoreFocus) trigger.value?.focus()
}

function onOutside(event: Event): void {
  const target = event.target
  if (target instanceof Node && (trigger.value?.contains(target) || menu.value?.contains(target))) return
  close()
}

function onViewportChange(): void {
  close()
}

async function toggle(): Promise<void> {
  if (props.busy) return
  if (open.value) return close(true)
  open.value = true
  place()
  document.addEventListener('pointerdown', onOutside, true)
  window.addEventListener('resize', onViewportChange)
  window.addEventListener('scroll', onViewportChange, true)
  await nextTick()
  place()
  menu.value?.querySelector<HTMLElement>('[aria-checked="true"]')?.focus()
}

function choose(status: CardStatus): void {
  close(true)
  if (status !== props.status) emit('select', status)
}

function onMenuKey(event: KeyboardEvent): void {
  event.stopPropagation()
  if (event.key === 'Escape') {
    event.preventDefault()
    return close(true)
  }
  if (event.key !== 'ArrowDown' && event.key !== 'ArrowUp') return
  event.preventDefault()
  const items = [...(menu.value?.querySelectorAll<HTMLElement>('[role="menuitemradio"]') ?? [])]
  const index = items.indexOf(document.activeElement as HTMLElement)
  const step = event.key === 'ArrowDown' ? 1 : -1
  items[(index + step + items.length) % items.length]?.focus()
}

onBeforeUnmount(() => close())
</script>

<template>
  <button
    ref="trigger"
    class="status-pill"
    :class="[statusTone(status), { active: isActive(status), hollow: isHollow(status) }]"
    type="button"
    aria-haspopup="menu"
    :aria-expanded="open"
    :disabled="busy"
    :title="t('cardStatus.change')"
    @click.stop="toggle"
    @keydown.stop
    @pointerdown.stop
  >
    <i aria-hidden="true" />
    <span>{{ t(cardStatusLabel(status)) }}</span>
    <svg viewBox="0 0 12 12" aria-hidden="true"><path d="m3 4.5 3 3 3-3" /></svg>
  </button>
  <Teleport to="body">
    <div v-if="open" ref="menu" class="status-menu" role="menu" :aria-label="t('cardStatus.change')" :style="position" @keydown="onMenuKey" @click.stop @pointerdown.stop>
      <button
        v-for="item in options"
        :key="item"
        class="status-menu-item"
        :class="[statusTone(item), { hollow: isHollow(item) }]"
        type="button"
        role="menuitemradio"
        :aria-checked="item === status"
        @click="choose(item)"
      >
        <i aria-hidden="true" />
        <span>{{ t(cardStatusLabel(item)) }}</span>
        <svg v-if="item === status" viewBox="0 0 12 12" aria-hidden="true"><path d="m2.6 6.4 2.2 2.2 4.6-5" /></svg>
      </button>
    </div>
  </Teleport>
</template>

<style scoped>
.status-pill { display: inline-flex; align-items: center; gap: .36rem; max-width: 100%; min-height: 1.45rem; padding: 0 .45rem 0 .5rem; border: 1px solid var(--status-line); border-radius: 2rem; color: var(--status-ink); background: var(--status-soft); cursor: pointer; font-size: .64rem; font-weight: 650; line-height: 1; white-space: nowrap; transition: filter 140ms ease, box-shadow 140ms ease; }
.status-pill:hover:not(:disabled) { filter: brightness(.97); box-shadow: 0 1px 4px rgba(25, 36, 29, .1); }
.status-pill:focus-visible { outline: 2px solid var(--status-ink); outline-offset: 1px; }
.status-pill:disabled { cursor: progress; opacity: .6; }
.status-pill i, .status-menu-item i { width: .46rem; height: .46rem; flex: 0 0 auto; border-radius: 50%; background: var(--status-ink); }
.status-pill.active i { animation: status-pulse 1.6s ease-in-out infinite; }
.status-pill.hollow i, .status-menu-item.hollow i { background: transparent; box-shadow: inset 0 0 0 1.5px var(--status-ink); }
.status-pill svg { width: .62rem; height: .62rem; fill: none; stroke: currentColor; stroke-width: 1.5; stroke-linecap: round; stroke-linejoin: round; opacity: .7; }
.status-menu { position: fixed; z-index: 1400; width: 11.5rem; padding: .3rem; border: 1px solid rgba(29, 29, 31, .09); border-radius: .8rem; background: rgba(255, 255, 255, .98); box-shadow: 0 14px 40px rgba(24, 28, 26, .16), 0 2px 8px rgba(24, 28, 26, .06); backdrop-filter: blur(16px); animation: status-menu-in 120ms ease-out; }
.status-menu-item { display: flex; align-items: center; gap: .55rem; width: 100%; min-height: 2.05rem; padding: 0 .6rem; border: 0; border-radius: .52rem; color: #3b4440; background: transparent; cursor: pointer; font-size: .74rem; font-weight: 580; text-align: left; }
.status-menu-item:hover, .status-menu-item:focus-visible { outline: 0; background: var(--status-soft); color: var(--status-ink); }
.status-menu-item[aria-checked="true"] { color: var(--status-ink); background: var(--status-soft); font-weight: 680; }
.status-menu-item span { flex: 1; }
.status-menu-item svg { width: .72rem; height: .72rem; fill: none; stroke: currentColor; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; }
@keyframes status-pulse { 50% { opacity: .35; } }
@keyframes status-menu-in { from { opacity: 0; transform: translateY(-3px) scale(.98); } }
@media (prefers-reduced-motion: reduce) {
  .status-pill.active i, .status-menu { animation: none; }
}
</style>
