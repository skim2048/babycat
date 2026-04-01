<script setup>
import { ref } from 'vue'
import { useSSE } from '../composables/useSSE.js'

const { state } = useSSE()
const collapsed = ref(false)
</script>

<template>
  <div class="section" :class="{ collapsed }">
    <div class="section-title" @click="collapsed = !collapsed">
      Pipeline <span class="arrow">&#9660;</span>
    </div>
    <div class="section-body">
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
</template>
