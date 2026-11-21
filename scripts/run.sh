#!/usr/bin/env sh
# One command on macOS or Linux: create the environment, build the desk and start InventIQ on http://127.0.0.1:8000
set -e
cd "$(dirname "$0")/.."
[ -d .venv ] || python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip -q
.venv/bin/python -m pip install -e ".[dev]" -q
if [ ! -f web/dist/index.html ]; then (cd web && npm ci --no-audit --no-fund && npm run build); fi
exec .venv/bin/python -m inventiq serve
