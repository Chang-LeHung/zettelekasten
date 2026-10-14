<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref } from 'vue'
import { useI18n } from '../i18n'
import type { CardStatus } from '../api/types'
import { CARD_STATUSES, STATUS_CARD_TYPES, cardStatusLabel, statusTone, toggleCardStatusFilter } from '../utils/cardStatus'
import '../styles/cardStatusTone.css'

/**
 * The library's status filter: one button that opens a panel of every status,
 * grouped by card type, instead of a dozen chips competing with the type row.
 * What is selected stays visible beside the button as removable tags.
 */
const props = defineProps<{ modelValue: readonly CardStatus[] }>()
const emit = defineEmits<{ 'update:modelValue': [value: CardStatus[]] }>()
const { t } = useI18n()

const open = ref(false)
const trigger = ref<HTMLButtonElement | null>(null)
const panel = ref<HTMLElement | null>(null)
const position = ref<Record<string, string>>({})
// Phones get a sheet pinned to the bottom edge, where a thumb can reach it.
const sheet = ref(false)

const count = computed(() => props.modelValue.length)

function setAll(next: CardStatus[]): void {
  emit('update:modelValue', next)
}

function toggle(status: CardStatus): void {
  setAll(toggleCardStatusFilter(props.modelValue, status))
}

function place(): void {
  sheet.value = window.matchMedia('(max-width: 600px)').matches
  const anchor = trigger.value?.getBoundingClientRect()
  if (!anchor || sheet.value) {
    position.value = {}
    return
  }
  const width = Math.min(34 * 16, window.innerWidth - 16)
  const height = panel.value?.offsetHeight ?? 300
  const below = window.innerHeight - anchor.bottom
  const top = below >= height + 12 || anchor.top < height + 12 ? anchor.bottom + 6 : anchor.top - height - 6
  position.value = { top: `${top}px`, left: `${Math.min(Math.max(8, anchor.left), window.innerWidth - width - 8)}px`, width: `${width}px` }
}

function close(restoreFocus = false): void {
  if (!open.value) return
  open.value = false
  document.removeEventListener('pointerdown', onOutside, true)
  window.removeEventListener('resize', place)
  window.removeEventListener('scroll', place, true)
  if (restoreFocus) trigger.value?.focus()
}

function onOutside(event: Event): void {
  const target = event.target
  if (target instanceof Node && (trigger.value?.contains(target) || panel.value?.contains(target))) return
  close()
}

async function openPanel(): Promise<void> {
  if (open.value) return close(true)
  open.value = true
  place()
  document.addEventListener('pointerdown', onOutside, true)
  window.addEventListener('resize', place)
  window.addEventListener('scroll', place, true)
  await nextTick()
  place()
  panel.value?.querySelector<HTMLElement>('button[role="checkbox"]')?.focus()
}

function onPanelKey(event: KeyboardEvent): void {
  if (event.key !== 'Escape') return
  event.stopPropagation()
  close(true)
}

onBeforeUnmount(() => close())
</script>

<template>
  <div class="status-filter">
    <button
      ref="trigger"
      class="status-filter-trigger"
      :class="{ engaged: count > 0 }"
      type="button"
      aria-haspopup="dialog"
      :aria-expanded="open"
      @click="openPanel"
    >
      <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M2.5 4h11M4.5 8h7M6.5 12h3" /></svg>
      <span>{{ t('cardStatus.filter') }}</span>
      <b v-if="count" class="status-filter-count">{{ count }}</b>
    </button>

    <ul v-if="count" class="status-filter-tags" :aria-label="t('cardStatus.filter')">
      <li v-for="status in modelValue" :key="status">
        <button class="status-tag" :class="statusTone(status)" type="button" :aria-label="`${t(cardStatusLabel(status))} ×`" @click="toggle(status)">
          <i aria-hidden="true" />{{ t(cardStatusLabel(status)) }}<span aria-hidden="true">×</span>
        </button>
      </li>
      <li><button class="status-clear" type="button" @click="setAll([])">{{ t('cardStatus.clear') }}</button></li>
    </ul>

    <Teleport to="body">
      <div
        v-if="open"
        ref="panel"
        class="status-panel"
        :class="{ sheet }"
        role="dialog"
        :aria-label="t('cardStatus.filter')"
        :style="position"
        @keydown="onPanelKey"
      >
        <div class="status-panel-grid">
          <section v-for="cardType in STATUS_CARD_TYPES" :key="cardType">
            <h3>{{ t(`cardType.${cardType}`) }}</h3>
            <button
              v-for="status in CARD_STATUSES[cardType]"
              :key="status"
              class="status-option"
              :class="statusTone(status)"
              type="button"
              role="checkbox"
              :aria-checked="modelValue.includes(status)"
              @click="toggle(status)"
            >
              <i aria-hidden="true" />
              <span>{{ t(cardStatusLabel(status)) }}</span>
              <svg viewBox="0 0 12 12" aria-hidden="true"><path d="m2.6 6.4 2.2 2.2 4.6-5" /></svg>
            </button>
          </section>
        </div>
        <footer>
          <button class="status-clear" type="button" :disabled="!count" @click="setAll([])">{{ t('cardStatus.clear') }}</button>
          <button class="status-apply" type="button" @click="close(true)">{{ t('cardStatus.close') }}</button>
        </footer>
      </div>
    </Teleport>
  </div>
</template>

<style>
.status-filter { display: inline-flex; flex-wrap: wrap; align-items: center; gap: .45rem; min-width: 0; }
.status-filter-trigger { display: inline-flex; align-items: center; gap: .4rem; min-height: 1.85rem; padding: 0 .7rem; border: 1px solid rgba(29,29,31,.1); border-radius: .58rem; color: #5f6862; background: rgba(255,255,255,.7); cursor: pointer; font-size: .72rem; font-weight: 610; transition: background 140ms ease, border-color 140ms ease; }
.status-filter-trigger:hover, .status-filter-trigger[aria-expanded="true"] { color: #2f3a33; background: #fff; border-color: rgba(29,29,31,.18); }
.status-filter-trigger.engaged { color: #2f5541; border-color: rgba(71,105,87,.3); background: #edf3ef; }
.status-filter-trigger svg { width: .9rem; height: .9rem; fill: none; stroke: currentColor; stroke-width: 1.5; stroke-linecap: round; }
.status-filter-count { display: grid; place-items: center; min-width: 1.15rem; height: 1.15rem; padding: 0 .25rem; border-radius: 1rem; color: #fff; background: #3d7a57; font-size: .62rem; font-weight: 700; }
.status-filter-tags { display: contents; margin: 0; padding: 0; list-style: none; }
.status-filter-tags li { display: contents; }
.status-tag { display: inline-flex; align-items: center; gap: .38rem; min-height: 1.7rem; padding: 0 .35rem 0 .6rem; border: 1px solid var(--status-line); border-radius: 2rem; color: var(--status-ink); background: var(--status-soft); cursor: pointer; font-size: .7rem; font-weight: 640; }
.status-tag i, .status-option i { width: .46rem; height: .46rem; flex: 0 0 auto; border-radius: 50%; background: var(--status-ink); }
.status-tag span { display: grid; place-items: center; width: 1.1rem; height: 1.1rem; border-radius: 50%; opacity: .6; font-size: .85rem; line-height: 1; }
.status-tag:hover span { opacity: 1; background: rgba(0,0,0,.07); }
.status-clear { padding: 0 .4rem; border: 0; color: #7a847d; background: transparent; cursor: pointer; font-size: .7rem; font-weight: 600; }
.status-clear:hover:not(:disabled) { color: #2f3a33; text-decoration: underline; }
.status-clear:disabled { opacity: .4; cursor: default; }

.status-panel { position: fixed; z-index: 1450; padding: .6rem .6rem .5rem; border: 1px solid rgba(29,29,31,.09); border-radius: .9rem; background: rgba(255,255,255,.98); box-shadow: 0 18px 54px rgba(24,28,26,.18), 0 2px 8px rgba(24,28,26,.06); backdrop-filter: blur(18px); animation: status-panel-in 130ms ease-out; }
.status-panel-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: .4rem; }
.status-panel h3 { margin: .15rem .5rem .3rem; color: #8a918c; font-size: .68rem; font-weight: 650; }
.status-option { display: flex; align-items: center; gap: .5rem; width: 100%; min-height: 2.1rem; padding: 0 .5rem; border: 0; border-radius: .5rem; color: #3b4440; background: transparent; cursor: pointer; font-size: .76rem; font-weight: 560; text-align: left; }
.status-option span { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.status-option svg { width: .75rem; height: .75rem; flex: 0 0 auto; fill: none; stroke: currentColor; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; opacity: 0; }
.status-option:hover, .status-option:focus-visible { outline: 0; background: var(--status-soft); }
.status-option[aria-checked="true"] { color: var(--status-ink); background: var(--status-soft); font-weight: 680; }
.status-option[aria-checked="true"] svg { opacity: 1; }
.status-panel footer { display: flex; align-items: center; justify-content: space-between; margin-top: .45rem; padding: .45rem .3rem 0; border-top: 1px solid #eef0ee; }
.status-apply { height: 1.85rem; padding: 0 .85rem; border: 0; border-radius: .5rem; color: #fff; background: #3d6a52; cursor: pointer; font-size: .74rem; font-weight: 620; }
@keyframes status-panel-in { from { opacity: 0; transform: translateY(-3px) scale(.99); } }

/* A narrow screen cannot spare three columns, so the panel becomes a sheet and the groups stack. */
@media (max-width: 600px) {
  .status-panel.sheet { top: auto; right: 0; bottom: 0; left: 0; width: auto; max-height: 78dvh; overflow-y: auto; padding-bottom: max(.7rem, env(safe-area-inset-bottom)); border-radius: 1.1rem 1.1rem 0 0; animation: status-sheet-in 180ms ease-out; }
  .status-panel.sheet .status-panel-grid { grid-template-columns: 1fr; gap: .15rem; }
  .status-panel.sheet .status-option { min-height: 2.6rem; font-size: .84rem; }
}
@keyframes status-sheet-in { from { transform: translateY(24px); opacity: 0; } }
@media (prefers-reduced-motion: reduce) { .status-panel, .status-panel.sheet { animation: none; } }
</style>
