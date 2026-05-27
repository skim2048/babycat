<script setup>
import { onMounted, ref } from 'vue'
import { api, getApiBase } from './api.js'

const apiBase = ref(getApiBase())
const loading = ref(true)
const error = ref('')
const playlist = ref(null)

async function load() {
  loading.value = true
  error.value = ''
  try {
    playlist.value = await api.getPlaylist()
  } catch (e) {
    error.value = String(e)
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <main>
    <header>
      <h1>fakecam</h1>
      <p class="meta">API base: <code>{{ apiBase }}</code></p>
    </header>

    <section>
      <button @click="load" :disabled="loading">{{ loading ? 'Loading…' : 'Reload /api/playlist' }}</button>
    </section>

    <section v-if="error" class="error">
      <h2>Error</h2>
      <pre>{{ error }}</pre>
    </section>

    <section v-else>
      <h2>/api/playlist response</h2>
      <pre>{{ JSON.stringify(playlist, null, 2) }}</pre>
    </section>
  </main>
</template>

<style>
body { font-family: system-ui, sans-serif; margin: 0; background: #111; color: #eee; }
main { max-width: 960px; margin: 0 auto; padding: 24px; }
header h1 { margin: 0 0 4px; }
.meta { color: #888; font-size: 0.9em; }
button { padding: 8px 16px; background: #2a2a2a; color: #eee; border: 1px solid #444; border-radius: 4px; cursor: pointer; }
button:disabled { opacity: 0.5; cursor: default; }
pre { background: #1a1a1a; padding: 12px; border-radius: 4px; overflow: auto; }
.error pre { color: #f88; }
</style>
