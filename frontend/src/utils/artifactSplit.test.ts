import { expect, it } from 'vitest'
import { clampArtifactListHeight } from './artifactSplit'

it('keeps the list and preview readable when the divider moves', () => {
  expect(clampArtifactListHeight(300, 800, 64)).toBe(300)
  expect(clampArtifactListHeight(999, 800, 64)).toBe(382)
  expect(clampArtifactListHeight(-20, 800, 64)).toBe(96)
})

it('bounds the list when the workspace becomes short', () => {
  expect(clampArtifactListHeight(200, 270, 64)).toBe(0)
  expect(clampArtifactListHeight(200, 380, 64)).toBe(0)
  expect(clampArtifactListHeight(200, 520, 64)).toBe(102)
})
