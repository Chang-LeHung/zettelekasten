/**
 * Add one tag path to the set a resource already carries.
 *
 * Dropping a card or a file onto a tag in the sidebar means "also classify it
 * with this", so the existing set is kept and the drop is complete once the path
 * is already in it. `changed` lets the caller tell the user nothing happened
 * instead of rewriting an identical set.
 */
export interface TagAssignment {
  paths: string[]
  changed: boolean
}

export function addTagPath(paths: string[], path: string): TagAssignment {
  if (paths.includes(path)) return { paths, changed: false }
  return { paths: [...new Set([...paths, path])], changed: true }
}
