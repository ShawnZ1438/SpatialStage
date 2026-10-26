#!/bin/zsh
# Double-click in Finder: start SpatialStage (installing on first run) and open
# the browser directly in Performance mode. Edit mode is one click away in the app.
cd "$(dirname "$0")"
export SPATIALSTAGE_URL='http://127.0.0.1:8765/?mode=perform'
exec ./run_mac.command
