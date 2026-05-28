<script setup>
import { computed } from 'vue'
import settings from '../assets/settings.svg?raw'
import add from '../assets/add.svg?raw'
import remove from '../assets/remove.svg?raw'
import shuffle from '../assets/shuffle.svg?raw'
import prev from '../assets/prev.svg?raw'
import play from '../assets/play.svg?raw'
import stop from '../assets/stop.svg?raw'
import next_ from '../assets/next.svg?raw'
import repeat from '../assets/repeat.svg?raw'
import repeatOne from '../assets/repeat-one.svg?raw'
import chevronDown from '../assets/chevron-down.svg?raw'
import chevronRight from '../assets/chevron-right.svg?raw'

const icons = {
  settings,
  add,
  remove,
  shuffle,
  prev,
  play,
  stop,
  next: next_,
  repeat,
  'repeat-one': repeatOne,
  'chevron-down': chevronDown,
  'chevron-right': chevronRight,
}

const props = defineProps({
  name: { type: String, required: true },
  size: { type: [Number, String], default: 16 },
})

const svg = computed(() => icons[props.name] || '')
const px = computed(() =>
  typeof props.size === 'number' ? `${props.size}px` : props.size,
)
</script>

<template>
  <span
    class="icon"
    :style="{ width: px, height: px }"
    aria-hidden="true"
    v-html="svg"
  />
</template>

<style scoped>
.icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  line-height: 0;
  color: inherit;
  flex-shrink: 0;
}
.icon :deep(svg) {
  width: 100%;
  height: 100%;
  display: block;
}
</style>
