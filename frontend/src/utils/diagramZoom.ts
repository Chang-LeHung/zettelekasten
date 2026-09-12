export const MIN_DIAGRAM_ZOOM = 0.5
export const MAX_DIAGRAM_ZOOM = 3
export const DIAGRAM_ZOOM_STEP = 0.25

export function clampDiagramZoom(zoom: number): number {
  return Math.min(MAX_DIAGRAM_ZOOM, Math.max(MIN_DIAGRAM_ZOOM, zoom))
}

export function changeDiagramZoom(zoom: number, direction: -1 | 1): number {
  return clampDiagramZoom(zoom + direction * DIAGRAM_ZOOM_STEP)
}
