<script setup>
import { ref, computed } from 'vue'
import { useAuth } from '../composables/useAuth.js'
import { getClipUrl } from '../endpoints.js'

const { getToken } = useAuth()

const props = defineProps({
  clip: Object,
  isChecked: Boolean,
})
const emit = defineEmits(['check', 'delete'])

const videoEl = ref(null)
const wrapEl = ref(null)
const playing = ref(false)
const isFullscreen = ref(false)
const expanded = ref(false)

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
const vlmText = computed(() => props.clip.vlm_text || '')

function togglePlay() {
  const vid = videoEl.value
  if (vid.paused) {
    vid.muted = false
    vid.play()
  } else {
    vid.pause()
  }
}

function onPlay() { playing.value = true }
function onPause() { playing.value = false }
function onEnded() {
  const vid = videoEl.value
  vid.muted = true
  vid.currentTime = 0
  playing.value = false
}
function toggleFullscreen(e) {
  e.stopPropagation()
  const el = wrapEl.value
  if (!el) return
  if (!document.fullscreenElement) {
    el.requestFullscreen()
  } else {
    document.exitFullscreen()
  }
}
function onFullscreenChange() {
  isFullscreen.value = !!document.fullscreenElement
}
</script>

<template>
  <div class="clip-card" :class="{ checked: isChecked }">
    <div class="clip-header">
      <input type="checkbox" class="clip-chk" :checked="isChecked" @change="emit('check', $event.target.checked)" />
      <span class="clip-time">{{ timeLabel }}</span>
    </div>

    <div ref="wrapEl" class="clip-video-wrap" @fullscreenchange="onFullscreenChange" @click="togglePlay">
      <video
        ref="videoEl"
        :src="clipSrc"
        preload="metadata"
        muted
        playsinline
        @play="onPlay"
        @pause="onPause"
        @ended="onEnded"
      ></video>
      <div class="clip-overlay" :class="{ hidden: playing }">
        <div class="clip-play-icon"></div>
      </div>
      <button class="clip-fs-btn" @click="toggleFullscreen">
        <svg v-if="!isFullscreen" width="14" height="14" viewBox="0 0 18 18" fill="none" stroke="rgba(255,255,255,0.9)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="11,1 17,1 17,7" />
          <polyline points="7,17 1,17 1,11" />
        </svg>
        <svg v-else width="14" height="14" viewBox="0 0 18 18" fill="none" stroke="rgba(255,255,255,0.9)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="17,7 11,7 11,1" />
          <polyline points="1,11 7,11 7,17" />
        </svg>
      </button>
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
.clip-video-wrap:fullscreen {
  background: #000;
}
.clip-video-wrap:fullscreen video {
  object-fit: contain;
}
.clip-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--overlay);
  transition: opacity 0.2s;
  pointer-events: none;
}
.clip-overlay.hidden {
  opacity: 0;
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

.clip-fs-btn {
  position: absolute;
  bottom: 6px;
  right: 6px;
  width: 28px;
  height: 28px;
  border: none;
  border-radius: 6px;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: background 0.15s;
  z-index: 2;
}
.clip-fs-btn:hover {
  background: rgba(0, 0, 0, 0.75);
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
</style>
