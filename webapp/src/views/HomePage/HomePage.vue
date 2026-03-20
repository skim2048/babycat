<template>
  <div class="page">
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

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100%;
  padding-bottom: var(--nav-height);
  overflow: hidden;
}
</style>
