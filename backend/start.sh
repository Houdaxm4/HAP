#!/usr/bin/env bash
# Production process for Render (single worker: pipeline uses in-process BackgroundTasks).
set -euo pipefail
cd "$(dirname "$0")"
exec uvicorn main:app --host 0.0.0.0 --port "${PORT:-8000}" --workers 1 --proxy-headers
