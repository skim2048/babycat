<script setup>
import { state } from '../state.js'
import FileTreeNode from './FileTreeNode.vue'
</script>

<template>
  <section class="pane">
    <header>
      <h2>파일 트리</h2>
    </header>
    <div v-if="state.libraryError" class="error">{{ state.libraryError }}</div>
    <ul v-else-if="state.library" class="tree">
      <FileTreeNode :node="state.library" :depth="0" />
    </ul>
    <div v-else class="empty">불러오는 중…</div>
  </section>
</template>

<style scoped>
.pane { display: flex; flex-direction: column; min-width: 0; }
header { display: flex; align-items: center; padding: 8px 12px; border-bottom: 1px solid var(--border); }
header h2 { margin: 0; font-size: 14px; font-weight: 600; }
.tree { list-style: none; padding: 8px 0; margin: 0; overflow: auto; flex: 1; font-size: 13px; }
.error { color: var(--danger); padding: 12px; }
.empty { color: var(--text-4); padding: 12px; }
</style>
