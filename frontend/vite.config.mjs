import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  build: {
    outDir: '../backend/zett/static',
    emptyOutDir: true,
  },
  server: {
    port: 5173,
  },
})
