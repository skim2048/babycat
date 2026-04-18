import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    // @claude Vite 5.0.12+/6 block non-localhost Host headers by default (CVE-2025-30208).
    // @claude We serve from a private network (Jetson IP), so all hosts are allowed.
    allowedHosts: true,
    proxy: {
      '/api':     'http://api:8000',
      '/clips':   'http://api:8000',   // @claude Clip list / download / delete go through api (Phase 4).
      '/events':  'http://app:8080',   // @claude SSE — query-token auth.
      '/prompt':  'http://app:8080',
      '/ptz':     'http://app:8080',
      '/camera':  'http://app:8080',
      '/vlm':     'http://app:8080',
    },
  },
})
