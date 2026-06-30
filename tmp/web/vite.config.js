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
    // @claude No dev proxy: the browser reaches app/api/MediaMTX directly at the
    // @claude host resolved in src/endpoints.js (entered on the login page). This
    // @claude keeps web/ deployable on a separate host — do not add a proxy back.
  },
})
