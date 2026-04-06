<script setup>
import { ref, watch } from 'vue'
import { useSSE } from '../composables/useSSE.js'

const { state } = useSSE()

const prompt = ref('')
const triggers = ref('')
const btnText = ref('적용')
let loaded = false

watch(
  () => [state.inference_prompt, state.trigger_keywords],
  ([p, t]) => {
    if (!loaded && (p || t)) {
      if (p) prompt.value = p
      if (t) triggers.value = t
      loaded = true
    }
  },
)

async function apply() {
  if (!prompt.value.trim()) return
  const res = await fetch('/prompt', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt: prompt.value.trim(), triggers: triggers.value.trim() }),
  })
  const data = await res.json()
  if (data.ok) {
    btnText.value = '적용됨'
    setTimeout(() => (btnText.value = '적용'), 1500)
  }
}

function onKey(e) {
  if (e.key === 'Enter') apply()
}
</script>

<template>
  <div>
    <div class="video-label">Prompting</div>
    <div class="prompt-row">
      <div class="prompt-fields">
        <input class="prompt-input" v-model="prompt" placeholder="VLM 프롬프트 입력..." @keydown="onKey" />
        <input class="prompt-input" v-model="triggers" placeholder="이벤트 트리거 키워드 (쉼표 구분)" @keydown="onKey" />
      </div>
      <button class="prompt-btn" @click="apply">{{ btnText }}</button>
    </div>
  </div>
</template>
