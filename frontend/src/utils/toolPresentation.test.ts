import { describe, expect, it } from 'vitest'
import { todoFromTool, toolOutputParts } from './toolPresentation'

const item = { content: 'Inspect', status: 'processing' }
const progress = { todos: [item], processing_index: 0, processing: item, completed: false }

describe('todoFromTool', () => {
  it('reads progress from an ordinary successful tool result', () => {
    expect(todoFromTool({ id: '1', name: 'todo_write', state: 'succeeded', output: progress })).toEqual(progress)
  })

  it.each([null, 'text', {}, { ...progress, processing_index: 8 }, { ...progress, todos: [{}] }])(
    'ignores malformed output without breaking the conversation', (output) => {
      expect(todoFromTool({ id: '1', name: 'todo_write', state: 'succeeded', output })).toBeNull()
    },
  )

  it('ignores other tools and failed calls', () => {
    expect(todoFromTool({ id: '1', name: 'read_file', state: 'succeeded', output: progress })).toBeNull()
    expect(todoFromTool({ id: '1', name: 'todo_write', state: 'failed', output: progress })).toBeNull()
  })
})

describe('toolOutputParts', () => {
  it('recognizes ordered text and image tool output', () => {
    expect(toolOutputParts([
      { text: 'before' },
      { type: 'image', url: 'data:image/png;base64,aW1hZ2U=', alt_text: 'preview.png' },
      { text: 'after' },
    ])).toEqual([
      { type: 'text', text: 'before' },
      { type: 'image', url: 'data:image/png;base64,aW1hZ2U=', alt_text: 'preview.png' },
      { type: 'text', text: 'after' },
    ])
    expect(toolOutputParts({ type: 'image', content_url: 'https://example.com/image.png' })).toEqual([
      { type: 'image', url: 'https://example.com/image.png', alt_text: null },
    ])
  })

  it('keeps ordinary JSON output on the text fallback', () => {
    expect(toolOutputParts({ lines: 12 })).toBeNull()
    expect(toolOutputParts([{ path: 'README.md' }])).toBeNull()
    expect(toolOutputParts([])).toBeNull()
  })
})
