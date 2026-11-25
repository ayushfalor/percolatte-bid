#!/usr/bin/env bash
# Waits until the API answers /health (used by CI; handy locally too).
set -euo pipefail
# Pick up custom ports from .env if you made one
if [ -f .env ]; then set -a; . ./.env; set +a; fi
URL="${API_URL:-http://localhost:${API_PORT:-8000}}/health"
for i in $(seq 1 90); do
  if curl -fsS "$URL" >/dev/null 2>&1; then echo "API healthy after ${i}x2s"; exit 0; fi
  sleep 2
done
echo "API did not become healthy: $URL" >&2
docker compose ps >&2 || true
exit 1
