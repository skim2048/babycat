import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    // Vite 5.0.12+/6은 기본적으로 localhost 외 Host 헤더를 차단 (CVE-2025-30208).
    // 사설망(Jetson IP)에서 접속하는 구성이므로 모든 호스트 허용.
    allowedHosts: true,
    proxy: {
      '/api':     'http://api:8000',
      '/clips':   'http://api:8000',   // 클립 목록/다운로드/삭제는 api 단일화 (Phase 4)
      '/events':  'http://app:8080',   // SSE — query token 인증
      '/prompt':  'http://app:8080',
      '/ptz':     'http://app:8080',
      '/camera':  'http://app:8080',
    },
  },
})
