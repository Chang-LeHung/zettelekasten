import { describe, expect, it } from 'vitest'

import { addTagPath } from './tagAssignment'

describe('addTagPath', () => {
  it('keeps the tags a resource already carries', () => {
    expect(addTagPath(['Engineering/Python'], 'Projects/Zett')).toEqual({
      paths: ['Engineering/Python', 'Projects/Zett'],
      changed: true,
    })
  })

  it('reports a repeated path instead of rewriting the same set', () => {
    const paths = ['Engineering/Python']
    const assignment = addTagPath(paths, 'Engineering/Python')

    expect(assignment.changed).toBe(false)
    expect(assignment.paths).toBe(paths)
  })

  it('never repeats a path when the set already carried it twice', () => {
    expect(addTagPath(['A', 'A'], 'B').paths).toEqual(['A', 'B'])
  })

  it('classifies an untagged resource', () => {
    expect(addTagPath([], 'Engineering/Python').paths).toEqual(['Engineering/Python'])
  })
})
