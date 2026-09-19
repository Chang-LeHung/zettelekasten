// @vitest-environment jsdom
import { createApp, h, nextTick, ref } from 'vue'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { getDocument } from 'pdfjs-dist'
import { assetClient } from '../api/client'
import PdfThumbnail from './PdfThumbnail.vue'
import appSource from '../App.vue?raw'
import thumbnailSource from './PdfThumbnail.vue?raw'

vi.mock('pdfjs-dist', () => ({ GlobalWorkerOptions: {}, getDocument: vi.fn() }))
vi.mock('../api/client', () => ({
  assetClient: {
    getUrlContent: vi.fn(),
  },
}))

const cleanups: Array<() => void> = []

beforeEach(() => vi.clearAllMocks())
afterEach(() => {
  cleanups.splice(0).forEach(cleanup => cleanup())
  vi.restoreAllMocks()
})

it('fits an artifact PDF first page inside both card dimensions', async () => {
  vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockReturnValue(240)
  vi.spyOn(HTMLElement.prototype, 'clientHeight', 'get').mockReturnValue(120)
  vi.mocked(assetClient.getUrlContent).mockResolvedValue(new ArrayBuffer(8))
  const render = vi.fn(() => ({ promise: Promise.resolve(), cancel: vi.fn() }))
  vi.mocked(getDocument).mockReturnValue({
    promise: Promise.resolve({
      getPage: vi.fn().mockResolvedValue({
        getViewport: ({ scale }: { scale: number }) => ({ width: 600 * scale, height: 800 * scale }),
        render,
      }),
    }),
    destroy: vi.fn().mockResolvedValue(undefined),
  } as never)

  const host = document.createElement('div')
  const app = createApp({
    render: () => h(PdfThumbnail, {
      asset: {
        id: 'artifact-1',
        session_id: 'session-1',
        content_url: '/api/files/artifacts/session-1/paper/paper.pdf',
      },
      artifact: true,
      fit: 'contain',
    }),
  })
  app.mount(host)
  try {
    await nextTick()
    await Promise.resolve()
    await Promise.resolve()
    await nextTick()
    const canvas = host.querySelector('canvas')!
    expect(assetClient.getUrlContent).toHaveBeenCalledWith(
      '/api/files/artifacts/session-1/paper/paper.pdf',
      expect.any(AbortSignal),
    )
    expect(canvas.style.width).toBe('90px')
    expect(canvas.style.height).toBe('120px')
    expect(Number.parseFloat(canvas.style.width)).toBeLessThanOrEqual(240)
    expect(Number.parseFloat(canvas.style.height)).toBeLessThanOrEqual(120)
  } finally {
    app.unmount()
  }
})

it('keeps the PDF preview constrained by both the thumbnail and card containers', () => {
  expect(thumbnailSource).toContain('max-width: 100%')
  expect(thumbnailSource).toContain('max-height: 100%')
  expect(appSource).toContain('class="library-pdf-thumbnail"')
  expect(appSource).toMatch(/\.library-pdf-thumbnail\s*\{[^}]*flex:\s*1 1 0;[^}]*min-height:\s*0;[^}]*overflow:\s*hidden;/u)
})

it('renders the first page of a global static PDF', async () => {
  vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockReturnValue(240)
  vi.spyOn(HTMLElement.prototype, 'clientHeight', 'get').mockReturnValue(120)
  vi.mocked(assetClient.getUrlContent).mockResolvedValue(new ArrayBuffer(8))
  vi.mocked(getDocument).mockReturnValue({
    promise: Promise.resolve({
      getPage: vi.fn().mockResolvedValue({
        getViewport: ({ scale }: { scale: number }) => ({ width: 60 * scale, height: 80 * scale }),
        render: vi.fn(() => ({ promise: Promise.resolve(), cancel: vi.fn() })),
      }),
    }),
    destroy: vi.fn().mockResolvedValue(undefined),
  } as never)

  const host = document.createElement('div')
  const app = createApp({
    render: () => h(PdfThumbnail, {
      asset: {
        id: 'static-1',
        name: 'paper.pdf',
        mime_type: 'application/pdf',
        size_bytes: 8,
        sha256: 'hash',
        storage_path: 'assets/static/static-1.pdf',
        content_url: '/api/files/assets/static/static-1.pdf',
        metadata: {},
        created_at: '',
        updated_at: '',
      },
    }),
  })
  app.mount(host)
  try {
    await nextTick()
    await Promise.resolve()
    await Promise.resolve()
    await nextTick()
    expect(assetClient.getUrlContent).toHaveBeenCalledWith(
      '/api/files/assets/static/static-1.pdf',
      expect.any(AbortSignal),
    )
    expect(host.querySelector('canvas')).not.toBeNull()
  } finally {
    app.unmount()
  }
})

it('does not reload when the parent rerenders with an equivalent asset object', async () => {
  vi.mocked(assetClient.getUrlContent).mockResolvedValue(new ArrayBuffer(8))
  vi.mocked(getDocument).mockReturnValue({
    promise: Promise.resolve({
      getPage: vi.fn().mockResolvedValue({
        getViewport: ({ scale }: { scale: number }) => ({ width: 60 * scale, height: 80 * scale }),
        render: vi.fn(() => ({ promise: Promise.resolve(), cancel: vi.fn() })),
      }),
    }),
    destroy: vi.fn().mockResolvedValue(undefined),
  } as never)
  const unrelated = ref(0)
  const host = document.createElement('div')
  const app = createApp({
    render: () => h('div', [
      h(PdfThumbnail, {
        asset: {
          id: 'artifact-1',
          session_id: 'session-1',
          content_url: '/api/files/artifacts/session-1/paper/paper.pdf',
        },
        artifact: true,
      }),
      h('span', String(unrelated.value)),
    ]),
  })
  app.mount(host)
  cleanups.push(() => { app.unmount(); host.remove() })

  await nextTick()
  await Promise.resolve()
  await Promise.resolve()
  expect(assetClient.getUrlContent).toHaveBeenCalledTimes(1)

  unrelated.value += 1
  await nextTick()
  expect(assetClient.getUrlContent).toHaveBeenCalledTimes(1)
})
