<script setup>
import { computed } from 'vue'
import { state, addCheckedToPlaylist } from '../state.js'
import FileTreeNode from './FileTreeNode.vue'

const disabled = computed(() => state.playlist?.is_playing === true)
const checkedCount = computed(() => state.treeChecked.size)

function filterTree(node, q) {
  if (!q) return node
  if (node.type === 'file') {
    return node.name.toLowerCase().includes(q) ? node : null
  }
  const children = (node.children || [])
    .map((c) => filterTree(c, q))
    .filter((c) => c !== null)
  if (children.length === 0) return null
  return { ...node, children }
}

function collectFiles(node, acc) {
  if (!node) return acc
  if (node.type === 'file') {
    acc.push(node.path)
    return acc
  }
  for (const c of node.children || []) collectFiles(c, acc)
  return acc
}

const filteredTree = computed(() => {
  if (!state.library) return null
  const q = state.treeQuery.trim().toLowerCase()
  return filterTree(state.library, q)
})

const visibleFiles = computed(() => collectFiles(filteredTree.value, []))

const allVisibleChecked = computed(
  () =>
    visibleFiles.value.length > 0 &&
    visibleFiles.value.every((p) => state.treeChecked.has(p)),
)
const someVisibleChecked = computed(() =>
  visibleFiles.value.some((p) => state.treeChecked.has(p)),
)

function toggleSelectAll() {
  if (disabled.value || visibleFiles.value.length === 0) return
  if (allVisibleChecked.value) {
    for (const p of visibleFiles.value) state.treeChecked.delete(p)
  } else {
    for (const p of visibleFiles.value) state.treeChecked.add(p)
  }
}
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
    <div class="toolbar">
      <label class="select-all" :class="{ disabled }">
        <input
          type="checkbox"
          :checked="allVisibleChecked"
          :indeterminate.prop="!allVisibleChecked && someVisibleChecked"
          :disabled="disabled || visibleFiles.length === 0"
          @change="toggleSelectAll"
        />
        <span>전체</span>
      </label>
      <input
        v-model="state.treeQuery"
        type="search"
        class="search"
        placeholder="파일명 검색"
      />
    </div>
    <div v-if="state.libraryError" class="error">{{ state.libraryError }}</div>
    <ul v-else-if="filteredTree" class="tree">
      <FileTreeNode
        :node="filteredTree"
        :depth="0"
        :dir-path="''"
        :auto-expand="state.treeQuery.trim().length > 0"
      />
    </ul>
    <div v-else-if="state.library" class="empty">일치하는 파일이 없습니다.</div>
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
.toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  border-bottom: 1px solid var(--border);
}
.select-all {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--text-3);
  user-select: none;
  cursor: pointer;
}
.select-all.disabled { cursor: default; opacity: 0.6; }
.select-all input { margin: 0; cursor: pointer; }
.select-all input:disabled { cursor: default; }
.search {
  flex: 1;
  min-width: 0;
  background: var(--bg-surface);
  color: var(--text-1);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 4px 8px;
  font-size: 12px;
  font-family: var(--font-ui);
}
.search:focus { outline: none; border-color: var(--accent); }
.tree { list-style: none; padding: 8px 0; margin: 0; overflow: auto; flex: 1; font-size: 13px; }
.error { color: var(--danger); padding: 12px; }
.empty { color: var(--text-4); padding: 12px; }
</style>
