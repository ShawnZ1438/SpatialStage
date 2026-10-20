#!/bin/zsh
set -e
cd "$(dirname "$0")"
if ! command -v python3.12 >/dev/null 2>&1; then
  echo 'Install supported Python 3.12 first: brew install python@3.12'
  exit 1
fi
if [ ! -d .venv ]; then
  python3.12 -m venv .venv
fi
source .venv/bin/activate
python -m pip install -e .
echo 'SpatialStage running at http://127.0.0.1:8765'
(open 'http://127.0.0.1:8765' >/dev/null 2>&1 || true) &
exec spatialstage
