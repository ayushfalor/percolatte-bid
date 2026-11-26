#!/usr/bin/env bash
# Restore a dump into a database and report what it holds.
#   bash scripts/restore-db.sh backups/bidbench-20260101-020000.sql.gz            # into a scratch db, then drop it
#   bash scripts/restore-db.sh backups/bidbench-20260101-020000.sql.gz bidbench_check  # into that db, keep it
#   FORCE=1 bash scripts/restore-db.sh <dump> bidbench                            # replace the live database
# Prints "documents: N" so a caller (or the eval suite) can check the restore against the live app.
set -euo pipefail
DUMP="${1:?Usage: bash scripts/restore-db.sh <dump.sql.gz> [database]}"
TARGET="${2:-bidbench_restore_scratch}"
SCRATCH=0; [ "$#" -lt 2 ] && SCRATCH=1
# The image's pg_dump (PostgreSQL 17 client) writes settings a 16 server does not know; psql would
# stop on them. They carry no data, so they are dropped on the way in.
SKIP_SET='^SET (transaction_timeout|idle_session_timeout) '

if [ "$TARGET" = "bidbench" ] && [ "${FORCE:-0}" != "1" ]; then
  echo "Refusing to replace the live database without FORCE=1" >&2; exit 2
fi

if [ -n "${DATABASE_URL:-}" ]; then
  URL="${DATABASE_URL/postgresql+psycopg:/postgresql:}"
  ADMIN="${URL%/*}/postgres"
  run_sql() { psql -v ON_ERROR_STOP=1 -qtA "$1" -c "$2"; }
  load() { gunzip -c "$DUMP" | grep -vE "$SKIP_SET" | psql -v ON_ERROR_STOP=1 -q "${URL%/*}/$TARGET" > /dev/null; }
else
  if [ -f .env ]; then set -a; . ./.env; set +a; fi
  run_sql() { docker compose exec -T db psql -v ON_ERROR_STOP=1 -qtA -U bidbench -d "${1##*/}" -c "$2"; }
  ADMIN="postgres"
  load() { gunzip -c "$DUMP" | grep -vE "$SKIP_SET" | docker compose exec -T db psql -v ON_ERROR_STOP=1 -q -U bidbench -d "$TARGET" > /dev/null; }
fi

run_sql "$ADMIN" "DROP DATABASE IF EXISTS $TARGET" > /dev/null
run_sql "$ADMIN" "CREATE DATABASE $TARGET" > /dev/null
load
COUNT=$(run_sql "${ADMIN%/*}/$TARGET" "SELECT count(*) FROM documents")
RUNS=$(run_sql "${ADMIN%/*}/$TARGET" "SELECT count(*) FROM runs")
echo "restored $DUMP into $TARGET. documents: $COUNT, runs: $RUNS"
if [ "$SCRATCH" = "1" ]; then run_sql "$ADMIN" "DROP DATABASE $TARGET" > /dev/null; echo "scratch database dropped"; fi
