# Folder Sync Mirror

Folder Sync Mirror is a small desktop utility for one-way folder mirroring. It watches a source folder, copies selected content into a target folder, and can remove target files that no longer belong to the selected source set.

Version: `1.0.0`

[中文介绍](docs/README.zh-CN.md)

## Features

- One-way source-to-target synchronization.
- Native desktop configuration for source, target, include rules, source exclusions, target protected content, trigger delay, and target cleanup.
- File-system event watching with an optional delay after changes.
- Include rules for syncing only selected files or folders.
- Source exclusion rules for content that should never be copied.
- Target protection rules for content that should not be deleted or overwritten.
- Optional deletion of extra target files so the target mirrors the selected source content.
- Background tray mode, pause/resume, manual sync, log opening, and close-to-tray behavior.
- Optional startup mode that launches in the background and starts synchronization automatically.
- Log cleanup by size: when `sync.log` exceeds 1 MB, only the last 1000 lines are kept.

## Quick Start

Download the package for your platform from the GitHub release page.

On Windows, run:

```powershell
FolderSyncMirror.exe
```

On macOS, open:

```text
FolderSyncMirror.app
```

The first launch creates `config.json` next to the app or executable. Users normally do not need to edit it by hand because the app window provides all configuration controls.

Synchronization is disabled by default. Choose a source folder and target folder, adjust rules if needed, then click `Start Sync`. After starting, the same button becomes `Pause Sync`.

## How It Works

The source folder is the authority. The target folder is managed to match the selected source content.

Rules are evaluated as relative paths:

- `include` controls what should be synced. Empty means everything.
- `exclude` removes matching source content from syncing.
- `target_protect` protects matching target content from deletion and overwrite.
- `delete_extra` removes unmanaged target files unless they match `target_protect`.

Folder rules usually use the `folder/**` pattern. Examples:

```json
{
  "include": ["docs/**", "*.md"],
  "exclude": ["node_modules/**", "*.tmp"],
  "target_protect": ["local-only/**"]
}
```

## Desktop Behavior

Closing the window hides the app to the tray instead of exiting. Use the in-app `Exit` button or tray menu to quit.

The status area uses these main states:

- `Not Started`: the app is open but not watching.
- `Listening`: waiting for source changes.
- `Change Detected`: a file-system event was received.
- `Syncing`: files are being copied, skipped, or deleted.
- `Sync Complete`: the current sync cycle finished.

The Windows build writes the startup entry to the current user's registry. The macOS build writes:

```text
~/Library/LaunchAgents/com.fusheng.foldersyncmirror.plist
```

## Command Line

Create a config file from the example, then run:

```bash
python sync_mirror.py --once
python sync_mirror.py --dry-run
python sync_mirror.py
```

Without `--once` or `--dry-run`, the command-line tool watches the source folder and syncs only when changes are detected.

## Build

Install dependencies:

```bash
python -m pip install -r requirements.txt
```

Build Windows:

```powershell
.\build_exe.ps1
```

Build macOS on macOS:

```bash
bash build_mac.sh
```

Build Linux on Linux:

```bash
bash build_linux.sh
```

PyInstaller does not cross-compile desktop apps. Build each platform on the matching operating system, or use the included GitHub Actions workflow.

## GitHub Actions Release

The workflow in `.github/workflows/release.yml` builds Windows, macOS, and Linux packages.

Create a `v1.0.0` tag and push it to publish release assets:

```bash
git tag v1.0.0
git push origin v1.0.0
```

The workflow can also be started manually from GitHub Actions.

## Author

Author: 浮生  
Email: wzxmer@outlook.com
