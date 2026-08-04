<script setup>
import { useTheme } from '../composables/useTheme.js'
import { useLocale } from '../composables/useLocale.js'

const { theme, setTheme } = useTheme()
const { t } = useLocale()

function toggle() {
  setTheme(theme.value === 'light' ? 'dark' : 'light')
}
</script>

<template>
  <button class="theme-toggle" :class="{ dark: theme === 'dark' }" @click="toggle" type="button" :aria-label="t('theme.toggle')">
    <span class="icon sun">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="12" cy="12" r="5"/>
        <line x1="12" y1="1" x2="12" y2="3"/>
        <line x1="12" y1="21" x2="12" y2="23"/>
        <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/>
        <line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/>
        <line x1="1" y1="12" x2="3" y2="12"/>
        <line x1="21" y1="12" x2="23" y2="12"/>
        <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/>
        <line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>
      </svg>
    </span>
    <span class="icon moon">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>
      </svg>
    </span>
    <span class="thumb" />
  </button>
</template>

<style scoped>
.theme-toggle {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 60px;
  height: 32px;
  padding: 0 3px;
  border: none;
  border-radius: 16px;
  background: var(--bg-surface-active);
  cursor: pointer;
  transition: background 0.25s;
}
.theme-toggle.dark {
  background: #2a2a36;
}

.icon {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  flex-shrink: 0;
  transition: color 0.25s;
}
.sun {
  color: var(--text-3);
}
.moon {
  color: var(--text-4);
}
.theme-toggle:not(.dark) .sun {
  color: #d4940a;
}
.theme-toggle.dark .moon {
  color: #e4e4ec;
}

.thumb {
  position: absolute;
  top: 3px;
  left: 3px;
  width: 26px;
  height: 26px;
  border-radius: 50%;
  background: var(--bg-surface);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.15);
  transition: left 0.25s cubic-bezier(0.4, 0, 0.2, 1), background 0.25s;
}
.theme-toggle.dark .thumb {
  left: 31px;
  background: #50505e;
}
</style>
