<template>
  <nav class="nav">
    <NavItem
      v-for="tab in tabs"
      :key="tab.path"
      :path="tab.path"
      :label="tab.label"
      :iconOn="tab.iconOn"
      :iconOff="tab.iconOff"
      :isActive="route.path === tab.path"
    />
  </nav>
</template>

<script setup>
import { useRoute } from 'vue-router'
import NavItem from '@/components/Nav/NavItem.vue'

const route = useRoute()

const tabs = [
  { label: '홈',     path: '/home',     iconOn: '/icons/Nav/Home_On.svg',     iconOff: '/icons/Nav/Home_Off.svg' },
  { label: '캘린더', path: '/schedule', iconOn: '/icons/Nav/Calender_On.svg', iconOff: '/icons/Nav/Calender_Off.svg' },
  { label: '알람',     path: '/alarm',    iconOn: '/icons/Nav/Bell_On.svg',     iconOff: '/icons/Nav/Bell_Off.svg' },
  { label: '설정',  path: '/settings', iconOn: '/icons/Nav/Setting_On.svg',  iconOff: '/icons/Nav/Setting_Off.svg' },
]
</script>

<style scoped>
.nav {
  display: flex;
  justify-content: space-around;
  position: fixed;
  bottom: 0;
  width: 100%;
  background-color: #FFFBF5;
  padding: 10px 0;
  padding-bottom: calc(10px + env(safe-area-inset-bottom));
}
</style>