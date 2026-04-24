<script setup>
import { computed, ref } from 'vue'
import { useClips } from '../composables/useClips.js'
import ClipItem from './ClipItem.vue'

const { clips, checked, searchQuery, deleteSelected, deleteClips, toggleCheck } = useClips()
const viewMode = ref('gallery')

const filteredClips = computed(() => {
  const q = searchQuery.value.trim().toLowerCase()
  if (!q) return clips.value
  return clips.value.filter((c) => c.name.toLowerCase().includes(q))
})

const selectedCount = computed(() =>
  filteredClips.value.filter((c) => checked.value[c.name]).length,
)

function toggleSelectAll() {
  const next = { ...checked.value }
  if (selectedCount.value > 0) {
    for (const c of filteredClips.value) delete next[c.name]
  } else {
    for (const c of filteredClips.value) next[c.name] = true
  }
  checked.value = next
}
</script>

<template>
  <div class="clips-panel">
    <div class="clips-toolbar">
      <input type="text" class="clip-search" v-model="searchQuery" placeholder="검색..." />
      <div class="view-mode-group" role="group" aria-label="보기 모드">
        <button
          class="clip-action-btn"
          :class="{ active: viewMode === 'gallery' }"
          @click="viewMode = 'gallery'"
        >
          갤러리
        </button>
        <button
          class="clip-action-btn"
          :class="{ active: viewMode === 'list' }"
          @click="viewMode = 'list'"
        >
          리스트
        </button>
      </div>
      <button
        class="clip-action-btn"
        :disabled="filteredClips.length === 0"
        @click="toggleSelectAll"
      >
        {{ selectedCount > 0 ? '선택 해제' : '모두 선택' }}
      </button>
      <button class="clip-action-btn danger" :disabled="selectedCount === 0" @click="deleteSelected">
        {{ selectedCount > 0 ? `삭제 (${selectedCount})` : '삭제' }}
      </button>
    </div>

    <div class="clips-gallery" :class="{ 'clips-list': viewMode === 'list' }">
      <template v-if="filteredClips.length > 0">
        <ClipItem
          v-for="clip in filteredClips"
          :key="clip.name"
          :clip="clip"
          :is-checked="!!checked[clip.name]"
          :view-mode="viewMode"
          @check="(val) => toggleCheck(clip.name, val)"
          @delete="deleteClips([clip.name])"
        />
      </template>
      <div v-else class="clip-empty">녹화된 클립 없음</div>
    </div>
  </div>
</template>

<style scoped>
.clips-panel {
  display: flex;
  flex-direction: column;
  gap: 12px;
  height: 100%;
}

.clips-toolbar {
  display: flex;
  gap: 6px;
  align-items: center;
  flex-wrap: wrap;
  flex-shrink: 0;
}
.view-mode-group {
  display: inline-flex;
  gap: 4px;
  padding: 2px;
  border: 1px solid var(--border-input);
  border-radius: calc(var(--radius) + 2px);
  background: var(--bg-surface-secondary);
}
.clips-gallery {
  flex: 1;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 12px;
  overflow-y: auto;
  padding: 2px;
  align-content: start;
}
.clips-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.clip-empty {
  grid-column: 1 / -1;
  font-size: 12px;
  color: var(--text-4);
  padding: 40px 0;
  text-align: center;
}
.clip-action-btn.active {
  background: var(--accent);
  border-color: var(--accent);
  color: #fff;
}
.clips-gallery::-webkit-scrollbar { width: 6px; }
.clips-gallery::-webkit-scrollbar-track { background: transparent; }
.clips-gallery::-webkit-scrollbar-thumb { background: var(--scrollbar); border-radius: 3px; }
.clips-gallery::-webkit-scrollbar-thumb:hover { background: var(--scrollbar-hover); }
</style>
