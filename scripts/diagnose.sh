#!/usr/bin/env bash
# @claude Babycat diagnostic script.
# @claude Collects state in one pass for a fresh Jetson or suspected issues.
# @claude Continues past individual failures (set +e).
#
# @claude Usage:  bash scripts/diagnose.sh
# @claude Or:     chmod +x scripts/diagnose.sh && ./scripts/diagnose.sh

set +e

# @claude Tee every line to stdout and to the result file (ANSI colors stripped from the file).
# @claude Override the result path with BABYCAT_DIAG_OUT.
RESULT="${BABYCAT_DIAG_OUT:-diagnose.result.txt}"
exec > >(tee >(sed -uE 's/\x1b\[[0-9;]*m//g' > "$RESULT")) 2>&1

H()    { printf "\n\033[1;36m=== %s ===\033[0m\n" "$1"; }
OK()   { printf "  \033[32m✓\033[0m %s\n" "$1"; }
WARN() { printf "  \033[33m!\033[0m %s\n" "$1"; }
FAIL() { printf "  \033[31m✗\033[0m %s\n" "$1"; }

# ── 1. Latest git commit ─────────────────────────────────────────────────────
H "1. Latest git commit (master should end at 34670ae or newer)"
git log --oneline -7 2>&1 | sed 's/^/  /'

# ── 2. Container status ──────────────────────────────────────────────────────
H "2. docker container status (watch for Up / Restarting / Exited)"
docker ps -a --format "table {{.Names}}\t{{.Status}}" 2>&1 | sed 's/^/  /'

# ── 3. babycat-app logs ──────────────────────────────────────────────────────
H "3. babycat-app last 60 lines (model load / traceback / restart loop clues)"
docker logs babycat-app --tail 60 2>&1 | sed 's/^/  /'

# ── 4. babycat-web logs ──────────────────────────────────────────────────────
H "4. babycat-web last 30 lines (vite proxy errors)"
docker logs babycat-web --tail 30 2>&1 | sed 's/^/  /'

# ── 5. babycat-api logs ──────────────────────────────────────────────────────
H "5. babycat-api last 30 lines"
docker logs babycat-api --tail 30 2>&1 | sed 's/^/  /'

# ── 6. Health endpoints ──────────────────────────────────────────────────────
H "6. /health status codes (200 = ok, ERR = unreachable)"
APP=$(curl -s -o /dev/null -w "%{http_code}" -m 3 http://localhost:8080/health 2>/dev/null || echo ERR)
API=$(curl -s -o /dev/null -w "%{http_code}" -m 3 http://localhost:8000/health 2>/dev/null || echo ERR)
WEB=$(curl -s -o /dev/null -w "%{http_code}" -m 3 http://localhost:5173/ 2>/dev/null || echo ERR)
echo "  app:8080  → $APP"
echo "  api:8000  → $API"
echo "  web:5173  → $WEB"

# ── 7. Token issuance ────────────────────────────────────────────────────────
H "7. Login + token issuance (admin/admin)"
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
  OK "token issued (length: ${#TOKEN})"
else
  FAIL "token issuance failed — api container down or user seeding failed"
fi

# ── 8..10. Token-dependent checks ────────────────────────────────────────────
if [ -n "$TOKEN" ]; then

  H "8. /clips (vite 5173 → api; response must be {clips,total})"
  RESP=$(curl -s -m 3 -H "Authorization: Bearer $TOKEN" http://localhost:5173/clips 2>/dev/null)
  echo "  $(echo "$RESP" | head -c 400)"
  echo "$RESP" | grep -q '"clips"' && OK "response OK ({clips,total} confirmed)" \
                                 || FAIL "unexpected shape — check that the vite proxy points at app:8080"

  H "9. /camera (vite 5173 → app)"
  curl -s -m 3 -H "Authorization: Bearer $TOKEN" http://localhost:5173/camera 2>/dev/null | head -c 300
  echo

  H "10. /events SSE first message (4s timeout)"
  echo "  ── via 5173 (vite → app) ──"
  timeout 4 curl -sN "http://localhost:5173/events?token=$TOKEN" 2>&1 | head -3 | sed 's/^/    /'
  echo "  ── via 8080 (app direct) ──"
  timeout 4 curl -sN "http://localhost:8080/events?token=$TOKEN" 2>&1 | head -3 | sed 's/^/    /'

fi

# ── 11. Disk state ───────────────────────────────────────────────────────────
H "11. ./data directory (models / DB / clips)"
if [ -d ./data ]; then
  ls -la ./data 2>/dev/null | head -10 | sed 's/^/  /'
  if [ -d ./data/models/mlc/dist ]; then
    OK "mlc compile output directory present"
    find ./data/models/mlc/dist -name "*.so" 2>/dev/null | head -3 | sed 's/^/    /'
  else
    WARN "./data/models/mlc/ missing — model compile likely incomplete"
  fi
else
  WARN "./data missing — containers may have never booted successfully"
fi

# ── 12. Config files ─────────────────────────────────────────────────────────
H "12. ./config directory"
ls -la ./config 2>&1 | sed 's/^/  /'

printf "\n\033[1;36m=== Diagnostics complete ===\033[0m\n"
echo "Result file: $RESULT (ANSI-stripped plain text)"
echo "Please send the output above or the result file."
