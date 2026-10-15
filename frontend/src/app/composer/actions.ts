import { computed, nextTick } from 'vue'
import { aiClient } from '../../api/client'
import type { AgentSlashCommand } from '../../api/types'
import { AtCommandInput } from '../../utils/atCommand'
import { readMessageImage, rebaseImagePositions } from '../../utils/messageParts'
import { SlashCommandInput } from '../../utils/slashCommand'
import { conversationStarted } from '../conversation/state'
import { errorMessage, showNotice } from '../notice'
import { conversationId } from '../sessions'
import { runtimeSettings } from '../settings'
import type { ComposerHighlightSegment, ComposerTarget } from '../types'
import { atCommands, atCommandsLoaded, atCommandsLoading, atMenu, atMenuCommands, composerComposing, followUp, followUpComposerHighlight, followUpComposerInput, initialComposerHighlight, initialComposerInput, pendingMessageImages, raw, selectedSlashCommand, slashCommands, slashCommandsLoaded, slashCommandsLoading, slashMenu, slashMenuCommands } from './state'

export const initialTokenHighlight = computed(() => composerHighlightSegments('initial'))
export const followUpTokenHighlight = computed(() => composerHighlightSegments('follow-up'))
export async function attachPastedImages(files: File[], position: number): Promise<void> {
  const available = Math.max(0, runtimeSettings.value.max_message_images - pendingMessageImages.value.length)
  const images = files.filter((file) => file.type.startsWith('image/')).slice(0, available)
  if (!images.length) return
  try {
    pendingMessageImages.value.push(...await Promise.all(images.map((file) => readMessageImage(file, position))))
    if (images.length < files.filter((file) => file.type.startsWith('image/')).length) {
      showNotice(`A message can contain up to ${runtimeSettings.value.max_message_images} images`, 'error')
    }
  } catch (error) {
    showNotice(errorMessage(error), 'error')
  }
}
export function removeMessageImage(id: string): void {
  pendingMessageImages.value = pendingMessageImages.value.filter((image) => image.id !== id)
}
function rebaseMessageImagePositions(previous: string, next: string): void {
  pendingMessageImages.value = rebaseImagePositions(pendingMessageImages.value, previous, next)
}
function composerTextarea(target: ComposerTarget): HTMLTextAreaElement | null {
  return target === 'initial' ? initialComposerInput.value : followUpComposerInput.value
}
function composerTextValue(target: ComposerTarget): string {
  return target === 'initial' ? raw.value : followUp.value
}
function composerHighlight(target: ComposerTarget): HTMLElement | null {
  return target === 'initial' ? initialComposerHighlight.value : followUpComposerHighlight.value
}
/**
 * Highlight every composer token the backend can resolve for this text: the
 * selected slash command and any `@` reference that matches a listed resource.
 * The textarea stays transparent above this mirror so both kinds read as chips.
 */
function composerHighlightSegments(target: ComposerTarget): ComposerHighlightSegment[] | null {
  const value = composerTextValue(target)
  const marked: Array<{ start: number; end: number; kind: 'slash' | 'reference' }> = []
  const slash = detectedSlashCommand(value)
  if (slash) marked.push({ ...slash.range, kind: 'slash' })
  for (const token of AtCommandInput.tokens(value)) {
    const reference = atCommands.value.find(item => item.name === token.name)
    if (reference) marked.push({ start: token.start, end: token.end, kind: 'reference' })
  }
  if (!marked.length) return null
  marked.sort((left, right) => left.start - right.start)
  const segments: ComposerHighlightSegment[] = []
  let cursor = 0
  for (const span of marked) {
    if (span.start < cursor) continue
    if (span.start > cursor) segments.push({ text: value.slice(cursor, span.start), kind: null })
    segments.push({ text: value.slice(span.start, span.end), kind: span.kind })
    cursor = span.end
  }
  if (cursor < value.length) segments.push({ text: value.slice(cursor), kind: null })
  return segments
}
function detectedSlashCommand(value: string): { command: AgentSlashCommand; range: { start: number; end: number } } | null {
  const selected = selectedSlashCommand.value
  if (selected) {
    const range = SlashCommandInput.range(value, selected.name)
    if (range) return { command: selected, range }
  }
  for (const token of SlashCommandInput.tokens(value)) {
    const command = slashCommands.value.find(item => item.name === token.name)
    if (command) return { command, range: { start: token.start, end: token.end } }
  }
  return null
}
export function slashCommandIdFor(value: string): string | null {
  return detectedSlashCommand(value)?.command.id ?? null
}
/**
 * Resolve the `@` tokens a message already contains. Like the slash command
 * lookup, the browser submits at most one reference: the first token that still
 * matches a listed resource owns the turn.
 */
export function atCommandIdFor(value: string): string | null {
  for (const token of AtCommandInput.tokens(value)) {
    const reference = atCommands.value.find(item => item.name === token.name)
    if (reference) return reference.id
  }
  return null
}
export function syncComposerHighlight(target: ComposerTarget): void {
  const textarea = composerTextarea(target)
  const highlight = composerHighlight(target)
  if (!textarea || !highlight) return
  highlight.scrollTop = textarea.scrollTop
  highlight.scrollLeft = textarea.scrollLeft
}
export function finishComposerComposition(): void {
  window.requestAnimationFrame(() => {
    composerComposing.value = false
    syncComposerHighlight(conversationStarted.value ? 'follow-up' : 'initial')
  })
}
function setComposerTextValue(target: ComposerTarget, value: string): void {
  if (target === 'initial') raw.value = value
  else followUp.value = value
}
export function clearSlashCommand(): void {
  selectedSlashCommand.value = null
  slashMenu.value = null
  atMenu.value = null
  composerComposing.value = false
}
async function loadAtCommands(force = false): Promise<void> {
  const sessionId = conversationId.value
  if (!sessionId) {
    atCommands.value = []
    atCommandsLoaded.value = true
    return
  }
  if (atCommandsLoaded.value && !force) return
  atCommandsLoading.value = true
  try {
    const commands = await aiClient.listAtCommands(sessionId)
    if (conversationId.value === sessionId) {
      atCommands.value = commands
      atCommandsLoaded.value = true
    }
  } catch (error) {
    showNotice(errorMessage(error), 'error')
  } finally {
    if (conversationId.value === sessionId) atCommandsLoading.value = false
  }
}
function refreshAtMenu(target: ComposerTarget, value: string, caret: number): void {
  if (!atCommandsLoaded.value && !atCommandsLoading.value && AtCommandInput.tokenNames(value).length) {
    void loadAtCommands()
  }
  const match = AtCommandInput.match(value, caret)
  if (!match) {
    if (atMenu.value?.target === target) atMenu.value = null
    return
  }
  const current = atMenu.value
  const sameRange = current?.target === target
    && current.match.start === match.start
  atMenu.value = {
    target,
    match,
    activeIndex: sameRange ? current.activeIndex : 0,
  }
  // References are created and deleted during the session, so every new token
  // refreshes the list while repeated keystrokes reuse the loaded one.
  if (!atCommandsLoading.value) void loadAtCommands(!sameRange)
}
export function selectAtCommand(index: number): void {
  const menu = atMenu.value
  const command = atMenuCommands.value[index]
  if (!menu || !command) return
  const textarea = composerTextarea(menu.target)
  const insertion = AtCommandInput.insert(composerTextValue(menu.target), menu.match, command.name)
  setComposerTextValue(menu.target, insertion.value)
  atMenu.value = null
  composerComposing.value = false
  void nextTick(() => {
    textarea?.focus()
    textarea?.setSelectionRange(insertion.caret, insertion.caret)
    syncComposerHighlight(menu.target)
  })
}
export function deleteReferenceToken(event: KeyboardEvent, target: ComposerTarget): boolean {
  if (event.key !== 'Backspace' && event.key !== 'Delete') return false
  const textarea = composerTextarea(target)
  if (!textarea) return false
  const value = textarea.value
  const selectionStart = textarea.selectionStart ?? 0
  const selectionEnd = textarea.selectionEnd ?? 0
  const token = AtCommandInput.tokens(value).find((candidate) => (
    event.key === 'Backspace'
      ? selectionStart >= candidate.start && selectionStart <= candidate.end + 1
      : selectionStart >= candidate.start - 1 && selectionStart <= candidate.end
  ))
  if (!token || !atCommands.value.some(item => item.name === token.name)) return false
  const deletion = AtCommandInput.deleteAtomically(
    value,
    token.name,
    selectionStart,
    selectionEnd,
    event.key,
  )
  if (!deletion) return false
  event.preventDefault()
  setComposerTextValue(target, deletion.value)
  atMenu.value = null
  void nextTick(() => {
    textarea.focus()
    textarea.setSelectionRange(deletion.caret, deletion.caret)
    syncComposerHighlight(target)
  })
  return true
}
async function loadSlashCommands(force = false): Promise<void> {
  const sessionId = conversationId.value
  if (!sessionId) {
    slashCommands.value = []
    slashCommandsLoaded.value = true
    return
  }
  if (slashCommandsLoaded.value && !force) return
  slashCommandsLoading.value = true
  try {
    const commands = await aiClient.listSlashCommands(sessionId)
    if (conversationId.value === sessionId) {
      slashCommands.value = commands
      slashCommandsLoaded.value = true
    }
  } catch (error) {
    showNotice(errorMessage(error), 'error')
  } finally {
    if (conversationId.value === sessionId) slashCommandsLoading.value = false
  }
}
function refreshSlashMenu(target: ComposerTarget, value: string, caret: number): void {
  if (!slashCommandsLoaded.value && !slashCommandsLoading.value && SlashCommandInput.tokenNames(value).length) {
    void loadSlashCommands()
  }
  if (selectedSlashCommand.value) {
    if (SlashCommandInput.contains(value, selectedSlashCommand.value.name)) {
      slashMenu.value = null
      return
    }
    selectedSlashCommand.value = null
  }
  const match = SlashCommandInput.match(value, caret)
  if (!match) {
    if (slashMenu.value?.target === target) slashMenu.value = null
    return
  }
  const current = slashMenu.value
  const sameRange = current?.target === target
    && current.match.start === match.start
  slashMenu.value = {
    target,
    match,
    activeIndex: sameRange ? current.activeIndex : 0,
  }
  if (!slashCommandsLoading.value) void loadSlashCommands(!sameRange)
}
export function selectSlashCommand(index: number): void {
  const menu = slashMenu.value
  const command = slashMenuCommands.value[index]
  if (!menu || !command) return
  const textarea = composerTextarea(menu.target)
  const insertion = SlashCommandInput.insert(composerTextValue(menu.target), menu.match, command.name)
  setComposerTextValue(menu.target, insertion.value)
  selectedSlashCommand.value = command
  slashMenu.value = null
  composerComposing.value = false
  void nextTick(() => {
    textarea?.focus()
    textarea?.setSelectionRange(insertion.caret, insertion.caret)
    syncComposerHighlight(menu.target)
  })
}
export function deleteSelectedSlashCommand(event: KeyboardEvent, target: ComposerTarget): boolean {
  if (event.key !== 'Backspace' && event.key !== 'Delete') return false
  const command = selectedSlashCommand.value
  const textarea = composerTextarea(target)
  if (!command || !textarea) return false
  const deletion = SlashCommandInput.deleteAtomically(
    textarea.value,
    command.name,
    textarea.selectionStart ?? 0,
    textarea.selectionEnd ?? 0,
    event.key,
  )
  if (!deletion) return false
  event.preventDefault()
  setComposerTextValue(target, deletion.value)
  clearSlashCommand()
  void nextTick(() => {
    textarea.focus()
    textarea.setSelectionRange(deletion.caret, deletion.caret)
    syncComposerHighlight(target)
  })
  return true
}
export function handleComposerSelection(target: ComposerTarget, event: MouseEvent): void {
  const textarea = event.currentTarget
  if (!(textarea instanceof HTMLTextAreaElement)) return
  refreshSlashMenu(target, textarea.value, textarea.selectionStart ?? textarea.value.length)
  refreshAtMenu(target, textarea.value, textarea.selectionStart ?? textarea.value.length)
}
export function updateComposerText(event: Event, target: 'initial' | 'follow-up'): void {
  const textarea = event.target as HTMLTextAreaElement
  const next = textarea.value
  const previous = target === 'initial' ? raw.value : followUp.value
  rebaseMessageImagePositions(previous, next)
  setComposerTextValue(target, next)
  refreshSlashMenu(target, next, textarea.selectionStart ?? next.length)
  refreshAtMenu(target, next, textarea.selectionStart ?? next.length)
  void nextTick(() => syncComposerHighlight(target))
}
