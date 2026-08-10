<script setup>
import { computed, ref } from 'vue'
import SheetFrame from './SheetFrame.vue'
import { useSSE } from '../composables/useSSE.js'
import { usePtz } from '../composables/usePtz.js'
import { useLocale } from '../composables/useLocale.js'

const props = defineProps({
  active: { type: Boolean, default: false }, // 재생 중 여부 — 낙관적 활성 정책의 사전 비활성 판단
})
const emit = defineEmits(['close'])

const { state } = useSSE()
const { speedLevel, setSpeedLevel, startMove, stopMove, savePreset, gotoPreset } = usePtz()
const { t } = useLocale()

const ptzPressing = ref(null)
const ptzSaveMode = ref(false)
const ptzMessage = ref('') // '' | 'saveFailed' | 'gotoEmpty'

const savedSlots = computed(() => new Set(state.ptz_presets || []))

const ptzDirs = [
  { id: 'up',    pan:  0, tilt:  1, icon: 'ph ph-caret-up' },
  { id: 'down',  pan:  0, tilt: -1, icon: 'ph ph-caret-down' },
  { id: 'left',  pan: -1, tilt:  0, icon: 'ph ph-caret-left' },
  { id: 'right', pan:  1, tilt:  0, icon: 'ph ph-caret-right' },
]

function ptzDown(dir, event) {
  if (!props.active) return
  event.preventDefault()
  ptzPressing.value = dir.id
  startMove(dir.pan, dir.tilt)
}

function ptzUp(dir) {
  if (ptzPressing.value !== dir.id) return
  ptzPressing.value = null
  stopMove()
}

function ptzStopNow() {
  if (!props.active) return
  ptzPressing.value = null
  stopMove()
}

async function onPresetClick(slot) {
  if (!props.active) return
  ptzMessage.value = ''
  if (ptzSaveMode.value) {
    const ok = await savePreset(slot)
    if (!ok) ptzMessage.value = 'saveFailed'
    ptzSaveMode.value = false
  } else {
    const ok = await gotoPreset(slot)
    if (!ok) ptzMessage.value = 'gotoEmpty'
  }
}

const ptzHint = computed(() => {
  if (ptzMessage.value === 'saveFailed') return t('live.ptz.saveFailed')
  if (ptzMessage.value === 'gotoEmpty') return t('live.ptz.gotoEmpty')
  return ptzSaveMode.value ? t('live.ptz.saveHint') : t('live.ptz.gotoHint')
})

function onClose() {
  if (ptzPressing.value != null) stopMove()
  emit('close')
}
</script>

<template>
  <SheetFrame title="PTZ" @close="onClose">
    <div class="ptz-sheet" :class="{ off: !active }" :aria-disabled="!active">
      <div class="ptz-top">
        <div class="ptz-pad">
          <button
            v-for="dir in ptzDirs"
            :key="dir.id"
            class="ptz-dir"
            :class="[dir.id, { pressing: ptzPressing === dir.id }]"
            :title="t(`live.ptz.${dir.id}`)"
            @mousedown="(e) => ptzDown(dir, e)"
            @mouseup="ptzUp(dir)"
            @mouseleave="ptzUp(dir)"
            @touchstart.prevent="(e) => ptzDown(dir, e)"
            @touchend="ptzUp(dir)"
          ><i :class="dir.icon"></i></button>
          <button class="ptz-stop" :title="t('live.ptz.stop')" @click="ptzStopNow">STOP</button>
        </div>

        <div class="ptz-mid">
          <!-- 줌 — 백엔드 미지원으로 비활성 UI만 유지 (인계 문서 「확정 방침」 2) -->
          <div class="ptz-zoom">
            <div class="ptz-row-head">
              <span>{{ t('live.ptz.zoom') }}</span>
              <span class="ptz-zoom-val">×1.0</span>
            </div>
            <div class="ptz-zoom-ctl">
              <button class="ptz-round" disabled><i class="ph ph-minus"></i></button>
              <input type="range" min="1" max="8" step="0.5" value="1" disabled />
              <button class="ptz-round" disabled><i class="ph ph-plus"></i></button>
            </div>
          </div>
          <div class="ptz-speed">
            <span class="ptz-row-label">{{ t('live.ptz.speed') }}</span>
            <div class="ptz-speed-seg">
              <button
                v-for="(label, i) in [t('live.ptz.speedSlow'), t('live.ptz.speedNormal'), t('live.ptz.speedFast')]"
                :key="i"
                class="ptz-speed-opt"
                :class="{ active: speedLevel === i }"
                @click="setSpeedLevel(i)"
              >{{ label }}</button>
            </div>
          </div>
        </div>
      </div>

      <div class="ptz-presets">
        <div class="ptz-presets-head">
          <span class="ptz-row-label">{{ t('live.ptz.presets') }}</span>
          <button class="ptz-save-toggle" @click="ptzSaveMode = !ptzSaveMode; ptzMessage = ''">
            {{ ptzSaveMode ? t('live.ptz.saveCancel') : t('live.ptz.savePosition') }}
          </button>
        </div>
        <div class="ptz-slots">
          <button
            v-for="slot in [1, 2, 3, 4]"
            :key="slot"
            class="ptz-slot"
            :class="{ saved: savedSlots.has(slot) }"
            @click="onPresetClick(slot)"
          >
            <i v-if="ptzSaveMode" class="ph ph-bookmark-simple"></i>{{ slot }}
          </button>
        </div>
        <span class="ptz-hint" :class="{ err: !!ptzMessage }">{{ ptzHint }}</span>
      </div>
    </div>
  </SheetFrame>
</template>

<style scoped>
.ptz-sheet {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.ptz-sheet.off {
  opacity: 0.45;
  pointer-events: none;
  user-select: none;
}
.ptz-top {
  display: flex;
  gap: 14px;
  align-items: center;
}
.ptz-pad {
  position: relative;
  width: 140px;
  height: 140px;
  flex: none;
  border-radius: 50%;
  background: var(--color-neutral-900);
}
.ptz-dir {
  position: absolute;
  width: 46px; height: 46px;
  border-radius: 50%;
  border: none;
  background: transparent;
  color: var(--color-text);
  font-size: 21px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}
.ptz-dir.up    { top: 6px; left: 50%; transform: translateX(-50%); }
.ptz-dir.down  { bottom: 6px; left: 50%; transform: translateX(-50%); }
.ptz-dir.left  { left: 6px; top: 50%; transform: translateY(-50%); }
.ptz-dir.right { right: 6px; top: 50%; transform: translateY(-50%); }
.ptz-dir.pressing { color: var(--color-accent); }
.ptz-stop {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: 46px; height: 46px;
  border-radius: 50%;
  border: none;
  background: color-mix(in srgb, var(--color-accent) 30%, transparent);
  color: var(--color-text);
  font-size: 10.5px;
  font-weight: 700;
  font-family: inherit;
  letter-spacing: 0.04em;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}

.ptz-mid {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.ptz-row-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 12.5px;
  color: var(--color-neutral-400);
}
.ptz-zoom { display: flex; flex-direction: column; gap: 7px; }
.ptz-zoom-val {
  color: var(--color-neutral-500);
  font-variant-numeric: tabular-nums;
}
.ptz-zoom-ctl {
  display: flex;
  align-items: center;
  gap: 10px;
  opacity: 0.45;
}
.ptz-round {
  width: 38px; height: 38px;
  flex: none;
  border-radius: 19px;
  border: none;
  background: var(--color-neutral-800);
  color: var(--color-text);
  font-size: 16px;
  cursor: default;
}
.ptz-zoom-ctl input[type='range'] {
  flex: 1;
  min-width: 0;
  appearance: none;
  height: 18px;
  background-image: linear-gradient(to right, var(--color-neutral-700), var(--color-neutral-700));
  background-size: 100% 4px;
  background-position: center;
  background-repeat: no-repeat;
  background-color: transparent;
  border-radius: 2px;
}
.ptz-zoom-ctl input[type='range']::-webkit-slider-thumb {
  appearance: none;
  width: 16px; height: 16px;
  border-radius: 50%;
  background: var(--color-neutral-500);
}
.ptz-speed { display: flex; flex-direction: column; gap: 7px; }
.ptz-row-label {
  font-size: 12.5px;
  color: var(--color-neutral-400);
}
.ptz-speed-seg {
  display: flex;
  gap: 6px;
  background: var(--color-neutral-900);
  border-radius: 100px;
  padding: 3px;
}
.ptz-speed-opt {
  flex: 1;
  height: 36px;
  border-radius: 100px;
  border: none;
  background: transparent;
  color: var(--color-text);
  font-size: 12.5px;
  font-family: inherit;
  cursor: pointer;
}
.ptz-speed-opt.active {
  background: color-mix(in srgb, var(--color-accent) 30%, transparent);
}

.ptz-presets {
  display: flex;
  flex-direction: column;
  gap: 7px;
}
.ptz-presets-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.ptz-save-toggle {
  border: none;
  background: none;
  padding: 0;
  color: var(--color-accent-300);
  font-size: 12.5px;
  font-family: inherit;
  cursor: pointer;
}
.ptz-slots {
  display: flex;
  gap: 8px;
}
.ptz-slot {
  flex: 1;
  height: 46px;
  border-radius: 100px;
  border: none;
  background: var(--color-neutral-900);
  color: var(--color-text);
  font-size: 13.5px;
  font-family: inherit;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
}
.ptz-slot.saved {
  background: color-mix(in srgb, var(--color-accent) 30%, transparent);
}
.ptz-slot i {
  font-size: 14px;
  color: var(--color-accent-300);
}
.ptz-hint {
  font-size: 12px;
  color: var(--color-neutral-400);
  line-height: 1.45;
}
.ptz-hint.err { color: #e07a86; }
</style>
