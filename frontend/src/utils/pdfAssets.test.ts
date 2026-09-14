import { expect, it, vi } from 'vitest'
import { pdfAssets } from '../../pdf-assets.mjs'

it('includes Chinese CMaps and fallback fonts in production assets', () => {
  const plugin = pdfAssets()
  const emitFile = vi.fn()
  plugin.generateBundle.call({ emitFile })
  const files = new Map(emitFile.mock.calls.map(([file]) => [file.fileName, file.source]))
  expect(files.get('pdfjs/cmaps/UniGB-UCS2-H.bcmap')?.byteLength).toBeGreaterThan(0)
  expect(files.get('pdfjs/cmaps/Adobe-GB1-UCS2.bcmap')?.byteLength).toBeGreaterThan(0)
  expect(files.get('pdfjs/standard_fonts/LiberationSans-Regular.ttf')?.byteLength).toBeGreaterThan(0)
})

it('serves the same resources in development under the configured base', () => {
  const plugin = pdfAssets()
  plugin.configResolved({ base: '/zett/' })
  const use = vi.fn()
  plugin.configureServer({ middlewares: { use } })
  const handler = use.mock.calls[0][0]
  const response = { setHeader: vi.fn(), end: vi.fn() }
  const next = vi.fn()
  handler({ url: '/zett/pdfjs/cmaps/UniGB-UCS2-H.bcmap' }, response, next)
  expect(response.end.mock.calls[0][0].byteLength).toBeGreaterThan(0)
  expect(next).not.toHaveBeenCalled()
  handler({ url: '/zett/pdfjs/../../package.json' }, response, next)
  expect(next).toHaveBeenCalledTimes(1)
})
