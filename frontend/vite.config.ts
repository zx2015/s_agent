import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'
import { readdirSync } from 'node:fs'

const matechatRoot = fileURLToPath(
  new URL('./node_modules/@matechat/core', import.meta.url),
)

// @matechat/core ships only a `module` field (no `exports` map), and its
// subpackages re-import each other as bare *directory* specifiers (e.g.
// `import ... from '@matechat/core/Locale'`). Vite's browser bundling
// resolves that leniently, but vitest executes source through Node's
// stricter ESM resolver, which refuses extension-less directory imports.
// Aliasing every subpackage straight to its `index.js` sidesteps that
// mismatch for dev, build, and test alike, without hand-maintaining the
// list as the package adds components.
const matechatSubpathAliases = Object.fromEntries(
  readdirSync(matechatRoot, { withFileTypes: true })
    .filter((entry) => entry.isDirectory() && entry.name !== 'node_modules')
    .map((entry) => [
      `@matechat/core/${entry.name}`,
      `${matechatRoot}/${entry.name}/index.js`,
    ]),
)

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
      ...matechatSubpathAliases,
      '@matechat/core': `${matechatRoot}/mate-chat.js`,
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