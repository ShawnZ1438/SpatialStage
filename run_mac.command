#!/bin/zsh
set -e
cd "$(dirname "$0")"
if ! command -v python3 >/dev/null 2>&1; then
  echo 'Python 3.11-3.13 is required. Install it via Homebrew or python.org.'
  exit 1
fi
if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
source .venv/bin/activate
python -m pip install -e .
echo 'Open http://127.0.0.1:8765 in Chrome or Safari.'
(open 'http://127.0.0.1:8765' >/dev/null 2>&1 || true) &
exec stagespatialcue
