#!/bin/sh
# Local deploy artifact: Vite dist + editable Python package (same layout as combined Docker).
set -eu
cd "$(dirname "$0")/.."
(cd frontend && npm ci && npm run build)
test -f frontend/dist/index.html
echo "STATIC_DIR=$(pwd)/frontend/dist"
echo "pactlify frontend built. Combined run:"
echo "  STATIC_DIR=$(pwd)/frontend/dist python -m uvicorn apps.api.main:app --workers 1 --host 0.0.0.0 --port 8000"
