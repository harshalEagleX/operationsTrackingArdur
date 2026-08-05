#!/usr/bin/env bash
#
# Probe every service. Exits non-zero if anything is down, so it works as a
# cron alert or a deploy gate.
#
#   ./scripts/healthcheck.sh
#   API_URL=http://127.0.0.1:8001 ./scripts/healthcheck.sh

set -uo pipefail

API_URL="${API_URL:-http://127.0.0.1:8000}"
WS_URL="${WS_URL:-http://127.0.0.1:8002}"

failures=0

check() {
  local label="$1" url="$2"
  if curl -fsS --max-time 5 "$url" >/dev/null 2>&1; then
    echo "  ok    $label"
  else
    echo "  FAIL  $label  ($url)"
    failures=$((failures + 1))
  fi
}

echo "Checking OpsTracking services…"

check "API liveness"   "$API_URL/health/"
check "API readiness"  "$API_URL/ready/"
check "WS process"     "$WS_URL/health/"

# The readiness endpoint reports its own dependency checks; surface them.
if body=$(curl -fsS --max-time 5 "$API_URL/ready/" 2>/dev/null); then
  echo "$body" | python3 -c '
import json, sys
data = json.load(sys.stdin).get("data", {})
for name, result in data.get("checks", {}).items():
    status = "ok  " if result.get("ok") else "FAIL"
    print(f"  {status}  {name}")
' 2>/dev/null || true
fi

if [ "$failures" -gt 0 ]; then
  echo ""
  echo "$failures check(s) failed."
  exit 1
fi

echo ""
echo "All checks passed."
