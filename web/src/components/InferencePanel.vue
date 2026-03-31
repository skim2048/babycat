<script setup>
import { ref } from 'vue'
import { useSSE } from '../composables/useSSE.js'

const { state } = useSSE()
const collapsed = ref(false)
</script>

<template>
  <div class="section" :class="{ collapsed }">
    <div class="section-title" @click="collapsed = !collapsed">
      Inference <span class="arrow">&#9660;</span>
    </div>
    <div class="section-body">
      <div class="result-box" :class="state.event_triggered ? 'alert' : 'normal'">
        <div class="result-raw">{{ state.infer_raw }}</div>
      </div>
      <div style="margin-top: 10px">
        <div class="row">
          <span class="k">추론 당 소요 시간</span>
          <span class="v">{{ state.infer_ms }} ms</span>
        </div>
        <div class="row">
          <span class="k">원본 해상도</span>
          <span class="v">{{ state.frame_w }} x {{ state.frame_h }}</span>
        </div>
        <div class="row">
          <span class="k">N_FRAMES</span>
          <span class="v">{{ state.cfg_n_frames || '-' }}</span>
        </div>
      </div>
    </div>
  </div>
</template>
