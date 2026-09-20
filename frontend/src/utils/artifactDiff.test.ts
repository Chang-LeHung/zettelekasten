import { describe, expect, it } from 'vitest'
import type { ArticleArtifactContent, CardArtifactContent } from '../api/types'
import { diffArtifactContent, diffHunks, diffLines } from './artifactDiff'

function card(changes: Partial<CardArtifactContent> = {}): CardArtifactContent {
  return {
    artifact_type: 'card',
    card_type: 'note',
    title: 'Card title',
    summary: 'Card summary',
    content: 'First line\nSecond line\nThird line',
    suggested_tags: [],
    keywords: [],
    ...changes,
  }
}

describe('diffLines', () => {
  it('keeps identical text as context only', () => {
    expect(diffLines('one\ntwo', 'one\ntwo')).toEqual([
      { kind: 'context', text: 'one' },
      { kind: 'context', text: 'two' },
    ])
  })

  it('marks inserted, removed, and rewritten lines', () => {
    expect(diffLines('one\ntwo\nthree', 'one\nsecond\nthree')).toEqual([
      { kind: 'context', text: 'one' },
      { kind: 'removed', text: 'two' },
      { kind: 'added', text: 'second' },
      { kind: 'context', text: 'three' },
    ])
    expect(diffLines('one', 'one\nextra')).toEqual([
      { kind: 'context', text: 'one' },
      { kind: 'added', text: 'extra' },
    ])
    expect(diffLines('one\nextra', 'one')).toEqual([
      { kind: 'context', text: 'one' },
      { kind: 'removed', text: 'extra' },
    ])
  })

  it('normalizes CRLF line endings before comparing', () => {
    expect(diffLines('one\r\ntwo', 'one\ntwo')).toEqual([
      { kind: 'context', text: 'one' },
      { kind: 'context', text: 'two' },
    ])
  })
})

describe('diffHunks', () => {
  it('returns nothing when only context lines exist', () => {
    expect(diffHunks([{ kind: 'context', text: 'same' }])).toEqual([])
  })

  it('keeps context around each change and splits distant changes', () => {
    const lines = Array.from({ length: 20 }, (_, index) => ({
      kind: index === 2 || index === 15 ? ('added' as const) : ('context' as const),
      text: `line ${index}`,
    }))

    const hunks = diffHunks(lines, 1)

    expect(hunks).toHaveLength(2)
    expect(hunks[0].map((line) => line.text)).toEqual(['line 1', 'line 2', 'line 3'])
    expect(hunks[1].map((line) => line.text)).toEqual(['line 14', 'line 15', 'line 16'])
  })
})

describe('diffArtifactContent', () => {
  it('compares the published card with its draft field by field', () => {
    const diff = diffArtifactContent(card(), card({ title: 'New title', content: 'First line\nRewritten\nThird line' }))

    expect(diff?.changed).toBe(true)
    expect(diff?.fields.map((field) => [field.label, field.changed])).toEqual([
      ['Title', true],
      ['Summary', false],
      ['Card type', false],
      ['Body', true],
    ])
    const body = diff?.fields.at(-1)
    expect(body?.hunks.flat().filter((line) => line.kind !== 'context').map((line) => [line.kind, line.text])).toEqual([
      ['removed', 'Second line'],
      ['added', 'Rewritten'],
    ])
  })

  it('includes the subtitle for articles', () => {
    const published: ArticleArtifactContent = {
      artifact_type: 'article',
      title: 'Article',
      subtitle: 'Old subtitle',
      summary: '',
      content: 'Body',
      suggested_tags: [],
      keywords: [],
    }
    const diff = diffArtifactContent(published, { ...published, subtitle: 'New subtitle' })

    expect(diff?.fields.map((field) => [field.label, field.changed])).toEqual([
      ['Title', false],
      ['Summary', false],
      ['Subtitle', true],
      ['Body', false],
    ])
  })

  it('returns nothing without a draft or for specialized artifact types', () => {
    expect(diffArtifactContent(card(), null)).toBeNull()
    expect(diffArtifactContent(null, card())).toBeNull()
    expect(diffArtifactContent(
      { artifact_type: 'image', title: 'Image', summary: '', prompt: '', alt_text: '', source_url: null, asset_path: null, suggested_tags: [], keywords: [] },
      { artifact_type: 'image', title: 'Image', summary: '', prompt: '', alt_text: '', source_url: null, asset_path: null, suggested_tags: [], keywords: [] },
    )).toBeNull()
  })
})
