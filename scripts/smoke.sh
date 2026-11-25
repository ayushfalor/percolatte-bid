#!/usr/bin/env bash
# Outside-in smoke test: the same few checks a reviewer would do by hand.
set -euo pipefail
# Pick up custom ports from .env if you made one
if [ -f .env ]; then set -a; . ./.env; set +a; fi
API="${API_URL:-http://localhost:${API_PORT:-8000}}"
WEB="${WEB_URL:-http://localhost:${WEB_PORT:-3000}}"

step() { printf "%-46s" "$1"; }

step "API health";                 curl -fsS "$API/health" | grep -q '"status":"ok"' && echo ok
step "UI loads";                   curl -fsS "$WEB/" | grep -q '<div id="root">' && echo ok
step "UI forwards API calls";      curl -fsS "$WEB/api/agents" | grep -q '"reader"' && echo ok
step "Sample files loaded";        curl -fsS "$API/api/documents" | grep -q 'bid_model.xlsx' && echo ok
step "Self test (engine + rules)"; curl -fsS "$API/api/selftest" | grep -q '"ok":true' && echo ok
echo "All smoke checks passed."
