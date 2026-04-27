<script setup>
import { computed, ref } from 'vue'
import { useAuth } from '../composables/useAuth.js'
import { getClipUrl } from '../endpoints.js'
import ClipPlayerModal from './ClipPlayerModal.vue'

const { getToken } = useAuth()

const props = defineProps({
  clip: Object,
  isChecked: Boolean,
  viewMode: {
    type: String,
    default: 'gallery',
  },
})
const emit = defineEmits(['check', 'delete'])

const expanded = ref(false)
const playerOpen = ref(false)

const clipSrc = computed(() =>
  getClipUrl(props.clip.name, props.clip.size, getToken()),
)

const timeLabel = computed(() => {
  const ts = props.clip.timestamp ?? props.clip.mtime ?? 0
  if (!ts) return ''
  const d = new Date(ts * 1000)
  const yy = String(d.getFullYear()).slice(2)
  const mm = String(d.getMonth() + 1).padStart(2, '0')
  const dd = String(d.getDate()).padStart(2, '0')
  const h = d.getHours()
  const min = String(d.getMinutes()).padStart(2, '0')
  const ampm = h < 12 ? 'AM' : 'PM'
  const h12 = h % 12 || 12
  return `${yy}-${mm}-${dd}  ${ampm} ${String(h12).padStart(2, '0')}:${min}`
})

const keywords = computed(() => props.clip.keywords || [])
const keywordLabel = computed(() => keywords.value.join(', '))
const vlmText = computed(() => props.clip.vlm_text || '')

function openPlayer() {
  playerOpen.value = true
}
</script>

<template>
  <div v-if="viewMode === 'list'" class="clip-card list" :class="{ checked: isChecked }">
    <label class="list-check" @click.stop>
      <input type="checkbox" class="clip-chk" :checked="isChecked" @change="emit('check', $event.target.checked)" />
    </label>

    <div class="list-thumb" @click="openPlayer">
      <video :src="clipSrc" preload="metadata" muted playsinline></video>
      <div class="clip-overlay">
        <div class="clip-play-icon"></div>
      </div>
    </div>

    <div class="list-meta">
      <span class="list-time">{{ timeLabel }}</span>
      <div class="list-info">
        <span class="list-kw">{{ keywordLabel || '—' }}</span>
        <span class="list-vlm">{{ vlmText || '—' }}</span>
      </div>
    </div>

    <button class="clip-delete-btn" @click="emit('delete')" aria-label="클립 삭제">
      <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
        <path d="M2.5 4h11" /><path d="M6 2h4" /><path d="M5 4v8" /><path d="M8 4v8" /><path d="M11 4v8" />
        <path d="M3.5 4.5l.5 9a1 1 0 0 0 1 .9h6a1 1 0 0 0 1-.9l.5-9" />
      </svg>
    </button>
  </div>

  <div v-else class="clip-card" :class="{ checked: isChecked }">
    <div class="clip-header">
      <input type="checkbox" class="clip-chk" :checked="isChecked" @change="emit('check', $event.target.checked)" />
      <span class="clip-time">{{ timeLabel }}</span>
      <button class="clip-delete-btn" @click="emit('delete')" aria-label="클립 삭제">
        <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <path d="M2.5 4h11" /><path d="M6 2h4" /><path d="M5 4v8" /><path d="M8 4v8" /><path d="M11 4v8" />
          <path d="M3.5 4.5l.5 9a1 1 0 0 0 1 .9h6a1 1 0 0 0 1-.9l.5-9" />
        </svg>
      </button>
    </div>

    <div class="clip-video-wrap" @click="openPlayer">
      <video :src="clipSrc" preload="metadata" muted playsinline></video>
      <div class="clip-overlay">
        <div class="clip-play-icon"></div>
      </div>
    </div>

    <div v-if="keywords.length > 0" class="clip-badges">
      <span v-for="kw in keywords" :key="kw" class="clip-badge">{{ kw }}</span>
    </div>

    <div v-if="vlmText" class="clip-vlm">
      <div class="clip-vlm-text" :class="{ expanded }">{{ vlmText }}</div>
      <button class="clip-expand-btn" @click="expanded = !expanded" :class="{ open: expanded }" aria-label="펼치기">
        <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="4,6 8,10 12,6" />
        </svg>
      </button>
    </div>
  </div>

  <ClipPlayerModal
    :open="playerOpen"
    :src="clipSrc"
    @close="playerOpen = false"
  />
</template>

<style scoped>
.clip-card {
  display: flex;
  flex-direction: column;
  gap: 8px;
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 10px;
  box-shadow: var(--shadow-sm);
  transition: border-color 0.15s, box-shadow 0.15s;
}
.clip-card:hover {
  box-shadow: var(--shadow-md);
}
.clip-card.checked {
  border-color: var(--accent);
  box-shadow: 0 0 0 2px var(--accent-shadow);
}
.list {
  flex-direction: row;
  align-items: center;
  height: 56px;
  min-height: 56px;
  max-height: 56px;
  gap: 0;
  padding: 0;
  overflow: hidden;
}
.list-check {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  flex-shrink: 0;
  cursor: pointer;
}
.list-thumb {
  position: relative;
  width: 88px;
  height: 56px;
  flex-shrink: 0;
  background: var(--clip-bg);
  border-left: 1px solid var(--border);
  border-right: 1px solid var(--border);
  cursor: pointer;
  overflow: hidden;
}
.list-thumb video {
  width: 100%;
  height: 100%;
  display: block;
  object-fit: cover;
}
.list-thumb .clip-play-icon {
  width: 22px;
  height: 22px;
}
.list-thumb .clip-play-icon::after {
  border-width: 5px 0 5px 8px;
  margin-left: 2px;
}
.list-meta {
  flex: 1;
  display: flex;
  align-items: center;
  min-width: 0;
  overflow: hidden;
  height: 100%;
}
.list-time {
  font-size: 12px;
  font-family: var(--font-mono);
  color: var(--text-2);
  white-space: nowrap;
  flex-shrink: 0;
  padding: 0 14px;
  border-right: 1px solid var(--border);
  height: 100%;
  display: flex;
  align-items: center;
}
.list-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 3px;
  padding: 0 14px;
  min-width: 0;
  overflow: hidden;
}
.list-kw {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-2);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.list-vlm {
  font-size: 12px;
  color: var(--text-3);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.clip-header {
  display: flex;
  align-items: center;
  gap: 8px;
}
.clip-chk {
  width: 15px;
  height: 15px;
  cursor: pointer;
  accent-color: var(--accent);
}
.clip-time {
  flex: 1;
  font-size: 12px;
  font-family: var(--font-mono);
  color: var(--text-2);
  font-weight: 500;
}
.clip-video-wrap {
  position: relative;
  width: 100%;
  aspect-ratio: 16 / 9;
  background: var(--clip-bg);
  border-radius: var(--radius);
  overflow: hidden;
  cursor: pointer;
}
.clip-video-wrap video {
  width: 100%;
  height: 100%;
  display: block;
  object-fit: contain;
}
.clip-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--overlay);
  pointer-events: none;
}
.clip-play-icon {
  width: 40px;
  height: 40px;
  background: var(--play-icon-bg);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
}
.clip-play-icon::after {
  content: "";
  display: block;
  width: 0;
  height: 0;
  border-style: solid;
  border-width: 8px 0 8px 14px;
  border-color: transparent transparent transparent var(--play-icon-arrow);
  margin-left: 3px;
}
.clip-badges {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.clip-badge {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--bg-surface-secondary);
  color: var(--text-2);
}
.clip-vlm {
  display: flex;
  align-items: flex-start;
  gap: 4px;
}
.clip-vlm-text {
  flex: 1;
  font-size: 12px;
  color: var(--text-2);
  line-height: 1.5;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.clip-vlm-text.expanded {
  white-space: normal;
}
.clip-expand-btn {
  flex-shrink: 0;
  background: none;
  border: none;
  color: var(--text-3);
  cursor: pointer;
  padding: 2px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
  transition: background 0.12s, transform 0.2s;
}
.clip-expand-btn:hover {
  background: var(--bg-surface-hover);
}
.clip-expand-btn.open {
  transform: rotate(180deg);
}
.clip-delete-btn {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 48px;
  border: none;
  border-left: 1px solid var(--border);
  background: transparent;
  color: var(--text-3);
  cursor: pointer;
}
.clip-header .clip-delete-btn {
  width: auto;
  border-left: none;
}
.clip-delete-btn:hover {
  background: transparent;
  color: var(--danger);
}
.clip-delete-btn svg {
  padding: 7px;
  border-radius: 8px;
  transition: background 0.15s, color 0.15s;
  box-sizing: content-box;
}
.clip-delete-btn:hover svg {
  background: var(--danger-bg);
}

@media (max-width: 600px) {
  .list {
    height: auto;
    min-height: auto;
    max-height: none;
    flex-direction: column;
    align-items: stretch;
  }
  .list-check {
    display: none;
  }
  .list-thumb {
    width: 100%;
    height: auto;
    aspect-ratio: 16 / 9;
    border-left: none;
    border-right: none;
    border-bottom: 1px solid var(--border);
  }
  .list-meta {
    flex-direction: column;
    align-items: flex-start;
    height: auto;
  }
  .list-time {
    border-right: none;
    border-bottom: 1px solid var(--border);
    height: auto;
    min-height: 36px;
    width: 100%;
  }
  .list-info {
    padding: 10px 14px;
  }
  .list-vlm {
    white-space: normal;
    overflow: visible;
  }
}
</style>
