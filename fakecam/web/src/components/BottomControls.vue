<script setup>
import { computed } from 'vue'
import { state, playback } from '../state.js'

const isPlaying = computed(() => state.playlist?.is_playing ?? false)
const itemCount = computed(() => state.playlist?.items?.length ?? 0)
const shuffleOn = computed(() => state.mode?.shuffle ?? false)
const repeat = computed(() => state.mode?.repeat ?? 'off')

const repeatLabel = computed(() => ({
  off: '반복 끄기',
  all: '전체 반복',
  one: '단일 반복',
})[repeat.value])

const playDisabled = computed(() => !isPlaying.value && itemCount.value === 0)
</script>

<template>
  <footer class="controls">
    <button
      class="ctl"
      :class="{ active: shuffleOn }"
      :title="shuffleOn ? '셔플 끄기' : '셔플 켜기'"
      @click="playback.toggleShuffle"
    >🔀</button>

    <button
      class="ctl"
      title="이전 파일"
      :disabled="!isPlaying"
      @click="playback.prev"
    >⏮</button>

    <button
      class="ctl primary"
      :title="isPlaying ? '정지' : '재생'"
      :disabled="playDisabled"
      @click="isPlaying ? playback.stop() : playback.play()"
    >
      <span v-if="isPlaying">⏹</span>
      <span v-else>▶</span>
    </button>

    <button
      class="ctl"
      title="다음 파일"
      :disabled="!isPlaying"
      @click="playback.next"
    >⏭</button>

    <button
      class="ctl"
      :class="{ active: repeat !== 'off' }"
      :title="repeatLabel"
      @click="playback.cycleRepeat"
    >
      <span v-if="repeat === 'one'">🔂</span>
      <span v-else>🔁</span>
    </button>
  </footer>
</template>

<style scoped>
.controls {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 12px;
  border-top: 1px solid var(--border);
  background: var(--bg-surface);
}
.ctl {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  padding: 0;
  font-size: 16px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: #2a2a2a;
  border: 1px solid #444;
  color: var(--text-2);
}
.ctl:hover:not(:disabled) { background: #333; color: var(--text-1); }
.ctl.active { color: var(--accent); border-color: var(--accent); }
.ctl.primary {
  width: 48px;
  height: 48px;
  font-size: 18px;
}
.ctl:disabled { opacity: 0.4; }
</style>
