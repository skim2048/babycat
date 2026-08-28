<script setup>
import { computed, defineAsyncComponent, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useCamera } from '../composables/useCamera.js'
import { useAuth } from '../composables/useAuth.js'
import { useLocale } from '../composables/useLocale.js'
import { useTheme } from '../composables/useTheme.js'
import { useSSE } from '../composables/useSSE.js'
import { useStreamProtocol } from '../composables/useStreamProtocol.js'
import { useInferLog } from '../composables/useInferLog.js'
import { useAnalysis } from '../composables/useAnalysis.js'
import { useVlmStatus } from '../composables/useVlmStatus.js'
import { authFetch } from '../composables/useFetch.js'
import { APP_ENDPOINTS } from '../endpoints.js'

const CameraPanel = defineAsyncComponent(() => import('../components/CameraPanel.vue'))
const ChangePasswordPanel = defineAsyncComponent(() => import('../components/ChangePasswordPanel.vue'))
const PromptPanel = defineAsyncComponent(() => import('../components/PromptPanel.vue'))
const ClipsPanel = defineAsyncComponent(() => import('../components/ClipsPanel.vue'))
const LiveStream = defineAsyncComponent(() => import('../components/LiveStream.vue'))
const StatCards = defineAsyncComponent(() => import('../components/StatCards.vue'))

const { cameraViewState, load: loadCamera } = useCamera()
const {
  logout, mustChangePassword,
  isAuthenticated, isPersistentSession, sessionRemainingSeconds,
} = useAuth()
const { t, locale, toggleLocale } = useLocale()
const { theme, setTheme } = useTheme()
const { state: sse } = useSSE()
const { preferredProtocol, setProtocol } = useStreamProtocol()
const { entries: inferLog, removeEntries } = useInferLog()
const { analysisActive, busy: analysisBusy, toggle: toggleAnalysis } = useAnalysis()

// ── Layout state ──
const activeTab = ref('video')
const railOpen = ref(true)
const modal = ref(null) // null | 'camera' | 'password'
const panel = ref('log') // 'prompt' | 'log' — right panel tab

// @claude The sidebar steps down automatically by window width:
// @claude >1100px expanded (user choice respected) → ≤1100px collapsed (icons) → ≤720px hidden.
// @claude Pressing the toggle at narrow widths expands it as an overlay over the body.
const windowWidth = ref(window.innerWidth)
const railOverlay = ref(false)
// @claude Keep absolute during the close transition so the width shrink does not push the body.
const railClosing = ref(false)
let railCloseTimer = null
function onWindowResize() {
  windowWidth.value = window.innerWidth
  railOverlay.value = false
  railClosing.value = false
  clearTimeout(railCloseTimer)
}
const railState = computed(() => {
  if (railOverlay.value) return 'overlay'
  if (railClosing.value) return 'closing'
  if (windowWidth.value <= 720) return 'hidden'
  if (windowWidth.value <= 1100) return 'collapsed'
  return railOpen.value ? 'open' : 'collapsed'
})
function closeOverlay() {
  if (!railOverlay.value) return
  railOverlay.value = false
  railClosing.value = true
  clearTimeout(railCloseTimer)
  railCloseTimer = setTimeout(() => { railClosing.value = false }, 220)
}
function toggleRail() {
  if (windowWidth.value > 1100) {
    railOpen.value = !railOpen.value
    return
  }
  if (railOverlay.value) closeOverlay()
  else {
    railClosing.value = false
    clearTimeout(railCloseTimer)
    railOverlay.value = true
  }
}
// @claude Picking an item while in overlay state closes the overlay.
function onRailClick() {
  if (railState.value === 'overlay') closeOverlay()
}

// @claude Forced first-login flow: the change-password modal opens by
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

// ── VLM status / model switch ──
const { vlmDot, vlmLabel } = useVlmStatus()

const modelMenu = ref(false)
// @claude Show only the last path segment of the model id
// @claude (e.g. Efficient-Large-Model/VILA1.5-3b → VILA1.5-3b).
function shortModelName(id) {
  if (!id) return ''
  const parts = id.split('/')
  return parts[parts.length - 1]
}
const modelLabel = computed(() =>
  shortModelName(sse.vlm_current_model) || t('dashboard.model.unknown'),
)
// @claude A refused switch (400 {detail}) or a transport failure is shown in
// @claude the panel; the note clears on the next successful request.
const modelError = ref('')
async function switchModel(name) {
  modelMenu.value = false
  if (!name || name === sse.vlm_current_model) return
  modelError.value = ''
  try {
    const res = await authFetch(APP_ENDPOINTS.vlmSwitch, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model: name }),
    })
    if (!res.ok) {
      const body = await res.json().catch(() => ({}))
      modelError.value = t('dashboard.model.switchFailed', { message: body.detail || t('prompt.status.unknown') })
    }
  } catch {
    modelError.value = t('dashboard.model.switchFailed', { message: t('changePassword.error.network') })
  }
}

// @claude If refused (streaming off), bring the prompt tab with the reason notice to the front.
async function onInferClick() {
  const ok = await toggleAnalysis()
  if (!ok) panel.value = 'prompt'
}

// ── Session log ──
const logQuery = ref('')
const logSelectMode = ref(false)
const logSelected = ref(new Set())

function localDate(offsetDays = 0) {
  const d = new Date()
  d.setDate(d.getDate() + offsetDays)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

// @claude Insert a divider only where the date changes, omitting today;
// @claude yesterday is shown as a phrase, anything earlier as YY-MM-DD.
const visibleLog = computed(() => {
  const q = logQuery.value.trim().toLowerCase()
  const today = localDate()
  const yesterday = localDate(-1)
  const filtered = q
    ? inferLog.filter((l) => l.text.toLowerCase().includes(q) || l.time.includes(q))
    : [...inferLog]
  let prevDay = null
  return filtered.map((entry) => {
    let header = null
    if (entry.day !== prevDay && entry.day !== today) {
      header = entry.day === yesterday ? t('dashboard.day.yesterday') : entry.day.slice(2)
    }
    prevDay = entry.day
    return { ...entry, header }
  })
})

function toggleLogSelect() {
  logSelectMode.value = !logSelectMode.value
  logSelected.value = new Set()
}
function toggleLogEntry(id) {
  if (!logSelectMode.value) return
  const next = new Set(logSelected.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  logSelected.value = next
}
const allLogSelected = computed(() =>
  visibleLog.value.length > 0 && visibleLog.value.every((l) => logSelected.value.has(l.id)),
)
function toggleLogSelectAll() {
  logSelected.value = allLogSelected.value
    ? new Set()
    : new Set(visibleLog.value.map((l) => l.id))
}
function deleteSelectedLogs() {
  if (!logSelected.value.size) return
  removeEntries([...logSelected.value])
  logSelected.value = new Set()
  logSelectMode.value = false
}

const modalTitle = computed(() => ({
  camera: t('dashboard.menu.camera'),
  password: t('dashboard.menu.password'),
}[modal.value] || ''))

onMounted(() => {
  loadCamera()
  window.addEventListener('resize', onWindowResize)
})
onBeforeUnmount(() => {
  window.removeEventListener('resize', onWindowResize)
  clearTimeout(railCloseTimer)
})
</script>

<template>
  <div class="app-frame">

    <!-- ── Top bar ── -->
    <header class="topbar">
      <span class="brand">
        <button
          class="rail-toggle"
          :title="railState === 'open' || railState === 'overlay' ? t('dashboard.sidebarHide') : t('dashboard.sidebarShow')"
          @click="toggleRail"
        >
          <i :class="railState === 'open' || railState === 'overlay' ? 'ph ph-sidebar-simple' : 'ph ph-sidebar'"></i>
        </button>
        Babycat
      </span>
      <div v-if="activeTab === 'video'" class="topbar-right">
        <span v-if="showSessionRemaining" class="session-chip">
          <i class="ph ph-clock"></i>{{ sessionRemainingText }}
        </span>
        <!-- Pressing any part of the pill switches to the opposite protocol -->
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

    <div class="app-body">

      <!-- ── Rail ── -->
      <!-- When switched to overlay the rail leaves the document flow, so hold the collapsed
           width to keep the body from jumping sideways (the hidden range was 0 width anyway) -->
      <div
        v-if="(railState === 'overlay' || railState === 'closing') && windowWidth > 720"
        class="rail-ghost"
      ></div>
      <div v-if="railState === 'overlay'" class="rail-backdrop" @click="closeOverlay"></div>
      <nav
        class="rail"
        :class="{
          collapsed: railState === 'collapsed' || (railState === 'closing' && windowWidth > 720),
          hidden: railState === 'hidden' || (railState === 'closing' && windowWidth <= 720),
          overlay: railState === 'overlay' || railState === 'closing',
        }"
        @click="onRailClick"
      >
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
            <LiveStream />

            <aside class="side-col">

              <!-- Panel tabs -->
              <div class="panel-tabs" role="tablist">
                <button
                  v-for="p in [
                    { key: 'prompt', icon: 'ph ph-chat-text', label: t('dashboard.panel.prompt') },
                    { key: 'log', icon: 'ph ph-list-dashes', label: t('dashboard.panel.log') },
                  ]"
                  :key="p.key"
                  class="panel-tab"
                  :class="{ active: panel === p.key }"
                  role="tab"
                  :aria-selected="panel === p.key"
                  @click="panel = p.key"
                ><i :class="p.icon"></i>{{ p.label }}</button>
              </div>

              <!-- Session log panel -->
              <div v-if="panel === 'log'" class="log-panel">
                <div class="log-head">
                  <span class="vlm-status">
                    <span class="vlm-dot" :style="{ background: vlmDot }"></span>{{ vlmLabel }}
                  </span>
                  <div class="log-head-actions">
                    <div class="model-wrap">
                      <button
                        class="model-btn"
                        :aria-expanded="modelMenu"
                        @click="modelMenu = !modelMenu"
                        @keydown.esc="modelMenu = false"
                      >
                        {{ modelLabel }}<i :class="modelMenu ? 'ph ph-caret-up' : 'ph ph-caret-down'"></i>
                      </button>
                      <div v-if="modelMenu" class="menu-backdrop" @click="modelMenu = false"></div>
                      <div v-if="modelMenu" class="model-menu" @keydown.esc="modelMenu = false">
                        <button
                          v-for="m in sse.vlm_models"
                          :key="m"
                          class="model-opt"
                          :class="{ current: m === sse.vlm_current_model }"
                          :title="m"
                          @click="switchModel(m)"
                        >
                          <span>{{ shortModelName(m) }}</span>
                        </button>
                        <div v-if="!sse.vlm_models.length" class="model-none">{{ t('dashboard.model.none') }}</div>
                      </div>
                    </div>
                    <button
                      class="infer-btn"
                      :class="{ on: analysisActive }"
                      :disabled="analysisBusy"
                      @click="onInferClick"
                    >
                      {{ analysisActive ? t('prompt.action.stop') : t('prompt.action.start') }}
                    </button>
                  </div>
                </div>

                <div v-if="modelError" class="form-note warn">
                  <i class="ph ph-warning-circle"></i><span>{{ modelError }}</span>
                </div>

                <div class="log-controls">
                  <div class="log-search">
                    <i class="ph ph-magnifying-glass"></i>
                    <input v-model="logQuery" :placeholder="t('dashboard.log.search')" />
                    <button v-if="logQuery" class="log-clear" @click="logQuery = ''"><i class="ph ph-x"></i></button>
                  </div>
                  <button class="chip-btn" :class="{ on: logSelectMode }" @click="toggleLogSelect">
                    {{ logSelectMode ? t('dashboard.log.cancel') : t('dashboard.log.select') }}
                  </button>
                  <button v-if="logSelectMode" class="chip-btn" @click="toggleLogSelectAll">
                    {{ allLogSelected ? t('dashboard.log.deselectAll') : t('dashboard.log.selectAll') }}
                  </button>
                  <button
                    v-if="logSelectMode"
                    class="chip-btn danger"
                    :disabled="!logSelected.size"
                    @click="deleteSelectedLogs"
                  >{{ t('dashboard.log.delete') }}</button>
                </div>

                <div class="log-rule"></div>

                <div class="log-list">
                  <div v-if="!visibleLog.length" class="log-none">
                    {{ logQuery ? t('dashboard.log.none') : t('dashboard.log.waiting') }}
                  </div>
                  <template v-for="(entry, i) in visibleLog" :key="entry.id">
                    <div v-if="entry.header" class="log-day">
                      <span class="log-day-rule"></span>
                      <span>{{ entry.header }}</span>
                      <span class="log-day-rule"></span>
                    </div>
                    <div
                      class="log-entry"
                      :class="{ latest: i === 0 && !logQuery, selecting: logSelectMode, picked: logSelected.has(entry.id) }"
                      @click="toggleLogEntry(entry.id)"
                    >
                      <span v-if="logSelectMode" class="log-check" :class="{ on: logSelected.has(entry.id) }">
                        <svg v-if="logSelected.has(entry.id)" class="check-glyph" viewBox="0 0 12 12" aria-hidden="true"><polyline points="2.5,6.5 5,9 9.5,3.5" /></svg>
                      </span>
                      <span class="log-time">{{ entry.time }}</span>
                      <span class="log-text">{{ entry.text }}</span>
                    </div>
                  </template>
                </div>
              </div>

              <!-- Inference prompt panel -->
              <div v-else class="prompt-holder">
                <PromptPanel />
              </div>

              <!-- System info -->
              <StatCards class="side-res" />
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
            <ChangePasswordPanel v-else-if="modal === 'password'" :forced="mustChangePassword" @close="modal = null" />
          </div>
        </div>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.check-glyph {
  width: 10px;
  height: 10px;
  fill: none;
  stroke: currentColor;
  stroke-width: 2.2;
  stroke-linecap: round;
  stroke-linejoin: round;
}

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
  height: 48px;
  flex: none;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 14px;
  border-bottom: 1px solid var(--color-divider);
}
.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  font-family: var(--font-brand);
  font-size: 21px;
}
.rail-toggle {
  width: 32px; height: 32px;
  border-radius: 8px;
  border: none;
  background: none;
  color: var(--color-neutral-300);
  font-size: 19px;
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
  font-size: 13px;
  color: var(--color-neutral-400);
  border: 1px solid var(--color-neutral-800);
  border-radius: 20px;
  padding: 5px 11px;
  font-variant-numeric: tabular-nums;
}
.session-chip i { font-size: 14px; }
.proto-pill {
  display: flex;
  border: 1px solid var(--color-neutral-800);
  border-radius: 20px;
  padding: 2px;
  background: none;
  cursor: pointer;
  font-family: inherit;
}
.proto-opt {
  border-radius: 18px;
  padding: 5px 11px;
  font-size: 12.5px;
  background: transparent;
  color: var(--color-neutral-400);
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
  position: relative;
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
.rail.hidden {
  width: 0;
  padding: 14px 0;
  border-right: none;
}
.rail.overlay {
  position: absolute;
  z-index: 100;
  height: 100%;
  background: var(--color-bg);
}
.rail-ghost {
  width: 64px;
  flex: none;
}
.rail-backdrop {
  position: absolute;
  inset: 0;
  z-index: 99;
  background: rgba(8, 9, 14, 0.4);
}
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
  color: var(--color-neutral-300);
  font-family: inherit;
  font-size: 13.5px;
  cursor: pointer;
  text-align: left;
  white-space: nowrap;
}
.rail-item.tab { height: 44px; font-size: 14.5px; }
.rail-item i { font-size: 18px; flex: none; }
.rail-item.tab i { font-size: 19px; }
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
  font-size: 12px;
  color: var(--color-neutral-500);
  transition: opacity 0.14s;
}
.rail.collapsed .rail-label,
.rail.collapsed .rail-value,
.rail.hidden .rail-label,
.rail.hidden .rail-value { opacity: 0; }
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
.clips-tab {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

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
  color: var(--color-neutral-500);
}
.empty-title { font-size: 18.5px; font-weight: 700; }
.empty-body {
  font-size: 14.5px;
  color: var(--color-neutral-400);
  line-height: 1.55;
  max-width: 420px;
  text-wrap: pretty;
}

/* — side column — */
.side-col {
  width: 380px;
  flex: none;
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-height: 0;
}
.panel-tabs {
  flex: none;
  display: flex;
  gap: 4px;
  padding: 3px;
  border-radius: 9px;
  background: var(--color-neutral-900);
}
.panel-tab {
  flex: 1;
  height: 34px;
  border-radius: 7px;
  border: none;
  background: transparent;
  color: var(--color-neutral-400);
  font-family: inherit;
  font-size: 13px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  transition: background 0.15s;
}
.panel-tab i { font-size: 15px; }
.panel-tab:hover { background: color-mix(in srgb, var(--color-accent) 18%, transparent); }
.panel-tab.active {
  background: color-mix(in srgb, var(--color-accent) 28%, transparent);
  color: var(--color-text);
}

/* — log panel — */
.log-panel,
.prompt-holder {
  flex: 1;
  min-height: 200px;
  border-radius: 8px;
  padding: 14px;
  background: var(--color-neutral-900);
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.log-head {
  flex: none;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.vlm-status {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  min-width: 0;
}
.vlm-dot {
  width: 6px; height: 6px;
  flex: none;
  border-radius: 50%;
}
.log-head-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: none;
}
.model-wrap { position: relative; }
.model-btn {
  height: 30px;
  padding: 0 10px 0 12px;
  border-radius: 7px;
  border: none;
  background: var(--color-bg);
  color: var(--color-text);
  font-family: inherit;
  font-size: 13px;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 6px;
  transition: background 0.15s;
  max-width: 150px;
  white-space: nowrap;
  overflow: hidden;
}
.model-btn:hover { background: color-mix(in srgb, var(--color-accent) 22%, transparent); }
.model-btn i { font-size: 12px; color: var(--color-neutral-400); }
.menu-backdrop {
  position: fixed;
  inset: 0;
  z-index: 19;
}
.model-menu {
  position: absolute;
  top: 36px;
  right: 0;
  z-index: 20;
  width: 180px;
  background: var(--color-surface);
  border-radius: 9px;
  padding: 4px;
  box-shadow: var(--shadow-md);
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.model-opt {
  height: 34px;
  padding: 0 10px;
  border-radius: 7px;
  border: none;
  background: transparent;
  color: var(--color-text);
  font-family: inherit;
  font-size: 13.5px;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 8px;
  text-align: left;
}
.model-opt span {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.model-opt:hover { background: color-mix(in srgb, var(--color-accent) 22%, transparent); }
.model-opt.current { background: color-mix(in srgb, var(--color-accent) 16%, transparent); }
.model-none {
  padding: 8px 10px;
  font-size: 12.5px;
  color: var(--color-neutral-500);
}
.infer-btn {
  height: 30px;
  flex: none;
  padding: 0 11px;
  border-radius: 7px;
  border: none;
  background: var(--color-bg);
  color: var(--color-text);
  font-family: inherit;
  font-size: 13px;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 6px;
  white-space: nowrap;
  transition: background 0.15s;
}
.infer-btn:hover:not(:disabled) { background: color-mix(in srgb, var(--color-accent) 32%, transparent); }
.infer-btn.on { background: color-mix(in srgb, var(--color-accent) 28%, transparent); }
.infer-btn:disabled { opacity: 0.6; cursor: default; }

.log-controls {
  flex: none;
  display: flex;
  align-items: center;
  gap: 6px;
}
.log-search {
  position: relative;
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
}
.log-search > i {
  position: absolute;
  left: 10px;
  font-size: 15.5px;
  color: var(--color-neutral-500);
  pointer-events: none;
}
.log-search input {
  width: 100%;
  box-sizing: border-box;
  height: 34px;
  border-radius: 7px;
  border: none;
  background: var(--color-bg);
  color: var(--color-text);
  padding: 0 30px;
  font-size: 13.5px;
  font-family: inherit;
  outline: none;
}
.log-search input:focus-visible { outline: 2px solid var(--color-accent); }
.log-clear {
  position: absolute;
  right: 6px;
  width: 22px; height: 22px;
  border: none;
  background: none;
  color: var(--color-neutral-400);
  font-size: 14.5px;
  cursor: pointer;
  border-radius: 11px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.log-clear:hover { background: var(--color-neutral-800); }
/* The panel is neutral-900, so chip buttons use the page-background fill */
.log-controls .chip-btn { background: var(--color-bg); }
.log-controls .chip-btn.on { background: color-mix(in srgb, var(--color-accent) 16%, transparent); }
.log-controls .chip-btn:hover:not(:disabled) { background: color-mix(in srgb, var(--color-accent) 22%, transparent); }
.log-controls .chip-btn.danger:hover:not(:disabled) { background: color-mix(in srgb, #e07a86 18%, transparent); }

.log-rule {
  flex: none;
  height: 1px;
  background: var(--color-divider);
}
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
  font-size: 13.5px;
  color: var(--color-neutral-500);
}
.log-day {
  flex: none;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 4px 0 2px;
  font-size: 12px;
  color: var(--color-neutral-500);
}
.log-day-rule {
  flex: 1;
  height: 1px;
  background: var(--color-divider);
}
.log-entry {
  flex: none;
  display: flex;
  gap: 9px;
  font-size: 13.5px;
  line-height: 1.5;
  color: var(--color-neutral-400);
  border-radius: 6px;
}
.log-entry.selecting {
  cursor: pointer;
  padding: 4px 6px;
}
.log-entry.picked { background: color-mix(in srgb, var(--color-accent) 16%, transparent); }
.log-entry.latest,
.log-entry.latest .log-text { color: var(--color-text); }
.log-check {
  flex: none;
  width: 16px; height: 16px;
  margin-top: 2px;
  border-radius: 4px;
  border: 1px solid var(--color-neutral-700);
  color: #12131c;
  font-size: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.log-check.on {
  border-color: var(--color-accent);
  background: var(--color-accent);
}
.log-time {
  flex: none;
  color: var(--color-neutral-500);
  font-variant-numeric: tabular-nums;
}

.prompt-holder { overflow: hidden; }
.side-res { flex: none; }

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
  border-radius: 12px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  box-shadow: var(--shadow-lg);
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
  font-size: 17px;
  font-weight: 700;
}
.modal-x {
  width: 38px; height: 38px;
  border: none;
  background: none;
  color: var(--color-neutral-300);
  font-size: 20.5px;
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

/* — narrow widths: the side column drops below the video — */
@media (max-width: 1100px) {
  /* In the stacked layout, do not distribute heights; let content flow at natural height + page scroll.
     Fixing the height makes the left column overflow and overlap the area below. */
  .video-tab { flex: none; flex-direction: column; min-height: auto; }
  .side-col { width: auto; min-height: auto; }
  .log-panel, .prompt-holder { max-height: 340px; }
}
</style>
