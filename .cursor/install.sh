#!/usr/bin/env bash
# Idempotent dependency refresh for the HAP Cloud Agent environment.
# Prepares the FastAPI backend (Python venv) and the Next.js frontend (npm).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# --- Backend: Python virtual environment + dependencies ---
# Ensure the stdlib venv/ensurepip support is present. On stock Debian/Ubuntu
# the python3-venv package is required to create virtual environments. This is
# a best-effort guard; the base snapshot normally already provides it.
if ! python3 -c "import ensurepip" >/dev/null 2>&1; then
  echo "[install] python venv support missing; attempting to install python3-venv"
  if command -v sudo >/dev/null 2>&1; then
    sudo apt-get update -qq && sudo apt-get install -y python3-venv || true
  fi
fi

cd "$REPO_ROOT/backend"
if [ ! -d .venv ]; then
  echo "[install] creating backend virtualenv"
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
. .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
deactivate

# --- Frontend: Node dependencies ---
cd "$REPO_ROOT/frontend"
npm install

echo "[install] HAP environment ready."
