<script setup>
import { useSSE } from '../composables/useSSE.js'

const { state } = useSSE()
</script>

<template>
  <div class="header">
    <span class="header-title">Babycat Debugging Page</span>
    <span class="uptime">{{ state.uptime }}</span>
  </div>
</template>
