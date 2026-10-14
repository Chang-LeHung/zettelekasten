<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from '../i18n'
import { filterCommands, type BlockCommand } from '../utils/blockCommands'
import { caretRect } from '../utils/caretCoordinates'
import { EditHistory, type EditSnapshot } from '../utils/editHistory'
import {
  blockKind,
  continueList,
  exitList,
  headingLevel,
  isPrefixOnly,
  isWrapped,
  joinBlocks,
  keepsLineBreaks,
  makeBlock,
  makeLink,
  reconcileBlocks,
  shiftLines,
  slideMarker,
  splitBlocks,
  toggleInline,
  turnInto,
  withoutSlideMarker,
  type Block,
  type BlockKind,
  type SplitOptions,
  type TextEdit,
  type TurnTarget,
} from '../utils/markdownBlocks'
import { toggleTask } from '../utils/markdownTasks'
import { moveItemBeforeOrAfter } from '../utils/reorder'
import EditorBlockMenu from './EditorBlockMenu.vue'
import EditorSelectionBar, { type InlineFormat } from './EditorSelectionBar.vue'
import EditorSlashMenu from './EditorSlashMenu.vue'
import MarkdownContent from './MarkdownContent.vue'

/**
 * A Notion-style editor over one Markdown string.
 *
 * Every block is shown rendered until you click it, and then it becomes plain
 * text in place, so what you type is always the real Markdown and nothing in the
 * document is ever rewritten behind your back. `/` opens the block menu, the
 * handle in the margin drags and edits a block, and selecting words floats a
 * formatting bar over them.
 */
const props = withDefaults(defineProps<{
  modelValue: string
  /** A slide deck: `--` and `---` lines are page breaks and always form their own block. */
  slides?: boolean
  /** Narrow pane: the margin controls move inside and the type is a little smaller. */
  compact?: boolean
  autofocus?: boolean
  /** Shown in the empty document. */
  placeholder?: string
}>(), { slides: false, compact: false, autofocus: false, placeholder: '' })

const emit = defineEmits<{
  'update:modelValue': [value: string]
  /** The caret tried to leave through the top or the bottom of the document. */
  edge: [direction: 'up' | 'down']
}>()

const { t } = useI18n()

const options = computed<SplitOptions>(() => ({ slides: props.slides }))
const blocks = ref<Block[]>(splitBlocks(props.modelValue, { slides: props.slides }))
const activeId = ref<number | null>(null)
const root = ref<HTMLElement | null>(null)
const textareas = new Map<number, HTMLTextAreaElement>()
let lastEmitted = props.modelValue
let composing = false

/** The document as written back: an empty block left at the end is not part of it. */
function serialize(list: readonly Block[]): string {
  let last = list.length - 1
  while (last > 0 && list[last]!.text === '') last -= 1
  if (last === list.length - 1) return joinBlocks(list)
  const kept = list.slice(0, last + 1)
  kept[last] = { ...kept[last]!, gap: list[list.length - 1]!.gap }
  return joinBlocks(kept)
}

const kinds = computed<BlockKind[]>(() => blocks.value.map((block) => blockKind(block.text, options.value)))
// Each block renders alone, so figures are numbered by how many came before.
const figureStarts = computed<number[]>(() => {
  let seen = 0
  return kinds.value.map((kind) => {
    const start = seen
    if (kind === 'image') seen += 1
    return start
  })
})

// ---------------------------------------------------------------------------
// History and write-back

function activeIndex(): number {
  return activeId.value === null ? 0 : Math.max(0, blocks.value.findIndex((block) => block.id === activeId.value))
}

function snapshot(): EditSnapshot {
  const element = activeId.value === null ? null : textareas.get(activeId.value) ?? null
  return { text: serialize(blocks.value), block: activeIndex(), caret: element?.selectionStart ?? 0 }
}

const history = new EditHistory(snapshot())

/** Publish the document. `typing` lets a run of keystrokes in one block count as one undo step. */
function commit(typing: boolean): void {
  const text = serialize(blocks.value)
  if (text !== lastEmitted) {
    lastEmitted = text
    emit('update:modelValue', text)
  }
  history.record(snapshot(), typing)
}

watch(() => props.modelValue, (value) => {
  if (value === lastEmitted) return
  // Changed somewhere else (the source column, a reload): keep the blocks that did not move.
  lastEmitted = value
  blocks.value = reconcileBlocks(blocks.value, value, options.value)
  history.reset(snapshot())
})

watch(() => props.slides, () => {
  blocks.value = reconcileBlocks(blocks.value, serialize(blocks.value), options.value)
})

function applySnapshot(target: EditSnapshot): void {
  lastEmitted = target.text
  blocks.value = reconcileBlocks(blocks.value, target.text, options.value)
  emit('update:modelValue', target.text)
  const block = blocks.value[Math.min(target.block, blocks.value.length - 1)]
  if (block) void focusBlock(block.id, target.caret)
}

function undo(): void {
  const previous = history.undo()
  if (previous) applySnapshot(previous)
}

function redo(): void {
  const next = history.redo()
  if (next) applySnapshot(next)
}

// ---------------------------------------------------------------------------
// Focus

function fit(element: HTMLTextAreaElement): void {
  element.style.height = 'auto'
  element.style.height = `${element.scrollHeight}px`
}

function setTextarea(id: number, element: unknown): void {
  if (element instanceof HTMLTextAreaElement) {
    textareas.set(id, element)
    fit(element)
  } else {
    textareas.delete(id)
  }
}

/** Make a block editable and put the caret in it; `'end'` is the default. */
async function focusBlock(id: number, caret: number | 'start' | 'end' = 'end'): Promise<HTMLTextAreaElement | null> {
  activeId.value = id
  await nextTick()
  const element = textareas.get(id)
  if (!element) return null
  element.focus({ preventScroll: false })
  const position = caret === 'start' ? 0 : caret === 'end' ? element.value.length : Math.min(caret, element.value.length)
  element.setSelectionRange(position, position)
  fit(element)
  history.moveCaret(blocks.value.findIndex((block) => block.id === id), position)
  return element
}

function blur(): void {
  activeId.value = null
  closePopups()
}

function focusStart(): void {
  const first = blocks.value[0]
  if (first) void focusBlock(first.id, 'start')
}

function focusEnd(): void {
  const last = blocks.value[blocks.value.length - 1]
  if (last) void focusBlock(last.id, 'end')
}

function activate(block: Block, event: MouseEvent): void {
  // A task's box flips on one click without opening the block, as a checklist should.
  const box = event.target instanceof Element ? event.target.closest<HTMLElement>('.task-box') : null
  if (box) {
    block.text = toggleTask(block.text, Number(box.dataset.task))
    commit(false)
    return
  }
  // Links, copy buttons, and diagram controls keep their own behaviour.
  if (event.target instanceof Element && event.target.closest('a, button, summary, input, [data-no-edit]')) return
  if (window.getSelection()?.toString()) return
  void focusBlock(block.id, 'end')
}

function onTailClick(): void {
  const last = blocks.value[blocks.value.length - 1]
  if (!last) return
  // Clicking below the document continues it, as in Notion: a new line unless the last one is already blank.
  if (last.text.trim() === '' || kinds.value[blocks.value.length - 1] === 'paragraph' && !last.text.trim()) {
    void focusBlock(last.id, 'end')
    return
  }
  const created = insertAfter(blocks.value.length - 1, '')
  commit(false)
  void focusBlock(created.id, 'start')
}

// ---------------------------------------------------------------------------
// Structure

/** Add a block after `index`. The spacing that ended the document stays at its end. */
function insertAfter(index: number, text: string): Block {
  const current = blocks.value[index]!
  const created = makeBlock(text, current.gap)
  current.gap = '\n\n'
  blocks.value.splice(index + 1, 0, created)
  return created
}

function removeAt(index: number): void {
  const [removed] = blocks.value.splice(index, 1)
  if (removed && index === blocks.value.length && blocks.value.length) blocks.value[index - 1]!.gap = removed.gap
  if (!blocks.value.length) blocks.value.push(makeBlock('', ''))
}

/** Spacing is rebuilt after a block moved, since each gap belonged to the old neighbour. */
function normalizeGaps(list: Block[], endingGap: string): Block[] {
  return list.map((block, index) => ({ ...block, gap: index === list.length - 1 ? endingGap : '\n\n' }))
}

function moveBlock(index: number, direction: -1 | 1): void {
  const target = index + direction
  if (target < 0 || target >= blocks.value.length) return
  const ending = blocks.value[blocks.value.length - 1]!.gap
  const next = [...blocks.value]
  const [moved] = next.splice(index, 1)
  next.splice(target, 0, moved!)
  blocks.value = normalizeGaps(next, ending)
  commit(false)
  if (activeId.value !== null) void focusBlock(moved!.id, textareas.get(moved!.id)?.selectionStart ?? 'end')
}

function duplicateBlock(index: number): void {
  const copy = insertAfter(index, blocks.value[index]!.text)
  commit(false)
  void focusBlock(copy.id, 'end')
}

function deleteBlock(index: number): void {
  const previous = blocks.value[index - 1]
  const following = blocks.value[index + 1]
  removeAt(index)
  commit(false)
  const next = previous ?? following ?? blocks.value[0]
  if (next) void focusBlock(next.id, previous ? 'end' : 'start')
}

function turnBlock(index: number, target: TurnTarget): void {
  const block = blocks.value[index]!
  block.text = turnInto(block.text, target)
  commit(false)
  void focusBlock(block.id, 'end')
}

// ---------------------------------------------------------------------------
// Typing

function onInput(event: Event, block: Block): void {
  const element = event.target as HTMLTextAreaElement
  block.text = element.value
  fit(element)
  if (composing) return
  if (splitAfterInput(block, element)) return
  updateSlash(block, element)
  commit(true)
}

function onCompositionEnd(event: Event, block: Block): void {
  composing = false
  onInput(event, block)
}

/**
 * A blank line inside a block makes it two blocks: this is how pasting several
 * paragraphs, or pressing Shift+Enter twice, ends up as separate blocks.
 */
function splitAfterInput(block: Block, element: HTMLTextAreaElement): boolean {
  const parts = splitBlocks(block.text, options.value)
  if (parts.length <= 1) return false
  const index = blocks.value.findIndex((candidate) => candidate.id === block.id)
  const caret = element.selectionStart
  let offset = 0
  let target = parts.length - 1
  let local = parts[target]!.text.length
  for (let position = 0; position < parts.length; position += 1) {
    const end = offset + parts[position]!.text.length
    if (caret <= end) {
      target = position
      local = caret - offset
      break
    }
    offset = end + parts[position]!.gap.length
    if (caret < offset && position + 1 < parts.length) {
      target = position + 1
      local = 0
      break
    }
  }
  parts[0]!.id = block.id
  parts[parts.length - 1]!.gap = block.gap
  blocks.value.splice(index, 1, ...parts)
  commit(false)
  void focusBlock(parts[target]!.id, local)
  return true
}

function currentEdit(element: HTMLTextAreaElement): { start: number; end: number } {
  return { start: element.selectionStart, end: element.selectionEnd }
}

/** Write an edit made on the textarea's text back into the block and restore the selection. */
async function applyEdit(block: Block, element: HTMLTextAreaElement, edit: TextEdit, typing = false): Promise<void> {
  block.text = edit.text
  await nextTick()
  element.setSelectionRange(edit.start, edit.end)
  fit(element)
  commit(typing)
  refreshSelectionBar(block, element)
}

// ---------------------------------------------------------------------------
// Keyboard

const FORMATS: Record<Exclude<InlineFormat, 'link'>, { marker: string; closing?: string }> = {
  bold: { marker: '**' },
  italic: { marker: '*' },
  strike: { marker: '~~' },
  code: { marker: '`' },
  math: { marker: '$' },
}

function format(kind: InlineFormat, block: Block, element: HTMLTextAreaElement): void {
  const { start, end } = currentEdit(element)
  const edit = kind === 'link'
    ? makeLink(block.text, start, end)
    : toggleInline(block.text, start, end, FORMATS[kind].marker, FORMATS[kind].closing)
  void applyEdit(block, element, edit)
}

function activeFormats(block: Block, element: HTMLTextAreaElement): InlineFormat[] {
  const { start, end } = currentEdit(element)
  return (Object.keys(FORMATS) as Array<keyof typeof FORMATS>).filter((name) =>
    isWrapped(block.text, start, end, FORMATS[name].marker, FORMATS[name].closing))
}

function onKeydown(event: KeyboardEvent, block: Block, index: number): void {
  const element = event.target as HTMLTextAreaElement
  // An IME candidate window owns Enter, arrows, and Escape until the text is committed.
  if (event.isComposing || event.keyCode === 229) return

  if (slash.value && handleSlashKey(event)) return

  const mod = event.metaKey || event.ctrlKey
  const key = event.key
  const kind = kinds.value[index]!

  if (mod && !event.altKey) {
    const lower = key.toLowerCase()
    if (lower === 'z') {
      event.preventDefault()
      if (event.shiftKey) redo()
      else undo()
      return
    }
    if (lower === 'y') {
      event.preventDefault()
      redo()
      return
    }
    const inline: Record<string, InlineFormat | undefined> = { b: 'bold', i: 'italic', e: 'code', k: 'link' }
    const requested = event.shiftKey ? (lower === 'x' ? 'strike' : undefined) : inline[lower]
    if (requested) {
      event.preventDefault()
      format(requested, block, element)
      return
    }
    if (event.shiftKey && (key === 'ArrowUp' || key === 'ArrowDown')) {
      event.preventDefault()
      moveBlock(index, key === 'ArrowUp' ? -1 : 1)
      return
    }
  }

  if (key === 'Escape') {
    event.stopPropagation()
    if (selectionBar.value) {
      selectionBar.value = null
      return
    }
    blur()
    element.blur()
    return
  }

  if (key === 'Enter' && !event.shiftKey && !mod && !event.altKey) {
    onEnter(event, block, index, element, kind)
    return
  }

  if (key === 'Backspace' || key === 'Delete') {
    onDelete(event, block, index, element, kind)
    return
  }

  if (key === 'Tab') {
    onTab(event, block, element, kind)
    return
  }

  if ((key === 'ArrowUp' || key === 'ArrowDown') && !event.shiftKey && !mod && !event.altKey) {
    onArrow(event, index, element)
  }
}

function onEnter(event: KeyboardEvent, block: Block, index: number, element: HTMLTextAreaElement, kind: BlockKind): void {
  if (keepsLineBreaks(kind, block.text)) return
  const { start, end } = currentEdit(element)

  if (kind === 'list' || kind === 'todo' || kind === 'quote') {
    const next = continueList(block.text, start)
    if (next?.action === 'continue') {
      event.preventDefault()
      element.setRangeText(next.insert, start, end, 'end')
      block.text = element.value
      fit(element)
      commit(false)
      return
    }
    // An empty last item leaves the list; in the middle of one it is just a new line.
    if (next?.action === 'exit' && block.text.indexOf('\n', start) === -1) {
      event.preventDefault()
      const left = exitList(block.text, start)
      block.text = left.text
      if (left.text === '') {
        commit(false)
        void focusBlock(block.id, 'start')
        return
      }
      const created = insertAfter(index, '')
      commit(false)
      void focusBlock(created.id, 'start')
      return
    }
    return
  }

  // Anywhere else Enter splits the block at the caret.
  event.preventDefault()
  const before = block.text.slice(0, start)
  const after = block.text.slice(end)
  block.text = before
  const created = insertAfter(index, after)
  commit(false)
  void focusBlock(created.id, 'start')
}

const SEPARATOR_KINDS: readonly BlockKind[] = ['divider', 'slideBreak', 'sectionBreak']

function onDelete(event: KeyboardEvent, block: Block, index: number, element: HTMLTextAreaElement, kind: BlockKind): void {
  const { start, end } = currentEdit(element)
  if (start !== end) return
  // A page break or rule has no text worth editing: Backspace removes the whole block.
  if (SEPARATOR_KINDS.includes(kind) && event.key === 'Backspace' && start === block.text.length) {
    event.preventDefault()
    if (blocks.value.length > 1) deleteBlock(index)
    return
  }
  if (event.key === 'Delete') return
  if (start !== 0) {
    // Backspace over a bare prefix ("- ", "## ") clears it, turning the block back into text.
    if (start === block.text.length && isPrefixOnly(block.text)) {
      event.preventDefault()
      void applyEdit(block, element, { text: '', start: 0, end: 0 })
    }
    return
  }
  if (index === 0) return
  event.preventDefault()
  const previous = blocks.value[index - 1]!
  const previousKind = kinds.value[index - 1]!
  if (block.text === '') {
    deleteBlock(index)
    return
  }
  // Two plain paragraphs join, as in any word processor; anything else only moves the caret up.
  if (kind === 'paragraph' && previousKind === 'paragraph') {
    const join = previous.text.length
    previous.text += block.text
    removeAt(index)
    commit(false)
    void focusBlock(previous.id, join)
    return
  }
  void focusBlock(previous.id, 'end')
}

function onTab(event: KeyboardEvent, block: Block, element: HTMLTextAreaElement, kind: BlockKind): void {
  const { start, end } = currentEdit(element)
  if (kind === 'list' || kind === 'todo') {
    event.preventDefault()
    const shifted = shiftLines(block.text, start, end, event.shiftKey ? -1 : 1)
    void applyEdit(block, element, shifted)
    return
  }
  if (kind === 'code' || kind === 'diagram' || kind === 'html' || kind === 'math') {
    if (event.shiftKey) return
    event.preventDefault()
    element.setRangeText('  ', start, end, 'end')
    block.text = element.value
    commit(true)
  }
}

/** Whether the caret is on the first or last visual line, wrapped lines included. */
function onVerticalEdge(element: HTMLTextAreaElement, direction: 'up' | 'down'): boolean {
  const caret = element.selectionStart
  if (element.selectionStart !== element.selectionEnd) return false
  const reference = caretRect(element, direction === 'up' ? 0 : element.value.length)
  const here = caretRect(element, caret)
  return Math.abs(here.top - reference.top) < here.height / 2
}

function onArrow(event: KeyboardEvent, index: number, element: HTMLTextAreaElement): void {
  const direction = event.key === 'ArrowUp' ? 'up' : 'down'
  if (!onVerticalEdge(element, direction)) return
  const target = blocks.value[index + (direction === 'up' ? -1 : 1)]
  event.preventDefault()
  if (!target) {
    emit('edge', direction)
    return
  }
  void focusBlock(target.id, direction === 'up' ? 'end' : 'start')
}

// ---------------------------------------------------------------------------
// Slash menu

const slash = ref<{ blockId: number; from: number; query: string; anchor: { top: number } | { bottom: number }; left: number } | null>(null)
const slashIndex = ref(0)

const slashItems = computed<BlockCommand[]>(() => (
  slash.value ? filterCommands(slash.value.query, props.slides, (command) => t(`editor.cmd.${command.id}`)) : []
))

const SLASH_PATTERN = /(^|[\s])\/([^\s/]{0,30})$/u
const NO_SLASH_KINDS: readonly BlockKind[] = ['code', 'diagram', 'math', 'html', 'table']

function updateSlash(block: Block, element: HTMLTextAreaElement): void {
  const caret = element.selectionStart
  const index = blocks.value.findIndex((candidate) => candidate.id === block.id)
  if (element.selectionEnd !== caret || NO_SLASH_KINDS.includes(kinds.value[index]!) || keepsLineBreaks('paragraph', block.text)) {
    slash.value = null
    return
  }
  const match = SLASH_PATTERN.exec(block.text.slice(0, caret))
  if (!match) {
    slash.value = null
    return
  }
  const query = match[2]!
  const from = caret - query.length - 1
  if (filterCommands(query, props.slides, (command) => t(`editor.cmd.${command.id}`)).length === 0) {
    slash.value = null
    return
  }
  const rect = caretRect(element, from)
  const below = window.innerHeight - (rect.top + rect.height)
  // Below the caret when there is room; otherwise the menu grows upward from the caret's top edge.
  const anchor = below > 340 ? { top: rect.top + rect.height + 6 } : { bottom: window.innerHeight - rect.top + 6 }
  if (slash.value?.query !== query || slash.value.blockId !== block.id) slashIndex.value = 0
  slash.value = { blockId: block.id, from, query, anchor, left: Math.min(rect.left, window.innerWidth - 320) }
}

function handleSlashKey(event: KeyboardEvent): boolean {
  const items = slashItems.value
  if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
    event.preventDefault()
    const step = event.key === 'ArrowDown' ? 1 : -1
    slashIndex.value = (slashIndex.value + step + items.length) % Math.max(1, items.length)
    return true
  }
  if (event.key === 'Enter' || event.key === 'Tab') {
    const chosen = items[slashIndex.value]
    if (!chosen) return false
    event.preventDefault()
    runCommand(chosen)
    return true
  }
  if (event.key === 'Escape') {
    event.preventDefault()
    event.stopPropagation()
    slash.value = null
    return true
  }
  return false
}

const STRUCTURAL: readonly BlockKind[] = ['divider', 'slideBreak', 'sectionBreak']

function runCommand(command: BlockCommand): void {
  const menu = slash.value
  if (!menu) return
  slash.value = null
  const index = blocks.value.findIndex((block) => block.id === menu.blockId)
  const block = blocks.value[index]
  if (!block) return
  const element = textareas.get(block.id)
  const caret = element?.selectionStart ?? block.text.length
  const rest = block.text.slice(0, menu.from) + block.text.slice(caret)
  const hasWords = rest.trim() !== ''

  if (hasWords && command.turn) {
    block.text = turnInto(rest.trimEnd(), command.turn)
    commit(false)
    void focusBlock(block.id, 'end')
    return
  }

  let target = block
  if (hasWords) {
    block.text = rest.trimEnd()
    target = insertAfter(index, command.template)
  } else {
    block.text = command.template
  }
  const placed = blockKind(command.template, options.value)
  if (STRUCTURAL.includes(placed)) {
    // A rule or page break has nothing to type in, so the caret moves on to a fresh line below it.
    const targetIndex = blocks.value.findIndex((candidate) => candidate.id === target.id)
    const following = blocks.value[targetIndex + 1]
    const next = following && following.text === '' ? following : insertAfter(targetIndex, '')
    commit(false)
    void focusBlock(next.id, 'start')
    return
  }
  commit(false)
  void focusBlock(target.id, command.caret ?? command.template.length)
}

function addBelow(index: number): void {
  const block = blocks.value[index]!
  if (block.text === '') {
    void openSlashIn(block)
    return
  }
  const created = insertAfter(index, '/')
  commit(false)
  void openSlashIn(created)
}

async function openSlashIn(block: Block): Promise<void> {
  if (block.text === '') block.text = '/'
  const element = await focusBlock(block.id, 'end')
  if (element) updateSlash(block, element)
}

// ---------------------------------------------------------------------------
// Selection bar

const selectionBar = ref<{ blockId: number; top: number; left: number; active: InlineFormat[] } | null>(null)

function refreshSelectionBar(block: Block, element: HTMLTextAreaElement): void {
  const { start, end } = currentEdit(element)
  const index = blocks.value.findIndex((candidate) => candidate.id === block.id)
  const selected = element.value.slice(start, end)
  if (start === end || !selected.trim() || selected.includes('\n') && NO_SLASH_KINDS.includes(kinds.value[index]!)) {
    selectionBar.value = null
    return
  }
  const rect = caretRect(element, start)
  const wanted = rect.top - 46
  selectionBar.value = {
    blockId: block.id,
    top: wanted < 8 ? rect.top + rect.height + 8 : wanted,
    left: Math.min(Math.max(8, rect.left - 10), window.innerWidth - 260),
    active: activeFormats(block, element),
  }
}

function onSelectionChange(event: Event, block: Block): void {
  refreshSelectionBar(block, event.target as HTMLTextAreaElement)
}

function onBarFormat(kind: InlineFormat): void {
  const bar = selectionBar.value
  if (!bar) return
  const block = blocks.value.find((candidate) => candidate.id === bar.blockId)
  const element = textareas.get(bar.blockId)
  if (block && element) format(kind, block, element)
}

// ---------------------------------------------------------------------------
// Block menu and dragging

const menu = ref<{ blockId: number; top: number; left: number } | null>(null)
const dragging = ref<number | null>(null)
const dropTarget = ref<{ id: number; after: boolean } | null>(null)

function openMenu(block: Block, event: MouseEvent): void {
  const rect = (event.currentTarget as HTMLElement).getBoundingClientRect()
  const left = Math.min(rect.right + 6, window.innerWidth - 224)
  const top = Math.min(rect.top, window.innerHeight - 330)
  menu.value = { blockId: block.id, top: Math.max(8, top), left }
}

const menuIndex = computed(() => (menu.value ? blocks.value.findIndex((block) => block.id === menu.value!.blockId) : -1))
const menuCanTurn = computed(() => {
  const kind = kinds.value[menuIndex.value]
  return kind !== undefined && !['html', 'slideMarker', 'divider', 'slideBreak', 'sectionBreak', 'diagram', 'math', 'table', 'image', 'empty'].includes(kind)
})

function closePopups(): void {
  slash.value = null
  selectionBar.value = null
  menu.value = null
}

function onDragStart(event: DragEvent, block: Block): void {
  dragging.value = block.id
  menu.value = null
  if (event.dataTransfer) {
    event.dataTransfer.effectAllowed = 'move'
    event.dataTransfer.setData('text/plain', `zett-block:${block.id}`)
    const row = (event.currentTarget as HTMLElement).closest('.block-row')
    if (row) event.dataTransfer.setDragImage(row, 0, 12)
  }
}

function onDragOver(event: DragEvent, block: Block): void {
  if (dragging.value === null) return
  event.preventDefault()
  if (event.dataTransfer) event.dataTransfer.dropEffect = 'move'
  const row = event.currentTarget as HTMLElement
  const rect = row.getBoundingClientRect()
  dropTarget.value = { id: block.id, after: event.clientY > rect.top + rect.height / 2 }
}

function onDrop(event: DragEvent): void {
  if (dragging.value === null || !dropTarget.value) return
  event.preventDefault()
  const ending = blocks.value[blocks.value.length - 1]!.gap
  const moved = moveItemBeforeOrAfter(blocks.value, dragging.value, dropTarget.value.id, dropTarget.value.after, (block) => block.id)
  blocks.value = normalizeGaps(moved, ending)
  commit(false)
  endDrag()
}

function endDrag(): void {
  dragging.value = null
  dropTarget.value = null
}

// ---------------------------------------------------------------------------
// Lifecycle

function onPointerDownOutside(event: PointerEvent): void {
  const target = event.target
  if (!(target instanceof Node)) return
  if (root.value?.contains(target)) return
  if (target instanceof Element && target.closest('.block-popup')) return
  blur()
}

// The page scrolling (or a long selection scrolling the text field to show itself) moves the
// words the floating pieces point at, so they follow instead of closing.
let repositionFrame = 0
function onViewportChange(): void {
  if (repositionFrame) return
  repositionFrame = window.requestAnimationFrame(() => {
    repositionFrame = 0
    const id = activeId.value
    const block = id === null ? null : blocks.value.find((candidate) => candidate.id === id)
    const element = id === null ? null : textareas.get(id)
    if (!block || !element) {
      closePopups()
      return
    }
    if (selectionBar.value) refreshSelectionBar(block, element)
    if (slash.value) updateSlash(block, element)
  })
}

function onResize(): void {
  for (const element of textareas.values()) fit(element)
  onViewportChange()
}

onMounted(() => {
  document.addEventListener('pointerdown', onPointerDownOutside, true)
  window.addEventListener('resize', onResize)
  window.addEventListener('scroll', onViewportChange, true)
  if (props.autofocus) focusStart()
})

onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', onPointerDownOutside, true)
  window.removeEventListener('resize', onResize)
  window.removeEventListener('scroll', onViewportChange, true)
  if (repositionFrame) window.cancelAnimationFrame(repositionFrame)
})

function viewText(block: Block, kind: BlockKind): string {
  return kind === 'slideMarker' ? withoutSlideMarker(block.text) : block.text
}

function textareaClass(kind: BlockKind, text: string): string[] {
  const classes = [`ta-${kind}`]
  const level = headingLevel(text)
  if (level) classes.push(`ta-h${Math.min(level, 3)}`)
  return classes
}

const wordCount = computed(() => {
  const text = serialize(blocks.value)
  const cjk = (text.match(/[\u3400-\u9fff]/gu) ?? []).length
  const latin = text.replace(/[\u3400-\u9fff]/gu, ' ').split(/\s+/u).filter(Boolean).length
  return cjk + latin
})

/** Re-measure every open text field, for when the editor was hidden and shown again. */
function refit(): void {
  for (const element of textareas.values()) fit(element)
}

defineExpose({ focusStart, focusEnd, undo, redo, wordCount, refit, blur })
</script>

<template>
  <div ref="root" class="block-editor" :class="{ compact, slides }" data-testid="block-editor">
    <div
      v-for="(block, index) in blocks"
      :key="block.id"
      class="block-row"
      :class="[
        `kind-${kinds[index]}`,
        {
          active: activeId === block.id,
          dragging: dragging === block.id,
          'drop-before': dropTarget?.id === block.id && !dropTarget.after,
          'drop-after': dropTarget?.id === block.id && dropTarget.after,
        },
      ]"
      :data-block-id="block.id"
      @dragover="onDragOver($event, block)"
      @drop="onDrop"
    >
      <div class="block-gutter">
        <button class="gutter-button" type="button" tabindex="-1" :aria-label="t('editor.add')" :title="t('editor.add')" @mousedown.prevent @click="addBelow(index)">
          <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M8 3.5v9M3.5 8h9" /></svg>
        </button>
        <button
          class="gutter-button handle"
          type="button"
          tabindex="-1"
          draggable="true"
          :aria-label="t('editor.handle')"
          :title="t('editor.handle')"
          @click="openMenu(block, $event)"
          @dragstart="onDragStart($event, block)"
          @dragend="endDrag"
        >
          <svg viewBox="0 0 16 16" aria-hidden="true"><circle cx="6" cy="4" r="1.1" /><circle cx="10" cy="4" r="1.1" /><circle cx="6" cy="8" r="1.1" /><circle cx="10" cy="8" r="1.1" /><circle cx="6" cy="12" r="1.1" /><circle cx="10" cy="12" r="1.1" /></svg>
        </button>
      </div>

      <div class="block-body">
        <textarea
          v-if="activeId === block.id"
          :ref="(element) => setTextarea(block.id, element)"
          class="block-input"
          :class="textareaClass(kinds[index]!, block.text)"
          :value="block.text"
          :placeholder="blocks.length === 1 && !block.text ? (placeholder || t('editor.placeholder')) : t('editor.placeholder.block')"
          :aria-label="t('editor.placeholder.block')"
          rows="1"
          spellcheck="false"
          autocomplete="off"
          autocorrect="off"
          @input="onInput($event, block)"
          @keydown="onKeydown($event, block, index)"
          @compositionstart="composing = true"
          @compositionend="onCompositionEnd($event, block)"
          @select="onSelectionChange($event, block)"
          @mouseup="onSelectionChange($event, block)"
          @keyup="onSelectionChange($event, block)"
        />
        <div
          v-else
          class="block-view"
          :tabindex="index === 0 ? 0 : -1"
          @click="activate(block, $event)"
          @keydown.enter.self.prevent="focusBlock(block.id, 'end')"
        >
          <p v-if="kinds[index] === 'empty'" class="block-empty">{{ blocks.length === 1 ? (placeholder || t('editor.placeholder')) : '' }}</p>
          <hr v-else-if="kinds[index] === 'divider'" class="block-rule" />
          <div v-else-if="kinds[index] === 'slideBreak' || kinds[index] === 'sectionBreak'" class="slide-break" :class="kinds[index]" role="separator">
            <span>{{ t(kinds[index] === 'slideBreak' ? 'editor.slide.break' : 'editor.slide.section') }}</span>
          </div>
          <template v-else>
            <span v-if="kinds[index] === 'slideMarker'" class="slide-chip">{{ t(slideMarker(block.text) === 'cover' ? 'editor.slide.cover' : 'editor.slide.html') }}</span>
            <MarkdownContent
              :content="viewText(block, kinds[index]!)"
              :figure-start="figureStarts[index]"
              :allow-html="kinds[index] === 'html' || slideMarker(block.text) === 'html'"
            />
          </template>
        </div>
      </div>
    </div>
    <div class="editor-tail" aria-hidden="true" @click="onTailClick" />

    <EditorSlashMenu
      v-if="slash && slashItems.length"
      :items="slashItems"
      :active="slashIndex"
      :anchor="slash.anchor"
      :left="slash.left"
      @hover="slashIndex = $event"
      @pick="runCommand"
    />
    <EditorSelectionBar
      v-if="selectionBar"
      :top="selectionBar.top"
      :left="selectionBar.left"
      :active="selectionBar.active"
      @format="onBarFormat"
    />
    <EditorBlockMenu
      v-if="menu"
      :top="menu.top"
      :left="menu.left"
      :can-turn="menuCanTurn"
      :can-move-up="menuIndex > 0"
      :can-move-down="menuIndex < blocks.length - 1"
      :can-delete="blocks.length > 1 || blocks[0]?.text !== ''"
      @turn="turnBlock(menuIndex, $event); menu = null"
      @duplicate="duplicateBlock(menuIndex); menu = null"
      @remove="deleteBlock(menuIndex); menu = null"
      @move="moveBlock(menuIndex, $event); menu = null"
      @close="menu = null"
    />
  </div>
</template>

<style scoped>
.block-editor { --gutter: 3.4rem; position: relative; min-width: 0; color: #2b312d; font-size: 1rem; line-height: 1.7; }
.block-editor.compact { --gutter: 1.9rem; font-size: .88rem; line-height: 1.65; }

.block-row { position: relative; display: grid; grid-template-columns: minmax(0, 1fr); padding: .12rem 0; border-radius: .35rem; }
.block-row.kind-heading { padding-top: .9rem; }
.block-row.kind-heading:first-child { padding-top: .2rem; }
.block-row.dragging { opacity: .4; }
.block-row.drop-before::before, .block-row.drop-after::after { content: ""; position: absolute; left: 0; right: 0; height: 3px; border-radius: 3px; background: #4f8a68; box-shadow: 0 0 0 3px rgba(79,138,104,.16); }
.block-row.drop-before::before { top: -2px; }
.block-row.drop-after::after { bottom: -2px; }

/* The controls hang in the margin, left of the text, like Notion's. */
.block-gutter { position: absolute; top: .22rem; right: 100%; display: flex; align-items: center; gap: .05rem; margin-right: .3rem; opacity: 0; transition: opacity 120ms ease; }
.compact .block-gutter { right: auto; left: calc(var(--gutter) * -1); margin-right: 0; }
.block-row:hover .block-gutter, .block-row.active .block-gutter, .block-row:focus-within .block-gutter { opacity: 1; }
.block-row.kind-heading .block-gutter { top: 1.05rem; }
.block-row.kind-heading:first-child .block-gutter { top: .3rem; }
.gutter-button { display: grid; place-items: center; width: 1.4rem; height: 1.5rem; padding: 0; border: 0; border-radius: .3rem; color: #a2a8a4; background: transparent; cursor: pointer; }
.gutter-button:hover { color: #4a524d; background: #eef0ee; }
.gutter-button.handle { cursor: grab; }
.gutter-button.handle:active { cursor: grabbing; }
.compact .gutter-button { width: 1.15rem; }
.gutter-button svg { width: .95rem; height: .95rem; fill: currentColor; stroke: currentColor; stroke-width: 1.5; stroke-linecap: round; }
.gutter-button svg path { fill: none; }
@media (hover: none), (max-width: 720px) { .block-gutter { display: none; } }

.block-body { min-width: 0; }
.block-view { min-height: 1.7em; border-radius: .3rem; cursor: text; outline: 0; }
.block-view:focus-visible { box-shadow: 0 0 0 2px rgba(79,138,104,.35); }
.block-empty { min-height: 1.7em; margin: 0; color: #b0b5b1; }
.block-rule { margin: .7rem 0; border: 0; border-top: 1px solid #dfe3e0; }

/* Page breaks of a slide deck, drawn as the breaks they are. */
.slide-break { position: relative; display: flex; align-items: center; justify-content: center; height: 1.9rem; }
.slide-break::before { content: ""; position: absolute; left: 0; right: 0; top: 50%; border-top: 1px dashed #b8c3bb; }
.slide-break.sectionBreak::before { border-top: 2px solid #8fa89a; }
.slide-break span { position: relative; padding: .1rem .6rem; border-radius: 1rem; color: #6f7d74; background: #fbfcfb; font-size: .66rem; font-weight: 650; letter-spacing: .03em; }
.slide-break.sectionBreak span { color: #fff; background: #6a8a77; }
.slide-chip { display: inline-block; margin-bottom: .35rem; padding: .08rem .5rem; border-radius: 1rem; color: #7a5d2a; background: #f6ecd6; font-size: .64rem; font-weight: 650; }

/* The block being edited is plain text, tinted so it reads as "source" without a label. */
.block-input { display: block; width: 100%; min-height: 1.7em; margin: 0; padding: 0 .35rem; resize: none; overflow: hidden; border: 0; border-radius: .3rem; outline: 0; color: inherit; background: rgba(79,138,104,.055); font: inherit; line-height: inherit; letter-spacing: inherit; tab-size: 2; white-space: pre-wrap; overflow-wrap: anywhere; caret-color: #3d7a57; }
.block-input::placeholder { color: #b0b5b1; }
.block-input.ta-h1 { font-size: 1.875em; font-weight: 700; line-height: 1.25; letter-spacing: -.025em; }
.block-input.ta-h2 { font-size: 1.5em; font-weight: 680; line-height: 1.3; letter-spacing: -.02em; }
.block-input.ta-h3 { font-size: 1.25em; font-weight: 650; line-height: 1.35; letter-spacing: -.012em; }
.block-input.ta-code, .block-input.ta-diagram, .block-input.ta-math, .block-input.ta-html, .block-input.ta-table, .block-input.ta-slideMarker { font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace; font-size: .86em; line-height: 1.65; white-space: pre; overflow-x: auto; }
.block-input.ta-quote { color: #5a635d; }

.editor-tail { min-height: 7rem; cursor: text; }

/* Rendered blocks: Notion's type scale and rhythm over the shared Markdown styles. */
.block-view :deep(.markdown-body) { line-height: inherit; }
.block-view :deep(.markdown-body h1) { margin: 0; font-size: 1.875em; font-weight: 700; line-height: 1.25; letter-spacing: -.025em; }
.block-view :deep(.markdown-body h2) { margin: 0; font-size: 1.5em; font-weight: 680; line-height: 1.3; letter-spacing: -.02em; }
.block-view :deep(.markdown-body h3) { margin: 0; font-size: 1.25em; font-weight: 650; line-height: 1.35; letter-spacing: -.012em; }
.block-view :deep(.markdown-body h4) { margin: 0; font-size: 1.05em; }
.block-view :deep(.markdown-body p), .block-view :deep(.markdown-body ul), .block-view :deep(.markdown-body ol), .block-view :deep(.markdown-body blockquote) { margin: 0; }
.block-view :deep(.markdown-body ul), .block-view :deep(.markdown-body ol) { padding-left: 1.5em; }
.block-view :deep(.markdown-body blockquote) { padding: .1em 0 .1em 1em; border-left: 3px solid #2b312d; color: inherit; background: transparent; }
.block-view :deep(.markdown-body a) { color: inherit; text-decoration: underline; text-decoration-color: rgba(43,49,45,.35); text-underline-offset: 2px; }
.block-view :deep(.markdown-body a:hover) { text-decoration-color: currentColor; }
.block-view :deep(.markdown-body :not(pre) > code) { color: #b04a39; background: rgba(135,131,120,.15); }
.block-view :deep(.markdown-body .markdown-figure) { margin: .4em 0; }
.block-view :deep(.markdown-body table) { margin: .3em 0; }
.block-view :deep(.task-box) { cursor: pointer; }
.block-view :deep(.task-box:hover) { border-color: #3d7a57; }
</style>
