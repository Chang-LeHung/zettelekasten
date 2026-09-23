// @vitest-environment jsdom
import { createApp, h, nextTick } from 'vue'
import { afterEach, expect, it, vi } from 'vitest'
import type { Channel, ChannelPluginInfo } from '../api/types'

const mocks = vi.hoisted(() => ({
  list: vi.fn(),
  plugins: vi.fn(),
  update: vi.fn(),
  delete: vi.fn(),
  startLogin: vi.fn(),
  pollLogin: vi.fn(),
  listProviders: vi.fn(),
}))

vi.mock('../api/client', () => ({
  channelClient: {
    list: mocks.list,
    plugins: mocks.plugins,
    update: mocks.update,
    delete: mocks.delete,
    startLogin: mocks.startLogin,
    pollLogin: mocks.pollLogin,
  },
  aiClient: {
    listProviders: mocks.listProviders,
  },
}))

import ChannelsView from './ChannelsView.vue'

const provider = {
  id: 'provider-1',
  name: 'Local model',
  provider: 'openai_compatible',
  model: 'test-model',
  base_url: null,
  api_key_configured: true,
  enabled: true,
  temperature: 0.2,
  response: false,
  created_at: '',
  updated_at: '',
}

const channel: Channel = {
  id: 'channel-1',
  name: 'Demo bot',
  channel_type: 'demo',
  provider_id: 'provider-1',
  enabled: true,
  reasoning_effort: 'medium',
  allow_coding: false,
  config: {},
  secret_keys: ['bot_token'],
  created_at: '2026-09-23T00:00:00Z',
  updated_at: '2026-09-23T00:00:00Z',
}

const twoPlugins: ChannelPluginInfo[] = [
  { channel_type: 'demo', label: 'Demo IM' },
  { channel_type: 'wechat', label: 'WeChat' },
]

function mountView(plugins: ChannelPluginInfo[], channels: Channel[] = [channel]) {
  mocks.list.mockResolvedValue(channels)
  mocks.plugins.mockResolvedValue(plugins)
  mocks.listProviders.mockResolvedValue([provider])
  mocks.startLogin.mockResolvedValue({
    id: 'login-1',
    channel_type: plugins[0]!.channel_type,
    provider_id: 'provider-1',
    name: null,
    status: 'pending',
    qr_url: null,
    qr_data_url: 'data:image/svg+xml;base64,abc',
    message: null,
    channel_id: null,
    expires_at: '2026-09-23T00:05:00Z',
    created_at: '2026-09-23T00:00:00Z',
    updated_at: '2026-09-23T00:00:00Z',
  })
  mocks.pollLogin.mockResolvedValue({
    id: 'login-1',
    channel_type: plugins[0]!.channel_type,
    provider_id: 'provider-1',
    name: null,
    status: 'pending',
    qr_url: null,
    qr_data_url: 'data:image/svg+xml;base64,abc',
    message: null,
    channel_id: null,
    expires_at: '2026-09-23T00:05:00Z',
    created_at: '2026-09-23T00:00:00Z',
    updated_at: '2026-09-23T00:00:00Z',
  })
  const host = document.createElement('div')
  document.body.append(host)
  const app = createApp({ render: () => h(ChannelsView) })
  app.mount(host)
  return { host, app }
}

function openSetupModal(host: HTMLElement): void {
  host.querySelector<HTMLButtonElement>('.channel-topbar-actions .primary-action')!.click()
}

afterEach(() => {
  for (const mock of Object.values(mocks)) mock.mockReset()
  document.body.innerHTML = ''
})

it('lists every installed plugin and sends the picked platform', async () => {
  const { host, app } = mountView(twoPlugins)
  try {
    await vi.waitFor(() => expect(host.textContent).toContain('Demo IM'))
    expect(host.textContent).toContain('Connect a chat platform')

    openSetupModal(host)
    await nextTick()
    const select = document.body.querySelector<HTMLSelectElement>('.setup-modal select')!
    expect([...select.options].map((option) => option.textContent?.trim())).toEqual(['Demo IM', 'WeChat'])

    select.value = 'wechat'
    select.dispatchEvent(new Event('change', { bubbles: true }))
    document.body.querySelector<HTMLFormElement>('.setup-modal')!.dispatchEvent(
      new Event('submit', { bubbles: true, cancelable: true }),
    )

    await vi.waitFor(() => expect(mocks.startLogin).toHaveBeenCalledWith(expect.objectContaining({
      channel_type: 'wechat',
      provider_id: 'provider-1',
    })))
  } finally {
    app.unmount()
    host.remove()
  }
})

it('hides the platform picker when only one plugin is installed', async () => {
  const { host, app } = mountView(
    [twoPlugins[1]!],
    [{ ...channel, channel_type: 'wechat', name: 'WeChat bot' }],
  )
  try {
    await vi.waitFor(() => expect(host.textContent).toContain('WeChat bot'))
    expect(host.textContent).toContain('WeChat')

    openSetupModal(host)
    await nextTick()

    // Only the provider and reasoning selects remain once no picker is needed.
    expect(document.body.querySelectorAll('.setup-modal select')).toHaveLength(2)
  } finally {
    app.unmount()
    host.remove()
  }
})
