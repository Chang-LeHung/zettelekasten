import { describe, expect, it } from 'vitest'
import {
  MAX_DIAGRAM_ZOOM,
  MIN_DIAGRAM_ZOOM,
  changeDiagramZoom,
  clampDiagramZoom,
} from './diagramZoom'

describe('diagram zoom', () => {
  it('clamps zoom to the supported range', () => {
    expect(clampDiagramZoom(0)).toBe(MIN_DIAGRAM_ZOOM)
    expect(clampDiagramZoom(1.75)).toBe(1.75)
    expect(clampDiagramZoom(10)).toBe(MAX_DIAGRAM_ZOOM)
  })

  it('changes zoom in stable quarter steps', () => {
    expect(changeDiagramZoom(1, 1)).toBe(1.25)
    expect(changeDiagramZoom(1, -1)).toBe(0.75)
    expect(changeDiagramZoom(MAX_DIAGRAM_ZOOM, 1)).toBe(MAX_DIAGRAM_ZOOM)
    expect(changeDiagramZoom(MIN_DIAGRAM_ZOOM, -1)).toBe(MIN_DIAGRAM_ZOOM)
  })
})
