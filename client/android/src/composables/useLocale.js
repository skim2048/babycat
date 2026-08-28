import { ref, watch } from 'vue'
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

// @claude Without a saved choice, derive from the browser language setting. Once the user
// @claude switches, that value is saved and takes precedence thereafter.
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

export function useLocale() {
  function toggleLocale() {
    locale.value = locale.value === 'en' ? 'ko' : 'en'
  }

  return {
    locale,
    toggleLocale,
    t,
  }
}
