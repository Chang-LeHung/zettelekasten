import { expect, it } from 'vitest'
import { editArguments, editDiffRows } from './editDiff'

const text = (row: { segments: { text: string }[] }) => row.segments.map((segment) => segment.text).join('')
const strong = (row: { segments: { text: string; strong: boolean }[] }) => row.segments.filter((segment) => segment.strong).map((segment) => segment.text)

it('emphasises only the words changed inside a modified line', () => {
  const rows = editDiffRows('const limit = 10\nkeep', 'const limit = 25\nkeep')
  expect(rows.map((row) => row.kind)).toEqual(['removed', 'added', 'context'])
  expect(strong(rows[0])).toEqual(['10'])
  expect(strong(rows[1])).toEqual(['25'])
  expect(text(rows[1])).toBe('const limit = 25')
})

it('leaves added and deleted lines plain', () => {
  const added = editDiffRows('a\nb', 'a\nnew line\nb')
  expect(added.map((row) => row.kind)).toEqual(['context', 'added', 'context'])
  expect(strong(added[1])).toEqual([])
  const deleted = editDiffRows('a\ngone\nb', 'a\nb')
  expect(deleted.map((row) => row.kind)).toEqual(['context', 'removed', 'context'])
  expect(strong(deleted[1])).toEqual([])
})

it('treats a mostly rewritten line as a plain replacement', () => {
  const [removed, added] = editDiffRows('alpha beta gamma', 'one two three four')
  expect(strong(removed)).toEqual([])
  expect(strong(added)).toEqual([])
})

it('pairs lines in order and keeps the extra ones plain', () => {
  const rows = editDiffRows('x = 1\ny = 2', 'x = 5\ny = 7\nz = 9')
  expect(rows.map((row) => row.kind)).toEqual(['removed', 'removed', 'added', 'added', 'added'])
  expect(strong(rows[2])).toEqual(['5'])
  expect(strong(rows[4])).toEqual([])
})

it('shows an empty side as pure insertion or deletion', () => {
  expect(editDiffRows('', 'a\nb').map((row) => row.kind)).toEqual(['added', 'added'])
  expect(editDiffRows('a', '').map((row) => row.kind)).toEqual(['removed'])
})

it('reads one pair or a list of pairs from edit arguments', () => {
  expect(editArguments({ old_text: 'a', new_text: 'b' })).toEqual([{ before: 'a', after: 'b' }])
  expect(editArguments({ path: 'x', edits: [{ old_text: 'a', new_text: 'b' }, { old_text: 'c', new_text: 'd' }, { old_text: 1 }] })).toEqual([
    { before: 'a', after: 'b' },
    { before: 'c', after: 'd' },
  ])
  expect(editArguments({ old_text: 'a' })).toEqual([{ before: 'a', after: '' }])
  expect(editArguments({ new_text: 'a' })).toEqual([])
  expect(editArguments(undefined)).toEqual([])
})
