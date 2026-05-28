<script setup>
import { computed } from 'vue'
import { state, removeCheckedFromPlaylist } from '../state.js'
import { useLocale } from '../composables/useLocale.js'
import Icon from './Icon.vue'

const { t } = useLocale()

const items = computed(() => state.playlist?.items ?? [])
const isPlaying = computed(() => state.playlist?.is_playing ?? false)
const currentPath = computed(() => state.playlist?.current_path ?? null)
const disabled = computed(() => isPlaying.value)
const checkedCount = computed(() => state.playlistChecked.size)

const filteredItems = computed(() => {
  const q = state.playlistQuery.trim().toLowerCase()
  if (!q) return items.value
  return items.value.filter(
    (it) =>
      it.name.toLowerCase().includes(q) || it.path.toLowerCase().includes(q),
  )
})

const allVisibleChecked = computed(
  () =>
    filteredItems.value.length > 0 &&
    filteredItems.value.every((it) => state.playlistChecked.has(it.path)),
)
const someVisibleChecked = computed(() =>
  filteredItems.value.some((it) => state.playlistChecked.has(it.path)),
)

function toggleChecked(path) {
  if (disabled.value) return
  if (state.playlistChecked.has(path)) state.playlistChecked.delete(path)
  else state.playlistChecked.add(path)
}

function toggleSelectAll() {
  if (disabled.value || filteredItems.value.length === 0) return
  if (allVisibleChecked.value) {
    for (const it of filteredItems.value) state.playlistChecked.delete(it.path)
  } else {
    for (const it of filteredItems.value) state.playlistChecked.add(it.path)
  }
}
</script>

<template>
  <section class="pane">
    <header>
      <h2>{{ t('playlist.title') }}</h2>
    </header>
    <div class="toolbar">
      <label class="select-all" :class="{ disabled }">
        <input
          type="checkbox"
          :checked="allVisibleChecked"
          :indeterminate.prop="!allVisibleChecked && someVisibleChecked"
          :disabled="disabled || filteredItems.length === 0"
          @change="toggleSelectAll"
        />
        <span>{{ t('common.selectAll') }}</span>
      </label>
      <input
        v-model="state.playlistQuery"
        type="search"
        class="search"
        :placeholder="t('playlist.search')"
      />
      <button
        class="action"
        :disabled="disabled || checkedCount === 0"
        :title="disabled ? t('common.disabledPlaying') : t('playlist.removeTitle')"
        :aria-label="t('playlist.removeAria')"
        @click="removeCheckedFromPlaylist"
      >
        <Icon name="remove" :size="14" />
        <span v-if="checkedCount > 0" class="count">{{ checkedCount }}</span>
      </button>
    </div>
    <ul v-if="filteredItems.length" class="list">
      <li
        v-for="item in filteredItems"
        :key="item.path"
        :class="{ current: currentPath === item.path }"
        @click="toggleChecked(item.path)"
      >
        <input
          type="checkbox"
          :checked="state.playlistChecked.has(item.path)"
          :disabled="disabled"
          @click.stop="toggleChecked(item.path)"
        />
        <span class="name">{{ item.name }}</span>
        <span class="path">{{ item.path }}</span>
      </li>
    </ul>
    <div v-else-if="items.length" class="empty">{{ t('playlist.noMatch') }}</div>
    <div v-else-if="state.playlist" class="empty">{{ t('playlist.empty') }}</div>
    <div v-else class="empty">{{ t('common.loading') }}</div>
    <div v-if="state.mutationError" class="error">{{ state.mutationError }}</div>
  </section>
</template>

<style scoped>
.pane { display: flex; flex-direction: column; min-width: 0; }
header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: var(--bg-surface);
  border-bottom: 1px solid var(--border);
}
header h2 { margin: 0; font-size: 12px; flex: 1; }
.action { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; line-height: 1; padding: 4px 8px; }
.action .count {
  font-size: 12px;
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
.list { list-style: none; padding: 8px 0; margin: 0; overflow: auto; flex: 1; font-size: 12px; }
.list li {
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: center;
  gap: 8px;
  padding: 4px 12px;
  cursor: pointer;
  user-select: none;
}
.list li:hover { background: var(--bg-hover); }
.list li.current { background: var(--bg-active); }
input[type="checkbox"] { margin: 0; cursor: pointer; }
input[type="checkbox"]:disabled { cursor: default; }
.name { color: var(--text-1); }
.path { color: var(--text-4); font-size: 12px; }
.empty { color: var(--text-4); padding: 12px; }
.error { color: var(--danger); padding: 8px 12px; font-size: 12px; border-top: 1px solid var(--border); }
</style>
