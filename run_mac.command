#!/bin/zsh
set -eu
cd "$(dirname "$0")"
URL="${SPATIALSTAGE_URL:-http://127.0.0.1:8765/}"
INSTALL_ONLY=0
NO_OPEN=0
for arg in "$@"; do
  case "$arg" in
    --simulation) export STAGE_SPATIAL_DATA="$PWD/SpatialStage-test-data" ;;
    --install-only) INSTALL_ONLY=1 ;;
    --no-open) NO_OPEN=1 ;;
    *) echo "Usage: $0 [--simulation] [--install-only] [--no-open]"; exit 2 ;;
  esac
done
if [ ! -d .venv ]; then
  PYTHON="${SPATIALSTAGE_PYTHON:-}"
  if [ -z "$PYTHON" ]; then
    # Explicit paths cover Homebrew/python.org installs when PATH is not set up yet.
    for candidate in python3.12 python3.13 python3.11 python3 /opt/homebrew/bin/python3.12 \
        /usr/local/bin/python3.12 /Library/Frameworks/Python.framework/Versions/3.12/bin/python3; do
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
# Find the code in this folder directly. The editable-install link inside .venv
# breaks if the folder was moved/renamed, and Python 3.13 on macOS skips it when
# the file carries the hidden flag (Desktop / iCloud folders) -> ModuleNotFoundError.
export PYTHONPATH="$PWD${PYTHONPATH:+:$PYTHONPATH}"
STAMP="$(shasum -a 256 pyproject.toml | cut -d ' ' -f 1)"
if [ ! -f .venv/.spatialstage-install ] || [ "$(cat .venv/.spatialstage-install)" != "$STAMP" ]; then
  python -m pip install -e .
  printf '%s\n' "$STAMP" > .venv/.spatialstage-install
fi
if ! python -c 'import stagespatialcue.server' 2>/dev/null; then
  echo 'Dependencies are missing or broken; reinstalling...'
  python -m pip install -e . && printf '%s
' "$STAMP" > .venv/.spatialstage-install
  if ! python -c 'import stagespatialcue.server'; then
    echo 'Still cannot load SpatialStage. Delete the .venv folder in this directory and double-click again.'
    exit 1
  fi
fi
if [ "$INSTALL_ONLY" = 1 ]; then
  echo 'Installation complete: use Start SpatialStage.command or Start Simulation (Mac).command'
  exit 0
fi
# Compare startup snapshots, including edited source and the selected data root.
if curl -fsS http://127.0.0.1:8765/api/health >/dev/null 2>&1; then
  if python - <<'PY'
import json, os, urllib.request
from stagespatialcue.runtime import runtime_identity
with urllib.request.urlopen('http://127.0.0.1:8765/api/health', timeout=3) as response:
    actual = json.load(response).get('runtime', {})
expected = runtime_identity(os.environ.get('STAGE_SPATIAL_DATA', '~/.spatialstage/projects'))
raise SystemExit(0 if all(actual.get(k) == expected[k] for k in ('source_root', 'source_sha256', 'data_root')) else 1)
PY
  then
    echo "Matching SpatialStage already running: $URL"
    [ "$NO_OPEN" = 1 ] || open "$URL"
    exit 0
  fi
  echo 'Port 8765 belongs to a different/stale engine or data mode. Save work, stop capture/measurement, PANIC, run Stop SpatialStage.command, then retry. No process was stopped.'
  exit 1
fi
if lsof -nP -iTCP:8765 -sTCP:LISTEN >/dev/null 2>&1; then
  echo 'Port 8765 is occupied by another service. No process was stopped.'
  exit 1
fi
echo "SpatialStage: $URL"
echo "Data: ${STAGE_SPATIAL_DATA:-$HOME/.spatialstage/projects}"
echo 'Keep this Terminal open. Ctrl+C stops the engine. Output starts disconnected/muted.'
if [ "$NO_OPEN" != 1 ]; then
  (
    for attempt in $(seq 1 80); do
      if curl -fsS http://127.0.0.1:8765/api/health >/dev/null 2>&1; then
        open "$URL" >/dev/null 2>&1 || true
        break
      fi
      sleep 0.25
    done
  ) &
fi
if command -v caffeinate >/dev/null 2>&1; then
  exec caffeinate -dims spatialstage
fi
exec spatialstage
