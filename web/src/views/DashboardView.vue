<script setup>
import { useRouter } from 'vue-router'
import CameraPanel from '../components/CameraPanel.vue'
import LiveStream from '../components/LiveStream.vue'
import ThemeToggle from '../components/ThemeToggle.vue'
import { useCamera } from '../composables/useCamera.js'
import { useAuth } from '../composables/useAuth.js'

const router = useRouter()
const { configured, connecting } = useCamera()
const { logout } = useAuth()

function handleLogout() {
  logout()
  router.push({ name: 'login' })
}
</script>

<template>
  <div class="header">
    <span class="header-title">Babycat</span>
    <div class="header-actions">
      <ThemeToggle />
      <button class="header-btn" @click="router.push({ name: 'change-password' })">비밀번호 변경</button>
      <button class="header-btn danger" @click="handleLogout">로그아웃</button>
    </div>
  </div>
  <div class="main">
    <div class="video-area">
      <LiveStream v-if="configured || connecting" />
      <div v-else class="empty-state">
        <p>카메라가 설정되지 않았습니다. 카메라를 설정하세요.</p>
      </div>
    </div>
    <div class="dash">
      <CameraPanel />
    </div>
  </div>
</template>

<style scoped>
.header-actions {
  display: flex;
  gap: 0.4rem;
}
.header-btn {
  font-size: 0.75rem;
  font-weight: 600;
  padding: 0.3rem 0.75rem;
  border: 1px solid var(--border-input);
  border-radius: var(--radius);
  background: var(--bg-surface);
  color: var(--text-2);
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}
.header-btn:hover {
  background: var(--bg-surface-hover);
}
.header-btn.danger:hover {
  background: var(--danger-bg);
  color: var(--danger);
  border-color: var(--danger-border);
}

.empty-state {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-4);
  font-size: 14px;
}
</style>
