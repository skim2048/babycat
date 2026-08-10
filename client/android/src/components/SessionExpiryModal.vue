<script setup>
import { useLocale } from '../composables/useLocale.js'

defineProps({
  show: { type: Boolean, default: false },
  remainingSeconds: { type: Number, default: 0 },
  canExtend: { type: Boolean, default: false },
  extending: { type: Boolean, default: false },
})

defineEmits(['extend', 'logout'])
const { t } = useLocale()
</script>

<template>
  <Teleport to="body">
    <Transition name="session-modal">
      <div v-if="show" class="session-backdrop" role="presentation">
        <div
          class="session-frame"
          role="dialog"
          aria-modal="true"
          aria-labelledby="session-expiry-title"
        >
          <div class="session-head">
            <span id="session-expiry-title" class="session-title">{{ t('session.title') }}</span>
          </div>
          <div class="session-body form-col">
            <div class="session-copy">{{ t('session.copy', { seconds: remainingSeconds }) }}</div>
            <div class="form-actions">
              <button
                v-if="canExtend"
                type="button"
                class="form-btn primary"
                :disabled="extending"
                @click="$emit('extend')"
              >
                {{ extending ? t('session.extending') : t('session.extend') }}
              </button>
              <button type="button" class="form-btn" @click="$emit('logout')">
                {{ t('session.logout') }}
              </button>
            </div>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.session-backdrop {
  position: fixed;
  inset: 0;
  z-index: 300;
  background: rgba(8, 9, 14, 0.62);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px;
}
.session-frame {
  width: 420px;
  max-width: 100%;
  background: var(--color-surface);
  border: 1px solid var(--color-neutral-800);
  border-radius: 12px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  box-shadow: 0 24px 60px rgba(0, 0, 0, 0.6);
}
.session-head {
  height: 56px;
  display: flex;
  align-items: center;
  padding: 0 20px;
  border-bottom: 1px solid var(--color-divider);
}
.session-title {
  font-size: 15.5px;
  font-weight: var(--font-heading-weight);
}
.session-body {
  padding: 18px 20px 24px;
}
.session-copy {
  font-size: 13.5px;
  line-height: 1.6;
}

.session-modal-enter-active,
.session-modal-leave-active { transition: opacity 0.2s; }
.session-modal-enter-from,
.session-modal-leave-to { opacity: 0; }
</style>
