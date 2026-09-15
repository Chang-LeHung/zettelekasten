import { expect, it } from 'vitest'
import type { Tag } from '../api/types'
import { visibleTagRows } from './tagTree'

function tag(id: string, path: string, children: Tag[] = []): Tag {
  return {
    id,
    path,
    normalized_path: path.toLowerCase(),
    name: path.split('/').at(-1)!,
    parent_id: null,
    description: null,
    color: null,
    direct_count: 0,
    total_count: 1,
    created_at: '',
    updated_at: '',
    children,
  }
}

it('keeps hierarchy depth and hides only descendants of collapsed nodes', () => {
  const tree = [tag('engineering', 'Engineering', [
    tag('python', 'Engineering/Python', [tag('asyncio', 'Engineering/Python/Asyncio')]),
  ])]

  expect(visibleTagRows(tree).map(({ id, depth, hasChildren }) => ({ id, depth, hasChildren }))).toEqual([
    { id: 'engineering', depth: 0, hasChildren: true },
    { id: 'python', depth: 1, hasChildren: true },
    { id: 'asyncio', depth: 2, hasChildren: false },
  ])
  expect(visibleTagRows(tree, new Set(['python'])).map(({ id }) => id)).toEqual(['engineering', 'python'])
})
