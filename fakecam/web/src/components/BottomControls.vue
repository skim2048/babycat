<script setup>
import { computed } from 'vue'
import { state, playback } from '../state.js'
import { useLocale } from '../composables/useLocale.js'
import Icon from './Icon.vue'

const { t } = useLocale()

const isPlaying = computed(() => state.playlist?.is_playing ?? false)
const itemCount = computed(() => state.playlist?.items?.length ?? 0)
const shuffleOn = computed(() => state.mode?.shuffle ?? false)
const repeat = computed(() => state.mode?.repeat ?? 'off')

const repeatLabel = computed(() => ({
  off: t('controls.repeatOff'),
  all: t('controls.repeatAll'),
  one: t('controls.repeatOne'),
})[repeat.value])

const playDisabled = computed(() => !isPlaying.value && itemCount.value === 0)
</script>

<template>
  <footer class="controls">
    <button
      class="ctl"
      :class="{ active: shuffleOn }"
      :title="shuffleOn ? t('controls.shuffleOn') : t('controls.shuffleOff')"
      :aria-label="t('controls.shuffleAria')"
      @click="playback.toggleShuffle"
    >
      <Icon name="shuffle" :size="22" />
    </button>

    <button
      class="ctl"
      :title="t('controls.prev')"
      :aria-label="t('controls.prev')"
      :disabled="!isPlaying"
      @click="playback.prev"
    >
      <Icon name="prev" :size="22" />
    </button>

    <button
      class="ctl"
      :title="isPlaying ? t('controls.stop') : t('controls.play')"
      :aria-label="isPlaying ? t('controls.stop') : t('controls.play')"
      :disabled="playDisabled"
      @click="isPlaying ? playback.stop() : playback.play()"
    >
      <Icon :name="isPlaying ? 'stop' : 'play'" :size="22" />
    </button>

    <button
      class="ctl"
      :title="t('controls.next')"
      :aria-label="t('controls.next')"
      :disabled="!isPlaying"
      @click="playback.next"
    >
      <Icon name="next" :size="22" />
    </button>

    <button
      class="ctl"
      :class="{ active: repeat !== 'off' }"
      :title="repeatLabel"
      :aria-label="t('controls.repeatAria')"
      @click="playback.cycleRepeat"
    >
      <Icon :name="repeat === 'one' ? 'repeat-one' : 'repeat'" :size="22" />
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
  width: 44px;
  height: 44px;
  border-radius: 50%;
  padding: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: var(--ctl-bg);
  border: 1px solid var(--ctl-border);
  color: var(--text-2);
}
.ctl:hover:not(:disabled) { background: var(--ctl-bg-hover); color: var(--text-1); }
.ctl.active { color: var(--accent); border-color: var(--accent); }
.ctl:disabled { opacity: 0.4; }
</style>
