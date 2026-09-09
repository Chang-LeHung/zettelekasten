import { afterEach, expect, it, vi } from 'vitest'
import { aiClient } from './client'

afterEach(() => vi.unstubAllGlobals())

it('awaits ordinary tool callbacks before delivering later text', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(
    'event: tool\ndata: {"id":"1","name":"read_file","state":"succeeded","output":"text"}\n\n'
    + 'event: message\ndata: {"content":"done"}\n\n'
    + 'event: result\ndata: null\n\n',
  )))
  const order: string[] = []
  const result = await aiClient.analyzeStream('session', 'hello', 1, 'medium', [], {
    onTool: async () => {
      await Promise.resolve()
      order.push('tool')
    },
    onMessage: () => { order.push('message') },
  })
  expect(order).toEqual(['tool', 'message'])
  expect(result).toBeNull()
})
