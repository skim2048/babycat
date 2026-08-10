import { computed } from 'vue'
import { useSSE } from './useSSE.js'
import { useAnalysis } from './useAnalysis.js'
import { t } from './useLocale.js'

// @claude 시안의 VLM 점 색: ready #5fbf8a · error #e05b6a · 전환/다운로드 #d9a44a.
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
    // @claude 시안: VLM이 대기 상태이고 분석이 도는 동안은 「구동 중」으로 표기.
    if (state.vlm_state === 'ready' && analysisActive.value) return t('dashboard.vlm.running')
    return t(`dashboard.vlm.${state.vlm_state}`)
  })

  return { vlmDot, vlmLabel }
}
