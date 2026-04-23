<script setup>
import SessionExpiryModal from './components/SessionExpiryModal.vue'
import { useAuth } from './composables/useAuth.js'

const { warningVisible, remainingSeconds, canExtendSession, extendingSession, extendSession, logout } = useAuth()

async function handleExtend() {
  await extendSession()
}

function handleLogout() {
  logout({ redirect: true })
}
</script>

<template>
  <router-view />
  <SessionExpiryModal
    :show="warningVisible"
    :remaining-seconds="remainingSeconds"
    :can-extend="canExtendSession"
    :extending="extendingSession"
    @extend="handleExtend"
    @logout="handleLogout"
  />
</template>
