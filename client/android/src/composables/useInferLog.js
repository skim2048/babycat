import { effectScope, reactive, readonly, watch } from 'vue'
import { useSSE } from './useSSE.js'

// @claude The right-hand panel lists inference reports over time, but the
// @claude backend stores only keyword events (/events: trigger + clip).
// @claude The narrative log therefore accumulates client-side from the SSE
// @claude infer_raw stream, newest first, capped for display. Deleting an
// @claude entry only removes it from this in-memory list — there is no
// @claude server-side counterpart to delete.
const MAX_LOG = 100

const entries = reactive([])
let started = false
let nextId = 1

function localDate(now) {
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`
}

export function useInferLog() {
  if (!started) {
    started = true
    // @claude The watcher lives in a detached scope: registered inside a
    // @claude component it would die with that component's unmount while the
    // @claude started flag stays true, silently ending accumulation.
    effectScope(true).run(() => {
      const { state } = useSSE()
      watch(() => state.infer_raw, (text) => {
        if (!text) return
        if (entries.length && entries[0].text === text) return
        const now = new Date()
        entries.unshift({
          id: nextId++,
          time: `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`,
          day: localDate(now),
          text,
          event: state.event_triggered,
        })
        if (entries.length > MAX_LOG) entries.length = MAX_LOG
      })
    })
  }

  function removeEntries(ids) {
    const drop = new Set(ids)
    for (let i = entries.length - 1; i >= 0; i--) {
      if (drop.has(entries[i].id)) entries.splice(i, 1)
    }
  }

  return { entries: readonly(entries), removeEntries }
}
