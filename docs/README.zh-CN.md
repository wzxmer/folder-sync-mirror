# Folder Sync Mirror 中文介绍

Folder Sync Mirror 是一个用于单向镜像同步文件夹的小工具。它会监听“来源”文件夹的变化，把符合规则的内容同步到“目标”文件夹，并可自动删除目标中多出的内容，让目标保持一致。

当前版本：`1.0.0`

[English README](../README.md)

## 主要功能

- 来源到目标的单向同步。
- 在软件界面中配置来源、目标、同步内容、排除内容、保留内容、触发延迟和清理选项。
- 只在来源内容发生变化时触发同步，可设置变动后的延迟，最低 0 秒。
- 可选择只同步指定文件或文件夹。
- 可排除来源中的指定文件或文件夹。
- 可设置目标中的保留内容，保留内容不会被删除，也不会被覆盖。
- 可开启“清理目标多余文件”，让目标与选中的来源内容保持一致。
- 支持托盘后台运行、暂停同步、继续同步、立即同步、打开日志。
- 点击关闭窗口不会退出程序，只会收起到托盘。
- 可开启“开机启动并启用同步”，开机后自动后台监听。
- 日志按大小清理：`sync.log` 超过 1 MB 时，只保留最后 1000 行。

## 使用方法

下载对应平台的发布包。

Windows 运行：

```powershell
FolderSyncMirror.exe
```

macOS 打开：

```text
FolderSyncMirror.app
```

Windows 首次启动会在程序旁边生成 `config.json`。macOS 和 Linux 会把配置与日志写入当前用户的应用配置目录。一般不需要手动打开配置文件，直接在软件窗口内选择和保存即可。

默认不会自动启动同步。先选择来源文件夹和目标文件夹，再按需要设置同步内容、排除内容、保留内容，然后点击“启动同步”。启动后按钮会变成“暂停同步”。

## 规则说明

来源是标准内容，目标是被同步和清理的目录。

- `同步内容`：只同步哪些来源内容。留空表示同步全部。
- `排除内容`：来源中不参与同步的内容，优先级高于同步内容。
- `保留内容`：目标中不想被删除或覆盖的内容。
- `清理目标多余文件`：开启后，目标中不属于同步结果且不在保留内容里的文件会被删除。

文件夹规则通常使用：

```text
folder/**
```

示例：

```json
{
  "include": ["docs/**", "*.md"],
  "exclude": ["node_modules/**", "*.tmp"],
  "target_protect": ["local-only/**"]
}
```

## 状态含义

- `未启动`：程序已打开，但没有监听。
- `监听中`：正在等待来源变化。
- `检测到变动`：已收到来源变化通知。
- `正在同步`：正在复制、跳过或删除文件。
- `同步完成`：本次同步已完成。

## 开机启动

Windows 会写入当前用户启动项，不需要管理员权限。

macOS 会写入：

```text
~/Library/LaunchAgents/com.fusheng.foldersyncmirror.plist
```

## 命令行使用

复制或创建配置后可以运行：

```bash
python sync_mirror.py --once
python sync_mirror.py --dry-run
python sync_mirror.py
```

不加 `--once` 或 `--dry-run` 时，命令行会监听来源文件夹，只在检测到变动后同步。

## 构建

安装依赖：

```bash
python -m pip install -r requirements.txt
```

Windows 打包：

```powershell
.\build_exe.ps1
```

macOS 需要在 macOS 上打包：

```bash
bash build_mac.sh
```

Linux 需要在 Linux 上打包：

```bash
bash build_linux.sh
```

PyInstaller 不能在 Windows 上直接交叉打包 macOS 程序。需要在对应系统上打包，或使用本项目的 GitHub Actions 自动构建。

## 作者

作者：浮生  
联系邮箱：wzxmer@outlook.com
