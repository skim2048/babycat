<script setup>
import { computed } from 'vue'
import { state } from '../state.js'
import Icon from './Icon.vue'

const props = defineProps({
  node: { type: Object, required: true },
  depth: { type: Number, default: 0 },
  dirPath: { type: String, default: '' },
  autoExpand: { type: Boolean, default: false },
})

const isFile = computed(() => props.node.type === 'file')
const isDir = computed(() => props.node.type === 'dir')
const disabled = computed(() => state.playlist?.is_playing === true)

const expanded = computed(
  () => props.autoExpand || state.treeExpanded.has(props.dirPath),
)

const checked = computed({
  get: () => isFile.value && state.treeChecked.has(props.node.path),
  set: (v) => {
    if (!isFile.value || disabled.value) return
    if (v) state.treeChecked.add(props.node.path)
    else state.treeChecked.delete(props.node.path)
  },
})

function childDirPath(child) {
  if (child.type !== 'dir') return ''
  return props.dirPath ? `${props.dirPath}/${child.name}` : child.name
}

function onRowClick() {
  if (isDir.value) {
    if (expanded.value) state.treeExpanded.delete(props.dirPath)
    else state.treeExpanded.add(props.dirPath)
  } else if (!disabled.value) {
    checked.value = !checked.value
  }
}
</script>

<template>
  <li class="node">
    <div
      class="row"
      :class="{ file: isFile, dir: isDir }"
      :style="{ paddingLeft: depth * 16 + 'px' }"
      @click="onRowClick"
    >
      <span class="caret">
        <Icon
          v-if="isDir"
          :name="expanded ? 'chevron-down' : 'chevron-right'"
          :size="12"
        />
      </span>
      <input
        v-if="isFile"
        type="checkbox"
        :checked="checked"
        :disabled="disabled"
        @click.stop="checked = !checked"
      />
      <span v-else class="checkbox-spacer" />
      <span class="label" :class="node.type">{{ node.name }}</span>
    </div>
    <ul v-if="isDir && expanded" class="children">
      <FileTreeNode
        v-for="child in node.children"
        :key="(child.path || '') + child.name"
        :node="child"
        :depth="depth + 1"
        :dir-path="childDirPath(child)"
        :auto-expand="autoExpand"
      />
    </ul>
  </li>
</template>

<style scoped>
.node { list-style: none; }
.children { padding: 0; margin: 0; }
.row { display: flex; align-items: center; gap: 6px; padding: 2px 0; user-select: none; cursor: pointer; }
.row:hover { background: var(--bg-hover); }
.caret {
  width: 14px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: var(--text-3);
}
.checkbox-spacer { display: inline-block; width: 13px; }
input[type="checkbox"] { margin: 0; cursor: pointer; }
input[type="checkbox"]:disabled { cursor: default; }
.label.dir { color: var(--text-2); }
.label.file { color: var(--accent); }
</style>
