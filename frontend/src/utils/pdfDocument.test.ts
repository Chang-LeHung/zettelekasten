import { expect, it } from 'vitest'
import { pdfDocumentOptions } from './pdfDocument'

it('provides local packed CMaps and font resources to every PDF renderer', () => {
  const bytes = new ArrayBuffer(8)
  const options = pdfDocumentOptions(bytes)
  expect(options.data).toEqual(new Uint8Array(bytes))
  expect(options).toMatchObject({
    cMapUrl: '/pdfjs/cmaps/', cMapPacked: true,
    standardFontDataUrl: '/pdfjs/standard_fonts/',
    wasmUrl: '/pdfjs/wasm/', iccUrl: '/pdfjs/iccs/', useSystemFonts: true,
  })
})
