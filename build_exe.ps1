$ErrorActionPreference = "Stop"

py -3 -m pip install -r requirements.txt
py -3 -m PyInstaller `
  --noconfirm `
  --clean `
  --windowed `
  --onefile `
  --name FolderSyncMirror `
  --distpath dist-onefile `
  --workpath build-onefile `
  --add-data "config.example.json;." `
  tray_app.py

Write-Host "Built: $PWD\dist-onefile\FolderSyncMirror.exe"
