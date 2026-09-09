import { afterEach, expect, it, vi } from 'vitest'
import { aiClient } from './client'

afterEach(() => vi.unstubAllGlobals())

it('awaits ordinary tool callbacks before delivering later text', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(
    'event: tool_completed\ndata: {"session_id":"session","phase":"ready","message":{"role":"tool","tool_call_id":"1","name":"read_file","success":true,"output":"text","attributes":{}}}\n\n'
    + 'event: text_delta\ndata: {"session_id":"session","phase":"generating","delta":"done"}\n\n'
    + 'event: run_completed\ndata: {"session_id":"session","phase":"completed"}\n\n',
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
