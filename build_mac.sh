#!/usr/bin/env bash
set -euo pipefail

python3 -m pip install -r requirements.txt
python3 -m PyInstaller \
  --noconfirm \
  --clean \
  --windowed \
  --name FolderSyncMirror \
  --distpath dist-mac \
  --workpath build-mac \
  --add-data "config.example.json:." \
  tray_app.py

echo "Built: $(pwd)/dist-mac/FolderSyncMirror.app"
