#!/usr/bin/env bash
# Upload any workbook and print what the app understood about it.
#   bash scripts/try-workbook.sh path/to/your_model.xlsx
set -euo pipefail
# Pick up custom ports from .env if you made one
if [ -f .env ]; then set -a; . ./.env; set +a; fi
FILE="${1:?Usage: bash scripts/try-workbook.sh path/to/model.xlsx}"
API="${API_URL:-http://localhost:${API_PORT:-8000}}"

RESP=$(curl -fsS -F "file=@${FILE}" "$API/api/documents")
DOC_ID=$(printf '%s' "$RESP" | sed -n 's/.*"document":{"id":"\([^"]*\)".*/\1/p')
echo "Uploaded as document $DOC_ID"
echo "--- structure (sheets, names, inputs, unused numbers)"
curl -fsS "$API/api/workbooks/$DOC_ID/structure"
echo
echo "--- does our engine agree with the values Excel saved?"
curl -fsS "$API/api/workbooks/$DOC_ID/parity"
echo
echo "Next: POST $API/api/workbooks/$DOC_ID/goal-seek  (see $API/docs)"
