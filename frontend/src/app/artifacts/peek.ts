import { computed, ref } from 'vue'
import { artifacts, selectedArtifactId } from './state'

/** How long the pointer rests on a list item before its preview appears; skimming past shows nothing. */
export const PEEK_DELAY_MS = 180
/** Grace period when the pointer moves from one item to the next, so the preview does not flash off. */
const PEEK_RELEASE_MS = 90

const peekedId = ref<string | null>(null)
let showTimer: number | null = null
let hideTimer: number | null = null

function clear(timer: number | null): null {
  if (timer !== null) window.clearTimeout(timer)
  return null
}

/** The artifact being previewed on hover; never the one that is already open. */
export const peekedArtifact = computed(() => {
  const id = peekedId.value
  if (!id || id === selectedArtifactId.value) return null
  return artifacts.value.find((artifact) => artifact.id === id) ?? null
})

export function startPeek(id: string): void {
  hideTimer = clear(hideTimer)
  showTimer = clear(showTimer)
  if (id === selectedArtifactId.value) { peekedId.value = null; return }
  // Moving between items keeps the preview up and swaps it at once.
  if (peekedArtifact.value !== null) { peekedId.value = id; return }
  peekedId.value = null
  showTimer = window.setTimeout(() => { peekedId.value = id }, PEEK_DELAY_MS)
}

export function endPeek(): void {
  showTimer = clear(showTimer)
  hideTimer = clear(hideTimer)
  hideTimer = window.setTimeout(() => { peekedId.value = null }, PEEK_RELEASE_MS)
}

export function cancelPeek(): void {
  showTimer = clear(showTimer)
  hideTimer = clear(hideTimer)
  peekedId.value = null
}
