#!/usr/bin/env bash
# Dump the database to <dir>/bidbench-<timestamp>.sql.gz and drop dumps older than KEEP_DAYS (14).
#   bash scripts/backup-db.sh /backups
# Works in two places:
#   inside a container that has DATABASE_URL (the nightly backup service, the api image)
#   on the host next to docker-compose.yml, where it goes through the db container
set -euo pipefail
DIR="${1:-./backups}"
KEEP_DAYS="${KEEP_DAYS:-14}"
mkdir -p "$DIR"
STAMP="$(date -u +%Y%m%d-%H%M%S)"
OUT="$DIR/bidbench-$STAMP.sql.gz"

if [ -n "${DATABASE_URL:-}" ]; then
  # SQLAlchemy's URL names the driver; libpq wants plain postgresql://
  URL="${DATABASE_URL/postgresql+psycopg:/postgresql:}"
  pg_dump --no-owner --no-privileges "$URL" | gzip > "$OUT"
else
  if [ -f .env ]; then set -a; . ./.env; set +a; fi
  docker compose exec -T db pg_dump --no-owner --no-privileges -U bidbench bidbench | gzip > "$OUT"
fi

SIZE=$(wc -c < "$OUT" | tr -d ' ')
if [ "$SIZE" -lt 1000 ]; then echo "backup looks empty ($SIZE bytes): $OUT" >&2; exit 1; fi
find "$DIR" -name 'bidbench-*.sql.gz' -mtime "+$KEEP_DAYS" -delete
echo "backup written: $OUT ($SIZE bytes), keeping $KEEP_DAYS days in $DIR"
