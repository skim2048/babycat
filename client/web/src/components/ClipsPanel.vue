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
const dateOpen = ref(false)

function localDate(offsetDays = 0) {
  const d = new Date()
  d.setDate(d.getDate() + offsetDays)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}
function monthStart() {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-01`
}

// @claude 프리셋과 임의 기간을 하나의 팝오버에 담고, 서버의
// @claude date_from/date_to로 그대로 대응시킨다.
const presets = computed(() => [
  { key: 'today', label: t('clips.preset.today'), range: () => [localDate(), localDate()] },
  { key: 'yesterday', label: t('clips.preset.yesterday'), range: () => [localDate(-1), localDate(-1)] },
  { key: 'week', label: t('clips.preset.week'), range: () => [localDate(-6), localDate()] },
  { key: 'month', label: t('clips.preset.month'), range: () => [monthStart(), localDate()] },
])

// @claude 활성 프리셋을 다시 누르면 해제된다.
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
function resetRange() {
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
  dateOpen.value = false
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
// @claude Deletion failure is reported here; the list is left as it was.
const actionError = ref('')
async function deleteSelected() {
  if (!selected.value.size) return
  actionError.value = ''
  const ok = await deleteClips([...selected.value])
  if (!ok) {
    actionError.value = t('clips.error.delete')
    return
  }
  selected.value = new Set()
  selectMode.value = false
}

// ── Playback ─────────────────────────────────────────────────────────────────
const playing = ref(null) // clip name or null
const playerSrc = computed(() =>
  playing.value ? getClipUrl(playing.value, accessToken.value || '') : '',
)

function onClipClick(clip) {
  if (selectMode.value) toggleSelected(clip.name)
  else playing.value = clip.name
}

// ── Server data ──────────────────────────────────────────────────────────────
// @claude Page sizes shared with the mobile client; 10 is the default so the
// @claude first page loads quickly even on a slow link.
const PAGE_SIZES = [10, 25, 50, 100]
const pageSize = ref(10)
const currentPage = ref(1)
const clips = ref([])
const total = ref(0)
// @claude Set when the list request fails; rendered instead of the empty state
// @claude so a broken backend is not mistaken for "no clips".
const loadError = ref('')
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
    if (!res.ok) {
      loadError.value = t('clips.error.loadStatus', { status: res.status })
      return
    }
    const data = await res.json()
    loadError.value = ''
    clips.value = data.clips || []
    total.value = data.total ?? 0
    const maxPage = Math.max(1, Math.ceil(total.value / pageSize.value))
    if (currentPage.value > maxPage) {
      currentPage.value = maxPage
      return
    }
    const names = new Set(clips.value.map((c) => c.name))
    selected.value = new Set([...selected.value].filter((n) => names.has(n)))
  } catch {
    loadError.value = t('clips.error.loadGeneric')
  }
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
// @claude 300 ms debounce: one request per typing pause instead of per keystroke.
const SEARCH_DEBOUNCE_MS = 300
let searchTimer = null
watch(searchQuery, () => {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => scheduleFetch(true), SEARCH_DEBOUNCE_MS)
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
  return getClipUrl(clip.name, accessToken.value || '')
}
</script>

<template>
  <div class="clips" @keydown.esc="dateOpen = false">

    <!-- ── Browse bar ── -->
    <div v-if="!selectMode" class="clips-bar">
      <div class="clips-search">
        <i class="ph ph-magnifying-glass"></i>
        <input v-model="searchQuery" :placeholder="t('clips.search')" />
        <button v-if="searchQuery" class="search-clear" @click="searchQuery = ''"><i class="ph ph-x"></i></button>
      </div>

      <div class="date-wrap">
        <button
          class="chip-btn"
          :class="{ on: rangeSet }"
          :aria-expanded="dateOpen"
          @click="dateOpen = !dateOpen"
        >
          <i class="ph ph-calendar-blank"></i>
          {{ rangeLabel }}
          <i :class="dateOpen ? 'ph ph-caret-up' : 'ph ph-caret-down'" class="caret"></i>
        </button>
        <div v-if="dateOpen" class="menu-backdrop" @click="dateOpen = false"></div>
        <div v-if="dateOpen" class="date-menu">
          <div class="date-presets">
            <button
              v-for="preset in presets"
              :key="preset.key"
              class="date-preset"
              :class="{ on: activePreset === preset.key }"
              @click="applyPreset(preset)"
            >{{ preset.label }}</button>
          </div>
          <div class="date-rule"></div>
          <div class="date-custom">
            <span class="date-custom-label">{{ t('clips.customRange') }}</span>
            <div class="date-inputs">
              <input v-model="dateFrom" type="date" @change="onDateInput" />
              <span class="date-tilde">~</span>
              <input v-model="dateTo" type="date" @change="onDateInput" />
            </div>
          </div>
          <div class="date-actions">
            <button class="date-reset" :class="{ dim: !rangeSet }" @click="resetRange">{{ t('clips.reset') }}</button>
            <button class="date-apply" @click="dateOpen = false">{{ t('clips.apply') }}</button>
          </div>
        </div>
      </div>

      <span class="bar-spacer"></span>
      <button class="chip-btn" @click="enterSelectMode">{{ t('clips.action.select') }}</button>
    </div>

    <!-- ── Select bar ── -->
    <div v-else class="clips-bar">
      <button class="chip-btn square" :title="t('clips.action.cancel')" @click="exitSelectMode"><i class="ph ph-x"></i></button>
      <span class="select-count">{{ t('clips.selectedCount', { count: selectedCount }) }}</span>
      <span class="bar-spacer"></span>
      <button class="chip-btn" @click="toggleSelectAll">
        {{ allOnPage ? t('clips.action.deselectAll') : t('clips.action.selectAll') }}
      </button>
      <button class="chip-btn danger" :disabled="!selectedCount" @click="deleteSelected">
        {{ t('clips.action.delete') }}
      </button>
    </div>

    <div v-if="actionError" class="form-note warn">
      <i class="ph ph-warning-circle"></i><span>{{ actionError }}</span>
    </div>

    <!-- ── Load error (distinct from an empty list) ── -->
    <div v-if="loadError" class="clips-empty">
      <i class="ph ph-warning-circle"></i>
      <div class="clips-empty-title">{{ t('clips.error.title') }}</div>
      <div class="clips-empty-body">{{ loadError }}</div>
    </div>

    <!-- ── Empty ── -->
    <div v-else-if="!clips.length" class="clips-empty">
      <i class="ph ph-film-slate"></i>
      <div class="clips-empty-title">{{ filterActive ? t('clips.noMatch.title') : t('clips.empty.title') }}</div>
      <div class="clips-empty-body">{{ filterActive ? t('clips.noMatch.body') : t('clips.empty.body') }}</div>
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
        <span class="clip-date">{{ clipDate(clip) }}</span>
        <span class="clip-caption">{{ clipCaption(clip) }}</span>
        <span v-if="selectMode" class="clip-pick" :class="{ on: selected.has(clip.name) }">
          <svg v-if="selected.has(clip.name)" class="check-glyph" viewBox="0 0 12 12" aria-hidden="true"><polyline points="2.5,6.5 5,9 9.5,3.5" /></svg>
        </span>
      </button>
    </div>

    <!-- ── Pager ── -->
    <div v-if="clips.length" class="clips-pager">
      <span class="pager-label">{{ t('clips.perPage') }}</span>
      <div class="size-seg">
        <button
          v-for="n in PAGE_SIZES"
          :key="n"
          class="size-opt"
          :class="{ active: pageSize === n }"
          @click="pageSize = n"
        >{{ n }}</button>
      </div>
      <span class="pager-count">{{ rangeText }}</span>
      <button class="chip-btn square" :disabled="currentPage <= 1" @click="currentPage--">
        <i class="ph ph-caret-left"></i>
      </button>
      <button class="chip-btn square" :disabled="currentPage >= totalPages" @click="currentPage++">
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

.clips {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

/* — filter / select bar — */
.clips-bar {
  flex: none;
  display: flex;
  gap: 8px;
  align-items: center;
}
.bar-spacer { flex: 1; }
.clips-search {
  position: relative;
  flex: 1;
  min-width: 0;
  max-width: 300px;
  display: flex;
  align-items: center;
}
.clips-search > i {
  position: absolute;
  left: 10px;
  font-size: 15.5px;
  color: var(--color-neutral-500);
  pointer-events: none;
}
.clips-search input {
  width: 100%;
  box-sizing: border-box;
  height: 34px;
  border-radius: 7px;
  border: none;
  background: var(--color-neutral-900);
  color: var(--color-text);
  padding: 0 30px;
  font-size: 13.5px;
  font-family: inherit;
  outline: none;
}
.clips-search input:focus-visible { outline: 2px solid var(--color-accent); }
.search-clear {
  position: absolute;
  right: 6px;
  width: 22px; height: 22px;
  border: none;
  background: none;
  color: var(--color-neutral-400);
  font-size: 14.5px;
  cursor: pointer;
  border-radius: 11px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.search-clear:hover { background: var(--color-neutral-800); }
.chip-btn.square { padding: 0; width: 34px; justify-content: center; font-size: 15px; }
.select-count { font-size: 13.5px; }

/* — date popover — */
.date-wrap { position: relative; flex: none; }
.date-wrap .caret { font-size: 12px; color: var(--color-neutral-400); }
.menu-backdrop {
  position: fixed;
  inset: 0;
  z-index: 19;
}
.date-menu {
  position: absolute;
  top: 40px;
  left: 0;
  z-index: 20;
  width: 288px;
  background: var(--color-surface);
  border-radius: 10px;
  padding: 12px;
  box-shadow: var(--shadow-md);
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.date-presets {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 6px;
}
.date-preset {
  height: 34px;
  border-radius: 7px;
  border: none;
  background: var(--color-neutral-900);
  color: var(--color-text);
  font-size: 13.5px;
  font-family: inherit;
  cursor: pointer;
}
.date-preset:hover { background: color-mix(in srgb, var(--color-accent) 22%, transparent); }
.date-preset.on { background: color-mix(in srgb, var(--color-accent) 16%, transparent); }
.date-rule { height: 1px; background: var(--color-divider); }
.date-custom {
  display: flex;
  flex-direction: column;
  gap: 7px;
}
.date-custom-label {
  font-size: 12.5px;
  color: var(--color-neutral-400);
}
.date-inputs {
  display: flex;
  align-items: center;
  gap: 6px;
}
.date-inputs input {
  flex: 1;
  min-width: 0;
  height: 34px;
  border-radius: 7px;
  border: none;
  background: var(--color-neutral-900);
  color: var(--color-text);
  padding: 0 10px;
  font-size: 13px;
  font-family: inherit;
  outline: none;
}
.date-inputs input:focus-visible { outline: 2px solid var(--color-accent); }
.date-tilde {
  color: var(--color-neutral-500);
  font-size: 13px;
}
.date-actions { display: flex; gap: 8px; }
.date-reset,
.date-apply {
  flex: 1;
  height: 34px;
  border-radius: 7px;
  border: none;
  font-size: 13.5px;
  font-family: inherit;
  cursor: pointer;
  color: var(--color-text);
}
.date-reset { background: var(--color-neutral-900); }
.date-reset.dim { opacity: 0.45; }
.date-reset:hover { background: color-mix(in srgb, var(--color-accent) 22%, transparent); }
.date-apply {
  background: color-mix(in srgb, var(--color-accent) 28%, transparent);
  font-weight: 700;
}
.date-apply:hover { background: color-mix(in srgb, var(--color-accent) 42%, transparent); }

/* — empty — */
.clips-empty {
  flex: 1;
  padding: 70px 20px;
  text-align: center;
  display: flex;
  flex-direction: column;
  gap: 10px;
  align-items: center;
  justify-content: center;
}
.clips-empty i { font-size: 34px; color: var(--color-neutral-500); }
.clips-empty-title { font-size: 16.5px; }
.clips-empty-body {
  font-size: 14px;
  color: var(--color-neutral-400);
  line-height: 1.5;
}

/* — grid — */
.clips-grid {
  flex: 1;
  min-height: 0;
  overflow: auto;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  grid-auto-rows: min-content;
  align-content: start;
  gap: 12px;
}
.clip-card {
  position: relative;
  aspect-ratio: 16 / 9;
  border-radius: 8px;
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
  left: 6px;
  top: 6px;
  font-size: 11.5px;
  color: rgba(233, 233, 237, 0.75);
  background: rgba(0, 0, 0, 0.5);
  padding: 2px 6px;
  border-radius: 4px;
  font-variant-numeric: tabular-nums;
}
.clip-caption {
  position: absolute;
  left: 6px;
  bottom: 6px;
  font-size: 12.5px;
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
  border-radius: 4px;
  border: 1px solid rgba(255, 255, 255, 0.4);
  background: rgba(0, 0, 0, 0.35);
  color: #12131c;
  font-size: 12.5px;
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
  flex: none;
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 13.5px;
  color: var(--color-neutral-400);
}
.pager-label { margin-left: auto; }
.size-seg {
  display: flex;
  gap: 3px;
  padding: 3px;
  border-radius: 8px;
  background: var(--color-neutral-900);
}
.size-opt {
  height: 28px;
  padding: 0 9px;
  border-radius: 6px;
  border: none;
  background: transparent;
  color: var(--color-neutral-400);
  font-size: 13px;
  font-family: inherit;
  cursor: pointer;
  font-variant-numeric: tabular-nums;
}
.size-opt.active {
  background: color-mix(in srgb, var(--color-accent) 28%, transparent);
  color: var(--color-text);
}
.pager-count {
  font-variant-numeric: tabular-nums;
  min-width: 90px;
  text-align: right;
}
</style>
