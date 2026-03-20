<template>
  <div class="page">
    <AppLogo />
    <div class="content">
      <p class="title">알람</p>
      <p class="desc">준비 중입니다.</p>
    </div>
  </div>
</template>

<script setup>
import AppLogo from '@/components/AppLogo.vue'
</script>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100%;
  padding-bottom: var(--nav-height);
}

.content {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: #84776e;
}

.title {
  font-size: 18px;
  font-weight: bold;
}

.desc {
  font-size: 14px;
}
</style>
