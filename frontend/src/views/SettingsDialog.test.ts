// @vitest-environment jsdom
import { createApp, nextTick } from 'vue'
import { afterEach, expect, it, vi } from 'vitest'
import { i18nPlugin } from '../i18n'
import { ai, providers, selectedProviderId } from '../app/providers'
import { settingsOpen, settingsSection } from '../app/settings'
import SettingsDialog from './SettingsDialog.vue'

vi.mock('../api/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/client')>()),
  settingsClient: { get: vi.fn(), update: vi.fn() },
  aiClient: { listProviders: vi.fn().mockResolvedValue([]) },
}))

const cleanups: (() => void)[] = []
afterEach(() => {
  cleanups.splice(0).forEach((cleanup) => cleanup())
  settingsOpen.value = false
})

function mountDialog(): HTMLElement {
  const host = document.createElement('div')
  document.body.append(host)
  const app = createApp(SettingsDialog)
  app.use(i18nPlugin)
  app.mount(host)
  cleanups.push(() => { app.unmount(); host.remove(); document.body.querySelectorAll('.settings-backdrop').forEach((node) => node.remove()) })
  return document.body
}

it('opens a provider that has no temperature instead of failing to render', async () => {
  // A provider saved through the API without a temperature comes back as null, and the
  // dialog used to call toFixed on it, which blanked the whole application.
  providers.value = [{ id: 'p1', name: 'Local', provider: 'openai_compatible', model: 'm', enabled: true } as never]
  selectedProviderId.value = 'p1'
  ai.value = { name: 'Local', provider: 'openai_compatible', model: 'm', base_url: '', api_key: '', temperature: null as never, response: false, multimodal: true, web_search: false, web_search_name: null, enabled: true }
  settingsSection.value = 'providers'
  settingsOpen.value = true

  const body = mountDialog()
  await nextTick()

  const output = body.querySelector('.temperature-field output')
  expect(output).not.toBeNull()
  expect(output?.textContent).toBe('—')
})

it('shows a stored temperature with one decimal', async () => {
  ai.value = { ...ai.value, temperature: 0.25 }
  settingsSection.value = 'providers'
  settingsOpen.value = true
  const body = mountDialog()
  await nextTick()
  expect(body.querySelector('.temperature-field output')?.textContent).toBe('0.3')
})
