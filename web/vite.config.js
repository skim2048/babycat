import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      '/stream': 'http://app:8080',
      '/events': 'http://app:8080',
      '/prompt': 'http://app:8080',
      '/ptz':    'http://app:8080',
      '/clips':  'http://app:8080',
      '/clip':   'http://app:8080',
    },
  },
})
