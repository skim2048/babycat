<template>
  <div :class="$style.page">
    <AppLogo />
    <StateBar />
    <CamView />
    <CamBar />
    <HomeIcons />
    <Chat />
  </div>
</template>

<script setup>
import AppLogo from '@/components/AppLogo.vue'
import Chat from '@/components/Chat.vue'
import StateBar from './StateBar.vue'
import CamView from './CamView.vue'
import CamBar from './CamBar.vue'
import HomeIcons from './HomeIcons.vue'
</script>

<style module>
.page {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  overflow: hidden;
}
</style>
