<script setup>
import { computed, ref } from 'vue'
import { state } from '../state.js'
import { buildRtspUrl } from '../streamUrl.js'
import { useLocale } from '../composables/useLocale.js'

const { t } = useLocale()

const settings = computed(() => state.settings)
const playlist = computed(() => state.playlist)
const mode = computed(() => state.mode)

const url = computed(() => buildRtspUrl(settings.value))

const currentItem = computed(() => {
  const items = playlist.value?.items ?? []
  const cp = playlist.value?.current_path
  return cp ? items.find((it) => it.path === cp) : null
})

const positionLabel = computed(() => {
  const items = playlist.value?.items ?? []
  const cp = playlist.value?.current_path
  if (!cp || items.length === 0) return ''
  const idx = items.findIndex((it) => it.path === cp)
  return idx >= 0 ? `${idx + 1} / ${items.length}` : ''
})

const repeatLabel = computed(() => {
  const r = mode.value?.repeat ?? 'off'
  return r === 'off' ? t('mode.repeatOff') : r === 'all' ? t('mode.repeatAll') : t('mode.repeatOne')
})

const audioLabel = computed(() =>
  settings.value?.audio === 'keep' ? t('params.audioKeep') : t('params.audioDrop'),
)

const passwordRevealed = ref(false)
const passwordMasked = computed(() => {
  const p = settings.value?.auth_password ?? ''
  return passwordRevealed.value ? p : '•'.repeat(Math.max(p.length, 4))
})
</script>

<template>
  <section class="dashboard" :class="{ playing: playlist?.is_playing }">
    <div class="card connection">
      <div class="card-header">
        <span class="card-title">{{ t('dashboard.uri') }}</span>
      </div>
      <div class="url-row">
        <span class="url">{{ url || t('dashboard.loading') }}</span>
      </div>
      <div class="auth-row" v-if="settings">
        <span class="auth-label">{{ t('dashboard.user') }}</span>
        <span class="auth-value">{{ settings.auth_user }}</span>
        <span class="auth-label">{{ t('dashboard.password') }}</span>
        <span class="auth-value">{{ passwordMasked }}</span>
        <button
          class="ghost tiny"
          @click="passwordRevealed = !passwordRevealed"
        >{{ passwordRevealed ? t('dashboard.hide') : t('dashboard.show') }}</button>
      </div>
    </div>

    <div class="card now-playing">
      <div class="card-header">
        <span class="card-title">{{ t('dashboard.status') }}</span>
        <span class="status" :class="{ on: playlist?.is_playing }">
          {{ playlist?.is_playing ? t('dashboard.statusOn') : t('dashboard.statusOff') }}
        </span>
      </div>
      <div class="np-body">
        <template v-if="playlist?.is_playing && currentItem">
          <div class="np-name">▶ {{ currentItem.name }}</div>
          <div class="np-path">{{ currentItem.path }}</div>
          <div class="np-meta">
            <span class="meta-pill">{{ positionLabel }}</span>
            <span class="meta-pill" :class="{ active: mode?.shuffle }">
              {{ mode?.shuffle ? t('mode.shuffleOn') : t('mode.shuffleOff') }}
            </span>
            <span class="meta-pill" :class="{ active: mode?.repeat !== 'off' }">
              {{ repeatLabel }}
            </span>
          </div>
        </template>
        <template v-else>
          <div class="np-idle">{{ t('dashboard.idle') }}</div>
        </template>
      </div>
    </div>

    <div class="card transcode" v-if="settings">
      <div class="card-header">
        <span class="card-title">{{ t('dashboard.params') }}</span>
      </div>
      <div class="transcode-grid">
        <span class="t-label">{{ t('params.resolution') }}</span>
        <span class="t-value">{{ settings.resolution }}</span>
        <span class="t-label">{{ t('params.fps') }}</span>
        <span class="t-value">{{ settings.fps }} {{ t('params.fpsUnit') }}</span>
        <span class="t-label">{{ t('params.bitrate') }}</span>
        <span class="t-value">{{ settings.bitrate_mbps }} {{ t('params.mbps') }}</span>
        <span class="t-label">{{ t('params.audio') }}</span>
        <span class="t-value">{{ audioLabel }}</span>
      </div>
    </div>
  </section>
</template>

<style scoped>
.dashboard {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
  padding: 12px 16px;
  background: var(--bg-page);
  border-bottom: 1px solid var(--border);
  font-family: var(--font-ui);
}

.card {
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 0;
}

.dashboard.playing .now-playing { border-color: var(--primary-border); }

.card-header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
}
.card-title {
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--text-1);
}

.url-row {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.url {
  flex: 1;
  min-width: 0;
  font-size: 12px;
  color: var(--accent);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  font-family: var(--font-ui);
}

.auth-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  flex-wrap: wrap;
}
.auth-label { color: var(--text-4); }
.auth-value { color: var(--text-2); font-family: var(--font-ui); }

.ghost {
  background: transparent;
  border: 1px solid var(--border);
  color: var(--text-2);
  padding: 4px 10px;
  font-size: 12px;
  font-family: var(--font-ui);
}
.ghost:hover:not(:disabled) { background: var(--bg-hover); }
.ghost.tiny { padding: 2px 8px; font-size: 12px; }

.status {
  font-size: 12px;
  padding: 2px 10px;
  border-radius: 10px;
  background: var(--pill-bg);
  color: var(--text-3);
}
.status.on { color: var(--accent); background: var(--bg-active); }

.np-body { min-height: 60px; display: flex; flex-direction: column; gap: 4px; }
.np-name { font-size: 12px; color: var(--text-1); }
.np-path { font-size: 12px; color: var(--text-4); font-family: var(--font-ui); }
.np-meta { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 4px; }
.meta-pill {
  font-size: 12px;
  padding: 2px 10px;
  border-radius: 10px;
  background: var(--pill-bg);
  color: var(--text-3);
}
.meta-pill.active { color: var(--accent); background: var(--bg-active); }
.np-idle { font-size: 12px; color: var(--text-4); align-self: center; text-align: center; padding: 8px; }

.transcode-grid {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 6px 12px;
  font-size: 12px;
}
.t-label { color: var(--text-4); }
.t-value { color: var(--text-2); font-family: var(--font-ui); }
</style>
