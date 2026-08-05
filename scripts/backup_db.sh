#!/usr/bin/env bash
#
# Nightly database and storage backup.
#
#   crontab -e
#   0 2 * * * /path/to/app/scripts/backup_db.sh
#
# A host snapshot protects the machine. It does not give you a point-in-time
# table restore when someone truncates the wrong thing at 4pm. Keep both.

set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_DIR="${BACKUP_DIR:-$APP_DIR/../backups}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"

# shellcheck disable=SC1091
[ -f "$APP_DIR/.env" ] && set -a && . "$APP_DIR/.env" && set +a

mkdir -p "$BACKUP_DIR"
stamp="$(date +%F_%H%M)"

# DATABASE_URL looks like postgres://user:pass@host:port/name
proto="${DATABASE_URL%%://*}"

case "$proto" in
  postgres|postgresql)
    echo "Backing up PostgreSQL…"
    pg_dump "$DATABASE_URL" | gzip > "$BACKUP_DIR/db_${stamp}.sql.gz"
    ;;
  mysql)
    echo "Backing up MySQL…"
    # --single-transaction keeps InnoDB consistent without locking the app out.
    mysqldump --single-transaction --quick --routines \
      -u"${DB_USER:?set DB_USER}" -p"${DB_PASSWORD:?set DB_PASSWORD}" \
      "${DB_NAME:?set DB_NAME}" | gzip > "$BACKUP_DIR/db_${stamp}.sql.gz"
    ;;
  *)
    echo "Unrecognised database in DATABASE_URL: $proto" >&2
    exit 1
    ;;
esac

echo "Backing up uploaded files…"
STORAGE="${PRIVATE_STORAGE_ROOT:-$APP_DIR/storage}"
[ -d "$STORAGE" ] && rsync -a --delete "$STORAGE/" "$BACKUP_DIR/storage/"

echo "Pruning backups older than ${RETENTION_DAYS} days…"
find "$BACKUP_DIR" -name 'db_*.sql.gz' -mtime "+$RETENTION_DAYS" -delete

echo "Done: $BACKUP_DIR/db_${stamp}.sql.gz"
echo ""
echo "A backup you have never restored is a hypothesis. Test one into a"
echo "scratch database on a schedule."
