import { readFileSync, readdirSync } from 'node:fs'

// PDF.js requests these by their original names; hashed JS imports cannot serve
// its CMap/font lookups. Keep the resources local and identical in dev and builds.
export function pdfAssets() {
  const resources = new Map()
  for (const directory of ['cmaps', 'standard_fonts', 'wasm', 'iccs']) {
    const root = new URL(`./node_modules/pdfjs-dist/${directory}/`, import.meta.url)
    for (const name of readdirSync(root)) {
      resources.set(`pdfjs/${directory}/${name}`, new URL(name, root))
    }
  }
  let base = '/'
  return {
    name: 'local-pdfjs-resources',
    configResolved(config) { base = config.base },
    configureServer(server) {
      server.middlewares.use((request, response, next) => {
        const path = (request.url || '').split('?')[0]
        const key = path.startsWith(base) ? path.slice(base.length) : ''
        const source = resources.get(key)
        if (!source) return next()
        response.setHeader('Content-Type', key.endsWith('.wasm') ? 'application/wasm' : key.endsWith('.js') ? 'text/javascript' : 'application/octet-stream')
        response.end(readFileSync(source))
      })
    },
    generateBundle() {
      for (const [fileName, source] of resources) {
        this.emitFile({ type: 'asset', fileName, source: readFileSync(source) })
      }
    },
  }
}
