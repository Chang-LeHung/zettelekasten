import { afterEach, expect, it, vi } from 'vitest'
import { aiClient, assetClient, libraryClient, settingsClient, tagClient } from './client'

afterEach(() => vi.unstubAllGlobals())

it('loads, uploads, and deletes global assets through the typed client', async () => {
  const asset = {
    id: 'asset-1',
    name: 'diagram.png',
    mime_type: 'image/png',
    size_bytes: 5,
    sha256: 'hash',
    storage_path: 'assets/static/asset-1.png',
    content_url: '/api/files/assets/static/asset-1.png',
    metadata: {},
    created_at: '',
    updated_at: '',
  }
  const fetchMock = vi.fn()
    .mockResolvedValueOnce(new Response(JSON.stringify([asset])))
    .mockResolvedValueOnce(new Response(JSON.stringify(asset)))
    .mockResolvedValueOnce(new Response(new Uint8Array([1, 2])))
    .mockResolvedValueOnce(new Response(JSON.stringify({ ok: true })))
  vi.stubGlobal('fetch', fetchMock)

  expect(await assetClient.list()).toEqual([asset])
  expect(await assetClient.upload(new File(['image'], 'diagram.png', { type: 'image/png' }))).toEqual(asset)
  expect(new Uint8Array(await assetClient.getUrlContent(asset.content_url))).toEqual(new Uint8Array([1, 2]))
  expect(await assetClient.delete('asset-1')).toEqual({ ok: true })
  expect(fetchMock).toHaveBeenNthCalledWith(1, '/api/assets?limit=500&offset=0', expect.any(Object))
  expect(fetchMock.mock.calls[1]?.[0]).toBe('/api/assets/upload?name=diagram.png')
  expect(fetchMock.mock.calls[2]?.[0]).toBe('/api/files/assets/static/asset-1.png')
  expect(fetchMock.mock.calls[3]?.[0]).toBe('/api/assets/asset-1')
})

it('loads the persistent tag tree and delegates subtree filtering to the backend', async () => {
  const tree = [{
    id: 'engineering', path: 'Engineering', normalized_path: 'engineering', name: 'Engineering',
    parent_id: null, description: null, color: null, direct_count: 0, total_count: 1,
    created_at: '', updated_at: '',
    children: [{
      id: 'python', path: 'Engineering/Python', normalized_path: 'engineering/python', name: 'Python',
      parent_id: 'engineering', description: null, color: null, direct_count: 1, total_count: 1,
      created_at: '', updated_at: '', children: [],
    }],
  }]
  const fetchMock = vi.fn()
    .mockResolvedValueOnce(new Response(JSON.stringify(tree)))
    .mockResolvedValueOnce(new Response(JSON.stringify([])))
  vi.stubGlobal('fetch', fetchMock)

  expect(await tagClient.list()).toEqual(tree)
  await libraryClient.list({ tagId: 'engineering' })

  expect(String(fetchMock.mock.calls[0]?.[0])).toContain('/library/tags')
  expect(String(fetchMock.mock.calls[1]?.[0])).toContain('tag_ids=engineering')
})

it('sends selected artifact types to the library endpoint', async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify([])))
  vi.stubGlobal('fetch', fetchMock)

  await libraryClient.list({ artifactTypes: ['slides', 'latex_pdf'] })

  const url = new URL(String(fetchMock.mock.calls[0]?.[0]), 'http://localhost')
  expect(url.searchParams.getAll('artifact_types')).toEqual(['slides', 'latex_pdf'])
  expect(url.searchParams.getAll('statuses')).toEqual(['saved'])
})

it('creates tags and explicitly requests recursive assignment cleanup when deleting', async () => {
  const created = {
    id: 'python', path: 'Engineering/Python', normalized_path: 'engineering/python', name: 'Python',
    parent_id: 'engineering', description: null, color: null, created_at: '', updated_at: '',
  }
  const fetchMock = vi.fn()
    .mockResolvedValueOnce(new Response(JSON.stringify(created), { status: 201 }))
    .mockResolvedValueOnce(new Response(JSON.stringify({ ok: true })))
  vi.stubGlobal('fetch', fetchMock)

  await expect(tagClient.create({ path: 'Engineering/Python' })).resolves.toEqual(created)
  await expect(tagClient.delete('python/tag')).resolves.toEqual({ ok: true })

  expect(String(fetchMock.mock.calls[0]?.[0])).toContain('/library/tags')
  expect(fetchMock.mock.calls[0]?.[1]).toMatchObject({
    method: 'POST',
    body: JSON.stringify({ path: 'Engineering/Python' }),
  })
  expect(String(fetchMock.mock.calls[1]?.[0])).toContain('/library/tags/python%2Ftag?recursive=true&force=true')
  expect(fetchMock.mock.calls[1]?.[1]).toMatchObject({ method: 'DELETE' })
})

it('replaces an artifact tag set through the persistent tag endpoint', async () => {
  const artifact = {
    id: 'artifact-1',
    session_id: 'session-1',
    artifact_type: 'card',
    status: 'saved',
    content: {
      artifact_type: 'card',
      card_type: 'note',
      title: 'Card',
      summary: '',
      content: 'Body',
      suggested_tags: [],
      keywords: [],
    },
    raw_content: null,
    version: 1,
    metadata: {},
    tags: [{ id: 'python', path: 'Engineering/Python', name: 'Python' }],
    created_at: '',
    updated_at: '',
  }
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(artifact)))
  vi.stubGlobal('fetch', fetchMock)

  await expect(tagClient.replaceArtifactTags('artifact-1', ['Engineering/Python'])).resolves.toEqual(artifact)
  expect(fetchMock).toHaveBeenCalledWith('/api/library/tags/artifacts/artifact-1', expect.objectContaining({
    method: 'PUT',
    body: JSON.stringify({ paths: ['Engineering/Python'] }),
  }))
})

it('loads minimal LaTeX references without expecting Markdown metadata', async () => {
  const artifact = {
    id: 'latex-1', session_id: 'session-1', artifact_type: 'latex_pdf', status: 'saved',
    content: { artifact_type: 'latex_pdf', project_path: 'artifacts/session-1/paper', pdf_name: 'paper.pdf' },
    raw_content: null, version: 1, metadata: {}, created_at: '', updated_at: '',
    content_url: '/api/files/artifacts/session-1/paper/paper.pdf',
  }
  const fetchMock = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify([artifact])))
    .mockResolvedValueOnce(new Response('%PDF-1.4'))
  vi.stubGlobal('fetch', fetchMock)
  const [item] = await libraryClient.list()
  expect(item).toMatchObject({ session_id: 'session-1', item_type: 'latex_pdf', title: 'paper', content: '', tags: [] })
  expect(String(fetchMock.mock.calls[0]?.[0])).toContain('artifact_types=latex_pdf')
  expect(libraryClient.documentReference(item.id)).toEqual({
    id: 'latex-1',
    session_id: 'session-1',
    content_url: '/api/files/artifacts/session-1/paper/paper.pdf',
  })
  const controller = new AbortController()
  const bytes = await assetClient.getUrlContent(artifact.content_url, controller.signal)
  expect(new TextDecoder().decode(bytes!)).toBe('%PDF-1.4')
  expect(String(fetchMock.mock.calls[1]?.[0])).toContain('/api/files/artifacts/session-1/paper/paper.pdf')
  expect(fetchMock.mock.calls[1]?.[1]).toMatchObject({ signal: controller.signal })
  await expect(libraryClient.update('latex_pdf', item.id, {
    title: 'Changed', subtitle: null, summary: null, content: 'Not LaTeX',
  })).rejects.toThrow('Edit the LaTeX project files')
  expect(fetchMock).toHaveBeenCalledTimes(2)
})

it('renames an asset through a metadata-only request', async () => {
  const updated = { id: 'asset-1', name: 'Logo', content_url: '/unchanged/content' }
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(updated)))
  vi.stubGlobal('fetch', fetchMock)
  expect(await aiClient.renameSessionAsset('session-1', 'asset-1', 'Logo')).toEqual(updated)
  expect(String(fetchMock.mock.calls[0]?.[0])).toContain('/agent/session-1/assets/asset-1/name')
  expect(fetchMock.mock.calls[0]?.[1]).toMatchObject({ method: 'PATCH', body: JSON.stringify({ name: 'Logo' }) })
})

it('imports a static asset into a session as an object reference', async () => {
  const imported = {
    id: 'session-asset-1',
    session_id: 'session-1',
    asset_type: 'link',
    name: 'reference.png',
    mime_type: 'image/png',
    size_bytes: 17,
    sha256: 'url-hash',
    text_content: null,
    source_url: null,
    storage_path: null,
    source_path: 'assets/static/static-1.png',
    content_url: '/api/files/assets/static/static-1.png',
    metadata: { static_asset_id: 'static-1' },
    created_at: '',
    updated_at: '',
  }
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(imported)))
  vi.stubGlobal('fetch', fetchMock)

  await expect(aiClient.importStaticAsset('session-1', 'static-1')).resolves.toEqual(imported)
  expect(fetchMock).toHaveBeenCalledWith(
    '/api/agent/session-1/assets/import/static/static-1',
    expect.objectContaining({ method: 'POST' }),
  )
})

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

it('sends the selected shell approval mode with an Agent request', async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response(
    'event: run_completed\ndata: {"session_id":"session","phase":"completed"}\n\n',
  ))
  vi.stubGlobal('fetch', fetchMock)

  await aiClient.analyzeStream('session', 'hello', 'provider', 'medium', [], {}, undefined, [], 'allow_all')

  const body = JSON.parse(String((fetchMock.mock.calls[0]?.[1] as RequestInit).body))
  expect(body.shell_approval_mode).toBe('allow_all')
})

it('delivers steering message parts to the active stream callback', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(
    'event: steering_started\n'
    + 'data: {"session_id":"session","phase":"generating","steering_message":{"text":"Look here","parts":[{"type":"text","text":"Look here"},{"type":"image","name":"clipboard.png","mime_type":"image/png","content_url":"data:image/png;base64,aW1hZ2U="}],"attributes":{}}}\n\n'
    + 'event: run_completed\ndata: {"session_id":"session","phase":"completed"}\n\n',
  )))
  const steering: Array<{ content: string; parts: unknown[] }> = []

  await aiClient.analyzeStream('session', 'hello', 'provider', 'medium', [], {
    onSteering: (message) => { steering.push(message) },
  })

  expect(steering).toEqual([
    {
      content: 'Look here',
      parts: [
        { type: 'text', text: 'Look here' },
        {
          type: 'image',
          name: 'clipboard.png',
          mime_type: 'image/png',
          content_url: 'data:image/png;base64,aW1hZ2U=',
        },
      ],
    },
  ])
})

it('sends multimodal steering through the typed endpoint', async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ accepted: true })))
  vi.stubGlobal('fetch', fetchMock)

  await aiClient.steerAgent('session-id', 'Inspect this', [
    {
      type: 'image',
      name: 'clipboard.png',
      mime_type: 'image/png',
      data_base64: 'aW1hZ2U=',
    },
  ])

  expect(String(fetchMock.mock.calls[0]?.[0])).toContain('/agent/session-id/steer')
  expect(JSON.parse(String((fetchMock.mock.calls[0]?.[1] as RequestInit).body))).toEqual({
    raw_content: 'Inspect this',
    parts: [
      {
        type: 'image',
        name: 'clipboard.png',
        mime_type: 'image/png',
        data_base64: 'aW1hZ2U=',
      },
    ],
  })
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

it('loads object content through the unified file URL', async () => {
  const payload = new Uint8Array([37, 80, 68, 70])
  const fetchMock = vi.fn().mockResolvedValue(new Response(payload))
  vi.stubGlobal('fetch', fetchMock)

  const result = await assetClient.getUrlContent('/api/files/assets/static/asset-1.pdf')

  expect(new Uint8Array(result)).toEqual(payload)
  expect(fetchMock).toHaveBeenCalledWith('/api/files/assets/static/asset-1.pdf', { signal: undefined })
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
    .mockResolvedValueOnce(new Response(JSON.stringify({ max_message_images: 32, max_turn_iterations: 128, max_asset_size_bytes: 262144000, compaction_max_tokens: 800000, compaction_keep_recent_tokens: 64000 })))
    .mockResolvedValueOnce(new Response(JSON.stringify({ max_message_images: 48, max_turn_iterations: 64, max_asset_size_bytes: 134217728, compaction_max_tokens: 512000, compaction_keep_recent_tokens: 64000 })))
  vi.stubGlobal('fetch', fetchMock)

  expect(await settingsClient.get()).toEqual({ max_message_images: 32, max_turn_iterations: 128, max_asset_size_bytes: 262144000, compaction_max_tokens: 800000, compaction_keep_recent_tokens: 64000 })
  const update = { max_message_images: 48, max_turn_iterations: 64, max_asset_size_bytes: 134217728, compaction_max_tokens: 512000, compaction_keep_recent_tokens: 64000 }
  expect(await settingsClient.update(update)).toEqual({
    max_message_images: 48,
    max_turn_iterations: 64,
    max_asset_size_bytes: 134217728,
    compaction_max_tokens: 512000,
    compaction_keep_recent_tokens: 64000,
  })
  expect(fetchMock).toHaveBeenNthCalledWith(1, '/api/settings', expect.any(Object))
  expect(fetchMock.mock.calls[1]?.[1]).toMatchObject({
    method: 'PUT',
    body: JSON.stringify(update),
  })
})

it('loads model usage activity for the settings chart', async () => {
  const days = [{
    date: '2026-09-19',
    requests: 2,
    input_tokens: 100,
    output_tokens: 20,
    cache_read_tokens: 80,
    cache_write_tokens: 0,
    reasoning_tokens: 5,
    total_tokens: 120,
  }]
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(days)))
  vi.stubGlobal('fetch', fetchMock)

  expect(await settingsClient.getUsageActivity(30)).toEqual(days)
  expect(fetchMock).toHaveBeenCalledWith('/api/settings/usage-activity?days=30', expect.any(Object))
})

it('loads model usage activity grouped by provider model', async () => {
  const series = [{
    provider: 'deepseek',
    model: 'deepseek-flash',
    days: [{
      date: '2026-09-19',
      requests: 2,
      input_tokens: 100,
      output_tokens: 20,
      cache_read_tokens: 80,
      cache_write_tokens: 0,
      reasoning_tokens: 5,
      total_tokens: 120,
    }],
  }]
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(series)))
  vi.stubGlobal('fetch', fetchMock)

  expect(await settingsClient.getModelUsageActivity(30)).toEqual(series)
  expect(fetchMock).toHaveBeenCalledWith('/api/settings/model-usage-activity?days=30', expect.any(Object))
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

it('loads and updates the persisted shell approval mode for one session', async () => {
  const fetchMock = vi.fn()
    .mockResolvedValueOnce(new Response(JSON.stringify({ mode: 'review' })))
    .mockResolvedValueOnce(new Response(JSON.stringify({ mode: 'allow_all' })))
  vi.stubGlobal('fetch', fetchMock)

  expect(await aiClient.getAgentSessionShellApproval('session-7')).toEqual({ mode: 'review' })
  expect(await aiClient.updateAgentSessionShellApproval('session-7', 'allow_all')).toEqual({ mode: 'allow_all' })
  expect(fetchMock).toHaveBeenNthCalledWith(
    2,
    '/api/agent/sessions/session-7/shell-approval',
    expect.objectContaining({ method: 'PUT', body: JSON.stringify({ mode: 'allow_all' }) }),
  )
})

it('loads the latest context composition for a historical session', async () => {
  const composition = {
    system_prompt: 0.1,
    tool_prompt: 0.2,
    tool_output: 0.3,
    user: 0.15,
    assistant: 0.25,
  }
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(composition)))
  vi.stubGlobal('fetch', fetchMock)

  expect(await aiClient.getAgentSessionContextComposition('session-7')).toEqual(composition)
  expect(fetchMock).toHaveBeenCalledWith(
    '/api/agent/sessions/session-7/context-composition',
    expect.any(Object),
  )
})
