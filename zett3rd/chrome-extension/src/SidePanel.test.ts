// @vitest-environment jsdom
import { createApp, nextTick } from 'vue'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import SidePanel from './SidePanel.vue'
import { ZettClient, type StreamTurnOptions } from './api/zett-client'
import { BrowserBridgeClient } from './api/browser-bridge'
import { pageKey } from './chat/page-sessions'

let pageUrl = 'https://example.com'
vi.mock('./page/page-reader', () => ({
  readActivePage: vi.fn(async () => ({ title: 'Example page', url: pageUrl, text: 'Page text' })),
}))

const cleanups: Array<() => void> = []
let stored: Record<string, unknown>
let tabUrl: string
let sessionSequence: number
let options: StreamTurnOptions
let finish: (value: string) => void
let fail: (error: Error) => void

async function flush(): Promise<void> {
  for (let i = 0; i < 12; i++) await nextTick()
}

beforeEach(() => {
  history.replaceState({}, '', '/sidepanel.html?tabId=7&panelNonce=aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa')
  pageUrl = 'https://example.com'
  tabUrl = pageUrl
  stored = {}
  sessionSequence = 0
  vi.stubGlobal('chrome', {
    storage: { local: {
      get: vi.fn(async () => ({ ...stored })),
      set: vi.fn(async (values: Record<string, unknown>) => { Object.assign(stored, values) }),
      remove: vi.fn(async (key: string) => { delete stored[key] }),
    } },
    tabs: {
      get: vi.fn(async () => ({ id: 7, url: tabUrl })),
      sendMessage: vi.fn(async () => ({ ok: true, url: tabUrl })),
      onUpdated: { addListener: vi.fn(), removeListener: vi.fn() },
      create: vi.fn(),
    },
  })
  vi.spyOn(ZettClient.prototype, 'health').mockResolvedValue({ ok: true })
  vi.spyOn(ZettClient.prototype, 'startSession').mockImplementation(async () => ({ conversation_id: `test-session-${++sessionSequence}` }))
  vi.spyOn(ZettClient.prototype, 'session').mockResolvedValue({ messages: [] })
  vi.spyOn(ZettClient.prototype, 'listProviders').mockResolvedValue([{ id: 'p', name: 'Test', provider: 'test', model: 'test-model', enabled: true }])
  vi.spyOn(ZettClient.prototype, 'listArtifacts').mockResolvedValue([])
  vi.spyOn(ZettClient.prototype, 'runtimeSettings').mockResolvedValue({ compaction_max_tokens: 200000, max_message_images: 4 })
  vi.spyOn(ZettClient.prototype, 'steerAgent').mockResolvedValue({ accepted: true })
  vi.spyOn(ZettClient.prototype, 'emitAgentEvent').mockResolvedValue({ accepted: true })
  vi.spyOn(BrowserBridgeClient.prototype, 'connect').mockImplementation(async function (this: BrowserBridgeClient, _url: string, tabId: number) {
    this.tabId = tabId
    this.token = 't'.repeat(43)
  })
  vi.spyOn(BrowserBridgeClient.prototype, 'disconnect').mockImplementation(async function (this: BrowserBridgeClient) {
    this.token = undefined
    this.tabId = undefined
  })
  vi.spyOn(ZettClient.prototype, 'streamTurn').mockImplementation(value => {
    options = value
    return new Promise((resolve, reject) => { finish = resolve; fail = reject })
  })
})

afterEach(() => {
  cleanups.splice(0).forEach(cleanup => cleanup())
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  history.replaceState({}, '', '/')
})

async function mount(): Promise<HTMLElement> {
  return await mountPanel().then(result => result.host)
}

async function mountPanel(): Promise<{ host: HTMLElement; close: () => void }> {
  const host = document.createElement('div')
  document.body.append(host)
  const app = createApp(SidePanel)
  app.mount(host)
  let closed = false
  const close = () => {
    if (closed) return
    closed = true
    app.unmount()
    host.remove()
  }
  cleanups.push(close)
  await vi.waitFor(() => {
    expect(host.querySelector('.model-trigger')?.textContent).toContain('test-model')
    expect(host.querySelector<HTMLButtonElement>('.send-button')).not.toBeNull()
    expect(host.querySelector<HTMLButtonElement>('.send-button')?.disabled).toBe(true)
    expect(Object.keys(stored).some(key => key.startsWith('pageSession:'))).toBe(true)
  })
  await flush()
  return { host, close }
}

async function send(host: HTMLElement): Promise<void> {
  const input = host.querySelector('textarea')!
  input.value = 'Read this page'
  input.dispatchEvent(new Event('input', { bubbles: true }))
  await nextTick()
  input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }))
  await nextTick()
}

it('opens the More menu on hover and closes composer menus on leave or outside press', async () => {
  const host = await mount()
  const modelPicker = host.querySelector<HTMLElement>('.picker')!
  host.querySelector<HTMLButtonElement>('.model-trigger')!.click()
  await nextTick()
  const modelPopover = host.querySelector('.model-popover')!
  expect(modelPopover).not.toBeNull()
  // The menu is inside the trigger's own hover region, so reaching it never
  // crosses a gap and the close can stay immediate.
  expect(modelPicker.contains(modelPopover)).toBe(true)
  modelPicker.dispatchEvent(new Event('pointerleave'))
  await nextTick()
  expect(host.querySelector('.model-popover')).toBeNull()
  // Hovering the trigger shows what a click shows; leaving closes it again.
  const moreMenu = host.querySelector<HTMLElement>('.more-menu')!
  moreMenu.dispatchEvent(new Event('pointerenter'))
  await nextTick()
  expect(host.querySelector('.more-popover')).not.toBeNull()
  moreMenu.dispatchEvent(new Event('pointerleave'))
  await nextTick()
  expect(host.querySelector('.more-popover')).toBeNull()
  host.querySelector<HTMLButtonElement>('.more-trigger')!.click()
  await nextTick()
  expect(host.querySelector('.more-popover')).not.toBeNull()
  host.querySelector('.chat-title strong')!.dispatchEvent(new Event('pointerdown', { bubbles: true, cancelable: true }))
  await nextTick()
  expect(host.querySelector('.more-popover')).toBeNull()
})

it('reports context compaction while the run organizes its history', async () => {
  const host = await mount()
  await send(host)
  options.onEvent?.({ id: 'compaction-1', type: 'compaction', activity: { state: 'started', content: '', reasoning: '' } })
  await nextTick()
  expect(host.querySelector('.turn-execution-copy strong')?.textContent).toBe('Organizing conversation context')
  options.onEvent?.({ id: 'compaction-2', type: 'compaction', activity: { state: 'completed', applied: true, content: 'Summary', reasoning: '' } })
  await nextTick()
  expect(host.querySelector('.turn-execution-copy strong')?.textContent).toBe('Thinking through your request')
  expect(host.textContent).toContain('Context compaction')
  finish('')
  await flush()
})

/** Type into the composer and press Enter, whatever the turn state is. */
async function enter(host: HTMLElement, text: string): Promise<void> {
  const input = host.querySelector('textarea')!
  input.value = text
  input.dispatchEvent(new Event('input', { bubbles: true }))
  await nextTick()
  input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }))
  await nextTick()
}

it('queues a follow-up while the turn runs and sends it when the turn ends', async () => {
  const host = await mount()
  await send(host)
  await enter(host, 'Then check the second page')
  expect(host.querySelector('.queued-followup p')?.textContent).toBe('Then check the second page')
  expect(host.querySelector('textarea')!.value).toBe('')
  const firstTurn = options
  finish('Answer')
  await flush()
  expect(options).not.toBe(firstTurn)
  expect(options.text).toBe('Then check the second page')
  expect(host.querySelector('.queued-followup')).toBeNull()
  finish('')
  await flush()
})

it('steers the running turn with a queued follow-up and marks it waiting', async () => {
  const host = await mount()
  await send(host)
  await enter(host, 'Use the short version')
  host.querySelector<HTMLButtonElement>('.queued-followup-steer')!.click()
  await flush()
  expect(vi.mocked(ZettClient.prototype.steerAgent)).toHaveBeenCalledWith('test-session-1', 'Use the short version')
  expect(host.querySelector('.queued-followup')).toBeNull()
  const prompts = [...host.querySelectorAll('.turn.user')]
  expect(prompts.at(-1)?.textContent).toContain('Use the short version')
  expect(prompts.at(-1)?.textContent).toContain('Will respond after the current tool call or turn finishes.')
  finish('')
  await flush()
  expect(host.querySelector('.steering-pending')).toBeNull()
})

it('shows a steering message another client injected into the running turn', async () => {
  const host = await mount()
  await send(host)
  options.onSteering?.({ content: 'Stop and explain first', parts: [] })
  await nextTick()
  expect(host.textContent).toContain('Stop and explain first')
  finish('')
  await flush()
})

it('drops queued follow-ups when the running turn is stopped', async () => {
  const host = await mount()
  await send(host)
  await enter(host, 'Never sent')
  host.querySelector<HTMLButtonElement>('[aria-label="Stop generation"]')!.click()
  await nextTick()
  expect(host.querySelector('.queued-followup')).toBeNull()
  fail(new DOMException('Aborted', 'AbortError'))
  await flush()
  expect(vi.mocked(ZettClient.prototype.streamTurn)).toHaveBeenCalledTimes(1)
})

it('answers an ask_user question so a suspended turn can continue', async () => {
  const host = await mount()
  await send(host)
  options.onCustom?.({ name: 'ask_user', payload: {
    tool_call_id: 'call-7',
    question: 'Which reply should I post?',
    options: ['Short', 'Long'],
    allow_multiple: false,
    response_event: 'ask_user_response',
  } })
  await nextTick()
  expect(host.querySelector('.ask-user h3')?.textContent).toBe('Which reply should I post?')
  expect(host.querySelector('.turn-execution-copy strong')?.textContent).toBe('Waiting for your answer')
  const choices = [...host.querySelectorAll<HTMLInputElement>('.ask-choice input[type="radio"]')]
  choices[0].dispatchEvent(new Event('change', { bubbles: true }))
  await nextTick()
  expect(host.querySelectorAll('.ask-choice.selected')).toHaveLength(1)
  host.querySelector<HTMLButtonElement>('.ask-submit')!.click()
  await flush()
  expect(vi.mocked(ZettClient.prototype.emitAgentEvent)).toHaveBeenCalledWith('test-session-1', 'ask_user_response', {
    session_id: 'test-session-1',
    tool_call_id: 'call-7',
    answer: 'Short',
    parts: [],
  })
  expect(host.querySelector('.ask-user')).toBeNull()
  finish('')
  await flush()
})

it('takes a typed ask_user answer and keeps later questions queued', async () => {
  const host = await mount()
  await send(host)
  options.onCustom?.({ name: 'ask_user', payload: {
    tool_call_id: 'first', question: 'First?', options: [], allow_multiple: false, response_event: 'ask_user_response',
  } })
  options.onCustom?.({ name: 'ask_user', payload: {
    tool_call_id: 'second', question: 'Second?', options: ['Yes'], allow_multiple: true, response_event: 'ask_user_response',
  } })
  await nextTick()
  expect(host.querySelector('.ask-user header small')?.textContent).toContain('1 more waiting')
  const input = host.querySelector<HTMLInputElement>('.ask-choice.custom input')!
  input.value = 'Drafted answer'
  input.dispatchEvent(new Event('input', { bubbles: true }))
  await nextTick()
  host.querySelector<HTMLButtonElement>('.ask-submit')!.click()
  await flush()
  expect(vi.mocked(ZettClient.prototype.emitAgentEvent)).toHaveBeenCalledWith('test-session-1', 'ask_user_response', {
    session_id: 'test-session-1',
    tool_call_id: 'first',
    answer: 'Drafted answer',
    parts: [],
  })
  expect(host.querySelector('.ask-user h3')?.textContent).toBe('Second?')
  finish('')
  await flush()
})

it('drops a pending ask_user question when the turn is stopped', async () => {
  const host = await mount()
  await send(host)
  options.onCustom?.({ name: 'ask_user', payload: {
    tool_call_id: 'call-7', question: 'Still there?', options: [], allow_multiple: false, response_event: 'ask_user_response',
  } })
  await nextTick()
  expect(host.querySelector('.ask-user')).not.toBeNull()
  host.querySelector<HTMLButtonElement>('[aria-label="Stop generation"]')!.click()
  await nextTick()
  expect(host.querySelector('.ask-user')).toBeNull()
  fail(new DOMException('Aborted', 'AbortError'))
  await flush()
})

it('reports generation speed from the timed model step', async () => {
  const host = await mount()
  await send(host)
  vi.spyOn(performance, 'now').mockReturnValueOnce(1_000).mockReturnValueOnce(3_000)
  options.onModelStarted?.()
  options.onUsage?.({ input_tokens: 100, output_tokens: 40, cache_read_tokens: 0, cache_write_tokens: 0, reasoning_tokens: 0 })
  await nextTick()
  host.querySelector<HTMLButtonElement>('.more-trigger')!.click()
  await nextTick()
  expect(host.querySelector('.usage-details')?.textContent).toContain('Speed 20.0 tok/s')
  finish('')
  await flush()
})

it('removes the page bar, retains automatic page context, and clears on Enter before the response', async () => {
  const host = await mount()
  expect(host.querySelector('.page-strip')).toBeNull()
  expect(host.querySelector('.include-toggle')).toBeNull()
  expect(host.textContent).not.toContain('Example page')
  await send(host)
  expect(host.querySelector('textarea')!.value).toBe('')
  expect(options.text).toBe('Read this page')
  expect(options.browserToken).toBe('t'.repeat(43))
  expect(host.querySelector<HTMLDetailsElement>('.turn-execution')!.open).toBe(true)
  finish('')
  await flush()
})

it('uses expandable web tool rows and preserves their open state when a result arrives', async () => {
  const host = await mount()
  await send(host)
  options.onEvent?.({ id: 'thinking', type: 'reasoning', content: 'Inspect the page first.' })
  options.onEvent?.({ id: 'tool-1', type: 'tool', activity: { id: '1', name: 'run_shell', state: 'started', arguments: { command: 'echo hello' } } })
  await nextTick()
  const tool = host.querySelector<HTMLDetailsElement>('.tool-activity')!
  tool.querySelector('summary')!.click()
  await nextTick()
  expect(tool.open).toBe(true)
  expect(tool.textContent).toContain('echo hello')
  expect(tool.textContent).toContain('Waiting for result')
  options.onEvent?.({ id: 'tool-1', type: 'tool', activity: { id: '1', name: 'run_shell', state: 'succeeded', output: 'hello' } })
  options.onEvent?.({ id: 'answer', type: 'message', content: '**Final answer**' })
  await nextTick()
  expect(host.querySelectorAll('.tool-activity')).toHaveLength(1)
  expect(tool.open).toBe(true)
  expect(tool.classList.contains('succeeded')).toBe(true)
  expect(tool.textContent).toContain('echo hello')
  expect(tool.textContent).toContain('hello')
  finish('Final answer')
  await flush()
  const execution = host.querySelector<HTMLDetailsElement>('.turn-execution')!
  expect(execution.open).toBe(false)
  execution.querySelector('summary')!.click()
  await nextTick()
  expect(execution.open).toBe(true)
  const reasoning = host.querySelector<HTMLDetailsElement>('.reasoning-panel')!
  reasoning.querySelector('summary')!.click()
  expect(reasoning.open).toBe(true)
  expect(reasoning.textContent).toContain('Inspect the page first.')
  expect(host.querySelector('.turn-response strong')?.textContent).toBe('Final answer')
})

it('keeps a manually collapsed running turn collapsed and preserves text typed for the next turn', async () => {
  const host = await mount()
  await send(host)
  const execution = host.querySelector<HTMLDetailsElement>('.turn-execution')!
  execution.querySelector('summary')!.click()
  await nextTick()
  expect(execution.open).toBe(false)
  const input = host.querySelector('textarea')!
  input.value = 'Next question'
  input.dispatchEvent(new Event('input', { bubbles: true }))
  options.onEvent?.({ id: 'a', type: 'message', content: 'Answer' })
  finish('Answer')
  await flush()
  expect(input.value).toBe('Next question')
  expect(execution.open).toBe(false)
})

it('retains failed-turn details and stops showing abandoned tools as running', async () => {
  const host = await mount()
  await send(host)
  options.onEvent?.({ id: 'tool-1', type: 'tool', activity: { id: '1', name: 'run_shell', state: 'started', arguments: { command: 'echo hello' } } })
  fail(new Error('Connection lost'))
  await flush()
  expect(host.querySelector('.tool-activity.cancelled')).not.toBeNull()
  expect(host.querySelector('[role="alert"]')?.textContent).toBe('Connection lost')
  host.querySelector<HTMLElement>('.turn-execution > summary')!.click()
  await nextTick()
  expect(host.querySelector<HTMLDetailsElement>('.turn-execution')!.open).toBe(true)
  expect(host.textContent).toContain('echo hello')
})

it('keeps connection visible and moves usage details into the compact menu', async () => {
  const host = await mount()
  expect(host.querySelector('.model-trigger .picker-label')?.textContent).toBe('Test')
  host.querySelector<HTMLButtonElement>('.model-trigger')!.click()
  await nextTick()
  expect(host.querySelector('.model-option')?.textContent).toContain('Test')
  host.querySelector<HTMLButtonElement>('.model-option')!.click()
  await send(host)
  options.onUsage?.({ input_tokens: 40000, output_tokens: 1000, cache_read_tokens: 30000, cache_write_tokens: 0, reasoning_tokens: 50 })
  options.onComposition?.({ system_prompt: .2, tool_prompt: .2, tool_output: .2, user: .2, assistant: .2 })
  await nextTick()
  expect(host.querySelector('.usage-details')).toBeNull()
  host.querySelector<HTMLButtonElement>('.more-trigger')!.click()
  await nextTick()
  expect(host.querySelector('.usage-details')?.textContent).toContain('75.0%')
  expect(host.querySelector('.usage-details')?.textContent).toContain('21%')
  expect(host.querySelector('.more-popover')?.textContent).toContain('Disconnect page')
  expect(host.querySelector('.more-popover')?.textContent).toContain('Save all artifacts')
  expect(host.querySelector('.turn-execution-metrics')?.textContent).toContain('Cache 75%')
  finish('')
  await flush()
})

it('stops an in-flight turn, revokes browser consent, and keeps partial output and the next draft', async () => {
  const disconnect = vi.mocked(BrowserBridgeClient.prototype.disconnect)
  const host = await mount()
  await send(host)
  disconnect.mockClear()
  const signal = options.signal!
  expect(signal.aborted).toBe(false)
  options.onEvent?.({ id: 'a', type: 'message', content: 'Partial answer' })
  const input = host.querySelector('textarea')!
  input.value = 'Next question'
  input.dispatchEvent(new Event('input', { bubbles: true }))
  await nextTick()
  const stop = host.querySelector<HTMLButtonElement>('[aria-label="Stop generation"]')!
  expect(stop.disabled).toBe(false)
  stop.click()
  expect(signal.aborted).toBe(true)
  expect(disconnect).toHaveBeenCalledTimes(1)
  options.onEvent?.({ id: 'late', type: 'message', content: 'Late text that must not arrive' })
  fail(new DOMException('Aborted', 'AbortError'))
  await flush()
  expect(host.textContent).toContain('Partial answer')
  expect(host.textContent).not.toContain('Late text')
  expect(host.textContent).toContain('Stopped. Send a message to continue.')
  expect(host.querySelector('[role="alert"]')).toBeNull()
  expect(host.querySelector('.turn-execution.running')).toBeNull()
  expect(input.value).toBe('Next question')
  expect(host.querySelector<HTMLButtonElement>('[aria-label="Send"]')!.disabled).toBe(false)
  host.querySelector<HTMLButtonElement>('[aria-label="Send"]')!.click()
  await nextTick()
  expect(options.signal!.aborted).toBe(false)
  expect(options.signal).not.toBe(signal)
  finish('Next answer')
  await flush()
})

it('restores the same page after closing, while a different tab/page starts separate sessions', async () => {
  const first = await mountPanel()
  expect(pageKey('http://127.0.0.1:6280', 7, pageUrl)).not.toBeNull()
  expect(stored[pageKey('http://127.0.0.1:6280', 7, pageUrl)!]).toBe('test-session-1')
  await send(first.host)
  options.onEvent?.({ id: 'message', type: 'message', content: 'Page one answer' })
  finish('Page one answer')
  await flush()
  first.close()

  const restored = await mountPanel()
  expect(vi.mocked(ZettClient.prototype.session)).toHaveBeenCalledWith('test-session-1')
  expect(sessionSequence).toBe(1)
  expect(restored.host.querySelector('.chat-header')).not.toBeNull()
  restored.close()

  pageUrl = 'https://example.com/other'
  tabUrl = pageUrl
  const second = await mountPanel()
  expect(sessionSequence).toBe(2)
  expect(second.host.querySelector<HTMLButtonElement>('.send-button')?.disabled).toBe(true)
  second.close()

  history.replaceState({}, '', '/sidepanel.html?tabId=8&panelNonce=bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb')
  vi.mocked(chrome.tabs.get).mockResolvedValue({ id: 8, url: pageUrl } as chrome.tabs.Tab)
  const third = await mountPanel()
  expect(sessionSequence).toBe(3)
  third.close()
})

it('follows the bottom when turns stream and when an existing page chat is restored', async () => {
  const first = await mountPanel()
  const thread = first.host.querySelector<HTMLElement>('.thread')!
  Object.defineProperty(thread, 'scrollHeight', { configurable: true, value: 700 })
  await send(first.host)
  await flush()
  expect(thread.scrollTop).toBe(700)
  Object.defineProperty(thread, 'scrollHeight', { configurable: true, value: 1200 })
  options.onEvent?.({ id: 'message', type: 'message', content: 'A streamed answer' })
  await flush()
  expect(thread.scrollTop).toBe(1200)
  finish('A streamed answer')
  await flush()
  first.close()

  // A restored transcript changes after the iframe mounts, so it must also
  // scroll into view without a user-generated wheel event.
  const session = vi.mocked(ZettClient.prototype.session)
  session.mockResolvedValueOnce({ messages: [
    {
      id: 'user', session_id: 'test-session-1', request_id: 'turn', sequence: 1,
      role: 'user', content: 'Ask', parts: [], attributes: {}, metadata: {}, tags: {},
    },
    {
      id: 'answer', session_id: 'test-session-1', request_id: 'turn', sequence: 2,
      role: 'assistant', content: 'Restored answer', parts: [], tool_calls: [], attributes: {}, metadata: {}, tags: {},
      input_tokens: 100, output_tokens: 20, cache_read_tokens: 50, cache_write_tokens: 0,
      reasoning_tokens: 0, duration_ns: 1_000_000,
    },
  ] as import('../../../frontend/src/api/types').AgentPersistedMessage[] })
  const second = await mountPanel()
  expect(second.host.textContent).toContain('Restored answer')
  expect(second.host.querySelector('.thread')).not.toBeNull()
  second.close()
})
