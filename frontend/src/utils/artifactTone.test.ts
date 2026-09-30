import { expect, it } from 'vitest'
import { artifactTone } from './artifactTone'

it('gives every artifact kind a stable distinct color hook', () => {
  const types = ['card', 'article', 'image', 'slides', 'latex_pdf'] as const
  expect(new Set(types.map(artifactTone)).size).toBe(types.length)
  expect(artifactTone('latex_pdf')).toBe('artifact-tone-latex-pdf')
})
