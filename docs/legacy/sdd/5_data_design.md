# 5. 데이터 설계 (Data Design)

## 5.1 데이터 모델 (Data Model)

시스템의 영속 데이터는 다섯 갈래이며, 데이터 단독 소유 원칙(§2.2)에 따라 갈래마다 소유자가 하나다.

|데이터|소유자|저장 형태|
|---|---|---|
|사용자 계정·리프레시 토큰|***Request router***|SQLite (`router.db`)|
|비디오 소스 프로필(홈 위치 포함)|***Video streamer***|JSON 파일|
|이벤트 발생 이력|***Event recorder***|SQLite (`recorder.db`)|
|비디오 클립·사이드카 메타데이터|***Event recorder***|파일시스템(mp4 + json 쌍)|
|런타임 상태(프롬프트·키워드·분석 활성 여부)|***Video analyzer***·***Event recorder*** 각자|JSON 파일|

모든 소유자는 자기 데이터의 유일한 소비자이기도 하다. 프로필은 ***Video streamer***가 저장하고 자신이 소스 접속·PTZ에 사용하며, 계정 데이터는 ***Request router***가 저장하고 자신이 인증에 사용한다.

관계는 두 가지다. 발생 이력 레코드는 클립 식별자로 클립 파일을 가리키고, 클립 파일과 사이드카는 같은 기본 이름의 쌍이다. 클립 파일 자체는 데이터베이스에 넣지 않고 식별 정보만 기록한다(SRS §6.4).

영속 데이터 외에, 재배포 스트림에서 파생되는 휘발 버퍼가 두 개 있다. 같은 스트림의 서로 다른 가공물이며, 형태가 소비 목적에 맞춰져 있어 서로의 용도를 대신할 수 없다 — 두 소비자가 스트림을 독립적으로 받는 결정(§2.4 (7))의 근거가 이 표다.

| |***Video analyzer***의 링 버퍼|***Event recorder***의 세그먼트 버퍼|
|---|---|---|
|위치|프로세스 메모리|tmpfs 파일(램 기반)|
|담는 단위|디코딩된 프레임|1초 단위 H.264 세그먼트 파일|
|내용|VLM 입력 크기로 축소된 RGB, 목표 주기당 1장|원본 해상도, 1초 키프레임으로 재인코딩된 압축 비디오|
|보존|링 크기만큼(수십 초)|보존 창(사전 구간 + 사후 구간 + 결합 여유)|
|순환|가장 오래된 프레임 자동 축출|보존 시간 지난 파일 삭제|
|용도|VLM에 넣을 최신 프레임 묶음|이벤트 전후 구간의 클립 결합 재료|

## 5.2 데이터베이스 스키마 (Database Schema)

두 데이터베이스 모두 단일 프로세스만 접근하므로 잠금 경합이 없다. WAL 저널 모드를 사용한다.

### `router.db` (***Request router***)

|테이블|컬럼|비고|
|---|---|---|
|`users`|`id` INTEGER PK, `username` TEXT UNIQUE, `password_hash` TEXT, `salt` TEXT, `password_changed` INTEGER, `token_epoch` INTEGER, `failed_count` INTEGER, `locked_until` REAL, `created_at` TEXT|해시는 솔트와 결합한 PBKDF2 산출물(`NFR-012`). `token_epoch`는 즉시 폐기용 세대(§4.1). 실패 계수·차단 만료는 재시작 회피를 막기 위해 DB에 둔다(`FR-007`)|
|`refresh_tokens`|`id` INTEGER PK, `token_hash` TEXT UNIQUE, `username` TEXT, `expires_at` INTEGER, `revoked` INTEGER, `created_at` INTEGER|원문은 저장하지 않는다(`FR-002`). 회전·폐기는 `revoked` 표시로 무효화한다(`FR-045`)|

### `recorder.db` (***Event recorder***)

|테이블|컬럼|비고|
|---|---|---|
|`events`|`id` INTEGER PK AUTOINCREMENT, `trigger` TEXT, `clip_name` TEXT, `created_at` TEXT(ISO 8601, 판정 시각)|`FR-031`의 세 요소: 트리거·클립 식별자·발생 시각. 컬럼 이름은 프로토타입의 외부 계약(`EventOut`)을 승계한다|

인덱스는 `events(created_at)` 하나만 둔다. 조회 조건(SRS `FR-034`) 중 날짜 범위는 이 인덱스가 감당하고, 키워드는 부분 일치(LIKE)라서 인덱스 효과가 없으나 이력 규모가 저장 공간 상한에 의해 유계이므로 전수 검색으로 충분하다.

## 5.3 파일시스템 구조 (Filesystem Layout)

호스트의 `./data`와 `./config`를 컨테이너에 마운트한다. 경로 규칙은 다음과 같다.

```
data/
├─ db/
│  ├─ router/router.db      # router에만 마운트
│  └─ recorder/recorder.db  # recorder에만 마운트
├─ clips/{YYYY}/{MM}/       # recorder에만 마운트
│  ├─ {YYYYMMDD}_{HHMMSS}_{ms}.mp4
│  └─ {YYYYMMDD}_{HHMMSS}_{ms}.json
├─ state/
│  ├─ analyzer/analyzer.json  # analyzer에만 마운트
│  └─ recorder/recorder.json  # recorder에만 마운트
└─ models/                  # analyzer에만 마운트 (VLM 캐시·컴파일 결과)
config/
└─ cam_profile.json         # streamer에만 마운트
```

데이터베이스와 상태 파일이 서비스별 하위 디렉터리에 놓이는 것은 마운트 구획 때문이다. 컨테이너에는 자기 하위 디렉터리만 마운트되므로, 소유하지 않은 데이터는 파일시스템 수준에서 보이지 않는다(§8.1).

클립과 사이드카는 같은 기본 이름의 쌍이며, 발생 이력의 `clip` 컬럼이 이 기본 이름을 가리킨다. 연/월 디렉터리는 파일 수 폭증을 막기 위한 분할이고, 기본 이름의 시각이 곧 발생 시각이므로 별도 매핑 없이 경로를 유도할 수 있다.

세그먼트 버퍼는 영속 볼륨이 아니라 `recorder` 컨테이너의 tmpfs(`/run/babycat-segments`)에 둔다. 초당 파일 생성·삭제가 반복되는 데이터를 플래시 스토리지에 쓰지 않기 위함이다.

## 5.4 설정 데이터 (Configuration Data)

사용자가 설정하는 값의 저장 형식과 기본값은 다음과 같다. 외부에서 주입받는 값은 §8.3에서 다룬다.

- **비디오 소스 프로필** (`config/cam_profile.json`) — `source_type`(v1.0은 `rtsp_camera` 고정), `ip`, `username`, `password`, `rtsp_port`(기본 554), `stream_path`(기본 `stream1`), `onvif_port`(선택), `ptz_home`(선택). 조회 응답에서는 `password`를 설정 여부로만 반환한다(`FR-013`).
- **analyzer 상태 파일** (컨테이너 안 `/data/state/analyzer.json`, 호스트는 §5.3의 구획 `data/state/analyzer/`) — `prompt`(기본 `Describe the scene.`, `FR-026`), `keywords`(기본 빈 목록 — 이때 키워드 매칭을 수행하지 않는다, `FR-027`), `analysis_active`(기본 false — 저장만으로 분석이 시작되지 않는다, `FR-025`).
- **recorder 상태 파일** (컨테이너 안 `/data/state/recorder.json`, 호스트는 §5.3의 구획 `data/state/recorder/`) — `buffer_active`(기본 false). 분석 시작과 함께 참이 된다(§2.4 (4)).

상태 파일은 재기동 복원(`FR-014`)의 근거다. 각 소유자가 자기 파일만 읽고 쓰므로 복원에 컴포넌트 간 조율이 없다(§3.5).

## 5.5 데이터 수명 주기 (Data Lifecycle)

- **클립·사이드카·이력** — 이벤트 판정 시 한 절차에서 함께 생성된다(§4.4). 소멸 경로는 둘이다. ① 사용자 삭제(`FR-039`·`FR-040`): 클립과 사이드카를 쌍으로 삭제한다(`FR-041`). 발생 이력은 남긴다 — 이벤트가 발생했다는 사실은 클립을 지워도 사실이며, 이력 삭제는 별도 기능(`FR-035`·`FR-036`)이다. 클립이 없는 이력의 재생 요청은 부재 응답을 받는다. ② 자동 삭제(`FR-033`): 가용 공간이 임계 이하로 떨어지면 가장 오래된 클립부터 사이드카·대응 이력과 함께 삭제하고, 삭제 사실을 로그에 남긴다(`NFR-010`).
- **세그먼트** — 분석 중에만 생성되며(§2.4 (4)), 보존 창(사전 구간 + 사후 구간 + 결합 지연 여유)을 지난 세그먼트는 즉시 삭제된다. tmpfs에 있으므로 재시작 시 전량 소멸하며, 이는 감수된 손실이다(§4.4).
- **리프레시 토큰** — 발급 시 해시로 저장되고, 갱신 시 회전으로 폐기·재발급되며(`FR-045`), 만료 레코드는 접근 시 지연 삭제된다.
- **발생 이력** — 자동 삭제(`FR-033`) 외에는 사용자 삭제(`FR-035`·`FR-036`)로만 소멸한다. 보존 상한은 SRS가 보류한 항목이므로 별도 상한을 두지 않고, 저장 공간 임계가 실질 상한으로 작동한다.
