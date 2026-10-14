import type { CardStatus, CardType } from '../api/types'

/**
 * The statuses each card type carries, in menu order; the first is where a new
 * card starts. Mirrors `CARD_STATUSES` in the backend's `schemas/cards.py`, and
 * a card type that is absent here (note, quote) has no status at all.
 */
export const CARD_STATUSES: Readonly<Partial<Record<CardType, readonly CardStatus[]>>> = {
  todo: ['open', 'in_progress', 'on_hold', 'done', 'cancelled'],
  idea: ['captured', 'exploring', 'adopted', 'dropped'],
  reference: ['unread', 'reading', 'read'],
}

/** Card types that carry a status, in the order the library lists their groups. */
export const STATUS_CARD_TYPES = Object.keys(CARD_STATUSES) as CardType[]

/** The card type a status belongs to; values never overlap between types. */
export function cardStatusType(status: CardStatus): CardType {
  const owner = STATUS_CARD_TYPES.find((type) => CARD_STATUSES[type]!.includes(status))
  if (!owner) throw new Error(`Unknown card status: ${status}`)
  return owner
}

/** Every status of the card type that owns `status`, which is what its menu lists. */
export function statusOptions(status: CardStatus): readonly CardStatus[] {
  return CARD_STATUSES[cardStatusType(status)]!
}

/** i18n key of one status label. */
export function cardStatusLabel(status: CardStatus): string {
  return `cardStatus.${status}`
}

/** CSS class carrying the per-status look; one class name per status. */
export function statusTone(status: CardStatus): string {
  return `status-${status.replace('_', '-')}`
}

/** Statuses that end a card's story without success; their titles are struck through. */
export function isStruck(status: CardStatus): boolean {
  return status === 'done' || status === 'cancelled' || status === 'dropped'
}

/** The drawing inside a status mark. */
export type StatusGlyph = 'ring' | 'half' | 'pause' | 'check' | 'cross' | 'dot' | 'spark'

export function statusGlyph(status: CardStatus): StatusGlyph {
  switch (status) {
    case 'in_progress':
    case 'reading':
      return 'half'
    case 'on_hold':
      return 'pause'
    case 'done':
    case 'adopted':
    case 'read':
      return 'check'
    case 'cancelled':
    case 'dropped':
      return 'cross'
    case 'captured':
      return 'dot'
    case 'exploring':
      return 'spark'
    default:
      return 'ring'
  }
}

/** Whether a status is drawn with a moving ring: work in motion. */
export function isActive(status: CardStatus): boolean {
  return status === 'in_progress' || status === 'exploring' || status === 'reading'
}

/**
 * Where one click on a card's mark sends it, or `null` when a click should not
 * decide anything. A task is finished or reopened, and a reference is read or
 * marked unread again. Adopting an idea is a decision, so its mark is not a
 * button: that one goes through the status menu.
 */
export function quickTarget(status: CardStatus): CardStatus | null {
  switch (cardStatusType(status)) {
    case 'todo':
      return status === 'done' || status === 'cancelled' ? 'open' : 'done'
    case 'reference':
      return status === 'read' ? 'unread' : 'read'
    default:
      return null
  }
}

/** Add or remove one status from a multi-select filter, keeping menu order. */
export function toggleCardStatusFilter(selected: readonly CardStatus[], status: CardStatus): CardStatus[] {
  const next = new Set(selected)
  if (!next.delete(status)) next.add(status)
  return STATUS_CARD_TYPES.flatMap((type) => CARD_STATUSES[type]!).filter((item) => next.has(item))
}
