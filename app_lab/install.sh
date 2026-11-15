#!/bin/bash
# Build the Owl Tutor App Lab app from this repository, on the board.
#   bash app_lab/install.sh            # from the repository root
#   arduino-app-cli app start user:owl-tutor
# Needs data/index.db (python3 build_index.py) and the problem files in data/ (prepare_m3kang.py).
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
APP=~/ArduinoApps/owl-tutor
mkdir -p "$APP/python" "$APP/sketch"
cp "$REPO/app_lab/owl-tutor/app.yaml" "$APP/"
cp "$REPO/app_lab/owl-tutor/python/main.py" "$APP/python/"
cp "$REPO/owl_eyes/sketch/sketch.ino" "$REPO/owl_eyes/sketch/sketch.yaml" "$APP/sketch/"
rm -rf "$APP/python/copilot" "$APP/python/teach" "$APP/python/owl_eyes"
cp -r "$REPO/copilot" "$REPO/teach" "$APP/python/"
mkdir -p "$APP/python/owl_eyes/python" && cp "$REPO/owl_eyes/python/eyes_bridge.py" "$APP/python/owl_eyes/python/"
cp "$REPO/config.env" "$APP/python/"
mkdir -p "$APP/python/data"
for f in index.db val.jsonl demo; do [ -e "$REPO/data/$f" ] && cp -r "$REPO/data/$f" "$APP/python/data/"; done
[ -e "$REPO/data/images" ] && rm -rf "$APP/python/data/images" && cp -r "$REPO/data/images" "$APP/python/data/"  # the app container may not see paths outside the app
find "$APP" -name __pycache__ -prune -exec rm -rf {} +
echo "Built $APP. Start it: arduino-app-cli app start user:owl-tutor   (then open http://<board-ip>:8000)"
