// @vitest-environment jsdom
import { createApp, h, nextTick } from 'vue'
import { afterEach, expect, it, vi } from 'vitest'
import { getDocument } from 'pdfjs-dist'
import { aiClient } from '../api/client'
import PdfThumbnail from './PdfThumbnail.vue'
import appSource from '../App.vue?raw'
import thumbnailSource from './PdfThumbnail.vue?raw'

vi.mock('pdfjs-dist', () => ({ GlobalWorkerOptions: {}, getDocument: vi.fn() }))
vi.mock('../api/client', () => ({
  aiClient: {
    getArtifactPdfContent: vi.fn(),
    getSessionAssetContent: vi.fn(),
  },
}))

afterEach(() => vi.restoreAllMocks())

it('fits an artifact PDF first page inside both card dimensions', async () => {
  vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockReturnValue(240)
  vi.spyOn(HTMLElement.prototype, 'clientHeight', 'get').mockReturnValue(120)
  vi.mocked(aiClient.getArtifactPdfContent).mockResolvedValue(new ArrayBuffer(8))
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
      asset: { id: 'artifact-1', session_id: 'session-1' },
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
    expect(aiClient.getArtifactPdfContent).toHaveBeenCalledWith('session-1', 'artifact-1', expect.any(AbortSignal))
    expect(aiClient.getSessionAssetContent).not.toHaveBeenCalled()
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
