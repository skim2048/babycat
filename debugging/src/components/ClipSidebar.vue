<script setup>
import { computed } from 'vue'
import { useClips } from '../composables/useClips.js'
import ClipItem from './ClipItem.vue'

const { clips, checked, searchQuery, deleteAll, deleteSelected, deleteClips, toggleCheck } = useClips()

const selectedCount = computed(() =>
  Object.values(checked.value).filter(Boolean).length,
)

const filteredClips = computed(() => {
  const q = searchQuery.value.trim().toLowerCase()
  if (!q) return clips.value
  return clips.value.filter((c) => c.name.toLowerCase().includes(q))
})
</script>

<template>
  <div class="clip-sidebar">
    <div class="video-label">Event Clips</div>
    <div class="clip-toolbar">
      <input type="text" class="clip-search" v-model="searchQuery" placeholder="검색..." />
      <button class="clip-action-btn danger" :disabled="selectedCount === 0" @click="deleteSelected">
        {{ selectedCount > 0 ? `선택 삭제 (${selectedCount})` : '선택 삭제' }}
      </button>
      <button class="clip-action-btn danger" @click="deleteAll">모두 삭제</button>
    </div>
    <div class="clip-gallery">
      <template v-if="filteredClips.length > 0">
        <ClipItem
          v-for="clip in filteredClips"
          :key="clip.name"
          :clip="clip"
          :is-checked="!!checked[clip.name]"
          @check="(val) => toggleCheck(clip.name, val)"
          @delete="deleteClips([clip.name])"
        />
      </template>
      <div v-else class="clip-empty">녹화된 클립 없음</div>
    </div>
  </div>
</template>
