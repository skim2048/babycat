<script setup>
import { useSSE } from '../composables/useSSE.js'

const { state } = useSSE()
</script>

<template>
  <div class="header">
    <img src="/banner.png" alt="Babycat" class="header-logo" />
    <span class="uptime">{{ state.uptime }}</span>
  </div>
</template>
