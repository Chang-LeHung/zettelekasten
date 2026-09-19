// @vitest-environment jsdom
import { createApp, nextTick } from 'vue'
import { afterEach, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  list: vi.fn(),
  upload: vi.fn(),
  delete: vi.fn(),
}))

vi.mock('../api/client', () => ({ assetClient: mocks }))
vi.mock('./PdfThumbnail.vue', async () => {
  const { defineComponent } = await import('vue')
  return {
    default: defineComponent({ template: '<span data-testid="pdf-thumbnail" />' }),
  }
})

import StaticAssetsView from './StaticAssetsView.vue'

const cleanups: (() => void)[] = []
afterEach(() => {
  cleanups.splice(0).forEach(cleanup => cleanup())
  mocks.list.mockReset()
  mocks.upload.mockReset()
  mocks.delete.mockReset()
})

async function mountView() {
  const host = document.createElement('div')
  document.body.append(host)
  const app = createApp(StaticAssetsView)
  app.mount(host)
  cleanups.push(() => { app.unmount(); host.remove() })
  await nextTick()
  await Promise.resolve()
  await nextTick()
  return host
}

it('lists assets and uploads files pasted into the Assets view', async () => {
  const existing = {
    id: 'asset-1',
    name: 'notes.txt',
    mime_type: 'text/plain',
    size_bytes: 5,
    sha256: 'hash-1',
    content_url: '/api/files/assets/static/asset-1.png',
    metadata: {},
    created_at: '2026-09-19T00:00:00Z',
    updated_at: '2026-09-19T00:00:00Z',
  }
  const pasted = {
    ...existing,
    id: 'asset-2',
    name: 'clipboard.png',
    mime_type: 'image/png',
    sha256: 'hash-2',
    content_url: '/api/files/assets/static/asset-2.png',
  }
  mocks.list.mockResolvedValue([existing])
  mocks.upload.mockResolvedValue(pasted)
  const host = await mountView()

  expect(host.querySelectorAll('.static-asset-card')).toHaveLength(1)
  expect(host.textContent).toContain('notes.txt')

  const file = new File(['image'], 'clipboard.png', { type: 'image/png' })
  const event = new Event('paste') as ClipboardEvent
  Object.defineProperties(event, {
    clipboardData: {
      value: {
        items: [{ kind: 'file', getAsFile: () => file }],
      },
    },
  })
  window.dispatchEvent(event)
  await Promise.resolve()
  await nextTick()

  expect(mocks.upload).toHaveBeenCalledWith(file)
  expect(host.textContent).toContain('clipboard.png')
  expect(host.querySelector('.static-asset-card img')).not.toBeNull()
})

it('renders a PDF first-page thumbnail and uses English dates', async () => {
  mocks.list.mockResolvedValue([{
    id: 'asset-pdf',
    name: 'paper.pdf',
    mime_type: 'application/pdf',
    size_bytes: 1024,
    sha256: 'hash-pdf',
    content_url: '/api/files/assets/static/asset-pdf.pdf',
    metadata: {},
    created_at: '2026-09-19T12:00:00Z',
    updated_at: '2026-09-19T12:00:00Z',
  }])
  const host = await mountView()
  await nextTick()

  await vi.waitFor(() => expect(host.querySelector('[data-testid="pdf-thumbnail"]')).not.toBeNull())
  expect(host.textContent).toContain('Sep 19, 2026')
})
