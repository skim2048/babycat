<script setup>
import { ref } from 'vue'

const props = defineProps({
  node: { type: Object, required: true },
  depth: { type: Number, default: 0 },
})

const expanded = ref(props.depth === 0)

function toggle() {
  if (props.node.type === 'dir') {
    expanded.value = !expanded.value
  }
}
</script>

<template>
  <li class="node">
    <div class="row" :style="{ paddingLeft: depth * 16 + 'px' }" @click="toggle">
      <span v-if="node.type === 'dir'" class="caret">{{ expanded ? '▾' : '▸' }}</span>
      <span v-else class="caret leaf">·</span>
      <span class="label" :class="node.type">{{ node.name }}</span>
    </div>
    <ul v-if="node.type === 'dir' && expanded" class="children">
      <FileTreeNode
        v-for="child in node.children"
        :key="(child.path || '') + child.name"
        :node="child"
        :depth="depth + 1"
      />
    </ul>
  </li>
</template>

<style scoped>
.node { list-style: none; }
.children { padding: 0; margin: 0; }
.row { display: flex; align-items: center; gap: 6px; padding: 2px 0; cursor: default; user-select: none; }
.row:hover { background: var(--bg-hover); }
.caret { width: 12px; display: inline-block; color: var(--text-3); text-align: center; }
.caret.leaf { color: var(--text-4); }
.label.dir { color: var(--text-2); font-weight: 500; }
.label.file { color: var(--accent); }
</style>
