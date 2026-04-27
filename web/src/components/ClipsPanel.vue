<script setup>
import { computed, ref, watch } from 'vue'
import { useClips } from '../composables/useClips.js'
import ClipItem from './ClipItem.vue'

const { clips, checked, searchQuery, deleteSelected, deleteClips, toggleCheck } = useClips()
const viewMode = ref('gallery')

const filteredClips = computed(() => {
  const q = searchQuery.value.trim().toLowerCase()
  if (!q) return clips.value
  return clips.value.filter((c) => c.name.toLowerCase().includes(q))
})

const PAGE_SIZE = 10
const currentPage = ref(1)

watch(filteredClips, () => { currentPage.value = 1 })

const totalPages = computed(() => Math.max(1, Math.ceil(filteredClips.value.length / PAGE_SIZE)))

const pagedClips = computed(() => {
  const start = (currentPage.value - 1) * PAGE_SIZE
  return filteredClips.value.slice(start, start + PAGE_SIZE)
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
          class="view-mode-btn"
          :class="{ active: viewMode === 'gallery' }"
          @click="viewMode = 'gallery'"
          aria-label="갤러리 보기"
          :aria-pressed="viewMode === 'gallery'"
        >
          <svg width="15" height="15" viewBox="0 0 16 16" fill="currentColor">
            <rect x="1" y="1" width="6" height="6" rx="1" />
            <rect x="9" y="1" width="6" height="6" rx="1" />
            <rect x="1" y="9" width="6" height="6" rx="1" />
            <rect x="9" y="9" width="6" height="6" rx="1" />
          </svg>
        </button>
        <button
          class="view-mode-btn"
          :class="{ active: viewMode === 'list' }"
          @click="viewMode = 'list'"
          aria-label="리스트 보기"
          :aria-pressed="viewMode === 'list'"
        >
          <svg width="15" height="15" viewBox="0 0 16 16" fill="currentColor">
            <rect x="1" y="2" width="14" height="2" rx="1" />
            <rect x="1" y="7" width="14" height="2" rx="1" />
            <rect x="1" y="12" width="14" height="2" rx="1" />
          </svg>
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
      <template v-if="pagedClips.length > 0">
        <ClipItem
          v-for="clip in pagedClips"
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

    <div v-if="totalPages > 1" class="clips-pagination">
      <button class="page-btn" :disabled="currentPage === 1" @click="currentPage--" aria-label="이전 페이지">
        <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="10,2 4,8 10,14" />
        </svg>
      </button>
      <span class="page-info">{{ currentPage }} / {{ totalPages }}</span>
      <button class="page-btn" :disabled="currentPage === totalPages" @click="currentPage++" aria-label="다음 페이지">
        <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="6,2 12,8 6,14" />
        </svg>
      </button>
      <span class="page-count">{{ filteredClips.length }}개 중 {{ (currentPage - 1) * PAGE_SIZE + 1 }}–{{ Math.min(currentPage * PAGE_SIZE, filteredClips.length) }}</span>
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
  gap: 2px;
  padding: 2px;
  border: 1px solid var(--border-input);
  border-radius: calc(var(--radius) + 2px);
  background: var(--bg-surface-secondary);
}
.view-mode-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 26px;
  border: none;
  border-radius: var(--radius);
  background: transparent;
  color: var(--text-3);
  cursor: pointer;
  transition: background 0.12s, color 0.12s;
}
.view-mode-btn:hover {
  background: var(--bg-surface-hover);
  color: var(--text-1);
}
.view-mode-btn.active {
  background: var(--accent);
  color: #fff;
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
.clips-pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  flex-shrink: 0;
  padding: 4px 0;
}
.page-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border: 1px solid var(--border-input);
  border-radius: var(--radius);
  background: var(--bg-surface);
  color: var(--text-2);
  cursor: pointer;
  transition: background 0.12s, color 0.12s;
}
.page-btn:hover:not(:disabled) {
  background: var(--bg-surface-hover);
  color: var(--text-1);
}
.page-btn:disabled {
  opacity: 0.35;
  cursor: default;
}
.page-info {
  font-size: 13px;
  font-family: var(--font-mono);
  color: var(--text-2);
  min-width: 52px;
  text-align: center;
}
.page-count {
  font-size: 11px;
  color: var(--text-4);
  margin-left: 4px;
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
