import type { Tag } from '../api/types'

export type VisibleTag = Tag & { depth: number; hasChildren: boolean }

export function visibleTagRows(
  nodes: Tag[],
  collapsed: ReadonlySet<string> = new Set<string>(),
  depth = 0,
): VisibleTag[] {
  return nodes.flatMap((tag) => {
    const row = { ...tag, depth, hasChildren: tag.children.length > 0 }
    return collapsed.has(tag.id) ? [row] : [row, ...visibleTagRows(tag.children, collapsed, depth + 1)]
  })
}
