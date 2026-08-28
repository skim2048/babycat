import { computed } from 'vue'
import { useSSE } from './useSSE.js'
import { useAnalysis } from './useAnalysis.js'
import { t } from './useLocale.js'

// @claude VLM status dot colors: ready #5fbf8a · error #e05b6a · switching/downloading #d9a44a.
const VLM_DOTS = {
  ready: '#5fbf8a',
  error: '#e05b6a',
  switching: '#d9a44a',
  downloading: '#d9a44a',
}

export function useVlmStatus() {
  const { state } = useSSE()
  const { analysisActive } = useAnalysis()

  const vlmDot = computed(() => VLM_DOTS[state.vlm_state] || 'var(--color-neutral-500)')
  const vlmLabel = computed(() => {
    // @claude While the VLM is idle and analysis is running, show it as "running".
    if (state.vlm_state === 'ready' && analysisActive.value) return t('dashboard.vlm.running')
    return t(`dashboard.vlm.${state.vlm_state}`)
  })

  return { vlmDot, vlmLabel }
}
