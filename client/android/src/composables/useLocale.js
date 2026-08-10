import { computed, ref, watch } from 'vue'
import { messages } from '../i18n/messages.js'

const LOCALE_KEY = 'locale'
const DEFAULT_LOCALE = 'en'
const SUPPORTED_LOCALES = new Set(['en', 'ko'])

function hasWindow() {
  return typeof window !== 'undefined'
}

function normalizeLocale(value) {
  return SUPPORTED_LOCALES.has(value) ? value : DEFAULT_LOCALE
}

// @claude 저장된 선택이 없으면 브라우저 언어 설정에서 유도한다. 사용자가 한 번
// @claude 전환하면 그 값이 저장되어 이후에는 저장값을 우선한다.
function browserLocale() {
  if (!hasWindow()) return DEFAULT_LOCALE
  const languages = navigator.languages?.length ? navigator.languages : [navigator.language]
  for (const language of languages) {
    const base = String(language || '').toLowerCase().split('-')[0]
    if (SUPPORTED_LOCALES.has(base)) return base
  }
  return DEFAULT_LOCALE
}

function readStoredLocale() {
  if (!hasWindow()) return DEFAULT_LOCALE
  const stored = window.localStorage.getItem(LOCALE_KEY)
  if (stored && SUPPORTED_LOCALES.has(stored)) return stored
  return browserLocale()
}

function syncLocale(value) {
  if (!hasWindow()) return
  const normalized = normalizeLocale(value)
  document.documentElement.setAttribute('lang', normalized)
  window.localStorage.setItem(LOCALE_KEY, normalized)
}

function interpolate(template, params = {}) {
  return template.replace(/\{(\w+)\}/g, (_, key) => String(params[key] ?? ''))
}

const locale = ref(readStoredLocale())

watch(locale, (value) => {
  syncLocale(value)
}, { immediate: true })

export function t(key, params) {
  const entry = messages[key]
  if (!entry) return key
  const template = entry[locale.value] ?? entry[DEFAULT_LOCALE] ?? key
  return typeof template === 'string' ? interpolate(template, params) : key
}

export function hasMessage(key) {
  return Object.prototype.hasOwnProperty.call(messages, key)
}

export function formatDateTime(value, options) {
  const tag = locale.value === 'ko' ? 'ko-KR' : 'en-US'
  return new Intl.DateTimeFormat(tag, options).format(value)
}

export function useLocale() {
  const isKorean = computed(() => locale.value === 'ko')

  function setLocale(value) {
    locale.value = normalizeLocale(value)
  }

  function toggleLocale() {
    locale.value = locale.value === 'en' ? 'ko' : 'en'
  }

  return {
    locale,
    isKorean,
    setLocale,
    toggleLocale,
    t,
  }
}
