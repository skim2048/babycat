<script setup>
import { computed, defineAsyncComponent, onMounted, ref, watch } from 'vue'
import { useCamera } from '../composables/useCamera.js'
import { useAuth } from '../composables/useAuth.js'
import { useLocale } from '../composables/useLocale.js'
import { useTheme } from '../composables/useTheme.js'
import { useSSE } from '../composables/useSSE.js'
import { useStreamProtocol } from '../composables/useStreamProtocol.js'
import { useInferLog } from '../composables/useInferLog.js'

const CameraPanel = defineAsyncComponent(() => import('../components/CameraPanel.vue'))
const ChangePasswordPanel = defineAsyncComponent(() => import('../components/ChangePasswordPanel.vue'))
const PromptPanel = defineAsyncComponent(() => import('../components/PromptPanel.vue'))
const ClipsPanel = defineAsyncComponent(() => import('../components/ClipsPanel.vue'))
const LiveStream = defineAsyncComponent(() => import('../components/LiveStream.vue'))

const { cameraViewState, load: loadCamera } = useCamera()
const {
  logout, mustChangePassword,
  isAuthenticated, isPersistentSession, sessionRemainingSeconds,
} = useAuth()
const { t, locale, toggleLocale } = useLocale()
const { theme, setTheme } = useTheme()
const { state: sse } = useSSE()
const { preferredProtocol, setProtocol } = useStreamProtocol()
const { entries: inferLog } = useInferLog()

// ── Layout state ──
const activeTab = ref('video')
const railOpen = ref(true)
const modal = ref(null) // null | 'camera' | 'prompt' | 'password'

// @claude Forced first-login flow (FR-006): the change-password modal opens by
// @claude itself and cannot be dismissed until the password is changed.
watch(mustChangePassword, (forced) => {
  if (forced) modal.value = 'password'
}, { immediate: true })

const modalClosable = computed(() => !(modal.value === 'password' && mustChangePassword.value))

function openModal(name) {
  modal.value = name
}
function closeModal() {
  if (!modalClosable.value) return
  modal.value = null
}
function onBackdropClick(e) {
  if (e.target === e.currentTarget) closeModal()
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
  const minutes = Math.floor(total / 60)
  const seconds = total % 60
  return `${minutes}:${String(seconds).padStart(2, '0')}`
})
const protocolOptions = [
  { key: 'hls', label: 'HLS' },
  { key: 'webrtc', label: 'WebRTC' },
]

// ── Rail ──
const railTabs = computed(() => [
  { key: 'video', icon: 'ph ph-monitor-play', label: t('dashboard.tab.video') },
  { key: 'clips', icon: 'ph ph-film-strip', label: t('dashboard.tab.clips') },
])
const railFeatures = computed(() => [
  { key: 'camera', icon: 'ph ph-video-camera', label: t('dashboard.menu.camera') },
  { key: 'prompt', icon: 'ph ph-chat-text', label: t('dashboard.menu.prompt') },
])
const railPrefs = computed(() => [
  {
    key: 'lang', icon: 'ph ph-translate', label: t('locale.switchControl'),
    value: locale.value === 'ko' ? 'KO' : 'EN', onClick: toggleLocale,
  },
  {
    key: 'theme', icon: 'ph ph-moon', label: t('dashboard.menu.theme'),
    value: theme.value === 'dark' ? t('dashboard.theme.dark') : t('dashboard.theme.light'),
    onClick: toggleTheme,
  },
])
const railBottom = computed(() => [
  { key: 'password', icon: 'ph ph-key', label: t('dashboard.menu.password'), onClick: () => openModal('password') },
  { key: 'logout', icon: 'ph ph-sign-out', label: t('dashboard.menu.logout'), onClick: handleLogout },
])

// ── VLM log panel ──
const VLM_DOTS = {
  ready: '#5fbf8a',
  error: '#e05b6a',
  switching: '#d9a44a',
  downloading: '#d9a44a',
}
const vlmDot = computed(() => VLM_DOTS[sse.vlm_state] || 'var(--color-neutral-500)')
const vlmLabel = computed(() => {
  const base = t(`dashboard.vlm.${sse.vlm_state}`)
  if (sse.vlm_state === 'ready' && sse.vlm_current_model) return `${base} · ${sse.vlm_current_model}`
  return base
})
const logQuery = ref('')
const visibleLog = computed(() => {
  const q = logQuery.value.trim().toLowerCase()
  if (!q) return inferLog
  return inferLog.filter((l) => l.text.toLowerCase().includes(q) || l.time.includes(q))
})

const modalTitle = computed(() => ({
  camera: t('dashboard.menu.camera'),
  prompt: t('dashboard.menu.prompt'),
  password: t('dashboard.menu.password'),
}[modal.value] || ''))

onMounted(loadCamera)
</script>

<template>
  <div class="app-frame">

    <!-- ── Top bar ── -->
    <header class="topbar">
      <span class="brand">
        <button
          class="rail-toggle"
          :title="railOpen ? t('dashboard.sidebarHide') : t('dashboard.sidebarShow')"
          @click="railOpen = !railOpen"
        >
          <i :class="railOpen ? 'ph ph-sidebar-simple' : 'ph ph-sidebar'"></i>
        </button>
        <i class="ph ph-cat brand-mark"></i>BABYCAT
      </span>
      <div v-if="activeTab === 'video'" class="topbar-right">
        <span v-if="showSessionRemaining" class="session-chip">
          <i class="ph ph-clock"></i>{{ sessionRemainingText }}
        </span>
        <div class="proto-pill" role="group">
          <button
            v-for="p in protocolOptions"
            :key="p.key"
            class="proto-opt"
            :class="{ active: preferredProtocol === p.key }"
            :aria-pressed="preferredProtocol === p.key"
            @click="setProtocol(p.key)"
          >{{ p.label }}</button>
        </div>
      </div>
    </header>

    <div class="app-body">

      <!-- ── Rail ── -->
      <nav class="rail" :class="{ collapsed: !railOpen }">
        <button
          v-for="tab in railTabs"
          :key="tab.key"
          class="rail-item tab"
          :class="{ active: activeTab === tab.key }"
          :title="tab.label"
          @click="activeTab = tab.key; modal = modalClosable ? null : modal"
        >
          <i :class="tab.icon"></i><span class="rail-label">{{ tab.label }}</span>
        </button>
        <div class="rail-spacer"></div>
        <button
          v-for="item in railFeatures"
          :key="item.key"
          class="rail-item"
          :title="item.label"
          @click="openModal(item.key)"
        >
          <i :class="item.icon"></i><span class="rail-label">{{ item.label }}</span>
        </button>
        <div class="rail-rule"></div>
        <button
          v-for="item in railPrefs"
          :key="item.key"
          class="rail-item"
          :title="item.label"
          @click="item.onClick"
        >
          <i :class="item.icon"></i><span class="rail-label">{{ item.label }}</span>
          <span class="rail-value">{{ item.value }}</span>
        </button>
        <div class="rail-rule"></div>
        <button
          v-for="item in railBottom"
          :key="item.key"
          class="rail-item"
          :title="item.label"
          @click="item.onClick"
        >
          <i :class="item.icon"></i><span class="rail-label">{{ item.label }}</span>
        </button>
      </nav>

      <!-- ── Content ── -->
      <main class="content">

        <template v-if="activeTab === 'video'">
          <div v-if="cameraViewState === 'unconfigured'" class="empty-state">
            <i class="ph ph-video-camera-slash"></i>
            <div class="empty-title">{{ t('dashboard.empty.title') }}</div>
            <div class="empty-body">{{ t('dashboard.empty.body') }}</div>
            <button class="btn btn-primary" @click="openModal('camera')">{{ t('dashboard.empty.cta') }}</button>
          </div>

          <div v-else class="video-tab">
            <LiveStream @open-prompt="openModal('prompt')" />

            <aside class="log-panel">
              <div class="log-head">
                <span class="vlm-status">
                  <span class="vlm-dot" :style="{ background: vlmDot }"></span>{{ vlmLabel }}
                </span>
              </div>
              <div class="log-search">
                <i class="ph ph-magnifying-glass"></i>
                <input v-model="logQuery" :placeholder="t('dashboard.log.search')" />
                <button v-if="logQuery" class="log-clear" @click="logQuery = ''"><i class="ph ph-x"></i></button>
              </div>
              <div class="log-list">
                <div v-if="!visibleLog.length" class="log-none">
                  {{ logQuery ? t('dashboard.log.none') : t('dashboard.log.waiting') }}
                </div>
                <div
                  v-for="(entry, i) in visibleLog"
                  :key="`${entry.time}-${i}`"
                  class="log-entry"
                  :class="{ latest: i === 0 && !logQuery }"
                >
                  <span class="log-time">{{ entry.time }}</span>
                  <span class="log-text">{{ entry.text }}</span>
                </div>
              </div>
            </aside>
          </div>
        </template>

        <div v-else-if="activeTab === 'clips'" class="clips-tab">
          <ClipsPanel />
        </div>

      </main>
    </div>

    <!-- ── Modal ── -->
    <Transition name="modal">
      <div v-if="modal" class="modal-backdrop" @click="onBackdropClick">
        <div class="modal-frame">
          <div class="modal-head">
            <span class="modal-title">{{ modalTitle }}</span>
            <button v-if="modalClosable" class="modal-x" @click="closeModal"><i class="ph ph-x"></i></button>
          </div>
          <div class="modal-body">
            <CameraPanel v-if="modal === 'camera'" @close="modal = null" />
            <PromptPanel v-else-if="modal === 'prompt'" @close="modal = null" />
            <ChangePasswordPanel v-else-if="modal === 'password'" :forced="mustChangePassword" @close="modal = null" />
          </div>
        </div>
      </div>
    </Transition>
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

/* — top bar — */
.topbar {
  height: 60px;
  flex: none;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 20px;
  border-bottom: 1px solid var(--color-divider);
}
.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 13.5px;
  font-weight: 600;
  letter-spacing: 0.08em;
}
.brand-mark {
  color: var(--color-accent);
  font-size: 17px;
}
.rail-toggle {
  width: 32px; height: 32px;
  border-radius: 8px;
  border: none;
  background: none;
  color: var(--color-neutral-400);
  font-size: 18px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}
.rail-toggle:hover { background: var(--color-neutral-900); color: var(--color-text); }
.topbar-right {
  display: flex;
  align-items: center;
  gap: 10px;
}
.session-chip {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--color-neutral-500);
  border: 1px solid var(--color-neutral-800);
  border-radius: 20px;
  padding: 5px 11px;
  font-variant-numeric: tabular-nums;
}
.session-chip i { font-size: 13px; }
.proto-pill {
  display: flex;
  border: 1px solid var(--color-neutral-800);
  border-radius: 20px;
  padding: 2px;
}
.proto-opt {
  border: none;
  border-radius: 18px;
  padding: 5px 11px;
  font-size: 11.5px;
  background: transparent;
  color: var(--color-neutral-500);
  cursor: pointer;
  font-family: inherit;
}
.proto-opt.active {
  background: var(--color-accent);
  color: #12131c;
}

/* — body / rail — */
.app-body {
  flex: 1;
  min-height: 0;
  display: flex;
}
.rail {
  width: 224px;
  flex: none;
  border-right: 1px solid var(--color-divider);
  display: flex;
  flex-direction: column;
  padding: 14px 12px;
  gap: 4px;
  transition: width 0.2s ease;
  overflow: hidden;
}
.rail.collapsed { width: 64px; }
.rail-item {
  height: 40px;
  flex: none;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 0 12px;
  border-radius: 8px;
  border: none;
  background: none;
  color: var(--color-neutral-400);
  font-family: inherit;
  font-size: 12.5px;
  cursor: pointer;
  text-align: left;
  white-space: nowrap;
}
.rail-item.tab { height: 44px; font-size: 13.5px; }
.rail-item i { font-size: 17px; flex: none; }
.rail-item.tab i { font-size: 18px; }
.rail-item:hover { background: var(--color-neutral-900); }
.rail-item.active {
  background: color-mix(in srgb, var(--color-accent) 14%, transparent);
  color: var(--color-accent);
}
.rail-label {
  flex: 1;
  opacity: 1;
  transition: opacity 0.14s;
  overflow: hidden;
  text-overflow: ellipsis;
}
.rail-value {
  font-size: 11px;
  color: var(--color-neutral-600);
  transition: opacity 0.14s;
}
.rail.collapsed .rail-label,
.rail.collapsed .rail-value { opacity: 0; }
.rail-spacer { flex: 1; }
.rail-rule {
  height: 1px;
  background: var(--color-divider);
  margin: 8px 4px;
  flex: none;
}

/* — content — */
.content {
  flex: 1;
  min-width: 0;
  min-height: 0;
  overflow: auto;
  padding: 20px;
  display: flex;
  flex-direction: column;
}
.video-tab {
  flex: 1;
  min-height: 0;
  display: flex;
  gap: 20px;
  align-items: stretch;
}
.clips-tab { max-width: 1000px; }

/* — empty state — */
.empty-state {
  flex: 1;
  min-height: 520px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 14px;
  text-align: center;
}
.empty-state > i {
  font-size: 38px;
  color: var(--color-neutral-600);
}
.empty-title { font-size: 17px; font-weight: var(--font-heading-weight); }
.empty-body {
  font-size: 13px;
  color: var(--color-neutral-500);
  line-height: 1.55;
  max-width: 420px;
  text-wrap: pretty;
}

/* — log panel — */
.log-panel {
  width: 340px;
  flex: none;
  display: flex;
  flex-direction: column;
  gap: 10px;
  border: 1px solid var(--color-neutral-800);
  border-radius: 8px;
  padding: 14px;
  background: var(--color-neutral-900);
  min-height: 200px;
}
.log-head {
  flex: none;
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.vlm-status {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12.5px;
}
.vlm-dot {
  width: 6px; height: 6px;
  border-radius: 50%;
}
.log-search {
  flex: none;
  position: relative;
  display: flex;
  align-items: center;
}
.log-search > i {
  position: absolute;
  left: 10px;
  font-size: 14px;
  color: var(--color-neutral-600);
  pointer-events: none;
}
.log-search input {
  width: 100%;
  box-sizing: border-box;
  height: 34px;
  border-radius: 7px;
  border: 1px solid var(--color-neutral-800);
  background: transparent;
  color: var(--color-text);
  padding: 0 30px;
  font-size: 12px;
  font-family: inherit;
  outline: none;
}
.log-search input:focus-visible { border-color: var(--color-accent); }
.log-clear {
  position: absolute;
  right: 6px;
  width: 22px; height: 22px;
  border: none;
  background: none;
  color: var(--color-neutral-500);
  font-size: 13px;
  cursor: pointer;
  border-radius: 11px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.log-clear:hover { background: var(--color-neutral-800); }
.log-list {
  flex: 1;
  min-height: 0;
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding-right: 12px;
}
.log-none {
  padding: 14px 2px;
  font-size: 12px;
  color: var(--color-neutral-600);
}
.log-entry {
  flex: none;
  display: flex;
  gap: 9px;
  font-size: 12px;
  line-height: 1.5;
  color: var(--color-neutral-500);
}
.log-entry.latest { color: var(--color-text); }
.log-entry.latest .log-text { color: var(--color-text); }
.log-time {
  flex: none;
  color: var(--color-neutral-600);
  font-variant-numeric: tabular-nums;
}

/* — modal — */
.modal-backdrop {
  position: fixed;
  inset: 0;
  z-index: 200;
  background: rgba(8, 9, 14, 0.62);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px;
}
.modal-frame {
  width: 560px;
  max-height: 80%;
  background: var(--color-surface);
  border: 1px solid var(--color-neutral-800);
  border-radius: 12px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  box-shadow: 0 24px 60px rgba(0, 0, 0, 0.6);
}
.modal-head {
  flex: none;
  height: 56px;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 10px 0 20px;
  border-bottom: 1px solid var(--color-divider);
}
.modal-title {
  flex: 1;
  font-size: 15.5px;
  font-weight: var(--font-heading-weight);
}
.modal-x {
  width: 38px; height: 38px;
  border: none;
  background: none;
  color: var(--color-neutral-400);
  font-size: 19px;
  cursor: pointer;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.modal-x:hover { background: var(--color-neutral-900); }
.modal-body {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 18px 20px 24px;
}

.modal-enter-active,
.modal-leave-active { transition: opacity 0.2s; }
.modal-enter-from,
.modal-leave-to { opacity: 0; }

/* — narrow widths: the log panel drops below the video — */
@media (max-width: 1100px) {
  .video-tab { flex-direction: column; }
  .log-panel { width: auto; max-height: 320px; }
}
@media (max-width: 720px) {
  .rail { position: absolute; z-index: 100; height: 100%; background: var(--color-bg); }
  .rail.collapsed { width: 0; padding: 14px 0; border-right: none; }
  .app-body { position: relative; }
}
</style>
