import { expect, it } from 'vitest'
import { clampArtifactListWidth, maxArtifactListWidth, parseArtifactListWidth } from './artifactSplit'

it('reports the widest list a pane allows', () => {
  expect(maxArtifactListWidth(900)).toBe(568)
  expect(maxArtifactListWidth(100)).toBe(0)
})

it('keeps the list and preview readable when the divider moves', () => {
  expect(clampArtifactListWidth(300, 900)).toBe(300)
  expect(clampArtifactListWidth(9999, 900)).toBe(568)
  expect(clampArtifactListWidth(-20, 900)).toBe(176)
})

it('bounds the list when the workspace becomes narrow', () => {
  expect(clampArtifactListWidth(200, 300)).toBe(0)
  expect(clampArtifactListWidth(200, 400)).toBe(68)
})

it('ignores a stored width that is not a positive number', () => {
  expect(parseArtifactListWidth(null)).toBeNull()
  expect(parseArtifactListWidth('abc')).toBeNull()
  expect(parseArtifactListWidth('-5')).toBeNull()
  expect(parseArtifactListWidth('260')).toBe(260)
})
