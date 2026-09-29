import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  css: {
    // vue-devui ships a CSS bundle that contains legacy IE hacks like
    // `*zoom`, which lightningcss refuses to minify by default. Skipping
    // those rules is harmless in modern browsers.
    lightningcss: {
      errorRecovery: true,
    },
  },
  server: {
    port: 5173,
    proxy: {
      // Point this at the FastAPI backend to switch off the mock layer.
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    include: ['tests/**/*.spec.ts'],
  },
})