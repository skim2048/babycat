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
  const storedTheme = normalizeTheme(window.localStorage.getItem(THEME_KEY))
  if (storedTheme !== DEFAULT_THEME || window.localStorage.getItem(THEME_KEY) === DEFAULT_THEME) {
    return storedTheme
  }

  if (typeof window.matchMedia === 'function' && window.matchMedia('(prefers-color-scheme: dark)').matches) {
    return 'dark'
  }

  return DEFAULT_THEME
}

function syncTheme(value) {
  if (!hasWindow()) return
  const resolvedTheme = normalizeTheme(value)
  document.documentElement.setAttribute('data-theme', resolvedTheme)
  window.localStorage.setItem(THEME_KEY, resolvedTheme)
}

const theme = ref(readStoredTheme())

watch(theme, (value) => {
  syncTheme(value)
}, { immediate: true })

export function useTheme() {
  function setTheme(value) {
    theme.value = normalizeTheme(value)
  }

  return { theme, setTheme }
}
