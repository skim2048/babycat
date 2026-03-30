<script setup>
import { ref, onMounted } from 'vue'
import { useSSE } from '../composables/useSSE.js'

const { state } = useSSE()
const collapsed = ref(false)
const streamEl = ref(null)

onMounted(() => {
  streamEl.value.src = '/stream'
})
</script>

<template>
  <div class="section" :class="{ collapsed }">
    <div class="section-title" @click="collapsed = !collapsed">
      Inference <span class="arrow">&#9660;</span>
    </div>
    <div class="section-body">
      <img ref="streamEl" class="infer-img" alt="VLM input" />
      <div class="result-box" :class="state.event_triggered ? 'alert' : 'normal'" style="margin-top: 8px">
        <div class="result-raw">{{ state.infer_raw }}</div>
      </div>
      <div style="margin-top: 8px">
        <div class="row">
          <span class="k">추론 당 소요 시간</span>
          <span class="v">{{ state.infer_ms }} ms</span>
        </div>
      </div>
    </div>
  </div>
</template>
