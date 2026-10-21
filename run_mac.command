#!/bin/zsh
set -eu
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  PYTHON="${SPATIALSTAGE_PYTHON:-}"
  if [ -z "$PYTHON" ]; then
    for candidate in python3.12 python3.13 python3.11 python3; do
      if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; assert (3,11) <= sys.version_info[:2] < (3,14)' 2>/dev/null; then
        PYTHON="$candidate"
        break
      fi
    done
  fi
  if [ -z "$PYTHON" ]; then
    echo 'Install supported Python first: brew install python@3.12'
    exit 1
  fi
  "$PYTHON" -m venv .venv
fi
if ! .venv/bin/python -c 'import sys; assert (3,11) <= sys.version_info[:2] < (3,14)'; then
  echo 'Existing .venv is incompatible. Back up and recreate it with Python 3.11-3.13.'
  exit 1
fi
source .venv/bin/activate
STAMP="$(shasum -a 256 pyproject.toml | cut -d ' ' -f 1)"
if [ ! -f .venv/.spatialstage-install ] || [ "$(cat .venv/.spatialstage-install)" != "$STAMP" ]; then
  python -m pip install -e .
  printf '%s\n' "$STAMP" > .venv/.spatialstage-install
fi
echo 'SpatialStage running at http://127.0.0.1:8765'
(
  for attempt in $(seq 1 40); do
    if curl -fsS http://127.0.0.1:8765/api/health >/dev/null 2>&1; then
      open 'http://127.0.0.1:8765' >/dev/null 2>&1 || true
      break
    fi
    sleep 0.25
  done
) &
exec spatialstage
