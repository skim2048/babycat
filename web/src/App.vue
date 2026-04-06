<script setup>
import CameraPanel from './components/CameraPanel.vue'
import LiveStream from './components/LiveStream.vue'
import { useCamera } from './composables/useCamera.js'

const { configured, connecting } = useCamera()
</script>

<template>
  <div class="header">
    <span class="header-title">Babycat</span>
  </div>
  <div class="main">
    <div class="video-area">
      <LiveStream v-if="configured || connecting" />
      <div v-else class="empty-state">
        <p>No camera configured. Set up a camera to begin.</p>
      </div>
    </div>
    <div class="dash">
      <CameraPanel />
    </div>
  </div>
</template>

<style scoped>
.empty-state {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-4);
  font-size: 14px;
}
</style>
