import { describe, expect, it } from 'vitest'
import { todoFromTool } from './toolPresentation'

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
