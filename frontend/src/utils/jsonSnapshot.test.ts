import { reactive } from 'vue'
import { describe, expect, it } from 'vitest'

import { jsonSnapshot } from './jsonSnapshot'

describe('jsonSnapshot', () => {
  it('copies nested Vue proxies into plain detached values', () => {
    const timeline = reactive([
      {
        id: 'tool-1',
        type: 'tool',
        activity: {
          id: 'tool-1',
          name: 'read_file',
          arguments: { file_path: '/notes/context.md' },
          output: { content: 'done' },
        },
      },
    ])

    const snapshot = jsonSnapshot(timeline)
    timeline[0].activity.output.content = 'changed'

    expect(snapshot).toEqual([
      {
        id: 'tool-1',
        type: 'tool',
        activity: {
          id: 'tool-1',
          name: 'read_file',
          arguments: { file_path: '/notes/context.md' },
          output: { content: 'done' },
        },
      },
    ])
  })
})
