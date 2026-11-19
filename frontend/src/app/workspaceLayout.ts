import { computed, ref } from 'vue'
import {
  DEFAULT_CHAT_SHARE,
  SHARE_STEP,
  clampShare,
  parseMode,
  parseShare,
  readStored,
  shareFromPointer,
  writeStored,
  type WorkspaceMode,
} from '../utils/workspaceLayout'

const MODE_KEY = 'zett.workspace-mode'
const SHARE_KEY = 'zett.workspace-chat-share'

export const workspaceMode = ref<WorkspaceMode>(parseMode(readStored(MODE_KEY)))
export const chatShare = ref(parseShare(readStored(SHARE_KEY)))
export const resizingWorkspace = ref(false)

/** CSS variables the workspace grid reads; fractions keep the two panes proportional at any width. */
export const workspaceGridVars = computed(() => ({
  '--chat-fr': `${Math.round(chatShare.value * 1000)}fr`,
  '--art-fr': `${Math.round((1 - chatShare.value) * 1000)}fr`,
}))

export function setWorkspaceMode(mode: WorkspaceMode): void {
  workspaceMode.value = mode
  writeStored(MODE_KEY, mode)
}

function setShare(value: number): void {
  chatShare.value = clampShare(value)
  writeStored(SHARE_KEY, String(chatShare.value))
}

export function resetChatShare(): void {
  setShare(DEFAULT_CHAT_SHARE)
}

let region: { left: number; width: number } | null = null

export function startWorkspaceResize(event: PointerEvent, workspace: HTMLElement | null, chat: HTMLElement | null): void {
  if (!workspace || !chat) return
  const right = workspace.getBoundingClientRect().right
  const left = chat.getBoundingClientRect().left
  region = { left, width: right - left }
  resizingWorkspace.value = true
  ;(event.currentTarget as HTMLElement).setPointerCapture(event.pointerId)
  event.preventDefault()
}

export function moveWorkspaceResize(event: PointerEvent): void {
  if (!resizingWorkspace.value || !region) return
  setShare(shareFromPointer(event.clientX, region.left, region.width))
}

export function endWorkspaceResize(): void {
  resizingWorkspace.value = false
  region = null
}

export function keyWorkspaceResize(event: KeyboardEvent): void {
  if (event.key === 'ArrowLeft') setShare(chatShare.value - SHARE_STEP)
  else if (event.key === 'ArrowRight') setShare(chatShare.value + SHARE_STEP)
  else if (event.key === 'Home' || event.key === 'Enter') resetChatShare()
  else return
  event.preventDefault()
}
