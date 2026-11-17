import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vite'

/** The page-world probe is injected as a classic script into the page itself,
 * so it is bundled on its own, without the panel's module graph.
 */
export default defineConfig({
  build: {
    outDir: 'dist',
    emptyOutDir: false,
    lib: {
      entry: fileURLToPath(new URL('./src/page/page-probe.ts', import.meta.url)),
      name: 'ZettPageProbe',
      formats: ['iife'],
      fileName: () => 'page-probe.js',
    },
  },
})
