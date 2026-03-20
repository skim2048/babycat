# 260321 — 모노레포 구조 개편 및 프론트엔드 초기 구성

이전 세션 파일: `260319_onvif_ptz_dashboard.md`

---

## 1. 모노레포 구조 개편

### 1.1 디렉토리 이름 변경

| 변경 전 | 변경 후 | 이유 |
|---|---|---|
| `backend/` | `server/` | 알파벳 정렬 시 시각적 일관성 |
| `frontend/` | `webapp/` | 동일 |
| `docs/` (→ `backend/docs/`에서 루트로 이동됐었음) | `journal/` | 내용이 API 문서가 아닌 개발 일지이므로 |

최종 루트 구조:
```
wally/
├── docker-compose.yml
├── journal/
├── server/
└── webapp/
```

### 1.2 docker-compose.yml 루트 이동

`server/docker-compose.yml` → 루트 `docker-compose.yml`로 이동.
`server/`와 `webapp/` 두 서비스를 단일 파일에서 오케스트레이션.

경로 참조 변경:
- `./backend/` → `./server/`
- `./frontend/` → `./webapp/`

---

## 2. 프론트엔드 Docker 서비스 구성

### 2.1 구성

- `webapp/docker/Dockerfile` — multi-stage: `node:22-alpine` 빌드 → `nginx:alpine` 서빙
- `webapp/docker/nginx.conf` — Vue Router history mode (`try_files $uri /index.html`)
- 포트: 3000 → 80

### 2.2 트러블슈팅

| 증상 | 원인 | 해결 |
|---|---|---|
| 컨테이너 crash loop | nginx 시작 시 upstream `wally-backend-api` resolve 실패 (api 미구현) | `/api/` proxy 블록 제거 (api 구현 후 재추가) |
| `depends_on: api` 빌드 실패 | `server/src/api/` 디렉토리 없음 | `depends_on` 제거 (api 구현 후 재추가) |

---

## 3. 프론트엔드 레이아웃 수정

### 3.1 문제

기존 코드는 Figma export 결과물로 추정 — 모든 요소가 픽셀 절대값으로 배치돼 화면 크기 변화 시 레이아웃 붕괴.
`src/assets/main.css`에 Vite 기본 보일러플레이트(`#app { max-width: 1280px; padding: 2rem }`)가 앱 스타일을 덮어쓰는 문제도 있었음.

### 3.2 수정 내용

| 컴포넌트 | 변경 내용 |
|---|---|
| `main.css` | Vite 보일러플레이트 제거 |
| `App.vue` | `--nav-height: 64px` CSS 변수 선언 |
| `HomePage.vue` | `position: fixed` → flexbox column, `padding-bottom: var(--nav-height)` |
| `AppLogo.vue` | `position: absolute` → flexbox |
| `StateBar.vue` | 픽셀 절대값 → `justify-content: space-between` |
| `CamView.vue` | `flex-shrink: 0` 추가 |
| `CamBar.vue` | 픽셀 절대값 → `justify-content: space-evenly` |
| `HomeIcons.vue` | 픽셀 절대값 → `justify-content: space-around`, `flex: 1` |
| `Chat.vue` | `left: 322px; top: 670px` → `right: 16px; bottom: calc(var(--nav-height) + 16px)` FAB |
| `NavItem.vue` | 아이콘 24px, 레이블 11px 명시 |

캘린더·알람·설정 페이지: `AppLogo` + "준비 중" placeholder.

---

## 4. 미결 및 다음 세션 후보

| 항목 | 내용 |
|---|---|
| docker profiles (`prod`/`dev`) | nginx ↔ vite dev 서버 전환 구성 |
| `depends_on: api` 복원 | api 서버 구현 완료 후 |
| 캘린더·알람·설정 페이지 구현 | 미착수 |
| 백엔드 API 서버 구현 | `server/src/api/` 미존재 |
