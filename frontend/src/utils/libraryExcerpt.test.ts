import { expect, it } from 'vitest'
import { libraryExcerptText } from './libraryExcerpt'

it('extracts short prose without mounting slide cover images or embedded HTML', () => {
  expect(libraryExcerptText('<!-- slide:cover -->\n# Title\n\n## Subtitle\n\nA **useful** explanation with `code`.\n\n![logo](/logo.png)\n\n<div>Layout</div>')).toBe('A useful explanation with code.')
  expect(libraryExcerptText('```mermaid\ngraph TD\nA-->B\n```')).toBe('')
})

it('bounds long summaries and retains link labels as plain text', () => {
  expect(libraryExcerptText('[Documentation](https://example.com)')).toBe('Documentation')
  expect(libraryExcerptText('x'.repeat(500))).toHaveLength(221)
})
