#!/usr/bin/env bash
# Start the backend in dev mode (auto-reload). Run from the backend/ directory.
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f .env ] || cp .env.example .env
exec uvicorn app.main:app --reload --host 0.0.0.0 --port "${PORT:-8000}"
