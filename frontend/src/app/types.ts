import type { AgentSteeringMessage, AgentTimelineEntry, LibraryItem, MessagePart, SessionType, ShellApprovalMode, StaticAsset } from '../api/types'
import type { AtCommandMatch } from '../utils/atCommand'
import type { SlashCommandMatch } from '../utils/slashCommand'

export type View = 'library' | 'search' | 'new' | 'assets' | 'scheduledTasks' | 'channels' | 'settings'
export type SessionScope = Extract<SessionType, 'normal' | 'scheduled' | 'channel'>
export type NoticeKind = 'success' | 'error'
export type AssetEditorMode = 'closed' | 'text' | 'link'
export type AssetFilter = 'all' | 'documents' | 'images' | 'links' | 'notes' | 'code'
export type SettingsSection = 'general' | 'usage' | 'providers' | 'limits'
export type ComposerTarget = 'initial' | 'follow-up'
export type AgentMessageTimelineEntry = Extract<AgentTimelineEntry, { type: 'message' }>
export interface ConfirmationState {
  open: boolean
  title: string
  message: string
  confirmLabel: string
}
export interface AskUserState {
  toolCallId: string
  question: string
  options: string[]
  allowMultiple: boolean
  responseEvent: string
}
export interface ShellApprovalState {
  toolCallId: string
  command: string
  timeoutSeconds: number
  responseEvent: string
  rememberSupported: boolean
}
export interface QueuedFollowUp {
  id: number
  content: string
  parts: MessagePart[]
  shellApprovalMode: ShellApprovalMode
  slashCommandId: string | null
  atCommandId: string | null
}
export interface PendingSteeringEcho {
  message: AgentSteeringMessage
  applied: boolean
}
export interface ActiveSlashMenu {
  target: ComposerTarget
  match: SlashCommandMatch
  activeIndex: number
}
export interface ActiveAtMenu {
  target: ComposerTarget
  match: AtCommandMatch
  activeIndex: number
}
export interface ComposerHighlightSegment {
  text: string
  kind: 'slash' | 'reference' | null
}
/** What a drag carries: a library artifact, or a static asset from the asset view. */
export type DraggedResource =
  | { kind: 'artifact'; item: LibraryItem }
  | { kind: 'asset'; asset: StaticAsset }
