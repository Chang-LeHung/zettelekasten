/**
 * Build the panel and the service worker into `dist/`, and copy the manifest in.
 *
 * Chrome loads the built directory, so the manifest cannot live in `src` and the
 * service worker needs a stable file name: an extension's background script is
 * named by the manifest, not by a bundler's hash.
 */

import { copyFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

const root = fileURLToPath(new URL('.', import.meta.url))

export default defineConfig({
  // The panel imports the web app's presentation components, not its runtime.
  // Both trees must resolve a single Vue instance for slots/reactivity to work.
  resolve: { dedupe: ['vue'] },
  plugins: [
    vue(),
    {
      name: 'zett-copy-manifest',
      closeBundle() {
        copyFileSync(`${root}manifest.json`, `${root}dist/manifest.json`)
      },
    },
  ],
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    rollupOptions: {
      // The panel is an HTML entry so Vite injects its bundled script; the
      // service worker is a module the manifest names directly.
      input: {
        sidepanel: `${root}sidepanel.html`,
        background: `${root}src/background.ts`,
      },
      output: {
        entryFileNames: (chunk) => (chunk.name === 'background' ? 'background.js' : 'assets/[name]-[hash].js'),
        chunkFileNames: 'assets/[name]-[hash].js',
        assetFileNames: 'assets/[name]-[hash][extname]',
      },
    },
  },
})
