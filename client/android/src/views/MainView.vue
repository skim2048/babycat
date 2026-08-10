<script setup>
import { computed, defineAsyncComponent, onMounted, ref, watch } from 'vue'
import { useCamera } from '../composables/useCamera.js'
import { useAuth } from '../composables/useAuth.js'
import { useLocale } from '../composables/useLocale.js'
import { useTheme } from '../composables/useTheme.js'
import { useStreamProtocol } from '../composables/useStreamProtocol.js'
import SheetFrame from '../components/SheetFrame.vue'

const LiveMobile = defineAsyncComponent(() => import('../components/LiveMobile.vue'))
const ClipsMobile = defineAsyncComponent(() => import('../components/ClipsMobile.vue'))
const CameraPanel = defineAsyncComponent(() => import('../components/CameraPanel.vue'))
const ChangePasswordPanel = defineAsyncComponent(() => import('../components/ChangePasswordPanel.vue'))
const PromptSheet = defineAsyncComponent(() => import('../components/PromptSheet.vue'))
const PtzSheet = defineAsyncComponent(() => import('../components/PtzSheet.vue'))
const ResourcesSheet = defineAsyncComponent(() => import('../components/ResourcesSheet.vue'))

const { cameraViewState, connected, ptzEnabled, load: loadCamera } = useCamera()
const {
  logout, mustChangePassword,
  isAuthenticated, isPersistentSession, sessionRemainingSeconds,
} = useAuth()
const { t, locale, toggleLocale } = useLocale()
const { theme, setTheme } = useTheme()
const { preferredProtocol, setProtocol } = useStreamProtocol()

// ── Layout state ──
const activeTab = ref('video')
const drawerOpen = ref(false)
const sheet = ref(null) // null | 'camera' | 'password' | 'prompt' | 'ptz' | 'resources'

// @claude Forced first-login flow (FR-006): the change-password sheet opens by
// @claude itself and cannot be dismissed until the password is changed.
watch(mustChangePassword, (forced) => {
  if (forced) sheet.value = 'password'
}, { immediate: true })

const sheetClosable = computed(() => !(sheet.value === 'password' && mustChangePassword.value))

function openSheet(name) {
  sheet.value = name
  drawerOpen.value = false
}
function closeSheet() {
  if (!sheetClosable.value) return
  sheet.value = null
}

function goTab(key) {
  activeTab.value = key
  drawerOpen.value = false
  if (sheetClosable.value) sheet.value = null
}

function toggleTheme() {
  setTheme(theme.value === 'light' ? 'dark' : 'light')
}

function handleLogout() {
  logout({ redirect: true })
}

// ── Top bar ──
const showSessionRemaining = computed(() =>
  isAuthenticated.value && !isPersistentSession.value && sessionRemainingSeconds.value > 0,
)
const sessionRemainingText = computed(() => {
  const total = sessionRemainingSeconds.value
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`
})
const protocolOptions = [
  { key: 'hls', label: 'HLS' },
  { key: 'webrtc', label: 'WebRTC' },
]

// ── Drawer (웹 레일과 같은 구성: 탭 상단, 기능·설정·하단 항목) ──
const drawerTabs = computed(() => [
  { key: 'video', icon: 'ph ph-monitor-play', label: t('dashboard.tab.video') },
  { key: 'clips', icon: 'ph ph-film-strip', label: t('dashboard.tab.clips') },
])
// @claude 기능 그룹: 바텀 시트를 여는 항목들. PTZ는 포트 미입력 시 숨긴다
// @claude (낙관적 활성 정책의 사전 비활성 조건과 동일).
const drawerFeatures = computed(() => [
  { key: 'camera', icon: 'ph ph-video-camera', label: t('dashboard.menu.camera'), onClick: () => openSheet('camera') },
  { key: 'prompt', icon: 'ph ph-chat-text', label: t('dashboard.panel.prompt'), onClick: () => openSheet('prompt') },
  ...(ptzEnabled.value ? [{ key: 'ptz', icon: 'ph ph-arrows-out-cardinal', label: 'PTZ', onClick: () => openSheet('ptz') }] : []),
  { key: 'resources', icon: 'ph ph-gauge', label: t('dashboard.resources'), onClick: () => openSheet('resources') },
])
const drawerPrefs = computed(() => [
  { key: 'lang', icon: 'ph ph-translate', label: t('locale.switchControl'), value: locale.value === 'ko' ? '한국어' : 'English', onClick: toggleLocale },
  {
    key: 'theme', icon: 'ph ph-moon', label: t('dashboard.menu.theme'),
    value: theme.value === 'dark' ? t('dashboard.theme.dark') : t('dashboard.theme.light'),
    onClick: toggleTheme,
  },
])
const drawerBottom = computed(() => [
  { key: 'password', icon: 'ph ph-key', label: t('dashboard.menu.password'), value: '', onClick: () => openSheet('password') },
  { key: 'logout', icon: 'ph ph-sign-out', label: t('dashboard.menu.logout'), value: '', onClick: handleLogout },
])

const sheetTitle = computed(() => ({
  camera: t('dashboard.menu.camera'),
  password: t('dashboard.menu.password'),
}[sheet.value] || ''))

onMounted(loadCamera)
</script>

<template>
  <div class="app-frame">

    <!-- ── Top app bar ── -->
    <header class="topbar">
      <span class="brand">
        <button class="drawer-toggle" :title="t('dashboard.sidebarShow')" @click="drawerOpen = true">
          <i class="ph ph-list"></i>
        </button>
        Babycat
      </span>
      <div v-if="activeTab === 'video'" class="topbar-right">
        <span v-if="showSessionRemaining" class="session-chip">
          <i class="ph ph-clock"></i>{{ sessionRemainingText }}
        </span>
        <!-- 알약의 어느 부분을 눌러도 반대 프로토콜로 전환된다 -->
        <button
          class="proto-pill"
          role="switch"
          :aria-checked="preferredProtocol === 'webrtc'"
          :aria-label="t('live.protocolToggle')"
          @click="setProtocol(preferredProtocol === 'hls' ? 'webrtc' : 'hls')"
        >
          <span
            v-for="p in protocolOptions"
            :key="p.key"
            class="proto-opt"
            :class="{ active: preferredProtocol === p.key }"
          >{{ p.label }}</span>
        </button>
      </div>
    </header>

    <!-- ── Content ── -->
    <main class="content">

      <template v-if="activeTab === 'video'">
        <div v-if="cameraViewState === 'unconfigured'" class="empty-state">
          <i class="ph ph-video-camera-slash"></i>
          <div class="empty-title">{{ t('dashboard.empty.title') }}</div>
          <div class="empty-body">{{ t('dashboard.empty.body') }}</div>
          <button class="empty-cta" @click="openSheet('camera')">{{ t('dashboard.empty.cta') }}</button>
        </div>
        <LiveMobile v-else @open-sheet="openSheet" />
      </template>

      <div v-else class="clips-tab">
        <ClipsMobile />
      </div>

    </main>

    <!-- ── Drawer ── -->
    <Transition name="drawer">
      <div v-if="drawerOpen" class="drawer-backdrop" @click.self="drawerOpen = false">
        <nav class="drawer">
          <!-- 상단바와 같은 높이·구성의 머리: 햄버거는 닫기 동작 -->
          <div class="drawer-head">
            <button class="drawer-toggle" :title="t('dashboard.sidebarHide')" @click="drawerOpen = false">
              <i class="ph ph-list"></i>
            </button>
            Babycat
          </div>
          <button
            v-for="tab in drawerTabs"
            :key="tab.key"
            class="drawer-item tab"
            :class="{ active: activeTab === tab.key }"
            @click="goTab(tab.key)"
          >
            <i :class="tab.icon"></i><span class="drawer-label">{{ tab.label }}</span>
          </button>
          <div class="drawer-spacer"></div>
          <button
            v-for="item in drawerFeatures"
            :key="item.key"
            class="drawer-item"
            @click="item.onClick"
          >
            <i :class="item.icon"></i><span class="drawer-label">{{ item.label }}</span>
          </button>
          <div class="drawer-rule"></div>
          <button
            v-for="item in drawerPrefs"
            :key="item.key"
            class="drawer-item"
            @click="item.onClick"
          >
            <i :class="item.icon"></i><span class="drawer-label">{{ item.label }}</span>
            <span class="drawer-value">{{ item.value }}</span>
          </button>
          <div class="drawer-rule"></div>
          <button
            v-for="item in drawerBottom"
            :key="item.key"
            class="drawer-item"
            @click="item.onClick"
          >
            <i :class="item.icon"></i><span class="drawer-label">{{ item.label }}</span>
          </button>
        </nav>
      </div>
    </Transition>

    <!-- ── Sheets ── -->
    <SheetFrame v-if="sheet === 'camera'" :title="sheetTitle" @close="closeSheet">
      <CameraPanel @close="sheet = null" />
    </SheetFrame>
    <SheetFrame v-else-if="sheet === 'password'" :title="sheetTitle" :closable="sheetClosable" @close="closeSheet">
      <ChangePasswordPanel :forced="mustChangePassword" @close="sheet = null" />
    </SheetFrame>
    <PromptSheet v-else-if="sheet === 'prompt'" @close="sheet = null" />
    <PtzSheet v-else-if="sheet === 'ptz'" :active="connected" @close="sheet = null" />
    <ResourcesSheet v-else-if="sheet === 'resources'" @close="sheet = null" />
  </div>
</template>

<style scoped>
.app-frame {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: var(--color-bg);
  color: var(--color-text);
  font-size: 14px;
}

/* — top app bar — */
.topbar {
  height: 52px;
  flex: none;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 12px;
}
.brand {
  display: flex;
  align-items: center;
  gap: 8px;
  font-family: var(--font-brand);
  font-size: 22px;
}
.drawer-toggle {
  width: 40px; height: 40px;
  border-radius: 100px;
  border: none;
  background: none;
  color: var(--color-neutral-300);
  font-size: 21px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}
.drawer-toggle:active { background: var(--color-neutral-900); }
.topbar-right {
  display: flex;
  align-items: center;
  gap: 6px;
}
.session-chip {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 12.5px;
  color: var(--color-neutral-400);
  background: var(--color-neutral-900);
  border-radius: 100px;
  padding: 6px 12px;
  font-variant-numeric: tabular-nums;
}
.session-chip i { font-size: 13.5px; }
.proto-pill {
  display: flex;
  border: 1px solid var(--color-neutral-800);
  border-radius: 100px;
  padding: 2px;
  background: none;
  cursor: pointer;
  font-family: inherit;
}
.proto-opt {
  border-radius: 100px;
  padding: 5px 11px;
  font-size: 11.5px;
  background: transparent;
  color: var(--color-neutral-400);
}
.proto-opt.active {
  background: var(--color-accent);
  color: #12131c;
}

/* — content — */
.content {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  padding-bottom: env(safe-area-inset-bottom);
}
.clips-tab {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 12px;
}

/* — empty state — */
.empty-state {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 14px;
  padding: 0 34px;
  text-align: center;
}
.empty-state > i {
  font-size: 34px;
  color: var(--color-neutral-500);
}
.empty-title { font-size: 16px; font-weight: 700; }
.empty-body {
  font-size: 13.5px;
  color: var(--color-neutral-400);
  line-height: 1.55;
  text-wrap: pretty;
}
.empty-cta {
  height: 52px;
  padding: 0 24px;
  border-radius: 100px;
  border: none;
  background: var(--color-accent);
  color: #12131c;
  font-size: 15px;
  font-weight: 700;
  font-family: inherit;
  cursor: pointer;
}

/* — drawer — */
.drawer-backdrop {
  position: fixed;
  inset: 0;
  z-index: 180;
  background: rgba(8, 9, 14, 0.5);
}
.drawer {
  position: absolute;
  top: 0; bottom: 0; left: 0;
  width: 264px;
  background: var(--color-bg);
  border-right: 1px solid var(--color-divider);
  display: flex;
  flex-direction: column;
  padding: 0 12px calc(14px + env(safe-area-inset-bottom));
  gap: 4px;
  overflow-y: auto;
}
/* 상단바와 같은 높이·구성 — 열림/닫힘 사이에 이질감이 없도록 정렬을 맞춘다 */
.drawer-head {
  height: 52px;
  flex: none;
  display: flex;
  align-items: center;
  gap: 8px;
  font-family: var(--font-brand);
  font-size: 22px;
  margin-bottom: 8px;
}
.drawer-item {
  height: 44px;
  flex: none;
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 0 14px;
  border-radius: 100px;
  border: none;
  background: none;
  color: var(--color-neutral-300);
  font-family: inherit;
  font-size: 14.5px;
  cursor: pointer;
  text-align: left;
  white-space: nowrap;
}
.drawer-item.tab { height: 48px; font-size: 15.5px; }
.drawer-item i { font-size: 19px; flex: none; }
.drawer-item.tab i { font-size: 20px; }
.drawer-item:active { background: var(--color-neutral-900); }
.drawer-item.active {
  background: color-mix(in srgb, var(--color-accent) 22%, transparent);
  color: var(--color-text);
}
.drawer-label {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
}
.drawer-value {
  font-size: 12.5px;
  color: var(--color-neutral-500);
}
.drawer-spacer { flex: 1; }
.drawer-rule {
  height: 1px;
  background: var(--color-divider);
  margin: 8px 4px;
  flex: none;
}

/* 서랍 전환: 배경은 흐려지고 패널은 좌측에서 밀려 나온다 */
.drawer-enter-active,
.drawer-leave-active { transition: opacity 0.2s; }
.drawer-enter-active .drawer,
.drawer-leave-active .drawer { transition: transform 0.2s ease; }
.drawer-enter-from,
.drawer-leave-to { opacity: 0; }
.drawer-enter-from .drawer,
.drawer-leave-to .drawer { transform: translateX(-100%); }
</style>
