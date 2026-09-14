// @vitest-environment jsdom
import { expect, it } from 'vitest'
import DOMPurify from 'dompurify'
import { renderMermaid } from './mermaidRenderer'

it('renders sequence message lines and arrow markers', async () => {
  SVGElement.prototype.getBBox = () => ({ x: 0, y: 0, width: 120, height: 18 }) as DOMRect
  const { svg } = await renderMermaid(`sequenceDiagram
autonumber
participant UI as Browser UI
participant API as FastAPI
UI->>API: POST /messages
API-->>UI: 200 text/event-stream`)

  expect(svg).toContain('messageLine0')
  expect(svg).toContain('messageLine1')
  expect(svg).toMatch(/marker-end=/u)
  const sanitized = DOMPurify.sanitize(svg, {
    ADD_TAGS: ['foreignObject'],
    FORBID_CONTENTS: [],
    HTML_INTEGRATION_POINTS: { foreignobject: true },
    USE_PROFILES: { html: true, svg: true, svgFilters: true },
  })
  expect(sanitized).toContain('messageLine0')
  expect(sanitized).toContain('<style>')
})
