import { ref, watch } from 'vue'

const THEME_KEY = 'theme'
const DEFAULT_THEME = 'dark'
const SUPPORTED_THEMES = new Set(['light', 'dark'])

function hasWindow() {
  return typeof window !== 'undefined'
}

function normalizeTheme(value) {
  return SUPPORTED_THEMES.has(value) ? value : DEFAULT_THEME
}

// @claude If an explicit saved choice exists use it; otherwise follow the browser/device
// @claude environment (prefers-color-scheme). The environment value is not saved, so until
// @claude the user switches, the environment is followed again on every run.
function initialTheme() {
  if (!hasWindow()) return DEFAULT_THEME
  const stored = window.localStorage.getItem(THEME_KEY)
  if (SUPPORTED_THEMES.has(stored)) return stored

  if (typeof window.matchMedia === 'function' && window.matchMedia('(prefers-color-scheme: light)').matches) {
    return 'light'
  }
  return DEFAULT_THEME
}

function applyTheme(value) {
  if (!hasWindow()) return
  document.documentElement.setAttribute('data-theme', normalizeTheme(value))
}

const theme = ref(initialTheme())

// @claude Applied immediately when main.js imports this module (app start) —
// @claude the login screen and the post-login screen must start with the same theme.
watch(theme, (value) => {
  applyTheme(value)
}, { immediate: true })

export function useTheme() {
  function setTheme(value) {
    const resolvedTheme = normalizeTheme(value)
    theme.value = resolvedTheme
    if (hasWindow()) window.localStorage.setItem(THEME_KEY, resolvedTheme)
  }

  return { theme, setTheme }
}
