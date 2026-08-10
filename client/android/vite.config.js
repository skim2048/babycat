import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    host: '0.0.0.0',
    port: 5174,
    // @claude Vite 5.0.12+/6 block non-localhost Host headers by default (CVE-2025-30208).
    // @claude We serve from a private network (Jetson IP), so all hosts are allowed.
    allowedHosts: true,
    // @claude No dev proxy: the app reaches the backend at the host entered on
    // @claude the login page (src/endpoints.js). Inside Capacitor there is no
    // @claude same-origin backend at all, so the address field is mandatory.
  },
})
