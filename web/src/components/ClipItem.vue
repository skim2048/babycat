<script setup>
import { computed, ref } from 'vue'
import { useAuth } from '../composables/useAuth.js'
import { formatDateTime, useLocale } from '../composables/useLocale.js'
import { getClipUrl } from '../endpoints.js'
import ClipPlayerModal from './ClipPlayerModal.vue'

const { getToken } = useAuth()
const { locale, t } = useLocale()

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
  locale.value
  return formatDateTime(d, {
    year: '2-digit',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: true,
  }).replace(',', '')
})

const keywords = computed(() => props.clip.keywords || [])
const keywordLabel = computed(() => keywords.value.join(', '))
const vlmText = computed(() => props.clip.vlm_text || '')

function openPlayer() {
  playerOpen.value = true
}
</script>

<template>
  <div class="clip-card" :class="[viewMode, { checked: isChecked }]">
    <label class="list-check list-only" @click.stop>
      <input type="checkbox" class="clip-chk" :checked="isChecked" @change="emit('check', $event.target.checked)" />
    </label>

    <div class="clip-header gallery-only">
      <input type="checkbox" class="clip-chk" :checked="isChecked" @change="emit('check', $event.target.checked)" />
      <span class="clip-time">{{ timeLabel }}</span>
      <button class="clip-delete-btn gallery-delete-btn" @click="emit('delete')" :aria-label="t('clips.item.delete')">
        <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <path d="M2.5 4h11" /><path d="M6 2h4" /><path d="M5 4v8" /><path d="M8 4v8" /><path d="M11 4v8" />
          <path d="M3.5 4.5l.5 9a1 1 0 0 0 1 .9h6a1 1 0 0 0 1-.9l.5-9" />
        </svg>
      </button>
    </div>

    <div class="clip-preview" @click="openPlayer">
      <video :src="clipSrc" preload="metadata" muted playsinline></video>
      <div class="clip-overlay">
        <div class="clip-play-icon"></div>
      </div>
    </div>

    <div class="list-meta list-only">
      <span class="list-time">{{ timeLabel }}</span>
      <div class="list-info">
        <div class="list-kw-badges">
          <template v-if="keywords.length > 0">
            <span v-for="kw in keywords" :key="kw" class="clip-badge">{{ kw }}</span>
          </template>
          <span v-else class="list-kw-empty">—</span>
        </div>
        <span class="list-vlm">{{ vlmText || '—' }}</span>
      </div>
    </div>

    <button class="clip-delete-btn list-delete-btn list-only" @click="emit('delete')" :aria-label="t('clips.item.delete')">
      <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
        <path d="M2.5 4h11" /><path d="M6 2h4" /><path d="M5 4v8" /><path d="M8 4v8" /><path d="M11 4v8" />
        <path d="M3.5 4.5l.5 9a1 1 0 0 0 1 .9h6a1 1 0 0 0 1-.9l.5-9" />
      </svg>
    </button>

    <div v-if="keywords.length > 0" class="clip-badges gallery-only">
      <span v-for="kw in keywords" :key="kw" class="clip-badge">{{ kw }}</span>
    </div>

    <div v-if="vlmText" class="clip-vlm gallery-only">
      <div class="clip-vlm-text" :class="{ expanded }">{{ vlmText }}</div>
      <button class="clip-expand-btn" @click="expanded = !expanded" :class="{ open: expanded }" :aria-label="t('clips.item.expand')">
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
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
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

.gallery-only {
  display: block;
}
.list-only {
  display: none;
}

.clip-card.gallery {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px;
}
.clip-card.gallery .gallery-only {
  display: flex;
}

.clip-card.list {
  display: grid;
  grid-template-columns: 36px 88px minmax(0, 1fr) 48px;
  grid-template-areas: "list-check preview list-meta list-delete";
  min-height: 56px;
  max-height: 56px;
  padding: 0;
  overflow: hidden;
}
.clip-card.list .gallery-only {
  display: none !important;
}
.clip-card.list .list-only {
  display: flex;
}

.list-check {
  grid-area: list-check;
  align-items: center;
  justify-content: center;
  cursor: pointer;
}

.clip-header {
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

.clip-preview {
  position: relative;
  width: 100%;
  aspect-ratio: 16 / 9;
  background: var(--clip-bg);
  border-radius: var(--radius);
  overflow: hidden;
  cursor: pointer;
}
.clip-preview video {
  width: 100%;
  height: 100%;
  display: block;
  object-fit: contain;
}

.clip-card.list .clip-preview {
  grid-area: preview;
  width: 88px;
  height: 56px;
  aspect-ratio: auto;
  border-radius: 0;
  border-left: 1px solid var(--border);
  border-right: 1px solid var(--border);
}
.clip-card.list .clip-preview video {
  object-fit: cover;
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

.clip-card.list .clip-play-icon {
  width: 22px;
  height: 22px;
}
.clip-card.list .clip-play-icon::after {
  border-width: 5px 0 5px 8px;
  margin-left: 2px;
}

.list-meta {
  grid-area: list-meta;
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
.list-kw-badges {
  display: flex;
  flex-wrap: nowrap;
  gap: 4px;
  overflow: hidden;
}
.list-kw-empty {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-2);
}
.list-vlm {
  font-size: 12px;
  color: var(--text-3);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
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
  align-items: center;
  justify-content: center;
  border: none;
  background: transparent;
  color: var(--text-3);
  cursor: pointer;
}
.gallery-delete-btn {
  width: auto;
}
.list-delete-btn {
  grid-area: list-delete;
  width: 48px;
  border-left: 1px solid var(--border);
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
  .clip-card.list {
    grid-template-columns: minmax(0, 1fr) 48px;
    grid-template-areas:
      "preview preview"
      "list-meta list-delete";
    min-height: auto;
    max-height: none;
  }
  .clip-card.list .list-check {
    display: none;
  }
  .clip-card.list .clip-preview {
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
  .list-delete-btn {
    width: 48px;
    border-left: 1px solid var(--border);
  }
}
</style>
