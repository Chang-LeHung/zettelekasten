import { afterEach, expect, it, vi } from 'vitest'
import type { AgentTimelineEntry } from '../../../../frontend/src/api/types'
import { splitTurnTimeline } from '../../../../frontend/src/utils/conversationTurns'
import { updateTimeline } from '../chat/timeline'
import { ZettClient } from './zett-client'

afterEach(() => vi.unstubAllGlobals())

function mockStream(events: Array<[string, unknown]>): void {
  const bytes = new TextEncoder().encode(events.map(([event, data]) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`).join(''))
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(new ReadableStream({
    start(controller) {
      // Exercise arbitrary SSE/network boundaries, including multibyte text.
      for (let i = 0; i < bytes.length; i += 7) controller.enqueue(bytes.slice(i, i + 7))
      controller.close()
    },
  }))))
}

const request = { conversationId: 's', providerId: 'p', reasoningEffort: 'medium' as const, text: 'Read this page' }

it('keeps arguments and reverse parallel results on the right call, not the tool name', async () => {
  mockStream([
    ['tool_started', { tool_calls: [
      { id: 'slow', name: 'run_shell', arguments: { command: 'echo slow' } },
      { id: 'fast', name: 'run_shell', arguments: { command: 'echo fast' } },
      { id: 'skip', name: 'run_shell', arguments: { command: 'echo skip' } },
    ] }],
    ['tool_completed', { message: { tool_call_id: 'fast', name: 'run_shell', success: true, output: 'fast output' } }],
    ['tool_failed', { message: { tool_call_id: 'slow', name: 'run_shell', success: false }, error: { message: 'command failed' } }],
    ['tool_skipped', { message: { tool_call_id: 'skip', name: 'run_shell', output: 'skipped' } }],
  ])
  let timeline: AgentTimelineEntry[] = []
  await new ZettClient().streamTurn({ ...request, onEvent: event => { timeline = updateTimeline(timeline, event) } })
  expect(timeline).toHaveLength(3)
  expect(timeline[0]).toMatchObject({ activity: { id: 'slow', state: 'failed', arguments: { command: 'echo slow' }, error_message: 'command failed' } })
  expect(timeline[1]).toMatchObject({ activity: { id: 'fast', state: 'succeeded', arguments: { command: 'echo fast' }, output: 'fast output' } })
  expect(timeline[2]).toMatchObject({ activity: { id: 'skip', state: 'cancelled' } })
})

it('separates thinking and intermediate text from the final answer using the web timeline', async () => {
  mockStream([
    ['reasoning_delta', { delta: '先检查' }],
    ['reasoning_delta', { delta: '页面。' }],
    ['text_delta', { delta: 'I will check.' }],
    ['tool_started', { tool_calls: [{ id: '1', name: 'run_shell', arguments: {} }] }],
    ['tool_completed', { message: { tool_call_id: '1', name: 'run_shell', success: true, output: 'ok' } }],
    ['text_delta', { delta: 'Final ' }],
    ['text_delta', { delta: 'answer.' }],
  ])
  let timeline: AgentTimelineEntry[] = []
  await new ZettClient().streamTurn({ ...request, onEvent: event => { timeline = updateTimeline(timeline, event) } })
  const sections = splitTurnTimeline(timeline)
  expect(sections.execution).toHaveLength(3)
  expect(sections.execution[0]).toMatchObject({ type: 'reasoning', content: '先检查页面。' })
  expect(sections.answer).toEqual([{ id: expect.any(String), type: 'message', content: 'Final answer.' }])
})

it('retains streamed provider-tool input and compaction details', async () => {
  mockStream([
    ['compaction_started', {}],
    ['compaction_text_delta', { delta: 'Summary' }],
    ['compaction_completed', {}],
    ['server_tool_started', { server_tool_call: { id: 'web', name: 'web_fetch', input: null } }],
    ['server_tool_input_delta', { server_tool_input_delta: { call_id: 'web', delta: '{"url":' } }],
    ['server_tool_input_delta', { server_tool_input_delta: { call_id: 'web', delta: '"https://example.com"}' } }],
    ['server_tool_completed', { server_tool_result: { call_id: 'web', name: 'web_fetch', output: { status: 200 } } }],
  ])
  let timeline: AgentTimelineEntry[] = []
  await new ZettClient().streamTurn({ ...request, onEvent: event => { timeline = updateTimeline(timeline, event) } })
  expect(timeline).toHaveLength(2)
  expect(timeline[0]).toMatchObject({ type: 'compaction', activity: { state: 'completed', content: 'Summary' } })
  expect(timeline[1]).toMatchObject({ type: 'server_tool', activity: { name: 'web_fetch', state: 'succeeded', input_delta: '{"url":"https://example.com"}', output: { status: 200 } } })
})

it('reports SSE failures rather than displaying an empty successful answer', async () => {
  mockStream([['text_delta', { delta: 'partial answer' }], ['error', { message: 'provider failed' }]])
  const onEvent = vi.fn()
  await expect(new ZettClient().streamTurn({ ...request, onEvent })).rejects.toThrow('provider failed')
  expect(onEvent).toHaveBeenCalledWith(expect.objectContaining({ content: 'partial answer' }))
})

it('still forwards artifact receipts for the Save cards', async () => {
  const receipt = { id: 'artifact-1', title: 'A card', artifact_type: 'card', pending_draft: true }
  mockStream([['tool_completed', { message: { tool_call_id: 'create-1', name: 'create_artifact', success: true, output: receipt } }]])
  const onTool = vi.fn()
  await new ZettClient().streamTurn({ ...request, onTool })
  expect(onTool).toHaveBeenCalledWith(expect.objectContaining({ id: 'create-1', state: 'succeeded', output: receipt }))
})

it('reads real usage/composition counters and sends a browser capability only when supplied', async () => {
  const usage = { input_tokens: 100, output_tokens: 10, cache_read_tokens: 75, cache_write_tokens: 0, reasoning_tokens: 2 }
  const composition = { system_prompt: .2, tool_prompt: .2, tool_output: .2, user: .2, assistant: .2 }
  mockStream([['model_started', {}], ['model_completed', { usage }], ['custom', { name: 'context_composition', payload: composition }]])
  const onUsage = vi.fn()
  const onComposition = vi.fn()
  const onModelStarted = vi.fn()
  await new ZettClient().streamTurn({ ...request, browserToken: 't'.repeat(43), onUsage, onComposition, onModelStarted })
  expect(onUsage).toHaveBeenCalledWith(usage)
  expect(onComposition).toHaveBeenCalledWith(composition)
  expect(onModelStarted).toHaveBeenCalledTimes(1)
  expect(JSON.parse(vi.mocked(fetch).mock.calls[0][1]!.body as string).browser_token).toBe('t'.repeat(43))
})

it('delivers steering echoes and posts steering through the urgent endpoint', async () => {
  mockStream([['steering_started', {
    steering_message: { text: 'Use the short version', parts: [{ type: 'text', text: 'Use the short version' }] },
  }]])
  const onSteering = vi.fn()
  await new ZettClient().streamTurn({ ...request, onSteering })
  expect(onSteering).toHaveBeenCalledWith({
    content: 'Use the short version',
    parts: [{ type: 'text', text: 'Use the short version' }],
  })

  vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({ accepted: true, accepted_by: 's' })))
  await new ZettClient().steerAgent('session-id', 'Use the short version')
  const [url, init] = vi.mocked(fetch).mock.calls.at(-1)!
  expect(String(url)).toContain('/api/agent/session-id/steer')
  expect(init?.method).toBe('POST')
  expect(JSON.parse(init?.body as string)).toEqual({ raw_content: 'Use the short version', parts: [] })
})

it('forwards ask_user custom events and posts the answer as an extension event', async () => {
  const ask = {
    tool_call_id: 'call-7',
    question: 'Which reply should I post?',
    options: ['Short', 'Long'],
    allow_multiple: false,
    response_event: 'ask_user_response',
  }
  mockStream([['custom', { name: 'ask_user', payload: ask }]])
  const onCustom = vi.fn()
  await new ZettClient().streamTurn({ ...request, onCustom })
  expect(onCustom).toHaveBeenCalledWith({ name: 'ask_user', payload: ask })

  vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({ accepted: true, accepted_by: 's' })))
  await new ZettClient().emitAgentEvent('session-id', 'ask_user_response', { tool_call_id: 'call-7', answer: 'Short' })
  const [url, init] = vi.mocked(fetch).mock.calls.at(-1)!
  expect(String(url)).toContain('/api/agent/session-id/events')
  expect(init?.method).toBe('POST')
  expect(JSON.parse(init?.body as string)).toEqual({
    name: 'ask_user_response',
    payload: { tool_call_id: 'call-7', answer: 'Short' },
  })
})

it('reads the stored context composition a reopened panel shows', async () => {
  const composition = { system_prompt: .3, tool_prompt: .1, tool_output: .1, user: .3, assistant: .2 }
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(composition))))
  await expect(new ZettClient().sessionContextComposition('session-id')).resolves.toEqual(composition)
  expect(String(vi.mocked(fetch).mock.calls[0][0])).toContain('/api/agent/sessions/session-id/context-composition')
})

it('lists the recent conversations the panel can reopen', async () => {
  const sessions = [{ id: 'one', title: 'First', updated_at: '2026-01-01T00:00:00Z', message_count: 2 }]
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(sessions))))
  await expect(new ZettClient().listSessions(20, 40)).resolves.toEqual(sessions)
  const url = String(vi.mocked(fetch).mock.calls[0][0])
  expect(url).toContain('/api/agent/sessions?')
  expect(url).toContain('limit=20')
  expect(url).toContain('offset=40')
  expect(url).toContain('types=normal')
})

it('aborts the actual response reader and preserves only deltas received before Stop', async () => {
  const controller = new AbortController()
  let streamController: ReadableStreamDefaultController<Uint8Array>
  const stream = new ReadableStream<Uint8Array>({
    start(value) { streamController = value },
  })
  vi.stubGlobal('fetch', vi.fn(async (_url, init: RequestInit) => {
    expect(init.signal).toBe(controller.signal)
    init.signal!.addEventListener('abort', () => {
      streamController.error(new DOMException('Aborted', 'AbortError'))
    }, { once: true })
    return new Response(stream)
  }))
  const onDelta = vi.fn()
  const running = new ZettClient().streamTurn({ ...request, signal: controller.signal, onDelta })
  streamController!.enqueue(new TextEncoder().encode('event: text_delta\ndata: {"delta":"Partial"}\n\n'))
  for (let i = 0; i < 5; i++) await Promise.resolve()
  expect(onDelta).toHaveBeenCalledWith('Partial')
  controller.abort()
  await expect(running).rejects.toMatchObject({ name: 'AbortError' })
  expect(onDelta).toHaveBeenCalledTimes(1)
  expect(stream.locked).toBe(false)
})
