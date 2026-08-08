<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { useClips } from '../composables/useClips.js'
import { useAuth } from '../composables/useAuth.js'
import { authFetch } from '../composables/useFetch.js'
import { API_ENDPOINTS, getClipUrl } from '../endpoints.js'
import { useLocale } from '../composables/useLocale.js'
import ClipPlayerModal from './ClipPlayerModal.vue'

const { clipVersion, deleteClips } = useClips()
const { isAuthenticated, accessToken } = useAuth()
const { t } = useLocale()

// ── Filter state ─────────────────────────────────────────────────────────────
const searchQuery = ref('')
const dateFrom = ref('')
const dateTo = ref('')
const activePreset = ref('all')

// @claude The mockup filters with date chips; the presets map to the same
// @claude date_from/date_to the backend already accepts.
function localDate(offsetDays = 0) {
  const d = new Date()
  d.setDate(d.getDate() + offsetDays)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}
const presets = [
  { key: 'all', label: () => t('clips.preset.all'), range: () => ['', ''] },
  { key: 'today', label: () => t('clips.preset.today'), range: () => [localDate(), localDate()] },
  { key: 'yesterday', label: () => t('clips.preset.yesterday'), range: () => [localDate(-1), localDate(-1)] },
  { key: 'week', label: () => t('clips.preset.week'), range: () => [localDate(-6), localDate()] },
]
function applyPreset(preset) {
  activePreset.value = preset.key
  const [from, to] = preset.range()
  dateFrom.value = from
  dateTo.value = to
}

// ── Selection ────────────────────────────────────────────────────────────────
const selectMode = ref(false)
const selected = ref(new Set())
const selectedCount = computed(() => selected.value.size)

function toggleSelectMode() {
  selectMode.value = !selectMode.value
  selected.value = new Set()
}
function toggleSelected(name) {
  const next = new Set(selected.value)
  if (next.has(name)) next.delete(name)
  else next.add(name)
  selected.value = next
}
async function deleteSelected() {
  if (!selected.value.size) return
  await deleteClips([...selected.value])
  selected.value = new Set()
  selectMode.value = false
}

// ── Playback ─────────────────────────────────────────────────────────────────
const playing = ref(null) // clip name or null
const playerSrc = computed(() =>
  playing.value ? getClipUrl(playing.value, 'full', accessToken.value || '') : '',
)

function onClipClick(clip) {
  if (selectMode.value) toggleSelected(clip.name)
  else playing.value = clip.name
}

// ── Server data ──────────────────────────────────────────────────────────────
const PAGE_SIZE = 24
const currentPage = ref(1)
const clips = ref([])
const total = ref(0)
const totalPages = computed(() => Math.max(1, Math.ceil(total.value / PAGE_SIZE)))

async function fetchClips() {
  if (!isAuthenticated.value) return
  const params = new URLSearchParams()
  if (searchQuery.value) params.set('q', searchQuery.value)
  if (dateFrom.value) params.set('date_from', dateFrom.value)
  if (dateTo.value) params.set('date_to', dateTo.value)
  params.set('limit', String(PAGE_SIZE))
  params.set('offset', String((currentPage.value - 1) * PAGE_SIZE))
  try {
    const res = await authFetch(`${API_ENDPOINTS.clips}?${params}`)
    if (!res.ok) return
    const data = await res.json()
    clips.value = data.clips || []
    total.value = data.total ?? 0
    const maxPage = Math.max(1, Math.ceil(total.value / PAGE_SIZE))
    if (currentPage.value > maxPage) {
      currentPage.value = maxPage
      return
    }
    const names = new Set(clips.value.map((c) => c.name))
    selected.value = new Set([...selected.value].filter((n) => names.has(n)))
  } catch {}
}

let fetchScheduled = false
function scheduleFetch(resetPage = false) {
  if (resetPage) currentPage.value = 1
  if (fetchScheduled) return
  fetchScheduled = true
  nextTick(() => {
    fetchScheduled = false
    fetchClips()
  })
}

watch(clipVersion, () => scheduleFetch(false), { immediate: true })
let searchTimer = null
watch(searchQuery, () => {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => scheduleFetch(true), 300)
})
watch([dateFrom, dateTo], () => scheduleFetch(true))
watch(currentPage, () => scheduleFetch(false))

// ── Presentation ─────────────────────────────────────────────────────────────
function clipCaption(clip) {
  let time = ''
  const parsed = new Date(clip.created_at)
  if (!Number.isNaN(parsed.getTime())) {
    time = `${String(parsed.getHours()).padStart(2, '0')}:${String(parsed.getMinutes()).padStart(2, '0')}`
  }
  const kind = clip.keywords && clip.keywords.length ? clip.keywords[0] : ''
  return kind ? `${time} · ${kind}` : time
}
function thumbUrl(clip) {
  return getClipUrl(clip.name, 'full', accessToken.value || '')
}
</script>

<template>
  <div class="clips">

    <!-- ── Filter row ── -->
    <div class="clips-bar">
      <button
        v-for="preset in presets"
        :key="preset.key"
        class="date-chip"
        :class="{ active: activePreset === preset.key }"
        @click="applyPreset(preset)"
      >{{ preset.label() }}</button>
      <span class="clips-search">
        <i class="ph ph-magnifying-glass"></i>
        <input v-model="searchQuery" :placeholder="t('clips.searchPlaceholder')" />
      </span>
      <button class="select-toggle" @click="toggleSelectMode">
        {{ selectMode ? t('clips.action.cancel') : t('clips.action.select') }}
      </button>
    </div>

    <!-- ── Empty ── -->
    <div v-if="!clips.length" class="clips-empty">
      <i class="ph ph-film-slate"></i>
      <div class="clips-empty-title">{{ t('clips.empty.title') }}</div>
      <div class="clips-empty-body">{{ t('clips.empty.body') }}</div>
    </div>

    <!-- ── Grid ── -->
    <div v-else class="clips-grid">
      <button
        v-for="clip in clips"
        :key="clip.name"
        class="clip-card"
        :class="{ picked: selected.has(clip.name) }"
        @click="onClipClick(clip)"
      >
        <video class="clip-thumb" :src="thumbUrl(clip)" preload="metadata" muted></video>
        <span class="clip-caption">{{ clipCaption(clip) }}</span>
        <span v-if="selectMode" class="clip-pick" :class="{ on: selected.has(clip.name) }">
          <i v-if="selected.has(clip.name)" class="ph-fill ph-check"></i>
        </span>
      </button>
    </div>

    <!-- ── Select footer ── -->
    <div v-if="selectMode" class="clips-footer">
      <span class="clips-count">{{ t('clips.selectedCount', { count: selectedCount }) }}</span>
      <button class="delete-btn" :disabled="!selectedCount" @click="deleteSelected">
        {{ t('clips.action.delete') }}
      </button>
    </div>

    <!-- ── Pagination ── -->
    <div v-if="totalPages > 1" class="clips-pager">
      <button class="pager-btn" :disabled="currentPage <= 1" @click="currentPage--">
        <i class="ph ph-caret-left"></i>
      </button>
      <span class="pager-count">{{ currentPage }} / {{ totalPages }}</span>
      <button class="pager-btn" :disabled="currentPage >= totalPages" @click="currentPage++">
        <i class="ph ph-caret-right"></i>
      </button>
    </div>

    <ClipPlayerModal :open="!!playing" :src="playerSrc" @close="playing = null" />
  </div>
</template>

<style scoped>
.clips {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

/* — filter row — */
.clips-bar {
  display: flex;
  gap: 7px;
  align-items: center;
  flex-wrap: wrap;
}
.date-chip {
  height: 34px;
  padding: 0 13px;
  border-radius: 17px;
  border: 1px solid var(--color-neutral-800);
  background: none;
  color: var(--color-neutral-400);
  font-size: 12px;
  font-family: inherit;
  cursor: pointer;
}
.date-chip.active {
  border-color: var(--color-accent);
  color: var(--color-accent);
}
.clips-search {
  position: relative;
  display: flex;
  align-items: center;
  margin-left: auto;
}
.clips-search i {
  position: absolute;
  left: 10px;
  font-size: 14px;
  color: var(--color-neutral-600);
  pointer-events: none;
}
.clips-search input {
  width: 180px;
  height: 34px;
  border-radius: 7px;
  border: 1px solid var(--color-neutral-800);
  background: transparent;
  color: var(--color-text);
  padding: 0 10px 0 30px;
  font-size: 12px;
  font-family: inherit;
  outline: none;
}
.clips-search input:focus-visible { border-color: var(--color-accent); }
.select-toggle {
  height: 34px;
  padding: 0 13px;
  border-radius: 17px;
  border: none;
  background: none;
  color: var(--color-accent-300);
  font-size: 12px;
  font-family: inherit;
  cursor: pointer;
}
.select-toggle:hover { background: var(--color-neutral-900); }

/* — empty — */
.clips-empty {
  padding: 80px 20px;
  text-align: center;
  display: flex;
  flex-direction: column;
  gap: 10px;
  align-items: center;
}
.clips-empty i { font-size: 34px; color: var(--color-neutral-600); }
.clips-empty-title { font-size: 15px; }
.clips-empty-body {
  font-size: 12.5px;
  color: var(--color-neutral-500);
  line-height: 1.5;
}

/* — grid — */
.clips-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
}
@media (max-width: 1100px) {
  .clips-grid { grid-template-columns: repeat(3, 1fr); }
}
@media (max-width: 720px) {
  .clips-grid { grid-template-columns: repeat(2, 1fr); }
}
.clip-card {
  position: relative;
  aspect-ratio: 16 / 9;
  border-radius: 8px;
  border: 1px solid var(--color-neutral-800);
  background: linear-gradient(150deg, #14161f, #22253a);
  cursor: pointer;
  overflow: hidden;
  padding: 0;
  font-family: inherit;
}
.clip-card.picked { border-color: var(--color-accent); }
.clip-thumb {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
  pointer-events: none;
}
.clip-caption {
  position: absolute;
  left: 6px;
  bottom: 6px;
  font-size: 10.5px;
  color: #e9e9ed;
  background: rgba(0, 0, 0, 0.5);
  padding: 3px 6px;
  border-radius: 4px;
}
.clip-pick {
  position: absolute;
  right: 6px;
  top: 6px;
  width: 18px; height: 18px;
  border-radius: 50%;
  border: 1px solid rgba(255, 255, 255, 0.4);
  background: rgba(0, 0, 0, 0.35);
  color: #12131c;
  font-size: 11px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.clip-pick.on {
  border-color: var(--color-accent);
  background: var(--color-accent);
}

/* — footer / pager — */
.clips-footer {
  display: flex;
  align-items: center;
  gap: 10px;
}
.clips-count {
  font-size: 12.5px;
  color: var(--color-neutral-500);
}
.delete-btn {
  margin-left: auto;
  height: 40px;
  padding: 0 16px;
  border-radius: 8px;
  border: 1px solid #a9525f;
  background: none;
  color: #e07a86;
  font-size: 12.5px;
  font-family: inherit;
  cursor: pointer;
}
.delete-btn:disabled { opacity: 0.45; cursor: default; }
.clips-pager {
  display: flex;
  align-items: center;
  gap: 10px;
  justify-content: center;
}
.pager-btn {
  width: 32px; height: 32px;
  border-radius: 8px;
  border: 1px solid var(--color-neutral-800);
  background: none;
  color: var(--color-neutral-400);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}
.pager-btn:disabled { opacity: 0.4; cursor: default; }
.pager-count {
  font-size: 12px;
  color: var(--color-neutral-500);
  font-variant-numeric: tabular-nums;
}
</style>
