import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { pdfAssets } from './pdf-assets.mjs'

export default defineConfig({
  plugins: [vue(), pdfAssets()],
  build: {
    outDir: '../backend/zett/static',
    emptyOutDir: true,
  },
  server: {
    port: 5173,
  },
})
