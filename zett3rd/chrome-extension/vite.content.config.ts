import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vite'

/** Chrome injects a classic script; bundle its dependencies into one IIFE,
 * independently of the panel's ES modules. Do not erase the panel build.
 */
export default defineConfig({
  build: {
    outDir: 'dist',
    emptyOutDir: false,
    lib: {
      entry: fileURLToPath(new URL('./src/page/content-script.ts', import.meta.url)),
      name: 'ZettDOMBridge',
      formats: ['iife'],
      fileName: () => 'content-script.js',
    },
  },
})
