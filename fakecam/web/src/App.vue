<script setup>
import { getApiBase } from './api.js'
import { state } from './state.js'
import FileTree from './components/FileTree.vue'
import Playlist from './components/Playlist.vue'
import BottomControls from './components/BottomControls.vue'

const apiBase = getApiBase()
</script>

<template>
  <div class="app">
    <header class="topbar">
      <h1>fakecam</h1>
      <span class="meta">API: <code>{{ apiBase }}</code></span>
      <span class="conn" :class="{ ok: state.sseConnected }">
        {{ state.sseConnected ? '● 실시간' : '○ 연결 끊김' }}
      </span>
    </header>
    <main class="panes">
      <FileTree class="pane left" />
      <Playlist class="pane right" />
    </main>
    <BottomControls />
  </div>
</template>

<style scoped>
.app { display: flex; flex-direction: column; height: 100%; }
.topbar {
  display: flex;
  align-items: baseline;
  gap: 16px;
  padding: 10px 16px;
  border-bottom: 1px solid var(--border);
  background: var(--bg-surface);
}
.topbar h1 { margin: 0; font-size: 16px; font-weight: 600; }
.topbar .meta { color: var(--text-3); font-size: 12px; flex: 1; }
.topbar .meta code { color: var(--text-2); font-size: 12px; }
.topbar .conn { color: var(--text-4); font-size: 12px; }
.topbar .conn.ok { color: var(--accent); }
.panes { display: grid; grid-template-columns: 1fr 1fr; flex: 1; min-height: 0; }
.pane.left { border-right: 1px solid var(--border); }
</style>
