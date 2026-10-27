#!/bin/zsh
set -eu
cd "$(dirname "$0")"
echo 'Save browser edits first. This stops only this checkout when idle and muted.'
if [ ! -x .venv/bin/python ]; then
  echo 'Missing local Python environment. No process stopped.'
  exit 1
fi
exec .venv/bin/python scripts/stop_spatialstage.py
