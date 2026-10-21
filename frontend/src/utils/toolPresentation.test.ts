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

import { serverToolLabel, serverToolView } from './toolPresentation'

describe('server tool presentation', () => {
  it('names a hosted tool the way a reader thinks of it', () => {
    expect(serverToolLabel('web_search')).toBe('Web search')
    expect(serverToolLabel('google_search')).toBe('Google Search')
    expect(serverToolLabel('vendor_search')).toBe('vendor search')
  })

  it('shows the queries a search ran and the pages it cited', () => {
    const view = serverToolView(
      'web_search',
      { queries: ['latest python'], pages: [{ url: 'https://python.org', title: 'Python' }] },
      null,
    )
    expect(view.label).toBe('Web search')
    expect(view.summary).toBe('latest python')
    expect(view.pages).toEqual([{ url: 'https://python.org', title: 'Python' }])
  })

  it('counts pages when the provider reported no query, and keeps a failure visible', () => {
    const pages = serverToolView('web_search', { pages: [{ url: 'https://a' }, { url: 'https://b' }] }, null)
    expect(pages.summary).toBe('2 pages')
    const failed = serverToolView('code_execution', { error: 'too_many_requests' }, 'too_many_requests')
    expect(failed.error).toBe('too_many_requests')
  })
})
