<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { useClips } from '../composables/useClips.js'
import { useAuth } from '../composables/useAuth.js'
import { authFetch } from '../composables/useFetch.js'
import { API_ENDPOINTS } from '../endpoints.js'
import ClipItem from './ClipItem.vue'

const { clipVersion, deleteClips } = useClips()
const { isAuthenticated } = useAuth()

// ── View state ───────────────────────────────────────────────────────────────
const viewMode = ref('gallery')

// ── Filter state ─────────────────────────────────────────────────────────────
const searchQuery = ref('')
const dateFrom = ref('')
const dateTo = ref('')

// ── Pagination state ─────────────────────────────────────────────────────────
const PAGE_SIZES = [10, 25, 50, 100]
const pageSize = ref(10)
const currentPage = ref(1)

// ── Server data ───────────────────────────────────────────────────────────────
const clips = ref([])
const total = ref(0)
const checked = ref({})

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize.value)))
const selectedCount = computed(() => Object.values(checked.value).filter(Boolean).length)

// ── Fetch ─────────────────────────────────────────────────────────────────────
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
      checked.value = {}
      currentPage.value = maxPage
      return
    }
    // Keep only checked items still present on the current page
    const names = new Set(clips.value.map((c) => c.name))
    checked.value = Object.fromEntries(Object.entries(checked.value).filter(([k]) => names.has(k)))
  } catch {}
}

// Batch concurrent reactive changes into a single fetch per tick
let fetchScheduled = false
function scheduleFetch(resetPage = false) {
  if (resetPage) {
    currentPage.value = 1
    checked.value = {}
  }
  if (fetchScheduled) return
  fetchScheduled = true
  nextTick(() => {
    fetchScheduled = false
    fetchClips()
  })
}

// SSE / auth change
watch(clipVersion, () => scheduleFetch(false), { immediate: true })

// Search (debounced 300 ms)
let searchTimer = null
watch(searchQuery, () => {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => scheduleFetch(true), 300)
})

// Date filters
watch([dateFrom, dateTo], () => scheduleFetch(true))

// Page size
watch(pageSize, () => scheduleFetch(true))

// Page navigation (currentPage watcher also fires when scheduleFetch resets it;
// fetchScheduled guard ensures only one fetch per batch)
watch(currentPage, () => {
  checked.value = {}
  scheduleFetch(false)
})

// ── Actions ───────────────────────────────────────────────────────────────────
function toggleCheck(name, val) {
  checked.value = { ...checked.value, [name]: val }
}

function toggleSelectAll() {
  const next = { ...checked.value }
  if (selectedCount.value > 0) {
    for (const c of clips.value) delete next[c.name]
  } else {
    for (const c of clips.value) next[c.name] = true
  }
  checked.value = next
}

async function deleteSelected() {
  const names = Object.entries(checked.value).filter(([, v]) => v).map(([k]) => k)
  if (names.length > 0) await deleteClips(names)
}

// ── Date filter popover ───────────────────────────────────────────────────────
const datePopoverOpen = ref(false)
const dateFilterBtnRef = ref(null)
const datePopoverPos = ref({ top: 0, left: 0 })

function openDatePopover() {
  if (datePopoverOpen.value) { datePopoverOpen.value = false; return }
  if (dateFilterBtnRef.value) {
    const rect = dateFilterBtnRef.value.getBoundingClientRect()
    const popoverWidth = 300
    const left = Math.min(rect.left, window.innerWidth - popoverWidth - 8)
    datePopoverPos.value = { top: rect.bottom + 4, left: Math.max(8, left) }
  }
  datePopoverOpen.value = true
}

function localDateStr(d = new Date()) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

function setPreset(preset) {
  const today = localDateStr()
  if (preset === 'today') {
    dateFrom.value = today; dateTo.value = today
  } else if (preset === 'yesterday') {
    const d = new Date(); d.setDate(d.getDate() - 1)
    dateFrom.value = dateTo.value = localDateStr(d)
  } else if (preset === 'week') {
    const d = new Date(); const day = d.getDay()
    d.setDate(d.getDate() - (day === 0 ? 6 : day - 1))
    dateFrom.value = localDateStr(d); dateTo.value = today
  } else if (preset === 'month') {
    const d = new Date()
    dateFrom.value = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-01`
    dateTo.value = today
  }
}

function clearDateFilter() { dateFrom.value = ''; dateTo.value = '' }

const hasDateFilter = computed(() => !!(dateFrom.value || dateTo.value))

const activePreset = computed(() => {
  if (!hasDateFilter.value) return null
  const today = localDateStr()
  if (dateFrom.value === today && dateTo.value === today) return 'today'
  const dy = new Date(); dy.setDate(dy.getDate() - 1)
  if (dateFrom.value === localDateStr(dy) && dateTo.value === localDateStr(dy)) return 'yesterday'
  const dw = new Date(); const day = dw.getDay()
  dw.setDate(dw.getDate() - (day === 0 ? 6 : day - 1))
  if (dateFrom.value === localDateStr(dw) && dateTo.value === today) return 'week'
  const dm = new Date()
  const monthStart = `${dm.getFullYear()}-${String(dm.getMonth() + 1).padStart(2, '0')}-01`
  if (dateFrom.value === monthStart && dateTo.value === today) return 'month'
  return 'custom'
})

const dateFilterLabel = computed(() => {
  if (!hasDateFilter.value) return '날짜'
  const fmt = (s) => s.slice(5).replace('-', '/')
  if (dateFrom.value && dateTo.value) {
    return dateFrom.value === dateTo.value ? fmt(dateFrom.value) : `${fmt(dateFrom.value)} ~ ${fmt(dateTo.value)}`
  }
  return dateFrom.value ? `${fmt(dateFrom.value)} ~` : `~ ${fmt(dateTo.value)}`
})
</script>

<template>
  <div class="clips-panel">
    <div class="clips-toolbar">
      <div class="view-mode-group" role="group" aria-label="보기 모드">
        <button
          class="view-mode-btn"
          :class="{ active: viewMode === 'gallery' }"
          @click="viewMode = 'gallery'"
          aria-label="갤러리 보기"
          :aria-pressed="viewMode === 'gallery'"
        >
          <svg width="15" height="15" viewBox="0 0 16 16" fill="currentColor">
            <rect x="1" y="1" width="6" height="6" rx="1" />
            <rect x="9" y="1" width="6" height="6" rx="1" />
            <rect x="1" y="9" width="6" height="6" rx="1" />
            <rect x="9" y="9" width="6" height="6" rx="1" />
          </svg>
        </button>
        <button
          class="view-mode-btn"
          :class="{ active: viewMode === 'list' }"
          @click="viewMode = 'list'"
          aria-label="리스트 보기"
          :aria-pressed="viewMode === 'list'"
        >
          <svg width="15" height="15" viewBox="0 0 16 16" fill="currentColor">
            <rect x="1" y="2" width="14" height="2" rx="1" />
            <rect x="1" y="7" width="14" height="2" rx="1" />
            <rect x="1" y="12" width="14" height="2" rx="1" />
          </svg>
        </button>
      </div>

      <input type="text" class="clip-search" v-model="searchQuery" placeholder="검색..." />

      <div class="date-filter-wrap">
        <button
          ref="dateFilterBtnRef"
          class="clip-action-btn date-filter-btn"
          :class="{ active: hasDateFilter }"
          @click="openDatePopover"
          aria-label="날짜 필터"
          :aria-expanded="datePopoverOpen"
        >
          <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <rect x="1.5" y="2.5" width="13" height="12" rx="1.5" />
            <line x1="1.5" y1="6.5" x2="14.5" y2="6.5" />
            <line x1="5" y1="1" x2="5" y2="4" />
            <line x1="11" y1="1" x2="11" y2="4" />
          </svg>
          {{ dateFilterLabel }}
        </button>
      </div>

      <Teleport to="body">
        <template v-if="datePopoverOpen">
          <div class="date-popover-backdrop" @click="datePopoverOpen = false"></div>
          <div
            class="date-popover"
            role="dialog"
            aria-label="날짜 필터"
            :style="{ top: datePopoverPos.top + 'px', left: datePopoverPos.left + 'px' }"
          >
            <div class="date-presets">
              <button
                v-for="(label, key) in { today: '오늘', yesterday: '어제', week: '이번 주', month: '이번 달' }"
                :key="key"
                class="date-preset-btn"
                :class="{ active: activePreset === key }"
                @click="setPreset(key)"
              >{{ label }}</button>
            </div>
            <div class="date-range">
              <input type="date" class="date-input" v-model="dateFrom" :max="dateTo || undefined" />
              <span class="date-sep">~</span>
              <input type="date" class="date-input" v-model="dateTo" :min="dateFrom || undefined" />
            </div>
            <div class="date-popover-footer">
              <button class="clip-action-btn" :disabled="!hasDateFilter" @click="clearDateFilter">초기화</button>
              <button class="clip-action-btn" @click="datePopoverOpen = false">닫기</button>
            </div>
          </div>
        </template>
      </Teleport>

      <button class="clip-action-btn" :disabled="clips.length === 0" @click="toggleSelectAll">
        {{ selectedCount > 0 ? '선택 해제' : '모두 선택' }}
      </button>
      <button class="clip-action-btn danger" :disabled="selectedCount === 0" @click="deleteSelected">
        {{ selectedCount > 0 ? `삭제 (${selectedCount})` : '삭제' }}
      </button>
    </div>

    <div class="clips-gallery" :class="{ 'clips-list': viewMode === 'list' }">
      <template v-if="clips.length > 0">
        <ClipItem
          v-for="clip in clips"
          :key="clip.name"
          :clip="clip"
          :is-checked="!!checked[clip.name]"
          :view-mode="viewMode"
          @check="(val) => toggleCheck(clip.name, val)"
          @delete="deleteClips([clip.name])"
        />
      </template>
      <div v-else class="clip-empty">녹화된 클립 없음</div>
    </div>

    <div v-if="total > 0" class="clips-pagination">
      <button class="page-btn" :disabled="currentPage === 1" @click="currentPage--" aria-label="이전 페이지">
        <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="10,2 4,8 10,14" />
        </svg>
      </button>
      <span class="page-info">{{ currentPage }} / {{ totalPages }}</span>
      <button class="page-btn" :disabled="currentPage === totalPages" @click="currentPage++" aria-label="다음 페이지">
        <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="6,2 12,8 6,14" />
        </svg>
      </button>
      <span class="page-count">{{ (currentPage - 1) * pageSize + 1 }}–{{ Math.min(currentPage * pageSize, total) }} / {{ total }}개</span>
      <select class="page-size-select" v-model="pageSize" aria-label="페이지 크기">
        <option v-for="n in PAGE_SIZES" :key="n" :value="n">{{ n }}개</option>
      </select>
    </div>
  </div>
</template>

<style scoped>
.clips-panel {
  display: flex;
  flex-direction: column;
  gap: 12px;
  height: 100%;
}

.clips-toolbar {
  display: flex;
  gap: 6px;
  align-items: center;
  flex-wrap: wrap;
  flex-shrink: 0;
}

/* ── View mode toggle ────────────────────────────────────────────────────── */

.view-mode-group {
  display: inline-flex;
  gap: 2px;
  padding: 2px;
  border: 1px solid var(--border-input);
  border-radius: calc(var(--radius) + 2px);
  background: var(--bg-surface-secondary);
}
.view-mode-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border: none;
  border-radius: var(--radius);
  background: transparent;
  color: var(--text-3);
  cursor: pointer;
  transition: background 0.12s, color 0.12s;
}
.view-mode-btn:hover {
  background: var(--bg-surface-hover);
  color: var(--text-1);
}
.view-mode-btn.active {
  background: var(--accent);
  color: #fff;
}

/* ── Clip grid / list ────────────────────────────────────────────────────── */

.clips-gallery {
  flex: 1;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 12px;
  overflow-y: auto;
  padding: 2px;
  align-content: start;
}
.clips-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.clip-empty {
  grid-column: 1 / -1;
  font-size: 12px;
  color: var(--text-4);
  padding: 40px 0;
  text-align: center;
}

/* ── Pagination ──────────────────────────────────────────────────────────── */

.clips-pagination {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  flex-shrink: 0;
  padding: 4px 0;
}
.page-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border: 1px solid var(--border-input);
  border-radius: var(--radius);
  background: var(--bg-surface);
  color: var(--text-2);
  cursor: pointer;
  transition: background 0.12s, color 0.12s;
}
.page-btn:hover:not(:disabled) {
  background: var(--bg-surface-hover);
  color: var(--text-1);
}
.page-btn:disabled {
  opacity: 0.35;
  cursor: default;
}
.page-info {
  font-size: 13px;
  font-family: var(--font-mono);
  color: var(--text-2);
  min-width: 52px;
  text-align: center;
}
.page-count {
  font-size: 11px;
  color: var(--text-4);
}
.page-size-select {
  position: absolute;
  right: 0;
  height: 28px;
  padding: 0 6px;
  font-size: 11px;
  font-family: var(--font-ui);
  border: 1px solid var(--border-input);
  border-radius: var(--radius);
  background: var(--bg-surface);
  color: var(--text-2);
  cursor: pointer;
  outline: none;
}
.page-size-select:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-shadow);
}

/* ── Misc ────────────────────────────────────────────────────────────────── */

.clip-action-btn.active {
  background: var(--accent);
  border-color: var(--accent);
  color: #fff;
}
.clips-gallery::-webkit-scrollbar { width: 6px; }
.clips-gallery::-webkit-scrollbar-track { background: transparent; }
.clips-gallery::-webkit-scrollbar-thumb { background: var(--scrollbar); border-radius: 3px; }
.clips-gallery::-webkit-scrollbar-thumb:hover { background: var(--scrollbar-hover); }
</style>
