import type { DocumentInitParameters } from 'pdfjs-dist/types/src/display/api'

export function pdfDocumentOptions(bytes: ArrayBuffer): DocumentInitParameters {
  const root = `${import.meta.env.BASE_URL}pdfjs/`
  return {
    data: new Uint8Array(bytes),
    cMapUrl: `${root}cmaps/`,
    cMapPacked: true,
    standardFontDataUrl: `${root}standard_fonts/`,
    wasmUrl: `${root}wasm/`,
    iccUrl: `${root}iccs/`,
    useSystemFonts: true,
  }
}
