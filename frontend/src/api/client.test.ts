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

it('delivers usage for every completed model step in one tool loop', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(
    'event: model_completed\ndata: {"session_id":"session","phase":"ready","usage":{"input_tokens":100,"output_tokens":20,"cache_read_tokens":80,"cache_write_tokens":0,"reasoning_tokens":5}}\n\n'
    + 'event: model_completed\ndata: {"session_id":"session","phase":"ready","usage":{"input_tokens":150,"output_tokens":30,"cache_read_tokens":100,"cache_write_tokens":0,"reasoning_tokens":0}}\n\n'
    + 'event: run_completed\ndata: {"session_id":"session","phase":"completed"}\n\n',
  )))
  const usages: number[] = []
  await aiClient.analyzeStream('session', 'hello', 'provider', 'medium', [], {
    onUsage: (usage) => usages.push(usage.input_tokens + usage.output_tokens),
  })
  expect(usages).toEqual([120, 180])
})
