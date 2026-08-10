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
const activePreset = ref('')
const filterOpen = ref(false)

function localDate(offsetDays = 0) {
  const d = new Date()
  d.setDate(d.getDate() + offsetDays)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}
function monthStart() {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-01`
}

const presets = computed(() => [
  { key: 'today', label: t('clips.preset.today'), range: () => [localDate(), localDate()] },
  { key: 'yesterday', label: t('clips.preset.yesterday'), range: () => [localDate(-1), localDate(-1)] },
  { key: 'week', label: t('clips.preset.week'), range: () => [localDate(-6), localDate()] },
  { key: 'month', label: t('clips.preset.month'), range: () => [monthStart(), localDate()] },
])

// @claude 시안: 활성 프리셋을 다시 누르면 해제된다.
function applyPreset(preset) {
  if (activePreset.value === preset.key) {
    activePreset.value = ''
    dateFrom.value = ''
    dateTo.value = ''
    return
  }
  activePreset.value = preset.key
  const [from, to] = preset.range()
  dateFrom.value = from
  dateTo.value = to
}
function onDateInput() {
  activePreset.value = ''
}
function resetFilter() {
  searchQuery.value = ''
  activePreset.value = ''
  dateFrom.value = ''
  dateTo.value = ''
}
function clearRange() {
  activePreset.value = ''
  dateFrom.value = ''
  dateTo.value = ''
}

const rangeSet = computed(() => !!(dateFrom.value || dateTo.value))
const shortDate = (d) => (d ? d.slice(2) : d)
const rangeLabel = computed(() => {
  const preset = presets.value.find((p) => p.key === activePreset.value)
  if (preset) return preset.label
  if (rangeSet.value) return `${shortDate(dateFrom.value) || '…'} ~ ${shortDate(dateTo.value) || '…'}`
  return t('clips.allPeriod')
})
const filterActive = computed(() => !!searchQuery.value.trim() || rangeSet.value)

// ── Selection ────────────────────────────────────────────────────────────────
const selectMode = ref(false)
const selected = ref(new Set())
const selectedCount = computed(() => selected.value.size)

function enterSelectMode() {
  selectMode.value = true
  selected.value = new Set()
  filterOpen.value = false
}
function exitSelectMode() {
  selectMode.value = false
  selected.value = new Set()
}
function toggleSelected(name) {
  const next = new Set(selected.value)
  if (next.has(name)) next.delete(name)
  else next.add(name)
  selected.value = next
}
const allOnPage = computed(() =>
  clips.value.length > 0 && clips.value.every((c) => selected.value.has(c.name)),
)
function toggleSelectAll() {
  selected.value = allOnPage.value ? new Set() : new Set(clips.value.map((c) => c.name))
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
// @claude 페이지당 개수는 모바일 규칙(25·50·100, 기본 25)을 따른다.
const PAGE_SIZES = [25, 50, 100]
const pageSize = ref(25)
const currentPage = ref(1)
const clips = ref([])
const total = ref(0)
const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize.value)))
const rangeText = computed(() => {
  if (!total.value) return '0 / 0'
  const start = (currentPage.value - 1) * pageSize.value + 1
  const end = start + clips.value.length - 1
  return `${start}–${end} / ${total.value}`
})

async function fetchClips() {
  if (!isAuthenticated.value) return
  const params = new URLSearchParams()
  if (searchQuery.value) params.set('q', searchQuery.value)
  if (dateFrom.value) params.set('date_from', dateFrom.value)
  if (dateTo.value) params.set('date_to', dateTo.value)
  params.set('limit', String(pageSize.value))
  params.set('offset', String((currentPage.value - 1) * pageSize.value))
  try {
    const res = await authFetch(`${API_ENDPOINTS.clips}?${params}`)
    if (!res.ok) return
    const data = await res.json()
    clips.value = data.clips || []
    total.value = data.total ?? 0
    const maxPage = Math.max(1, Math.ceil(total.value / pageSize.value))
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
  if (resetPage) {
    currentPage.value = 1
    selected.value = new Set()
  }
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
watch(pageSize, () => scheduleFetch(true))
watch(currentPage, () => scheduleFetch(false))

// ── Presentation ─────────────────────────────────────────────────────────────
function clipDate(clip) {
  const parsed = new Date(clip.created_at)
  if (Number.isNaN(parsed.getTime())) return ''
  return `${String(parsed.getFullYear()).slice(2)}-${String(parsed.getMonth() + 1).padStart(2, '0')}-${String(parsed.getDate()).padStart(2, '0')}`
}
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
  <div class="clips-mobile">

    <!-- ── Browse bar ── -->
    <div v-if="!selectMode" class="clips-head">
      <div class="clips-bar">
        <div class="clips-search">
          <i class="ph ph-magnifying-glass"></i>
          <input v-model="searchQuery" :placeholder="t('clips.search')" />
          <button v-if="searchQuery" class="search-clear" @click="searchQuery = ''"><i class="ph ph-x"></i></button>
        </div>
        <button
          class="round-btn"
          :class="{ on: filterOpen }"
          :aria-expanded="filterOpen"
          @click="filterOpen = !filterOpen"
        >
          <i class="ph ph-sliders-horizontal"></i>
          <span v-if="rangeSet" class="filter-dot"></span>
        </button>
        <button class="round-btn" :title="t('clips.action.select')" @click="enterSelectMode">
          <i class="ph ph-check-square"></i>
        </button>
      </div>

      <!-- 인라인 필터 패널 -->
      <div v-if="filterOpen" class="filter-panel">
        <div class="filter-group">
          <span class="filter-label">{{ t('clips.customRange') }}</span>
          <div class="preset-grid">
            <button
              v-for="preset in presets"
              :key="preset.key"
              class="preset-btn"
              :class="{ on: activePreset === preset.key }"
              @click="applyPreset(preset)"
            >{{ preset.label }}</button>
          </div>
          <div class="date-inputs">
            <input v-model="dateFrom" type="date" @change="onDateInput" />
            <span class="date-tilde">~</span>
            <input v-model="dateTo" type="date" @change="onDateInput" />
          </div>
        </div>
        <div class="filter-group">
          <span class="filter-label">{{ t('clips.perPage') }}</span>
          <div class="size-row">
            <button
              v-for="n in PAGE_SIZES"
              :key="n"
              class="preset-btn"
              :class="{ on: pageSize === n }"
              @click="pageSize = n"
            >{{ n }}</button>
          </div>
        </div>
        <div class="filter-actions">
          <button class="filter-reset" :class="{ dim: !filterActive }" @click="resetFilter">{{ t('clips.reset') }}</button>
          <button class="filter-apply" @click="filterOpen = false">{{ t('clips.apply') }}</button>
        </div>
      </div>

      <!-- 활성 기간 칩 -->
      <div v-if="!filterOpen && rangeSet" class="range-chip-row">
        <button class="range-chip" @click="clearRange">
          {{ rangeLabel }}<i class="ph ph-x"></i>
        </button>
      </div>
    </div>

    <!-- ── Select bar ── -->
    <div v-else class="clips-bar">
      <button class="round-btn" :title="t('clips.action.cancel')" @click="exitSelectMode"><i class="ph ph-x"></i></button>
      <span class="select-count">{{ t('clips.selectedCount', { count: selectedCount }) }}</span>
      <span class="bar-spacer"></span>
      <button class="pill-btn" @click="toggleSelectAll">
        {{ allOnPage ? t('clips.action.deselectAll') : t('clips.action.selectAll') }}
      </button>
      <button class="pill-btn danger" :disabled="!selectedCount" @click="deleteSelected">
        {{ t('clips.action.delete') }}
      </button>
    </div>

    <!-- ── Empty ── -->
    <div v-if="!clips.length" class="clips-empty">
      <i class="ph ph-film-slate"></i>
      <div class="clips-empty-title">{{ filterActive ? t('clips.noMatch.title') : t('clips.empty.title') }}</div>
      <div class="clips-empty-body">{{ filterActive ? t('clips.noMatch.body') : t('clips.empty.body') }}</div>
    </div>

    <!-- ── Grid (3열 정방형) ── -->
    <div v-else class="clips-grid">
      <button
        v-for="clip in clips"
        :key="clip.name"
        class="clip-card"
        :class="{ picked: selected.has(clip.name) }"
        @click="onClipClick(clip)"
      >
        <video class="clip-thumb" :src="thumbUrl(clip)" preload="metadata" muted></video>
        <span class="clip-date">{{ clipDate(clip) }}</span>
        <span class="clip-caption">{{ clipCaption(clip) }}</span>
        <span v-if="selectMode" class="clip-pick" :class="{ on: selected.has(clip.name) }">
          <svg v-if="selected.has(clip.name)" class="check-glyph" viewBox="0 0 12 12" aria-hidden="true"><polyline points="2.5,6.5 5,9 9.5,3.5" /></svg>
        </span>
      </button>
    </div>

    <!-- ── Pager ── -->
    <div v-if="clips.length" class="clips-pager">
      <span class="pager-count">{{ rangeText }}</span>
      <button class="round-btn" :disabled="currentPage <= 1" @click="currentPage--">
        <i class="ph ph-caret-left"></i>
      </button>
      <button class="round-btn" :disabled="currentPage >= totalPages" @click="currentPage++">
        <i class="ph ph-caret-right"></i>
      </button>
    </div>

    <ClipPlayerModal :open="!!playing" :src="playerSrc" @close="playing = null" />
  </div>
</template>

<style scoped>
.check-glyph {
  width: 10px;
  height: 10px;
  fill: none;
  stroke: currentColor;
  stroke-width: 2.2;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.clips-mobile {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.clips-head {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.clips-bar {
  display: flex;
  align-items: center;
  gap: 6px;
}
.bar-spacer { flex: 1; }

.clips-search {
  position: relative;
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
}
.clips-search > i {
  position: absolute;
  left: 12px;
  font-size: 15px;
  color: var(--color-neutral-500);
  pointer-events: none;
}
.clips-search input {
  width: 100%;
  box-sizing: border-box;
  height: 40px;
  border-radius: 100px;
  border: none;
  background: var(--color-neutral-800);
  color: var(--color-text);
  padding: 0 34px;
  font-size: 12.5px;
  font-family: inherit;
  outline: none;
}
.clips-search input:focus-visible { outline: 2px solid var(--color-accent); }
.search-clear {
  position: absolute;
  right: 8px;
  width: 24px; height: 24px;
  border: none;
  background: none;
  color: var(--color-neutral-400);
  font-size: 14px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}
.round-btn {
  position: relative;
  width: 40px; height: 40px;
  flex: none;
  border-radius: 100px;
  border: none;
  background: var(--color-neutral-800);
  color: var(--color-text);
  font-size: 17px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}
.round-btn.on { background: color-mix(in srgb, var(--color-accent) 22%, transparent); }
.round-btn:disabled { opacity: 0.45; cursor: default; }
.filter-dot {
  position: absolute;
  right: 8px;
  top: 8px;
  width: 6px; height: 6px;
  border-radius: 50%;
  background: var(--color-accent);
}
.pill-btn {
  flex: none;
  height: 34px;
  padding: 0 13px;
  border-radius: 100px;
  border: none;
  background: var(--color-neutral-800);
  color: var(--color-text);
  font-size: 12.5px;
  font-family: inherit;
  cursor: pointer;
}
.pill-btn.danger { color: #e07a86; }
.pill-btn:disabled { opacity: 0.45; cursor: default; }
.select-count { font-size: 12.5px; }

/* — filter panel — */
.filter-panel {
  border-radius: 16px;
  background: var(--color-neutral-900);
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.filter-group {
  display: flex;
  flex-direction: column;
  gap: 7px;
}
.filter-label {
  font-size: 12px;
  color: var(--color-neutral-400);
}
.preset-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 6px;
}
.size-row {
  display: flex;
  gap: 6px;
}
.size-row .preset-btn { flex: 1; }
.preset-btn {
  height: 38px;
  border-radius: 100px;
  border: none;
  background: var(--color-neutral-800);
  color: var(--color-text);
  font-size: 13px;
  font-family: inherit;
  cursor: pointer;
  font-variant-numeric: tabular-nums;
}
.preset-btn.on { background: color-mix(in srgb, var(--color-accent) 22%, transparent); }
.date-inputs {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 2px;
}
.date-inputs input {
  flex: 1;
  min-width: 0;
  height: 34px;
  border-radius: 8px;
  border: none;
  background: var(--color-neutral-800);
  color: var(--color-text);
  padding: 0 8px;
  font-size: 12px;
  font-family: inherit;
  outline: none;
}
.date-inputs input:focus-visible { outline: 2px solid var(--color-accent); }
.date-tilde {
  color: var(--color-neutral-500);
  font-size: 12px;
}
.filter-actions {
  display: flex;
  gap: 8px;
}
.filter-reset,
.filter-apply {
  flex: 1;
  height: 40px;
  border-radius: 100px;
  border: none;
  font-size: 13px;
  font-family: inherit;
  cursor: pointer;
  color: var(--color-text);
}
.filter-reset { background: var(--color-neutral-800); }
.filter-reset.dim { opacity: 0.45; }
.filter-apply {
  background: color-mix(in srgb, var(--color-accent) 28%, transparent);
  font-weight: 700;
}

.range-chip-row {
  display: flex;
  gap: 6px;
  align-items: center;
}
.range-chip {
  height: 32px;
  padding: 0 12px;
  border-radius: 100px;
  border: none;
  background: color-mix(in srgb, var(--color-accent) 22%, transparent);
  color: var(--color-text);
  font-size: 12.5px;
  font-family: inherit;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 6px;
}
.range-chip i { font-size: 12px; }

/* — empty — */
.clips-empty {
  padding: 48px 20px;
  text-align: center;
  display: flex;
  flex-direction: column;
  gap: 10px;
  align-items: center;
}
.clips-empty i { font-size: 30px; color: var(--color-neutral-500); }
.clips-empty-title { font-size: 15px; }
.clips-empty-body {
  font-size: 13px;
  color: var(--color-neutral-400);
  line-height: 1.5;
}

/* — grid — */
.clips-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 7px;
}
.clip-card {
  position: relative;
  aspect-ratio: 1 / 1;
  border-radius: 12px;
  border: 1px solid var(--color-neutral-800);
  background: linear-gradient(150deg, #141715, #22262a);
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
.clip-date {
  position: absolute;
  left: 5px;
  top: 5px;
  font-size: 10.5px;
  color: rgba(233, 233, 237, 0.75);
  background: rgba(0, 0, 0, 0.5);
  padding: 2px 5px;
  border-radius: 4px;
  font-variant-numeric: tabular-nums;
}
.clip-caption {
  position: absolute;
  left: 5px;
  bottom: 5px;
  font-size: 11.5px;
  color: #e9e9ed;
  background: rgba(0, 0, 0, 0.5);
  padding: 2px 5px;
  border-radius: 4px;
}
.clip-pick {
  position: absolute;
  right: 5px;
  top: 5px;
  width: 18px; height: 18px;
  border-radius: 4px;
  border: 1px solid rgba(255, 255, 255, 0.4);
  background: rgba(0, 0, 0, 0.35);
  color: #12131c;
  font-size: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.clip-pick.on {
  border-color: var(--color-accent);
  background: var(--color-accent);
}

/* — pager — */
.clips-pager {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12.5px;
  color: var(--color-neutral-400);
}
.pager-count {
  margin-left: auto;
  font-variant-numeric: tabular-nums;
}
</style>
