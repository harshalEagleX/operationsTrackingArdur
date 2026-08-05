#!/usr/bin/env bash
#
# Deploy the current branch.
#
#   ./scripts/deploy.sh
#
# Assumes the process manager on the host exposes the service names below.
# Adapt SERVICE_* to match however the app is supervised in your environment.

set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${VENV:-$APP_DIR/.venv}"
SETTINGS="${DJANGO_SETTINGS_MODULE:-opstracking.settings.prod}"

cd "$APP_DIR"

echo "→ Pulling changes"
git pull --ff-only

echo "→ Installing dependencies"
"$VENV/bin/pip" install -r requirements.txt --quiet

echo "→ Applying migrations"
"$VENV/bin/python" manage.py migrate --noinput --settings="$SETTINGS"

echo "→ Collecting static files"
"$VENV/bin/python" manage.py collectstatic --noinput --settings="$SETTINGS"

echo "→ Checking deployment settings"
"$VENV/bin/python" manage.py check --deploy --settings="$SETTINGS"

# Reload the HTTP process gracefully: in-flight requests finish, no 502s.
echo "→ Reloading web process"
${RELOAD_API_CMD:-true}

echo "→ Restarting background workers"
${RESTART_WORKER_CMD:-true}

# Restarting the websocket process disconnects every user, and they all
# reconnect at once. Only do it when consumer code actually changed.
if [ "${RESTART_WS:-0}" = "1" ]; then
  echo "→ Restarting websocket process"
  ${RESTART_WS_CMD:-true}
else
  echo "→ Skipping websocket restart (set RESTART_WS=1 when consumers changed)"
fi

echo "→ Verifying"
sleep 3
"$APP_DIR/scripts/healthcheck.sh"

echo ""
echo "Deployed."
