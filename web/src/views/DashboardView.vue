<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import CameraPanel from '../components/CameraPanel.vue'
import ChangePasswordPanel from '../components/ChangePasswordPanel.vue'
import PromptPanel from '../components/PromptPanel.vue'
import ClipsPanel from '../components/ClipsPanel.vue'
import LiveStream from '../components/LiveStream.vue'
import { useCamera } from '../composables/useCamera.js'
import { useAuth } from '../composables/useAuth.js'
import { useTheme } from '../composables/useTheme.js'

const router = useRouter()
const { cameraViewState, load: loadCamera } = useCamera()
const { logout } = useAuth()
const { theme, setTheme } = useTheme()

function toggleTheme() {
  setTheme(theme.value === 'light' ? 'dark' : 'light')
}

const menuOpen = ref(false)
const menuRef = ref(null)
const menuBtnRef = ref(null)
const profileMenuOpen = ref(false)
const profileMenuRef = ref(null)
const profileBtnRef = ref(null)
const cameraModalOpen = ref(false)
const passwordModalOpen = ref(false)
const promptModalOpen = ref(false)
const clipsModalOpen = ref(false)

function toggleMenu() {
  menuOpen.value = !menuOpen.value
  if (menuOpen.value) profileMenuOpen.value = false
}

function toggleProfileMenu() {
  profileMenuOpen.value = !profileMenuOpen.value
  if (profileMenuOpen.value) menuOpen.value = false
}

function closeMenu(e) {
  if (menuRef.value && !menuRef.value.contains(e.target) && !menuBtnRef.value.contains(e.target)) {
    menuOpen.value = false
  }
  if (profileMenuRef.value && !profileMenuRef.value.contains(e.target) && !profileBtnRef.value.contains(e.target)) {
    profileMenuOpen.value = false
  }
}

function openCameraModal() {
  menuOpen.value = false
  cameraModalOpen.value = true
}

function openPasswordModal() {
  profileMenuOpen.value = false
  passwordModalOpen.value = true
}

function openPromptModal() {
  menuOpen.value = false
  promptModalOpen.value = true
}

function openClipsModal() {
  menuOpen.value = false
  clipsModalOpen.value = true
}

let backdropMouseDown = false
function onBackdropMouseDown(e) {
  backdropMouseDown = e.target === e.currentTarget
}
function closeModal(e) {
  if (backdropMouseDown && e && e.target === e.currentTarget) {
    cameraModalOpen.value = false
    passwordModalOpen.value = false
    promptModalOpen.value = false
    clipsModalOpen.value = false
  }
  backdropMouseDown = false
}

onMounted(() => {
  document.addEventListener('click', closeMenu)
  loadCamera()
})
onBeforeUnmount(() => document.removeEventListener('click', closeMenu))

function handleLogout() {
  profileMenuOpen.value = false
  logout()
  router.push({ name: 'login' })
}
</script>

<template>
  <div class="header">
    <div class="header-left">
      <div class="header-actions">
        <div class="menu-wrapper">
          <button ref="menuBtnRef" class="menu-btn" @click="toggleMenu" aria-label="메뉴">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <line x1="3" y1="6" x2="21" y2="6"/>
              <line x1="3" y1="12" x2="21" y2="12"/>
              <line x1="3" y1="18" x2="21" y2="18"/>
            </svg>
          </button>
          <Transition name="dropdown">
            <div v-if="menuOpen" ref="menuRef" class="dropdown-menu">
              <button class="dropdown-item" @click="openCameraModal">카메라 설정</button>
              <button class="dropdown-item" @click="openPromptModal">프롬프트 설정</button>
              <button class="dropdown-item" @click="openClipsModal">녹화 클립</button>
              <button class="dropdown-item" @click="toggleTheme">테마 변경</button>
            </div>
          </Transition>
        </div>
      </div>
      <img :src="theme === 'dark' ? '/banner-dark-theme.png' : '/banner-light-theme.png'" alt="Babycat" class="header-logo" />
    </div>
    <div class="header-right">
      <div class="menu-wrapper">
        <button ref="profileBtnRef" class="profile-btn" @click="toggleProfileMenu" aria-label="프로필">
          <img src="/user_profile.svg" alt="" class="profile-icon" />
        </button>
        <Transition name="dropdown">
          <div v-if="profileMenuOpen" ref="profileMenuRef" class="dropdown-menu dropdown-menu-right">
            <button class="dropdown-item" @click="openPasswordModal">비밀번호 변경</button>
            <button class="dropdown-item danger" @click="handleLogout">로그아웃</button>
          </div>
        </Transition>
      </div>
    </div>
  </div>
  <div class="main">
    <div class="video-area">
      <LiveStream v-if="cameraViewState !== 'unconfigured'" />
      <div v-else class="empty-state">
        <p>카메라가 설정되지 않았습니다. 메뉴에서 카메라 설정을 완료하세요.</p>
      </div>
    </div>
  </div>

  <!-- @claude Camera Profile Modal -->
  <Transition name="modal">
    <div v-if="cameraModalOpen" class="modal-backdrop" @mousedown="onBackdropMouseDown" @click="closeModal">
      <div class="modal-content">
        <div class="modal-header">
          <span class="modal-title">카메라 설정</span>
          <button class="modal-close" @click="cameraModalOpen = false">&times;</button>
        </div>
        <div class="modal-body">
          <CameraPanel @close="cameraModalOpen = false" />
        </div>
      </div>
    </div>
  </Transition>

  <!-- @claude Change Password Modal -->
  <Transition name="modal">
    <div v-if="passwordModalOpen" class="modal-backdrop" @mousedown="onBackdropMouseDown" @click="closeModal">
      <div class="modal-content">
        <div class="modal-header">
          <span class="modal-title">비밀번호 변경</span>
          <button class="modal-close" @click="passwordModalOpen = false">&times;</button>
        </div>
        <div class="modal-body">
          <ChangePasswordPanel @close="passwordModalOpen = false" />
        </div>
      </div>
    </div>
  </Transition>

  <!-- @claude Clips Modal -->
  <Transition name="modal">
    <div v-if="clipsModalOpen" class="modal-backdrop" @mousedown="onBackdropMouseDown" @click="closeModal">
      <div class="modal-content clips-modal">
        <div class="modal-header">
          <span class="modal-title">녹화 클립</span>
          <button class="modal-close" @click="clipsModalOpen = false">&times;</button>
        </div>
        <div class="modal-body clips-modal-body">
          <ClipsPanel />
        </div>
      </div>
    </div>
  </Transition>

  <!-- @claude Prompt Settings Modal -->
  <Transition name="modal">
    <div v-if="promptModalOpen" class="modal-backdrop" @mousedown="onBackdropMouseDown" @click="closeModal">
      <div class="modal-content">
        <div class="modal-header">
          <span class="modal-title">프롬프트 설정</span>
          <button class="modal-close" @click="promptModalOpen = false">&times;</button>
        </div>
        <div class="modal-body">
          <PromptPanel @close="promptModalOpen = false" />
        </div>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.header-left {
  display: flex;
  align-items: center;
  gap: 0.6rem;
}
.header-right {
  display: flex;
  align-items: center;
}
.header-logo {
  height: 32px;
  display: block;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 0.4rem;
}

.menu-wrapper {
  position: relative;
}
.menu-btn,
.profile-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border: none;
  color: var(--text-2);
  cursor: pointer;
  padding: 0;
  transition: background 0.15s, color 0.15s, filter 0.15s;
}
.menu-btn {
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: transparent;
}
.menu-btn:hover {
  background: var(--bg-surface-hover);
}
.profile-btn {
  border-radius: 50%;
  background: transparent;
  overflow: hidden;
  padding: 0;
}
.profile-btn:hover {
  filter: brightness(0.95);
}
.profile-icon {
  display: block;
  width: 100%;
  height: 100%;
}

.dropdown-menu {
  position: absolute;
  top: calc(100% + 6px);
  left: 0;
  min-width: 140px;
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: var(--shadow-md);
  padding: 4px 0;
  z-index: 100;
}
.dropdown-menu.dropdown-menu-right {
  left: auto;
  right: 0;
}
.dropdown-item {
  display: block;
  width: 100%;
  padding: 0.45rem 0.85rem;
  border: none;
  background: none;
  color: var(--text-2);
  font-size: 0.8rem;
  font-weight: 500;
  text-align: left;
  cursor: pointer;
  transition: background 0.12s, color 0.12s;
}
.dropdown-item:hover {
  background: var(--bg-surface-hover);
}
.dropdown-item.danger:hover {
  background: var(--danger-bg);
  color: var(--danger);
}


.dropdown-enter-active,
.dropdown-leave-active {
  transition: opacity 0.15s, transform 0.15s;
}
.dropdown-enter-from,
.dropdown-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}

.empty-state {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-4);
  font-size: 14px;
}

/* @claude ── Modal ── */
.modal-backdrop {
  position: fixed;
  inset: 0;
  background: var(--overlay);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 200;
}
.modal-content {
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-lg);
  width: 90%;
  max-width: 420px;
  max-height: 85vh;
  overflow-y: auto;
}
.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px;
  border-bottom: 1px solid var(--border);
}
.modal-title {
  font-size: 14px;
  font-weight: 700;
  color: var(--text-1);
}
.modal-close {
  background: none;
  border: none;
  font-size: 20px;
  color: var(--text-3);
  cursor: pointer;
  line-height: 1;
  padding: 2px 6px;
  border-radius: var(--radius);
  transition: background 0.12s, color 0.12s;
}
.modal-close:hover {
  background: var(--bg-surface-hover);
  color: var(--text-1);
}
.modal-body {
  padding: 16px;
}

.clips-modal {
  width: 80vw;
  max-width: 80vw;
  height: 80vh;
  max-height: 80vh;
  display: flex;
  flex-direction: column;
}
.clips-modal-body {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.modal-enter-active,
.modal-leave-active {
  transition: opacity 0.2s;
}
.modal-enter-from,
.modal-leave-to {
  opacity: 0;
}
</style>
