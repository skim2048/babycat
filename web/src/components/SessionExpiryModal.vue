<script setup>
defineProps({
  show: { type: Boolean, default: false },
  remainingSeconds: { type: Number, default: 0 },
  canExtend: { type: Boolean, default: false },
  extending: { type: Boolean, default: false },
})

defineEmits(['extend', 'logout'])
</script>

<template>
  <Teleport to="body">
    <Transition name="session-modal">
      <div v-if="show" class="session-modal-backdrop" role="presentation">
        <div
          class="session-modal"
          role="dialog"
          aria-modal="true"
          aria-labelledby="session-expiry-title"
          aria-describedby="session-expiry-description"
        >
          <p class="session-modal-label">세션 안내</p>
          <h2 id="session-expiry-title" class="session-modal-title">로그인 세션이 곧 만료됩니다.</h2>
          <p id="session-expiry-description" class="session-modal-copy">
            {{ remainingSeconds }}초 후 자동 로그아웃됩니다. 계속 사용하려면 세션을 연장하세요.
          </p>
          <div class="session-modal-actions">
            <button
              v-if="canExtend"
              type="button"
              class="session-modal-btn session-modal-btn-primary"
              :disabled="extending"
              @click="$emit('extend')"
            >
              {{ extending ? '연장 중...' : '연장' }}
            </button>
            <button
              type="button"
              class="session-modal-btn"
              @click="$emit('logout')"
            >
              로그아웃
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.session-modal-backdrop {
  position: fixed;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 1.5rem;
  background: var(--overlay);
  z-index: 1000;
}

.session-modal {
  width: min(100%, 26rem);
  padding: 1.5rem;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--bg-surface);
  box-shadow: var(--shadow-lg);
}

.session-modal-label {
  margin-bottom: 0.35rem;
  font-size: 0.75rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  color: var(--text-3);
  text-transform: uppercase;
}

.session-modal-title {
  font-size: 1.1rem;
  font-weight: 700;
  color: var(--text-1);
}

.session-modal-copy {
  margin-top: 0.65rem;
  font-size: 0.92rem;
  color: var(--text-2);
}

.session-modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.75rem;
  margin-top: 1.2rem;
}

.session-modal-btn {
  min-width: 6.25rem;
  padding: 0.7rem 1rem;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--bg-surface-secondary);
  color: var(--text-1);
  font-size: 0.9rem;
  font-weight: 600;
  cursor: pointer;
}

.session-modal-btn:disabled {
  opacity: 0.6;
  cursor: default;
}

.session-modal-btn-primary {
  border-color: var(--accent);
  background: var(--accent);
  color: #fff;
}

.session-modal-enter-active,
.session-modal-leave-active {
  transition: opacity 0.18s ease;
}

.session-modal-enter-active .session-modal,
.session-modal-leave-active .session-modal {
  transition: transform 0.18s ease, opacity 0.18s ease;
}

.session-modal-enter-from,
.session-modal-leave-to {
  opacity: 0;
}

.session-modal-enter-from .session-modal,
.session-modal-leave-to .session-modal {
  opacity: 0;
  transform: translateY(8px);
}

@media (max-width: 640px) {
  .session-modal-actions {
    flex-direction: column;
  }

  .session-modal-btn {
    width: 100%;
  }
}
</style>
