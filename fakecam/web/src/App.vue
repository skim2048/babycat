<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { state } from './state.js'
import { useLocale } from './composables/useLocale.js'
import { useTheme } from './composables/useTheme.js'
import StreamDashboard from './components/StreamDashboard.vue'
import FileTree from './components/FileTree.vue'
import Playlist from './components/Playlist.vue'
import BottomControls from './components/BottomControls.vue'
import SettingsModal from './components/SettingsModal.vue'
import Icon from './components/Icon.vue'

const { t, toggleLocale } = useLocale()
const { toggleTheme } = useTheme()

const settingsOpen = ref(false)
const menuOpen = ref(false)
const menuBtnRef = ref(null)
const menuRef = ref(null)

function toggleMenu() {
  menuOpen.value = !menuOpen.value
}

function onLanguage() {
  menuOpen.value = false
  toggleLocale()
}

function onTheme() {
  menuOpen.value = false
  toggleTheme()
}

function onDocumentClick(e) {
  if (!menuOpen.value) return
  if (menuRef.value?.contains(e.target)) return
  if (menuBtnRef.value?.contains(e.target)) return
  menuOpen.value = false
}

onMounted(() => document.addEventListener('click', onDocumentClick))
onUnmounted(() => document.removeEventListener('click', onDocumentClick))
</script>

<template>
  <div class="app">
    <header class="topbar">
      <div class="menu-wrapper">
        <button
          ref="menuBtnRef"
          class="menu-btn"
          :aria-label="t('menu.aria')"
          @click="toggleMenu"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <line x1="3" y1="6" x2="21" y2="6"/>
            <line x1="3" y1="12" x2="21" y2="12"/>
            <line x1="3" y1="18" x2="21" y2="18"/>
          </svg>
        </button>
        <Transition name="dropdown">
          <div v-if="menuOpen" ref="menuRef" class="dropdown-menu">
            <button class="dropdown-item" @click="onLanguage">{{ t('menu.language') }}</button>
            <button class="dropdown-item" @click="onTheme">{{ t('menu.theme') }}</button>
          </div>
        </Transition>
      </div>
      <h1>FakeCam</h1>
      <span class="conn" :class="{ ok: state.sseConnected }">
        {{ state.sseConnected ? t('app.sseConnected') : t('app.sseDisconnected') }}
      </span>
      <button class="gear" :title="t('settings.title')" :aria-label="t('settings.title')" @click="settingsOpen = true">
        <Icon name="settings" />
      </button>
    </header>
    <StreamDashboard />
    <main class="panes">
      <FileTree class="pane left" />
      <Playlist class="pane right" />
    </main>
    <BottomControls />
    <SettingsModal v-if="settingsOpen" @close="settingsOpen = false" />
  </div>
</template>

<style scoped>
.app { display: flex; flex-direction: column; height: 100%; }
.topbar {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 10px 16px;
  border-bottom: 1px solid var(--border);
  background: var(--bg-surface);
}
.topbar h1 { margin: 0; font-size: 14px; flex: 1; }
.topbar .conn { color: var(--text-4); font-size: 12px; }
.topbar .conn.ok { color: var(--accent); }

.menu-wrapper { position: relative; display: inline-flex; }
.menu-btn {
  background: transparent;
  border: 1px solid var(--border);
  color: var(--text-2);
  padding: 4px 8px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
.menu-btn:hover { background: var(--bg-hover); color: var(--text-1); }

.dropdown-menu {
  position: absolute;
  top: calc(100% + 6px);
  left: 0;
  min-width: 180px;
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: 6px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.2);
  padding: 4px;
  z-index: 100;
  display: flex;
  flex-direction: column;
}
.dropdown-item {
  background: transparent;
  border: none;
  text-align: left;
  padding: 8px 12px;
  border-radius: 4px;
  color: var(--text-1);
  cursor: pointer;
}
.dropdown-item:hover { background: var(--bg-hover); }

.dropdown-enter-active, .dropdown-leave-active { transition: opacity 0.12s, transform 0.12s; transform-origin: top left; }
.dropdown-enter-from, .dropdown-leave-to { opacity: 0; transform: scaleY(0.95) translateY(-4px); }

.gear {
  background: transparent;
  border: 1px solid var(--border);
  color: var(--text-2);
  padding: 6px 10px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
.gear:hover { background: var(--bg-hover); color: var(--text-1); }

.panes { display: grid; grid-template-columns: 1fr 1fr; flex: 1; min-height: 0; }
.pane.left { border-right: 1px solid var(--border); }
</style>
