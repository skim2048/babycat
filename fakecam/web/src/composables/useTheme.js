// Theme switching with localStorage persistence and system preference fallback.
// Mirrors babycat-web — same `theme` key, same data-theme attribute on <html>.

import { ref, watch } from 'vue'

const THEME_KEY = 'theme'
const DEFAULT_THEME = 'light'
const SUPPORTED_THEMES = new Set(['light', 'dark'])

function hasWindow() {
  return typeof window !== 'undefined'
}

function normalizeTheme(value) {
  return SUPPORTED_THEMES.has(value) ? value : DEFAULT_THEME
}

function readStoredTheme() {
  if (!hasWindow()) return DEFAULT_THEME
  const stored = window.localStorage.getItem(THEME_KEY)
  if (SUPPORTED_THEMES.has(stored)) return stored
  if (
    typeof window.matchMedia === 'function' &&
    window.matchMedia('(prefers-color-scheme: dark)').matches
  ) {
    return 'dark'
  }
  return DEFAULT_THEME
}

function syncTheme(value) {
  if (!hasWindow()) return
  const resolved = normalizeTheme(value)
  document.documentElement.setAttribute('data-theme', resolved)
  window.localStorage.setItem(THEME_KEY, resolved)
}

const theme = ref(readStoredTheme())

watch(theme, (value) => {
  syncTheme(value)
}, { immediate: true })

export function useTheme() {
  function setTheme(value) {
    theme.value = normalizeTheme(value)
  }

  function toggleTheme() {
    theme.value = theme.value === 'light' ? 'dark' : 'light'
  }

  return { theme, setTheme, toggleTheme }
}
