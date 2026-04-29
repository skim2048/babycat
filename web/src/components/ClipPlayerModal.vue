<script setup>
import { nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { useLocale } from '../composables/useLocale.js'

const props = defineProps({
  open: Boolean,
  src: {
    type: String,
    required: true,
  },
})

const emit = defineEmits(['close'])
const { t } = useLocale()

const playerEl = ref(null)
const playerPlaying = ref(false)
const playerCurrentTime = ref(0)
const playerDuration = ref(0)
const playerVolume = ref(1)

watch(() => props.open, async (open) => {
  if (open) {
    document.addEventListener('keydown', onKeydown)
    await nextTick()
    const vid = playerEl.value
    if (!vid) return
    vid.volume = playerVolume.value
    vid.currentTime = 0
    await vid.play()
    return
  }
  document.removeEventListener('keydown', onKeydown)
  resetPlayer()
})

onBeforeUnmount(() => {
  document.removeEventListener('keydown', onKeydown)
  resetPlayer()
})

function closePlayer() {
  emit('close')
}

function resetPlayer() {
  const vid = playerEl.value
  if (vid) {
    vid.pause()
    vid.currentTime = 0
  }
  playerPlaying.value = false
  playerCurrentTime.value = 0
  playerDuration.value = 0
}

function togglePlayerPlay() {
  const vid = playerEl.value
  if (!vid) return
  if (vid.paused) vid.play()
  else vid.pause()
}

function onPlayerPlay() { playerPlaying.value = true }
function onPlayerPause() { playerPlaying.value = false }
function onPlayerEnded() {
  playerPlaying.value = false
  playerCurrentTime.value = 0
  if (playerEl.value) playerEl.value.currentTime = 0
}
function onLoadedMetadata() {
  playerDuration.value = playerEl.value?.duration ?? 0
}
function onTimeUpdate() {
  playerCurrentTime.value = playerEl.value?.currentTime ?? 0
}

function seekTo(e) {
  const vid = playerEl.value
  if (vid) vid.currentTime = Number(e.target.value)
}

function setVolume(e) {
  const v = Number(e.target.value)
  playerVolume.value = v
  if (playerEl.value) playerEl.value.volume = v
}

function formatTime(s) {
  if (!s || isNaN(s)) return '00:00'
  const m = Math.floor(s / 60)
  const sec = Math.floor(s % 60)
  return `${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`
}

function onKeydown(e) {
  if (!props.open) return
  if (e.key === 'Escape') {
    closePlayer()
    return
  }
  if (e.key === ' ') {
    e.preventDefault()
    togglePlayerPlay()
    return
  }
  const vid = playerEl.value
  if (!vid) return
  if (e.key === 'ArrowLeft') vid.currentTime = Math.max(0, vid.currentTime - 5)
  if (e.key === 'ArrowRight') vid.currentTime = Math.min(vid.duration, vid.currentTime + 5)
}
</script>

<template>
  <teleport to="body">
    <div v-if="open" class="player-backdrop" @click.self="closePlayer">
      <div class="player-dialog">
        <video
          ref="playerEl"
          :src="src"
          class="player-video"
          playsinline
          @play="onPlayerPlay"
          @pause="onPlayerPause"
          @ended="onPlayerEnded"
          @loadedmetadata="onLoadedMetadata"
          @timeupdate="onTimeUpdate"
        ></video>

        <div class="player-controls">
          <button class="player-btn" @click="togglePlayerPlay" :aria-label="playerPlaying ? t('player.pause') : t('player.play')">
            <svg v-if="!playerPlaying" width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
              <polygon points="3,1 14,8 3,15" />
            </svg>
            <svg v-else width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
              <rect x="2" y="1" width="5" height="14" rx="1" />
              <rect x="9" y="1" width="5" height="14" rx="1" />
            </svg>
          </button>

          <span class="player-time">{{ formatTime(playerCurrentTime) }}</span>

          <input
            type="range"
            class="player-seek"
            min="0"
            :max="playerDuration || 0"
            step="0.1"
            :value="playerCurrentTime"
            @input="seekTo"
          />

          <span class="player-time player-time-total">{{ formatTime(playerDuration) }}</span>

          <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" style="flex-shrink:0;opacity:0.6">
            <path d="M2 5h3l4-3v12l-4-3H2z" />
            <path d="M11 4a5 5 0 0 1 0 8" stroke="currentColor" stroke-width="1.5" fill="none" stroke-linecap="round" />
          </svg>
          <input
            type="range"
            class="player-volume"
            min="0"
            max="1"
            step="0.05"
            :value="playerVolume"
            @input="setVolume"
          />

          <button class="player-btn" @click="closePlayer" :aria-label="t('player.close')">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
              <line x1="2" y1="2" x2="14" y2="14" /><line x1="14" y1="2" x2="2" y2="14" />
            </svg>
          </button>
        </div>
      </div>
    </div>
  </teleport>
</template>

<style scoped>
.player-backdrop {
  position: fixed;
  inset: 0;
  z-index: 1000;
  background: rgba(0, 0, 0, 0.92);
  display: flex;
  align-items: center;
  justify-content: center;
}
.player-dialog {
  display: flex;
  flex-direction: column;
  width: 90vw;
  max-width: 1000px;
  border-radius: 10px;
  overflow: hidden;
  box-shadow: 0 24px 64px rgba(0, 0, 0, 0.6);
}
.player-video {
  width: 100%;
  max-height: 75vh;
  display: block;
  object-fit: contain;
  background: #000;
}
.player-controls {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  background: #1a1a1a;
}
.player-btn {
  flex-shrink: 0;
  width: 32px;
  height: 32px;
  background: none;
  border: none;
  color: rgba(255, 255, 255, 0.9);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  transition: background 0.12s;
}
.player-btn:hover {
  background: rgba(255, 255, 255, 0.12);
}
.player-time {
  font-size: 12px;
  font-family: var(--font-mono);
  color: rgba(255, 255, 255, 0.75);
  white-space: nowrap;
  flex-shrink: 0;
}
.player-time-total {
  color: rgba(255, 255, 255, 0.4);
}
.player-seek {
  flex: 1;
  accent-color: var(--accent);
  cursor: pointer;
  height: 4px;
}
.player-volume {
  width: 72px;
  accent-color: var(--accent);
  cursor: pointer;
  height: 4px;
}

@media (max-width: 600px) {
  .player-volume {
    display: none;
  }
}
</style>
