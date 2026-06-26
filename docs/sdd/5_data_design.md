# 5. Data Design; 데이터 설계

***Storage***에 보관되는 데이터는 두 갈래다 — SQLite 데이터베이스와 파일시스템 파일(클립·메타데이터·프로필·세그먼트). 본 절은 그 형식과 소유를 기술한다.

## 5.1 Clip Path Schema; 클립 경로 스키마

이벤트 클립은 날짜 계층 아래 시각 기반 이름으로 저장된다.

`{DATA_DIR}/{YYYY}/{MM}/{YYYYMMDD}_{HHMMSS}_{ms}.mp4`

- `DATA_DIR`는 기본 `/data`(컨테이너 `CAM_DIR`)이다.
- Babycat은 **단일 카메라**를 전제하므로, 프로필이 바뀌어도 클립은 카메라별로 나뉘지 않고 같은 날짜 계층에 누적된다.
- 각 클립에는 동명의 `.json` 메타데이터(§5.2)가 한 짝으로 따른다.
- 소유: ***App Server***가 쓰고 ***API Server***가 조회·삭제한다(§3.5, D-C).

## 5.2 Clip Metadata; 클립 메타데이터

클립과 동명의 `.json` 사이드카로, 소비용 필드와 진단용 필드로 나뉜다.

- **소비용**(***Client App***이 보는 정보) — `timestamp`(이벤트 시각), `keywords`(유발 키워드), `vlm_text`(VLM 판단 텍스트).
- **진단용** — `record_mode`(`segment_rollover`/`direct_rtsp_record`), `capture_source`, 클립 크기·길이, 추론·ffmpeg 소요 시간 등 사후 분석 정보.

DB가 아니라 파일시스템 사이드카로 둔 이유는, 클립 파일과 그 설명을 한 묶음으로 옮기거나 지우기 위함이다.

## 5.3 Database Schema; 데이터베이스 스키마

`/data/db/babycat.db`(SQLite, WAL 모드). 네 테이블로 구성된다.

| 테이블 | 주요 컬럼 | 용도 |
|---|---|---|
| `users` | `username`(UNIQUE)·`password_hash`·`salt`·`password_changed`·`created_at` | 계정 |
| `refresh_tokens` | `token_hash`(UNIQUE)·`username`·`expires_at`·`revoked`·`created_at` | 토큰 회전 |
| `events` | `trigger`·`clip_name`·`created_at` | 이벤트 이력 |
| `devices` | `fcm_token`(UNIQUE)·`label`·`registered_at` | 푸시 알림 기기 |

`events.clip_name`이 클립 파일(§5.1)을 가리켜 DB의 이벤트 이력과 파일시스템의 클립을 잇는다. 이벤트 정보가 DB와 파일(사이드카)에 나뉘어 있는 점, 그리고 ***App Server***의 기록과 ***API Server***의 조회가 같은 DB를 공유하는 점은 데이터 계약(D-C)에서 다룬다.

## 5.4 Camera Profile; 카메라 프로필

***RTSP Source*** 접속·제어 정보로, `/data/config/cam_profile.json`에 단일 JSON으로 저장된다(런타임 상태이므로 ***Storage*** 아래에 둔다).

| 필드 | 기본값 | 비고 |
|---|---|---|
| `ip` | — | 필수 |
| `username` | — | 필수 |
| `password` | — | 필수(빈 값이면 기존 값 유지) |
| `rtsp_port` | `554` | |
| `stream_path` | `stream1` | |
| `onvif_port` | (없음) | 선택; PTZ 지원 시에만 |

- RTSP URL은 `rtsp://{username}:{password}@{ip}:{rtsp_port}/{stream_path}`로 조립된다.
- ONVIF URL은 `http://{ip}:{onvif_port}/onvif/service`이며, `onvif_port`가 있을 때만 PTZ가 가능하다.
- 프로필 저장(2-1)은 이 파일을 갱신할 뿐이고, 실제 스트림 반영(적용, 2-4)은 ***MediaMTX Server*** 소스 설정(§3.3의 (3))으로 별도 수행된다.

근거: `app/camera.py`(`_normalize_rtsp_camera_profile`, `_build_rtsp_url`, `_build_onvif_url`), `api/auth.py`·`api/database.py`(DB 스키마), `app/trigger_clip_diagnostics.py`(`build_trigger_clip_meta`)
