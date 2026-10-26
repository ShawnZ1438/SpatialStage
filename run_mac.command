#!/bin/zsh
set -eu
cd "$(dirname "$0")"
URL="${SPATIALSTAGE_URL:-http://127.0.0.1:8765/}"
# A second double-click must not start a second engine on the operator port.
if curl -fsS http://127.0.0.1:8765/api/health >/dev/null 2>&1; then
  echo "SpatialStage is already running. Opening $URL"
  open "$URL"
  exit 0
fi
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
echo 'Keep this window open during the show; closing it stops the audio engine.'
echo '演出期间请保持此窗口打开；关闭窗口会停止音频引擎。'
(
  for attempt in $(seq 1 40); do
    if curl -fsS http://127.0.0.1:8765/api/health >/dev/null 2>&1; then
      open "$URL" >/dev/null 2>&1 || true
      break
    fi
    sleep 0.25
  done
) &
# caffeinate keeps the Mac and display awake only while the engine runs.
if command -v caffeinate >/dev/null 2>&1; then
  exec caffeinate -dims spatialstage
fi
exec spatialstage
