<script setup>
import { computed } from 'vue'
import { state } from '../state.js'

const items = computed(() => state.playlist?.items ?? [])
const isPlaying = computed(() => state.playlist?.is_playing ?? false)
const currentPath = computed(() => state.playlist?.current_path ?? null)
</script>

<template>
  <section class="pane">
    <header>
      <h2>재생 목록</h2>
      <span class="badge" :class="{ playing: isPlaying }">
        {{ isPlaying ? '재생 중' : '정지' }}
      </span>
    </header>
    <ul v-if="items.length" class="list">
      <li
        v-for="item in items"
        :key="item.path"
        :class="{ current: currentPath === item.path }"
      >
        <span class="indicator">{{ currentPath === item.path ? '▶' : '' }}</span>
        <span class="name">{{ item.name }}</span>
        <span class="path">{{ item.path }}</span>
      </li>
    </ul>
    <div v-else-if="state.playlist" class="empty">재생 목록이 비어 있습니다.</div>
    <div v-else class="empty">불러오는 중…</div>
  </section>
</template>

<style scoped>
.pane { display: flex; flex-direction: column; min-width: 0; }
header { display: flex; align-items: center; gap: 8px; padding: 8px 12px; border-bottom: 1px solid var(--border); }
header h2 { margin: 0; font-size: 14px; font-weight: 600; flex: 1; }
.badge { font-size: 12px; color: var(--text-3); padding: 2px 10px; background: #2a2a2a; border-radius: 10px; }
.badge.playing { color: var(--accent); }
.list { list-style: none; padding: 8px 0; margin: 0; overflow: auto; flex: 1; font-size: 13px; }
.list li { display: grid; grid-template-columns: 16px 1fr auto; align-items: center; gap: 8px; padding: 4px 12px; }
.list li.current { background: var(--bg-active); }
.indicator { color: var(--accent); text-align: center; }
.name { color: var(--text-1); }
.path { color: var(--text-4); font-size: 12px; }
.empty { color: var(--text-4); padding: 12px; }
</style>
