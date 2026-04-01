<script setup>
import AppHeader from './components/AppHeader.vue'
import ClipSidebar from './components/ClipSidebar.vue'
import LiveStream from './components/LiveStream.vue'
import PromptControl from './components/PromptControl.vue'
import CameraPanel from './components/CameraPanel.vue'
import InferencePanel from './components/InferencePanel.vue'
import HardwarePanel from './components/HardwarePanel.vue'
import PtzPanel from './components/PtzPanel.vue'
</script>

<template>
  <AppHeader />
  <div class="main">
    <ClipSidebar />
    <div class="video-area">
      <LiveStream />
      <PromptControl />
    </div>
    <div class="dash">
      <CameraPanel />
      <InferencePanel />
      <HardwarePanel />
      <PtzPanel />
    </div>
  </div>
</template>
