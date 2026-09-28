// @vitest-environment jsdom
import { createApp, nextTick, ref } from 'vue'
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
    tags: [],
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
    tags: [],
    created_at: '2026-09-19T12:00:00Z',
    updated_at: '2026-09-19T12:00:00Z',
  }])
  const host = await mountView()
  await nextTick()

  await vi.waitFor(() => expect(host.querySelector('[data-testid="pdf-thumbnail"]')).not.toBeNull())
  expect(host.textContent).toContain('Sep 19, 2026')
})

it('shows the tags a file carries and hands a dragged card to the sidebar', async () => {
  mocks.list.mockResolvedValue([{
    id: 'asset-tagged',
    name: 'notes.txt',
    mime_type: 'text/plain',
    size_bytes: 5,
    sha256: 'hash-tagged',
    content_url: '/api/files/assets/static/asset-tagged.txt',
    metadata: {},
    tags: [{ id: 'tag-1', path: 'Engineering/Python', name: 'Python' }],
    created_at: '2026-09-19T00:00:00Z',
    updated_at: '2026-09-19T00:00:00Z',
  }])
  const host = document.createElement('div')
  document.body.append(host)
  const dragged: unknown[] = []
  const app = createApp(StaticAssetsView, {
    onDragStart: (asset: unknown) => dragged.push(asset),
  })
  app.mount(host)
  cleanups.push(() => { app.unmount(); host.remove() })
  await nextTick()
  await Promise.resolve()
  await nextTick()

  const card = host.querySelector('.static-asset-card')
  expect(card?.getAttribute('draggable')).toBe('true')
  expect(host.querySelector('.static-asset-tags')?.textContent).toContain('Engineering/Python')

  const transfer = { effectAllowed: '', setData: vi.fn() }
  const event = new Event('dragstart') as DragEvent
  Object.defineProperty(event, 'dataTransfer', { value: transfer })
  card?.dispatchEvent(event)

  expect(dragged).toHaveLength(1)
  expect(transfer.setData).toHaveBeenCalledWith('application/x-zett-asset-id', 'asset-tagged')
})

it('lists only the selected collection and reloads when it changes', async () => {
  mocks.list.mockResolvedValue([])
  const host = document.createElement('div')
  document.body.append(host)
  const cleared: unknown[] = []
  const tagId = ref<string | null>('tag-projects')
  const app = createApp({
    components: { StaticAssetsView },
    setup: () => ({ tagId, cleared }),
    template: `<StaticAssetsView
      :tag-id="tagId"
      :tag-path="tagId ? 'Projects/Zett' : null"
      @clear-tag="cleared.push(true)"
    />`,
  })
  app.mount(host)
  cleanups.push(() => { app.unmount(); host.remove() })
  await nextTick()
  await Promise.resolve()
  await nextTick()

  // The grid asks for that collection, and says which one it is showing.
  expect(mocks.list).toHaveBeenCalledWith('', 500, 0, 'tag-projects')
  expect(host.textContent).toContain('Projects/Zett')
  expect(host.textContent).toContain('No files in this collection')

  host.querySelector<HTMLButtonElement>('.asset-collection-filter')?.click()
  expect(cleared).toHaveLength(1)

  tagId.value = 'tag-python'
  await nextTick()
  await Promise.resolve()
  await nextTick()
  expect(mocks.list).toHaveBeenLastCalledWith('', 500, 0, 'tag-python')
})
