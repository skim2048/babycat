<template>
  <RouterLink :to="path" class="nav-item">
    <img :src="isActive ? iconOn : iconOff" :alt="label" />
    <span :class="{ active: isActive }">{{ label }}</span>
  </RouterLink>
</template>

<script setup>
defineProps({
  path: String,
  label: String,
  iconOn: String,
  iconOff: String,
  isActive: Boolean,
})
</script>

<style scoped>
@font-face {
  font-family: 'Bazzi';
  src: url('@/assets/Fonts/Bazzi.ttf') format('truetype');
}

.nav-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  text-decoration: none;
}

span {
  font-family: 'Bazzi', sans-serif;
}
</style>