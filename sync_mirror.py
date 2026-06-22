#!/usr/bin/env python3
"""Mirror selected files from one folder to another."""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import re
import shutil
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from version import __version__


DEFAULT_INTERVAL_SECONDS = 0.0
DEFAULT_CONFIG_TEXT = """{
  // 来源文件夹：同步来源。请改成你的来源路径。
  "source": "",

  // 目标文件夹：同步目标。程序会让目标与来源中“被选择同步的内容”保持一致。
  "target": "",

  // 只同步哪些内容。
  // 留空 [] 表示同步来源下所有未被 exclude 排除的内容。
  // 示例："*.md" 只同步所有 md 文件，"docs/**" 只同步 docs 文件夹。
  "include": [],

  // 来源中排除哪些内容不同步。exclude 优先级高于 include。
  // 被 exclude 命中的内容不会从来源同步到目标。
  "exclude": [],

  // 目标中哪些内容不由程序管理。
  // 被 target_protect 命中的内容不会被覆盖，也不会因为目标与来源不一致而被自动删除。
  "target_protect": [],

  // 来源内容变动后延迟多少秒再同步。0 表示立即同步。
  "interval_seconds": 0,

  // 是否删除目标中多出的文件，让目标与来源中被选择同步的内容一致。
  "delete_extra": true,

  // 定时任务。
  "scheduled_tasks": {
    // 定时合并天行键自造词。来源文件夹应为 iCloud 方案目录，目标文件夹应为本机 RimeData。
    "auto_merge_zzc": false,

    // 合并写入哪些正式码表，路径相对来源文件夹。必须选择至少一个；新增词写入第一个目标码表。
    "zzc_target_dicts": [],

    // 自动合并自造词的最小间隔，单位分钟。
    "zzc_merge_interval_minutes": 30,

    // 开机启动后是否自动执行一次合并。
    "startup_auto_merge": false,

    // 开机后等待多少分钟再执行第一次自动合并，用来等待 iCloud 同步稳定。
    "startup_delay_minutes": 10,

    // 合并后是否自动重新部署。
    "auto_deploy_after_merge": false,

    // 重新部署命令。留空时程序会尝试自动查找小狼毫部署程序。
    "deploy_command": ""
  }
}
"""


@dataclass(frozen=True)
class ScheduledTasksConfig:
    auto_merge_zzc: bool
    zzc_target_dicts: tuple[str, ...]
    zzc_merge_interval_minutes: float
    startup_auto_merge: bool
    startup_delay_minutes: float
    auto_deploy_after_merge: bool
    deploy_command: str


@dataclass(frozen=True)
class SyncConfig:
    source: Path
    target: Path
    include: tuple[str, ...]
    exclude: tuple[str, ...]
    target_protect: tuple[str, ...]
    interval_seconds: float
    delete_extra: bool
    scheduled_tasks: ScheduledTasksConfig


@dataclass
class SyncStats:
    copied: int = 0
    deleted: int = 0
    skipped: int = 0
    errors: int = 0

    def has_changes(self) -> bool:
        return bool(self.copied or self.deleted or self.errors)


class SyncChangeHandler(FileSystemEventHandler):
    def __init__(self, callback) -> None:
        super().__init__()
        self.callback = callback

    def on_any_event(self, event: FileSystemEvent) -> None:
        if event.is_directory and event.event_type == "opened":
            return
        self.callback()


def load_config(config_path: Path) -> SyncConfig:
    try:
        config_text = strip_json_comments(config_path.read_text(encoding="utf-8"))
        data = json.loads(config_text)
    except FileNotFoundError:
        raise SystemExit(f"配置文件不存在: {config_path}")
    except json.JSONDecodeError as exc:
        raise SystemExit(f"配置文件格式错误: {exc}") from exc

    try:
        source_text = str(data["source"]).strip()
        target_text = str(data["target"]).strip()
        source = Path(source_text).expanduser() if source_text else Path()
        target = Path(target_text).expanduser() if target_text else Path()
    except KeyError as exc:
        raise SystemExit(f"配置缺少必填字段: {exc.args[0]}") from exc

    include = normalize_patterns(data.get("include", []))
    exclude = normalize_patterns(data.get("exclude", []))
    target_protect = normalize_patterns(data.get("target_protect", []))
    interval_seconds = float(data.get("interval_seconds", DEFAULT_INTERVAL_SECONDS))
    delete_extra = bool(data.get("delete_extra", True))
    scheduled_data = data.get("scheduled_tasks", {})
    if not isinstance(scheduled_data, dict):
        scheduled_data = {}
    scheduled_tasks = ScheduledTasksConfig(
        auto_merge_zzc=bool(scheduled_data.get("auto_merge_zzc", False)),
        zzc_target_dicts=normalize_patterns(scheduled_data.get("zzc_target_dicts", [])),
        zzc_merge_interval_minutes=float(scheduled_data.get("zzc_merge_interval_minutes", 30)),
        startup_auto_merge=bool(scheduled_data.get("startup_auto_merge", False)),
        startup_delay_minutes=float(scheduled_data.get("startup_delay_minutes", 10)),
        auto_deploy_after_merge=bool(scheduled_data.get("auto_deploy_after_merge", False)),
        deploy_command=str(scheduled_data.get("deploy_command", "")).strip(),
    )

    return SyncConfig(
        source=source.resolve() if source_text else source,
        target=target.resolve() if target_text else target,
        include=include,
        exclude=exclude,
        target_protect=target_protect,
        interval_seconds=interval_seconds,
        delete_extra=delete_extra,
        scheduled_tasks=scheduled_tasks,
    )


def strip_json_comments(text: str) -> str:
    pattern = re.compile(
        r"""
        ("(?:\\.|[^"\\])*")
        |(/\*.*?\*/)
        |(//[^\r\n]*)
        """,
        re.DOTALL | re.VERBOSE,
    )

    def replace(match: re.Match[str]) -> str:
        if match.group(1):
            return match.group(1)
        return ""

    return pattern.sub(replace, text)


def normalize_patterns(patterns: Iterable[str]) -> tuple[str, ...]:
    return tuple(str(item).replace("\\", "/") for item in patterns)


def create_default_config(config_path: Path) -> None:
    config_path.write_text(
        DEFAULT_CONFIG_TEXT,
        encoding="utf-8",
    )


def format_config_text(config: SyncConfig) -> str:
    include_text = format_pattern_list(config.include)
    exclude_text = format_pattern_list(config.exclude)
    target_protect_text = format_pattern_list(config.target_protect)
    delete_extra = "true" if config.delete_extra else "false"
    auto_merge_zzc = "true" if config.scheduled_tasks.auto_merge_zzc else "false"
    zzc_target_dicts = format_pattern_list(config.scheduled_tasks.zzc_target_dicts)
    startup_auto_merge = "true" if config.scheduled_tasks.startup_auto_merge else "false"
    auto_deploy_after_merge = "true" if config.scheduled_tasks.auto_deploy_after_merge else "false"
    deploy_command = json.dumps(config.scheduled_tasks.deploy_command, ensure_ascii=False)[1:-1]
    source_text = "" if is_empty_path(config.source) else json_escape_path(config.source)
    target_text = "" if is_empty_path(config.target) else json_escape_path(config.target)
    return f"""{{
  // 来源文件夹：同步来源。请改成你的来源路径。
  "source": "{source_text}",

  // 目标文件夹：同步目标。程序会让目标与来源中“被选择同步的内容”保持一致。
  "target": "{target_text}",

  // 只同步哪些内容。
  // 留空 [] 表示同步来源下所有未被 exclude 排除的内容。
  // 示例："*.md" 只同步所有 md 文件，"docs/**" 只同步 docs 文件夹。
  "include": {include_text},

  // 来源中排除哪些内容不同步。exclude 优先级高于 include。
  // 被 exclude 命中的内容不会从来源同步到目标。
  "exclude": {exclude_text},

  // 目标中哪些内容不由程序管理。
  // 被 target_protect 命中的内容不会被覆盖，也不会因为目标与来源不一致而被自动删除。
  "target_protect": {target_protect_text},

  // 来源内容变动后延迟多少秒再同步。0 表示立即同步。
  "interval_seconds": {config.interval_seconds:g},

  // 是否删除目标中多出的文件，让目标与来源中被选择同步的内容一致。
  "delete_extra": {delete_extra},

  // 定时任务。
  "scheduled_tasks": {{
    // 定时合并天行键自造词。来源文件夹应为 iCloud 方案目录，目标文件夹应为本机 RimeData。
    "auto_merge_zzc": {auto_merge_zzc},

    // 合并写入哪些正式码表，路径相对来源文件夹。必须选择至少一个；新增词写入第一个目标码表。
    "zzc_target_dicts": {zzc_target_dicts},

    // 自动合并自造词的最小间隔，单位分钟。
    "zzc_merge_interval_minutes": {config.scheduled_tasks.zzc_merge_interval_minutes:g},

    // 开机启动后是否自动执行一次合并。
    "startup_auto_merge": {startup_auto_merge},

    // 开机后等待多少分钟再执行第一次自动合并，用来等待 iCloud 同步稳定。
    "startup_delay_minutes": {config.scheduled_tasks.startup_delay_minutes:g},

    // 合并后是否自动重新部署。
    "auto_deploy_after_merge": {auto_deploy_after_merge},

    // 重新部署命令。留空时程序会尝试自动查找小狼毫部署程序。
    "deploy_command": "{deploy_command}"
  }}
}}
"""


def save_config(config_path: Path, config: SyncConfig) -> None:
    config_path.write_text(format_config_text(config), encoding="utf-8")


def json_escape_path(path: Path) -> str:
    return json.dumps(path.as_posix(), ensure_ascii=False)[1:-1]


def format_pattern_list(patterns: Iterable[str]) -> str:
    patterns = tuple(patterns)
    if not patterns:
        return "[]"
    lines = [json.dumps(pattern, ensure_ascii=False) for pattern in patterns]
    body = ",\n    ".join(lines)
    return f"[\n    {body}\n  ]"


def ensure_safe_config(config: SyncConfig) -> None:
    if is_empty_path(config.source) or is_empty_path(config.target):
        raise SystemExit("请先选择来源文件夹和目标文件夹。")
    if not config.source.exists():
        raise SystemExit(f"来源文件夹不存在: {config.source}")
    if not config.source.is_dir():
        raise SystemExit(f"来源路径不是文件夹: {config.source}")
    if config.source == config.target:
        raise SystemExit("来源文件夹和目标文件夹不能是同一个目录。")
    if is_relative_to(config.target, config.source):
        raise SystemExit("目标文件夹不能放在来源文件夹内部，否则会造成循环同步。")
    if is_relative_to(config.source, config.target):
        raise SystemExit("来源文件夹不能放在目标文件夹内部，否则清理目标时有误删风险。")
    if config.interval_seconds < 0:
        raise SystemExit("触发延迟不能小于 0 秒。")
    if config.scheduled_tasks.zzc_merge_interval_minutes < 0:
        raise SystemExit("自造词合并间隔不能小于 0 分钟。")
    if config.scheduled_tasks.startup_delay_minutes < 0:
        raise SystemExit("开机合并等待时间不能小于 0 分钟。")
    if config.scheduled_tasks.auto_merge_zzc and not config.scheduled_tasks.zzc_target_dicts:
        raise SystemExit("请先选择自造词合并目标码表。")


def is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def is_empty_path(path: Path) -> bool:
    return str(path).strip() in {"", "."}


def relative_posix(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def matches_any(relative_path: str, patterns: Iterable[str]) -> bool:
    normalized = relative_path.strip("/")
    name = Path(normalized).name

    for pattern in patterns:
        pattern = pattern.strip().strip("/")
        if not pattern:
            continue

        if fnmatch.fnmatch(normalized, pattern):
            return True
        if fnmatch.fnmatch(name, pattern):
            return True
        if "/" not in pattern and normalized.startswith(f"{pattern}/"):
            return True
        if pattern.endswith("/**"):
            prefix = pattern[:-3].strip("/")
            if normalized == prefix or normalized.startswith(f"{prefix}/"):
                return True

    return False


def is_included(relative_path: str, patterns: Iterable[str]) -> bool:
    patterns = tuple(patterns)
    return not patterns or matches_any(relative_path, patterns)


def is_excluded(relative_path: str, patterns: Iterable[str]) -> bool:
    return matches_any(relative_path, patterns)


def should_sync(relative_path: str, config: SyncConfig) -> bool:
    return is_included(relative_path, config.include) and not is_excluded(
        relative_path, config.exclude
    )


def should_walk_dir(relative_path: str, config: SyncConfig) -> bool:
    if is_excluded(relative_path, config.exclude):
        return False
    if not config.include:
        return True

    if any("/" not in pattern.strip().strip("/") for pattern in config.include):
        return True

    rel = relative_path.strip("/")
    for pattern in config.include:
        pattern = pattern.strip().strip("/")
        if not pattern:
            continue
        if matches_any(rel, (pattern,)):
            return True
        if pattern.startswith(f"{rel}/"):
            return True
        if pattern.endswith("/**"):
            prefix = pattern[:-3].strip("/")
            if prefix == rel or prefix.startswith(f"{rel}/"):
                return True

    return False


def iter_source_files(config: SyncConfig) -> dict[str, Path]:
    files: dict[str, Path] = {}

    for root, dir_names, file_names in os.walk(config.source):
        root_path = Path(root)

        kept_dirs = []
        for dir_name in dir_names:
            rel = (root_path / dir_name).relative_to(config.source).as_posix()
            if should_walk_dir(rel, config):
                kept_dirs.append(dir_name)
        dir_names[:] = kept_dirs

        for file_name in file_names:
            source_file = root_path / file_name
            rel = relative_posix(source_file, config.source)
            if not should_sync(rel, config):
                continue
            files[rel] = source_file

    return files


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def files_differ(source_file: Path, target_file: Path) -> bool:
    if not target_file.exists() or not target_file.is_file():
        return True

    source_stat = source_file.stat()
    target_stat = target_file.stat()
    if source_stat.st_size != target_stat.st_size:
        return True

    if source_stat.st_mtime_ns == target_stat.st_mtime_ns:
        return False

    return file_digest(source_file) != file_digest(target_file)


def copy_file(source_file: Path, target_file: Path) -> None:
    target_file.parent.mkdir(parents=True, exist_ok=True)
    temp_file = target_file.with_name(f".{target_file.name}.tmp-sync")
    shutil.copy2(source_file, temp_file)
    temp_file.replace(target_file)


def delete_extra_targets(config: SyncConfig, desired_files: set[str]) -> int:
    deleted = 0
    if not config.target.exists():
        return deleted

    for root, dir_names, file_names in os.walk(config.target, topdown=False):
        root_path = Path(root)

        for file_name in file_names:
            target_file = root_path / file_name
            rel = relative_posix(target_file, config.target)
            if rel in desired_files:
                continue
            if is_excluded(rel, config.target_protect):
                continue
            target_file.unlink()
            deleted += 1

        for dir_name in dir_names:
            target_dir = root_path / dir_name
            rel = relative_posix(target_dir, config.target)
            if is_excluded(rel, config.target_protect):
                continue
            try:
                target_dir.rmdir()
            except OSError:
                pass

    return deleted


def sync_once(config: SyncConfig, dry_run: bool = False, logger=print) -> SyncStats:
    stats = SyncStats()
    source_files = iter_source_files(config)
    desired_files = set(source_files)

    for rel, source_file in source_files.items():
        if is_excluded(rel, config.target_protect):
            stats.skipped += 1
            continue
        target_file = config.target / rel
        try:
            if files_differ(source_file, target_file):
                if dry_run:
                    print(f"[dry-run] copy {rel}")
                else:
                    copy_file(source_file, target_file)
                stats.copied += 1
            else:
                stats.skipped += 1
        except OSError as exc:
            stats.errors += 1
            logger(f"[error] 同步失败 {rel}: {exc}")

    if config.delete_extra:
        try:
            if dry_run:
                extras = preview_extra_targets(config, desired_files)
                for rel in extras:
                    print(f"[dry-run] delete {rel}")
                stats.deleted += len(extras)
            else:
                stats.deleted += delete_extra_targets(config, desired_files)
        except OSError as exc:
            stats.errors += 1
            logger(f"[error] 清理目标文件夹失败: {exc}")

    return stats


def preview_extra_targets(config: SyncConfig, desired_files: set[str]) -> list[str]:
    extras: list[str] = []
    if not config.target.exists():
        return extras

    for root, _, file_names in os.walk(config.target):
        root_path = Path(root)
        for file_name in file_names:
            target_file = root_path / file_name
            rel = relative_posix(target_file, config.target)
            if (
                rel not in desired_files
                and not is_excluded(rel, config.target_protect)
            ):
                extras.append(rel)

    return sorted(extras)


def print_stats(prefix: str, stats: SyncStats) -> None:
    print(
        f"{prefix}: copied={stats.copied} deleted={stats.deleted} "
        f"skipped={stats.skipped} errors={stats.errors}"
    )


def watch(config: SyncConfig) -> None:
    print(f"来源文件夹: {config.source}")
    print(f"目标文件夹: {config.target}")
    print(f"只同步规则: {', '.join(config.include) if config.include else '全部'}")
    print(f"来源排除规则: {', '.join(config.exclude) if config.exclude else '无'}")
    print(f"目标保留规则: {', '.join(config.target_protect) if config.target_protect else '无'}")
    print(f"触发延迟: {config.interval_seconds:g} 秒")
    print("开始监听来源变化，按 Ctrl+C 停止。")

    changed = threading.Event()

    def mark_changed() -> None:
        changed.set()

    observer = Observer()
    observer.schedule(SyncChangeHandler(mark_changed), str(config.source), recursive=True)
    observer.start()
    try:
        stats = sync_once(config)
        print_stats("首次同步完成", stats)
        while True:
            changed.wait()
            changed.clear()
            print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} 检测到变动")
            delay = max(0.0, config.interval_seconds)
            deadline = time.monotonic() + delay
            while delay and time.monotonic() < deadline:
                changed.wait(min(0.5, deadline - time.monotonic()))
                if changed.is_set():
                    changed.clear()
                    deadline = time.monotonic() + delay
            stats = sync_once(config)
            print_stats("同步完成", stats)
    finally:
        observer.stop()
        observer.join(timeout=2)

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="把来源文件夹按规则单向镜像同步到目标文件夹。"
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"txjx sync assistant {__version__}",
    )
    parser.add_argument(
        "-c",
        "--config",
        default="config.json",
        type=Path,
        help="配置文件路径，默认读取当前目录 config.json。",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="只同步一次，不持续监测。",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只预览会复制和删除的文件，不实际修改。",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_config(args.config)
    ensure_safe_config(config)
    config.target.mkdir(parents=True, exist_ok=True)

    if args.once or args.dry_run:
        stats = sync_once(config, dry_run=args.dry_run)
        print(
            f"完成: copied={stats.copied} deleted={stats.deleted} "
            f"skipped={stats.skipped} errors={stats.errors}"
        )
        return 1 if stats.errors else 0

    try:
        watch(config)
    except KeyboardInterrupt:
        print("\n已停止。")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
