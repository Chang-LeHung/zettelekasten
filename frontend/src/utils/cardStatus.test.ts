import { describe, expect, it } from 'vitest'
import {
  CARD_STATUSES,
  STATUS_CARD_TYPES,
  cardStatusLabel,
  cardStatusType,
  isActive,
  isStruck,
  quickTarget,
  statusGlyph,
  statusOptions,
  statusTone,
  toggleCardStatusFilter,
} from './cardStatus'

const ALL = STATUS_CARD_TYPES.flatMap((type) => CARD_STATUSES[type]!)

describe('card status', () => {
  it('gives todo, idea, and reference their own values and leaves notes and quotes out', () => {
    expect(STATUS_CARD_TYPES).toEqual(['todo', 'idea', 'reference'])
    expect(CARD_STATUSES.note).toBeUndefined()
    expect(CARD_STATUSES.quote).toBeUndefined()
    expect(new Set(ALL).size).toBe(ALL.length)
    expect(ALL).toHaveLength(12)
  })

  it('finds the type a value belongs to and lists only that type in its menu', () => {
    expect(cardStatusType('exploring')).toBe('idea')
    expect(cardStatusType('read')).toBe('reference')
    expect(statusOptions('on_hold')).toEqual(['open', 'in_progress', 'on_hold', 'done', 'cancelled'])
    expect(statusOptions('unread')).toEqual(['unread', 'reading', 'read'])
  })

  it('names one label key, one class, and one glyph for every status', () => {
    for (const status of ALL) {
      expect(cardStatusLabel(status)).toBe(`cardStatus.${status}`)
      expect(statusTone(status)).toMatch(/^status-[a-z-]+$/)
      expect(statusGlyph(status)).toBeTruthy()
    }
    expect(statusTone('in_progress')).toBe('status-in-progress')
    expect(new Set(ALL.map(statusTone)).size).toBe(ALL.length)
  })

  it('strikes the title only when the story ended without success', () => {
    expect(ALL.filter(isStruck)).toEqual(['done', 'cancelled', 'dropped'])
    expect(ALL.filter(isActive)).toEqual(['in_progress', 'exploring', 'reading'])
  })

  it('finishes or reopens a task and reads or unreads a reference in one click', () => {
    expect(['open', 'in_progress', 'on_hold'].map((s) => quickTarget(s as never))).toEqual(['done', 'done', 'done'])
    expect(quickTarget('done')).toBe('open')
    expect(quickTarget('cancelled')).toBe('open')
    expect(quickTarget('unread')).toBe('read')
    expect(quickTarget('reading')).toBe('read')
    expect(quickTarget('read')).toBe('unread')
  })

  it('never lets one click decide an idea', () => {
    for (const status of CARD_STATUSES.idea!) expect(quickTarget(status)).toBeNull()
  })

  it('toggles a filter status without disturbing the menu order', () => {
    expect(toggleCardStatusFilter([], 'done')).toEqual(['done'])
    expect(toggleCardStatusFilter(['done'], 'open')).toEqual(['open', 'done'])
    expect(toggleCardStatusFilter(['unread', 'open'], 'adopted')).toEqual(['open', 'adopted', 'unread'])
    expect(toggleCardStatusFilter(['open', 'done'], 'open')).toEqual(['done'])
  })
})
