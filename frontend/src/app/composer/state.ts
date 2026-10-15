import { computed, ref } from 'vue'
import type { AgentAtCommand, AgentSlashCommand, MessagePart } from '../../api/types'
import type { PositionedMessageImage } from '../../utils/messageParts'
import { query } from '../library/state'
import type { ActiveAtMenu, ActiveSlashMenu } from '../types'

export const raw = ref('')
export const followUp = ref('')
export const slashCommands = ref<AgentSlashCommand[]>([])
export const slashCommandsLoaded = ref(false)
export const slashCommandsLoading = ref(false)
export const slashMenu = ref<ActiveSlashMenu | null>(null)
export const selectedSlashCommand = ref<AgentSlashCommand | null>(null)
export const atCommands = ref<AgentAtCommand[]>([])
export const atCommandsLoaded = ref(false)
export const atCommandsLoading = ref(false)
export const atMenu = ref<ActiveAtMenu | null>(null)
export const initialComposerInput = ref<HTMLTextAreaElement | null>(null)
export const followUpComposerInput = ref<HTMLTextAreaElement | null>(null)
export const initialComposerHighlight = ref<HTMLElement | null>(null)
export const followUpComposerHighlight = ref<HTMLElement | null>(null)
export const composerComposing = ref(false)
export const initialMessageParts = ref<MessagePart[]>([])
export const pendingMessageImages = ref<PositionedMessageImage[]>([])
export const slashMenuCommands = computed(() => {
  const query = slashMenu.value?.match.query.trim().toLowerCase()
  if (!query) return slashCommands.value
  return slashCommands.value.filter((command) => (
    command.name.toLowerCase().includes(query)
    || command.description.toLowerCase().includes(query)
    || command.type.toLowerCase().includes(query)
  ))
})
export const slashMenuActiveIndex = computed(() => {
  const menu = slashMenu.value
  if (!menu || !slashMenuCommands.value.length) return 0
  return Math.min(menu.activeIndex, slashMenuCommands.value.length - 1)
})
export const slashMenuItems = computed(() => slashMenuCommands.value.map((command) => ({
  id: command.id,
  name: command.name,
  description: command.description,
  badge: command.type,
})))
export const atMenuCommands = computed(() => {
  const query = atMenu.value?.match.query.trim().toLowerCase()
  if (!query) return atCommands.value
  return atCommands.value.filter((command) => (
    command.name.toLowerCase().includes(query)
    || command.label.toLowerCase().includes(query)
    || command.kind.toLowerCase().includes(query)
  ))
})
export const atMenuActiveIndex = computed(() => {
  const menu = atMenu.value
  if (!menu || !atMenuCommands.value.length) return 0
  return Math.min(menu.activeIndex, atMenuCommands.value.length - 1)
})
export const atMenuItems = computed(() => atMenuCommands.value.map((command) => ({
  id: command.id,
  name: command.name,
  description: `${command.label} · ${command.description}`,
  badge: command.kind,
})))
