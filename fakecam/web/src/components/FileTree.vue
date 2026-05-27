<script setup>
import { computed } from 'vue'
import { state, addCheckedToPlaylist } from '../state.js'
import FileTreeNode from './FileTreeNode.vue'

const disabled = computed(() => state.playlist?.is_playing === true)
const checkedCount = computed(() => state.treeChecked.size)
</script>

<template>
  <section class="pane">
    <header>
      <h2>파일 트리</h2>
      <button
        class="action"
        :disabled="disabled || checkedCount === 0"
        :title="disabled ? '재생 중에는 변경할 수 없습니다' : '체크된 파일을 재생 목록에 추가'"
        @click="addCheckedToPlaylist"
      >
        ＋
        <span v-if="checkedCount > 0" class="count">{{ checkedCount }}</span>
      </button>
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
header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-bottom: 1px solid var(--border);
}
header h2 { margin: 0; font-size: 14px; font-weight: 600; flex: 1; }
.action { display: inline-flex; align-items: center; gap: 6px; font-size: 14px; line-height: 1; }
.action .count {
  font-size: 11px;
  background: var(--bg-active);
  color: var(--accent);
  padding: 1px 6px;
  border-radius: 8px;
}
.tree { list-style: none; padding: 8px 0; margin: 0; overflow: auto; flex: 1; font-size: 13px; }
.error { color: var(--danger); padding: 12px; }
.empty { color: var(--text-4); padding: 12px; }
</style>
