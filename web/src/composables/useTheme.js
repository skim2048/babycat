import { ref, watchEffect } from 'vue'

const theme = ref(localStorage.getItem('theme') || 'light')

watchEffect(() => {
  document.documentElement.setAttribute('data-theme', theme.value)
  localStorage.setItem('theme', theme.value)
})

export function useTheme() {
  function setTheme(value) {
    theme.value = value
  }

  return { theme, setTheme }
}
