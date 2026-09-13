import { afterEach, expect, it, vi } from 'vitest'
import { aiClient, libraryClient, settingsClient } from './client'

afterEach(() => vi.unstubAllGlobals())

it('loads slide decks into the library and keeps their content type when editing', async () => {
  const artifact = {
    id: 'slides-1',
    session_id: 'session-1',
    artifact_type: 'slides',
    status: 'saved',
    content: {
      artifact_type: 'slides',
      title: 'Zett in ten minutes',
      subtitle: 'A compact tour',
      summary: 'Presentation summary',
      suggested_tags: [],
      keywords: ['zett'],
      content: '# Opening\n\n---\n\n## Finish',
    },
    raw_content: null,
    version: 1,
    metadata: {},
    created_at: '2026-09-13T00:00:00Z',
    updated_at: '2026-09-13T00:00:00Z',
  }
  const fetchMock = vi.fn()
    .mockResolvedValueOnce(new Response(JSON.stringify([artifact])))
    .mockResolvedValueOnce(new Response(JSON.stringify({
      ...artifact,
      version: 2,
      content: { ...artifact.content, title: 'Updated deck' },
    })))
  vi.stubGlobal('fetch', fetchMock)

  const [item] = await libraryClient.list()
  expect(item).toMatchObject({ item_type: 'slides', subtitle: 'A compact tour' })
  expect(String(fetchMock.mock.calls[0]?.[0])).toContain('artifact_types=slides')

  const updated = await libraryClient.update('slides', item.id, {
    title: 'Updated deck',
    subtitle: 'A compact tour',
    summary: 'Presentation summary',
    content: artifact.content.content,
  })
  expect(updated.item_type).toBe('slides')
  const body = JSON.parse(String((fetchMock.mock.calls[1]?.[1] as RequestInit).body))
  expect(body.content).toMatchObject({ artifact_type: 'slides', title: 'Updated deck' })
})

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

it('delivers a parallel batch and correlates reverse mixed outcomes by tool-call ID', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(
    'event: tool_started\ndata: {"session_id":"session","phase":"running_tool","tool_calls":[{"id":"slow","name":"read_file","arguments":{"path":"slow"}},{"id":"fast","name":"read_file","arguments":{"path":"fast"}},{"id":"bad","name":"read_file","arguments":{"path":"bad"}}]}\n\n'
    + 'event: tool_completed\ndata: {"session_id":"session","phase":"running_tool","message":{"role":"tool","tool_call_id":"fast","name":"read_file","success":true,"output":"fast","attributes":{}}}\n\n'
    + 'event: tool_failed\ndata: {"session_id":"session","phase":"running_tool","message":{"role":"tool","tool_call_id":"bad","name":"read_file","success":false,"output":{"error":"failed"},"attributes":{}},"error":{"type":"RuntimeError","message":"failed"}}\n\n'
    + 'event: tool_completed\ndata: {"session_id":"session","phase":"ready","message":{"role":"tool","tool_call_id":"slow","name":"read_file","success":true,"output":"slow","attributes":{}}}\n\n',
  )))
  const tools: Array<{ id: string; state: string }> = []

  await aiClient.analyzeStream('session', 'hello', 'provider', 'medium', [], {
    onTool: (activity) => { tools.push({ id: activity.id, state: activity.state }) },
  })

  expect(tools).toEqual([
    { id: 'slow', state: 'started' },
    { id: 'fast', state: 'started' },
    { id: 'bad', state: 'started' },
    { id: 'fast', state: 'succeeded' },
    { id: 'bad', state: 'failed' },
    { id: 'slow', state: 'succeeded' },
  ])
})

it('delivers provider-hosted tool lifecycle events independently of local tools', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(
    'event: server_tool_started\ndata: {"session_id":"session","phase":"generating","server_tool_call":{"id":"hosted-1","name":"web_fetch","input":null}}\n\n'
    + 'event: server_tool_input_delta\ndata: {"session_id":"session","phase":"generating","server_tool_input_delta":{"call_id":"hosted-1","delta":"{\\"url\\":\\"https://example.com\\"}"}}\n\n'
    + 'event: server_tool_completed\ndata: {"session_id":"session","phase":"generating","server_tool_result":{"call_id":"hosted-1","name":"web_fetch","output":{"status":200},"error_code":null}}\n\n',
  )))
  const hosted: Array<{ id: string; state: string; delta?: string }> = []
  const local: string[] = []

  await aiClient.analyzeStream('session', 'fetch', 'provider', 'medium', [], {
    onServerTool: activity => hosted.push({
      id: activity.id,
      state: activity.state,
      delta: activity.input_delta,
    }),
    onTool: activity => local.push(activity.id),
  })

  expect(hosted).toEqual([
    { id: 'hosted-1', state: 'started', delta: undefined },
    { id: 'hosted-1', state: 'streaming', delta: '{"url":"https://example.com"}' },
    { id: 'hosted-1', state: 'succeeded', delta: undefined },
  ])
  expect(local).toEqual([])
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

it('forwards context composition ratios without interpreting custom payloads', async () => {
  const composition = {
    system_prompt: 0.1,
    tool_prompt: 0.2,
    tool_output: 0.3,
    user: 0.15,
    assistant: 0.25,
  }
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(
    `event: custom\ndata: ${JSON.stringify({ session_id: 'session', phase: 'ready', name: 'context_composition', payload: composition })}\n\n`,
  )))
  const events: Array<{ name: string; payload: Record<string, unknown> }> = []

  await aiClient.analyzeStream('session', 'hello', 'provider', 'medium', [], {
    onCustom: event => events.push(event),
  })

  expect(events).toEqual([{ name: 'context_composition', payload: composition }])
})

it('exposes the backend error detail instead of discarding it', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(
    JSON.stringify({ detail: 'The selected provider is unavailable' }),
    { status: 503 },
  )))

  await expect(aiClient.analyzeStream('session', 'hello', 'provider', 'medium', []))
    .rejects.toThrow('The selected provider is unavailable')
})

it('loads binary asset content through the typed API client', async () => {
  const payload = new Uint8Array([37, 80, 68, 70])
  const fetchMock = vi.fn().mockResolvedValue(new Response(payload))
  vi.stubGlobal('fetch', fetchMock)

  const result = await aiClient.getSessionAssetContent('session-1', 'asset-1')

  expect(new Uint8Array(result)).toEqual(payload)
  expect(fetchMock).toHaveBeenCalledWith('/api/agent/session-1/assets/asset-1/content', { signal: undefined })
})

it('sends pasted images in their position among text segments', async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response(
    'event: run_completed\ndata: {"session_id":"session","phase":"completed"}\n\n',
  ))
  vi.stubGlobal('fetch', fetchMock)

  await aiClient.analyzeStream('session', 'beforeafter', 'provider', 'medium', [], {}, undefined, [
    { type: 'text', text: 'before' },
    { type: 'image', name: 'paste.png', mime_type: 'image/png', data_base64: 'AA==' },
    { type: 'text', text: 'after' },
  ])

  const request = fetchMock.mock.calls[0]?.[1] as RequestInit
  expect(JSON.parse(String(request.body))).toMatchObject({
    raw_content: 'beforeafter',
    parts: [
      { type: 'text', text: 'before' },
      { type: 'image', name: 'paste.png', mime_type: 'image/png', data_base64: 'AA==' },
      { type: 'text', text: 'after' },
    ],
  })
})

it('loads and replaces runtime settings through the typed client', async () => {
  const fetchMock = vi.fn()
    .mockResolvedValueOnce(new Response(JSON.stringify({ max_message_images: 32, max_turn_iterations: 36, compaction_max_tokens: 128000, compaction_keep_recent_tokens: 32000 })))
    .mockResolvedValueOnce(new Response(JSON.stringify({ max_message_images: 48, max_turn_iterations: 64, compaction_max_tokens: 512000, compaction_keep_recent_tokens: 64000 })))
  vi.stubGlobal('fetch', fetchMock)

  expect(await settingsClient.get()).toEqual({ max_message_images: 32, max_turn_iterations: 36, compaction_max_tokens: 128000, compaction_keep_recent_tokens: 32000 })
  const update = { max_message_images: 48, max_turn_iterations: 64, compaction_max_tokens: 512000, compaction_keep_recent_tokens: 64000 }
  expect(await settingsClient.update(update)).toEqual({
    max_message_images: 48,
    max_turn_iterations: 64,
    compaction_max_tokens: 512000,
    compaction_keep_recent_tokens: 64000,
  })
  expect(fetchMock).toHaveBeenNthCalledWith(1, '/api/settings', expect.any(Object))
  expect(fetchMock.mock.calls[1]?.[1]).toMatchObject({
    method: 'PUT',
    body: JSON.stringify(update),
  })
})

it('loads the model most recently used by one session', async () => {
  const preference = {
    provider_id: 'provider-7',
    provider: 'deepseek',
    model: 'deepseek-v4-flash',
  }
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(preference)))
  vi.stubGlobal('fetch', fetchMock)

  expect(await aiClient.getAgentSessionModel('session-7')).toEqual(preference)
  expect(fetchMock).toHaveBeenCalledWith('/api/agent/sessions/session-7/model', expect.any(Object))
})
