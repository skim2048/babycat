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

// @claude 저장된 명시적 선택이 있으면 그것을, 없으면 브라우저/기기 환경
// @claude (prefers-color-scheme)을 따른다. 환경값은 저장하지 않으므로 사용자가
// @claude 전환하기 전까지는 매 실행마다 환경을 다시 따른다.
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

// @claude main.js가 이 모듈을 가져오는 시점(앱 시작)에 즉시 적용된다 —
// @claude 로그인 화면과 로그인 후 화면이 같은 테마로 시작해야 한다.
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
