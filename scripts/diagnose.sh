#!/usr/bin/env bash
# Babycat 진단 스크립트
# 새 젯슨 또는 동작 이상이 의심되는 환경에서 한번에 상태를 수집한다.
# 한 항목이 실패해도 다음 항목으로 진행 (set +e).
#
# 사용:  bash scripts/diagnose.sh
# 또는: chmod +x scripts/diagnose.sh && ./scripts/diagnose.sh

set +e

# 모든 출력을 stdout과 결과 파일에 동시 저장 (파일에는 ANSI 색상 제거).
# 결과 파일 경로는 BABYCAT_DIAG_OUT 환경변수로 덮어쓸 수 있다.
RESULT="${BABYCAT_DIAG_OUT:-diagnose.result.txt}"
exec > >(tee >(sed -uE 's/\x1b\[[0-9;]*m//g' > "$RESULT")) 2>&1

H()    { printf "\n\033[1;36m=== %s ===\033[0m\n" "$1"; }
OK()   { printf "  \033[32m✓\033[0m %s\n" "$1"; }
WARN() { printf "  \033[33m!\033[0m %s\n" "$1"; }
FAIL() { printf "  \033[31m✗\033[0m %s\n" "$1"; }

# ── 1. Git 최신 커밋 ─────────────────────────────────────────────────────────
H "1. Git 최신 커밋 (master 끝에 34670ae가 있어야 최신)"
git log --oneline -7 2>&1 | sed 's/^/  /'

# ── 2. 컨테이너 상태 ────────────────────────────────────────────────────────
H "2. docker 컨테이너 상태 (Up·Restarting·Exited 확인)"
docker ps -a --format "table {{.Names}}\t{{.Status}}" 2>&1 | sed 's/^/  /'

# ── 3. babycat-app 로그 ─────────────────────────────────────────────────────
H "3. babycat-app 최근 60줄 (모델 로드/Traceback/restart loop 단서)"
docker logs babycat-app --tail 60 2>&1 | sed 's/^/  /'

# ── 4. babycat-web 로그 ─────────────────────────────────────────────────────
H "4. babycat-web 최근 30줄 (vite proxy 에러)"
docker logs babycat-web --tail 30 2>&1 | sed 's/^/  /'

# ── 5. babycat-api 로그 ─────────────────────────────────────────────────────
H "5. babycat-api 최근 30줄"
docker logs babycat-api --tail 30 2>&1 | sed 's/^/  /'

# ── 6. health 엔드포인트 도달 ──────────────────────────────────────────────
H "6. /health 응답 코드 (200=정상, ERR=도달 실패)"
APP=$(curl -s -o /dev/null -w "%{http_code}" -m 3 http://localhost:8080/health 2>/dev/null || echo ERR)
API=$(curl -s -o /dev/null -w "%{http_code}" -m 3 http://localhost:8000/health 2>/dev/null || echo ERR)
WEB=$(curl -s -o /dev/null -w "%{http_code}" -m 3 http://localhost:5173/ 2>/dev/null || echo ERR)
echo "  app:8080  → $APP"
echo "  api:8000  → $API"
echo "  web:5173  → $WEB"

# ── 7. 토큰 발급 ──────────────────────────────────────────────────────────
H "7. 로그인 + 토큰 발급 (admin/admin)"
TOKEN=$(curl -s -m 3 -X POST http://localhost:8000/api/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"admin"}' \
  2>/dev/null \
  | python3 -c "import sys,json
try:
  d=json.load(sys.stdin); print(d.get('token',''))
except Exception:
  pass" 2>/dev/null)
if [ -n "$TOKEN" ]; then
  OK "토큰 발급 성공 (길이: ${#TOKEN})"
else
  FAIL "토큰 발급 실패 — api 컨테이너가 안 떴거나 user 시딩 실패"
fi

# ── 8~10. 토큰 의존 검증 ──────────────────────────────────────────────────
if [ -n "$TOKEN" ]; then

  H "8. /clips (vite 5173 → api 경로, 응답이 {clips,total} 형식이어야 정상)"
  RESP=$(curl -s -m 3 -H "Authorization: Bearer $TOKEN" http://localhost:5173/clips 2>/dev/null)
  echo "  $(echo "$RESP" | head -c 400)"
  echo "$RESP" | grep -q '"clips"' && OK "응답 OK ({clips,total} 형식 확인)" \
                                 || FAIL "예상 형식 아님 — vite proxy가 app:8080 가리키는지 확인"

  H "9. /camera (vite 5173 → app 경로)"
  curl -s -m 3 -H "Authorization: Bearer $TOKEN" http://localhost:5173/camera 2>/dev/null | head -c 300
  echo

  H "10. /events SSE 첫 메시지 (4초 timeout)"
  echo "  ── via 5173 (vite → app) ──"
  timeout 4 curl -sN "http://localhost:5173/events?token=$TOKEN" 2>&1 | head -3 | sed 's/^/    /'
  echo "  ── via 8080 (app 직접) ──"
  timeout 4 curl -sN "http://localhost:8080/events?token=$TOKEN" 2>&1 | head -3 | sed 's/^/    /'

fi

# ── 11. 디스크 상태 ─────────────────────────────────────────────────────────
H "11. ./data 디렉토리 (모델·DB·클립)"
if [ -d ./data ]; then
  ls -la ./data 2>/dev/null | head -10 | sed 's/^/  /'
  if [ -d ./data/models/mlc/dist ]; then
    OK "mlc 컴파일 결과 디렉토리 존재"
    find ./data/models/mlc/dist -name "*.so" 2>/dev/null | head -3 | sed 's/^/    /'
  else
    WARN "./data/models/mlc/ 없음 — 모델 컴파일 미완 가능성"
  fi
else
  WARN "./data 없음 — 컨테이너가 한 번도 정상 가동되지 않았을 가능성"
fi

# ── 12. 설정 파일 ──────────────────────────────────────────────────────────
H "12. ./config 디렉토리"
ls -la ./config 2>&1 | sed 's/^/  /'

printf "\n\033[1;36m=== 진단 완료 ===\033[0m\n"
echo "결과 파일: $RESULT (ANSI 색상 제거된 plain 버전)"
echo "위 출력 또는 결과 파일 내용을 보내 주세요."
