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
# The UI is a single bundle; its screens must be in it, named as the bid manager sees them.
BUNDLE="$(curl -fsS "$WEB/" | grep -o '/assets/[^"]*\.js' | head -1)"
step "UI names its screens";       curl -fsS "$WEB$BUNDLE" | grep -q 'War Room' && curl -fsS "$WEB$BUNDLE" | grep -q 'Bid Brief' && echo ok
WORKBOOK="$(curl -fsS "$API/api/documents" | grep -o '"id":"[0-9a-f-]*","kind":"workbook"' | head -1 | cut -d'"' -f4)"
step "Bid Brief answers";          curl -fsS "$API/api/brief/$WORKBOOK" | grep -q '"must_dos"' && echo ok
step "Copilot answers, grounded";  curl -fsS -X POST "$API/api/chat" -H 'Content-Type: application/json' -d '{"message":"What must we have ready to bid?"}' | grep -q '"ungrounded":\[\]' && echo ok
echo "All smoke checks passed."
