#!/usr/bin/env bash
set -euo pipefail

python3 -m pip install -r requirements.txt
python3 -m PyInstaller \
  --noconfirm \
  --clean \
  --windowed \
  --onefile \
  --name FolderSyncMirror \
  --distpath dist-linux \
  --workpath build-linux \
  --add-data "config.example.json:." \
  tray_app.py

echo "Built: $(pwd)/dist-linux/FolderSyncMirror"
