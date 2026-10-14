import { describe, expect, it } from 'vitest'
import { BLOCK_COMMANDS, commandsFor, filterCommands } from './blockCommands'
import { blockKind, hasOpenFence } from './markdownBlocks'

const label = (command: { id: string }) => command.id
const ids = (query: string, slides = false) => filterCommands(query, slides, label).map((command) => command.id)

describe('block commands', () => {
  it('lists the deck commands first in a deck, and hides them elsewhere', () => {
    expect(ids('', true).slice(0, 4)).toEqual(['slide', 'section', 'cover', 'htmlSlide'])
    expect(ids('')).not.toContain('slide')
    expect(ids('')).not.toContain('cover')
  })

  it('offers a plain divider only outside a deck, where it would be a section break', () => {
    expect(ids('')).toContain('divider')
    expect(ids('', true)).not.toContain('divider')
  })

  it('matches by name, by keyword, and by Chinese keyword', () => {
    expect(ids('h2')).toContain('h2')
    expect(ids('mermaid')).toEqual(['diagram'])
    expect(ids('公式')).toEqual(['math'])
    expect(ids('待办')).toEqual(['todo'])
    expect(ids('zzz')).toEqual([])
  })

  it('ranks a name that starts with the query above a keyword that merely contains it', () => {
    expect(ids('code')[0]).toBe('code')
    expect(ids('quote')[0]).toBe('quote')
  })

  it('has unique ids and a caret that lands inside its template', () => {
    expect(new Set(BLOCK_COMMANDS.map((command) => command.id)).size).toBe(BLOCK_COMMANDS.length)
    for (const command of BLOCK_COMMANDS) {
      if (command.caret !== undefined) expect(command.caret).toBeLessThanOrEqual(command.template.length)
    }
  })

  it('writes templates the editor reads back as the kind it promised', () => {
    const kind = (id: string, slides = false) => blockKind(BLOCK_COMMANDS.find((command) => command.id === id)!.template, { slides })
    expect(kind('h1')).toBe('heading')
    expect(kind('bullet')).toBe('list')
    expect(kind('todo')).toBe('todo')
    expect(kind('code')).toBe('code')
    expect(kind('diagram')).toBe('diagram')
    expect(kind('math')).toBe('math')
    expect(kind('table')).toBe('table')
    expect(kind('image')).toBe('image')
    expect(kind('callout')).toBe('quote')
    expect(kind('slide', true)).toBe('slideBreak')
    expect(kind('section', true)).toBe('sectionBreak')
    expect(kind('cover', true)).toBe('slideMarker')
    expect(kind('htmlSlide', true)).toBe('slideMarker')
  })

  it('never leaves a fence open in a template', () => {
    for (const command of BLOCK_COMMANDS) expect(hasOpenFence(command.template)).toBe(false)
  })

  it('counts the commands each mode offers', () => {
    expect(commandsFor(false).every((command) => !command.slidesOnly)).toBe(true)
    expect(commandsFor(true).every((command) => !command.proseOnly)).toBe(true)
  })
})
