#!/usr/bin/env python3
"""Desktop tray app for txjx sync assistant."""

from __future__ import annotations

import os
import plistlib
import subprocess
import sys
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
from tkinter import scrolledtext
from tkinter import filedialog, messagebox, ttk
import traceback
from dataclasses import replace
from pathlib import Path

import pystray
from PIL import Image, ImageDraw
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from sync_mirror import (
    ScheduledTasksConfig,
    SyncConfig,
    TaskSpec,
    append_auto_merge_protects,
    create_default_config,
    default_tasks_from_legacy,
    ensure_safe_config,
    ensure_safe_task,
    is_empty_path,
    load_config,
    save_config,
    sync_config_for_task,
    sync_once,
    sync_task_watch_paths,
    sync_tasks_once,
)
from task_scheduler import TaskScheduler, build_task_definition
from version import __version__
from zzc_merge import clear_ops, copy_managed_files, find_scheme, merge_root, reconcile_ops_between_roots

if sys.platform.startswith("win"):
    import winreg
else:
    winreg = None


APP_NAME = "天行键同步助手"
STARTUP_VALUE_NAME = "TxjxSyncAssistant"
MACOS_LAUNCH_AGENT_ID = "com.fusheng.txjxsync"
WINDOW_WIDTH = 900
WINDOW_HEIGHT = 949
WINDOW_MIN_HEIGHT = 640
BG_COLOR = "#eef3f7"
CARD_COLOR = "#ffffff"
TEXT_COLOR = "#1f2a37"
MUTED_COLOR = "#667085"
PRIMARY_COLOR = "#256d85"
PRIMARY_HOVER = "#1c5870"
BORDER_COLOR = "#d6dde5"
BUTTON_BG = "#eef3f8"
BUTTON_HOVER = "#dde7f2"
BUTTON_ACTIVE = "#cbd8e6"
UI_FONT = "Microsoft YaHei UI"
MONO_FONT = "Consolas"
LOG_MAX_BYTES = 1024 * 1024
LOG_MAX_LINES = 1000
LOG_CLEAN_INTERVAL_SECONDS = 24 * 60 * 60
ZZC_STABLE_SECONDS = 60
SINGLE_INSTANCE_MUTEX = "Local\\TxjxSyncAssistant"
MERGE_UNIT_KEYS = ("minutes", "hours", "days")

TRANSLATIONS = {
    "zh": {
        "language": "语言",
        "status": "状态",
        "settings": "同步设置",
        "source": "来源",
        "target": "目标",
        "choose": "选择",
        "clear": "清空",
        "include": "复制范围",
        "exclude": "排除文件",
        "keep": "保护文件",
        "clean": "删除文件",
        "delay": "触发延迟",
        "seconds": "秒",
        "options": "同步选项",
        "clean_extra": "清理目标多余文件",
        "startup": "开机启动并启用同步",
        "keep_hint": "保护文件会保留，并且不会覆盖",
        "include_rule_hint": "从来源复制哪些内容。\n留空表示同步全部。\n点击编辑会直接覆盖。",
        "exclude_rule_hint": "来源里哪些内容不复制到目标。\n优先级高于复制范围。\n点击编辑会直接覆盖。",
        "keep_rule_hint": "目标里哪些内容不覆盖、不删除。\n点击编辑会直接覆盖。",
        "clean_rule_hint": "目标里哪些位置允许删除多余文件。\n留空表示允许清理整个目标。\n点击编辑会直接覆盖。",
        "start": "启动同步",
        "pause": "暂停同步",
        "resume": "继续同步",
        "save": "保存配置",
        "sync_now": "立即同步",
        "merge_now": "立即合并",
        "sync_once": "立即同步一次",
        "show_window": "显示窗口",
        "deploy_now": "立即部署",
        "open_log": "打开日志",
        "exit": "退出",
        "author": "作者：浮生",
        "email": "邮箱：wzxmer@outlook.com",
        "select_file": "选择文件",
        "select_folder": "选择文件夹",
        "saved": "已保存配置",
        "scheduled_tasks": "定时任务",
        "auto_merge_zzc": "自动合并自造词",
        "auto_merge_zzc_hint": "开启后，普通同步会保护 *.zzc.dict.yaml 和 zzc_state/zzc_reset.tsv；关闭时完全按“保护文件”列表处理。",
        "zzc_target_dicts": "合并目标码表",
        "merge_interval": "合并间隔",
        "merge_unit_minutes": "分钟",
        "merge_unit_hours": "小时",
        "merge_unit_days": "天",
        "minutes": "分钟",
        "startup_auto_merge": "开机后自动执行合并",
        "startup_delay": "开机等待",
        "auto_deploy_after_merge": "合并后自动重新部署",
        "deploy_command": "部署命令",
        "deploy_command_hint": "留空时自动查找小狼毫部署程序；不勾选自动部署则无需填写。",
        "deploy_hint": "留空时自动查找小狼毫部署程序；不勾选则手动重新部署。",
        "target_dict_hint": "路径相对来源路径；只指定写入码表，不作为保护规则。",
        "tasks": "任务",
        "task_name": "任务名",
        "task_base": "任务信息",
        "task_enabled": "启用",
        "add_task": "新增",
        "duplicate_task": "复制",
        "delete_task": "删除",
    },
    "en": {
        "language": "Language",
        "status": "Status",
        "settings": "Sync Settings",
        "source": "Source",
        "target": "Target",
        "choose": "Choose",
        "clear": "Clear",
        "include": "Copy Scope",
        "exclude": "Excluded Files",
        "keep": "Protected Files",
        "clean": "Deleted Files",
        "delay": "Trigger Delay",
        "seconds": "sec",
        "options": "Options",
        "clean_extra": "Clean extra target files",
        "startup": "Start with system and sync",
        "keep_hint": "Kept content will not be deleted or overwritten",
        "include_rule_hint": "Controls which files/folders in the source folder are uploaded or synced.\nEmpty means sync all.\nEditing overwrites directly.",
        "exclude_rule_hint": "Controls which files/folders in the source folder are not uploaded or synced.\nTakes priority over sync content.\nEditing overwrites directly.",
        "keep_rule_hint": "Controls which files/folders in the target folder must be kept.\nThey are not deleted or overwritten.\nEditing overwrites directly.",
        "clean_rule_hint": "Controls where extra target files may be deleted.\nEmpty means the whole target can be cleaned.\nEditing overwrites directly.",
        "start": "Start Sync",
        "pause": "Pause Sync",
        "resume": "Resume Sync",
        "save": "Save",
        "sync_now": "Sync Now",
        "merge_now": "Merge Now",
        "sync_once": "Sync once now",
        "show_window": "Show window",
        "deploy_now": "Deploy Now",
        "open_log": "Open Log",
        "exit": "Exit",
        "author": "Author: Fusheng",
        "email": "Email: wzxmer@outlook.com",
        "select_file": "Select files",
        "select_folder": "Select folder",
        "saved": "Saved",
        "scheduled_tasks": "Scheduled Tasks",
        "auto_merge_zzc": "Auto merge zzc",
        "auto_merge_zzc_hint": "When enabled, normal sync protects *.zzc.dict.yaml and zzc_state/zzc_reset.tsv. When disabled, only Keep rules apply.",
        "zzc_target_dicts": "Target Dictionaries",
        "merge_interval": "Merge Interval",
        "merge_unit_minutes": "min",
        "merge_unit_hours": "hour",
        "merge_unit_days": "day",
        "minutes": "min",
        "startup_auto_merge": "Merge after startup",
        "startup_delay": "Startup Delay",
        "auto_deploy_after_merge": "Deploy after merge",
        "deploy_command": "Deploy Command",
        "deploy_command_hint": "Leave empty to auto-detect Weasel deployer. No need to fill if auto deploy is off.",
        "deploy_hint": "Leave empty to auto-detect Weasel deployer. Disable to deploy manually.",
        "target_dict_hint": "Paths relative to the source folder. Used only as merge destination, not as protection rules.",
        "tasks": "Tasks",
        "task_name": "Name",
        "task_base": "Task",
        "task_enabled": "Enabled",
        "add_task": "New",
        "duplicate_task": "Duplicate",
        "delete_task": "Delete",
    },
}

STATUS_TRANSLATIONS = {
    "未启动": "Not Started",
    "已暂停": "Paused",
    "运行中": "Running",
    "启动中": "Starting",
    "监听中": "Listening",
    "检测到变动": "Change Detected",
    "正在同步": "Syncing",
    "同步完成": "Sync Complete",
    "正在合并": "Merging",
    "合并成功": "Merge Succeeded",
    "合并失败": "Merge Failed",
    "监听或同步失败": "Sync Failed",
    "已保存配置": "Saved",
}


class SourceChangeHandler(FileSystemEventHandler):
    def __init__(self, callback, immediate: bool = False) -> None:
        super().__init__()
        self.callback = callback
        self.immediate = immediate

    def on_any_event(self, event: FileSystemEvent) -> None:
        if event.is_directory and event.event_type == "opened":
            return
        self.callback(self.immediate)


class RoundedButton(tk.Canvas):
    def __init__(
        self,
        parent: tk.Misc,
        text: str,
        command,
        variant: str = "secondary",
        min_width: int = 72,
    ) -> None:
        self.text = text
        self.command = command
        self.variant = variant
        self.font = tkfont.Font(family=UI_FONT, size=10, weight="bold")
        self.apply_variant(variant)
        self.shadow_fill = "#d8e0eb"
        width = max(min_width, self.font.measure(text) + 28)
        super().__init__(
            parent,
            width=width,
            height=38,
            bg=parent.cget("bg") if hasattr(parent, "cget") else BG_COLOR,
            highlightthickness=0,
            bd=0,
            cursor="hand2",
        )
        self._fill = self.normal_fill
        self._pressed = False
        self._draw()
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)

    def configure(self, cnf=None, **kwargs):  # type: ignore[override]
        cnf = cnf or {}
        if isinstance(cnf, dict):
            kwargs.update(cnf)
        if "text" in kwargs:
            self.text = kwargs.pop("text")
            width = max(72, self.font.measure(self.text) + 28)
            self.config(width=width)
            self._draw()
        if "variant" in kwargs:
            self.variant = kwargs.pop("variant")
            self.apply_variant(self.variant)
            self._fill = self.normal_fill
            self._draw()
        if kwargs:
            return super().configure(**kwargs)
        return None

    config = configure

    def apply_variant(self, variant: str) -> None:
        colors = {
            "primary": ("#2563eb", "#1d4ed8", "#1746a2", "#ffffff", "#2563eb"),
            "success": ("#16a34a", "#15803d", "#166534", "#ffffff", "#16a34a"),
            "warning": ("#f59e0b", "#d97706", "#b45309", "#ffffff", "#f59e0b"),
            "info": ("#0891b2", "#0e7490", "#155e75", "#ffffff", "#0891b2"),
            "danger": ("#dc2626", "#b91c1c", "#991b1b", "#ffffff", "#dc2626"),
            "secondary": ("#f8fbff", "#edf4ff", "#dfeaff", TEXT_COLOR, "#cfd8e6"),
        }
        (
            self.normal_fill,
            self.hover_fill,
            self.active_fill,
            self.text_fill,
            self.border_fill,
        ) = colors.get(variant, colors["secondary"])

    def _draw(self) -> None:
        self.delete("all")
        self._round_rect(3, 5, int(self["width"]) - 1, 36, 9, fill=self.shadow_fill, outline="")
        self._round_rect(
            1,
            1,
            int(self["width"]) - 3,
            33,
            9,
            fill=self._fill,
            outline=self.border_fill,
        )
        self.create_text(
            int(self["width"]) // 2 - 1,
            17,
            text=self.text,
            fill=self.text_fill,
            font=self.font,
        )

    def _round_rect(self, x1, y1, x2, y2, radius, **kwargs) -> None:
        points = [
            x1 + radius, y1,
            x2 - radius, y1,
            x2, y1,
            x2, y1 + radius,
            x2, y2 - radius,
            x2, y2,
            x2 - radius, y2,
            x1 + radius, y2,
            x1, y2,
            x1, y2 - radius,
            x1, y1 + radius,
            x1, y1,
        ]
        self.create_polygon(points, smooth=True, splinesteps=16, **kwargs)

    def _on_enter(self, _event) -> None:
        self._fill = self.hover_fill
        self._draw()

    def _on_leave(self, _event) -> None:
        self._pressed = False
        self._fill = self.normal_fill
        self._draw()

    def _on_press(self, _event) -> None:
        self._pressed = True
        self._fill = self.active_fill
        self._draw()

    def _on_release(self, event) -> None:
        was_pressed = self._pressed
        self._pressed = False
        self._fill = self.hover_fill
        self._draw()
        if was_pressed and 0 <= event.x <= int(self["width"]) and 0 <= event.y <= int(self["height"]):
            self.command()


class StatusPill(tk.Canvas):
    def __init__(
        self,
        parent: tk.Misc,
        text: str,
        min_width: int = 78,
        height: int = 34,
        radius: int = 10,
        font_size: int = 10,
    ) -> None:
        self.text = text
        self.min_width = min_width
        self.pill_height = height
        self.radius = radius
        self.font = tkfont.Font(family=UI_FONT, size=font_size, weight="bold")
        self.bg_fill = "#fee2e2"
        self.text_fill = "#b91c1c"
        width = max(self.min_width, self.font.measure(text) + 24)
        super().__init__(
            parent,
            width=width,
            height=self.pill_height,
            bg=parent.cget("bg") if hasattr(parent, "cget") else BG_COLOR,
            highlightthickness=0,
            bd=0,
        )
        self._draw()

    def configure(self, cnf=None, **kwargs):  # type: ignore[override]
        cnf = cnf or {}
        if isinstance(cnf, dict):
            kwargs.update(cnf)
        if "text" in kwargs:
            self.text = kwargs.pop("text")
            width = max(self.min_width, self.font.measure(self.text) + 24)
            self.config(width=width)
        if "bg_fill" in kwargs:
            self.bg_fill = kwargs.pop("bg_fill")
        if "text_fill" in kwargs:
            self.text_fill = kwargs.pop("text_fill")
        if "bg" in kwargs:
            super().configure(bg=kwargs.pop("bg"))
        if kwargs:
            super().configure(**kwargs)
        self._draw()
        return None

    config = configure

    def _draw(self) -> None:
        self.delete("all")
        width = int(self["width"])
        pill_bottom = self.pill_height - 4
        self._round_rect(0, 0, width, pill_bottom, self.radius, fill=self.bg_fill, outline="")
        self.create_text(
            width // 2,
            pill_bottom // 2,
            text=self.text,
            fill=self.text_fill,
            font=self.font,
        )

    def _round_rect(self, x1, y1, x2, y2, radius, **kwargs) -> None:
        points = [
            x1 + radius, y1,
            x2 - radius, y1,
            x2, y1,
            x2, y1 + radius,
            x2, y2 - radius,
            x2, y2,
            x2 - radius, y2,
            x1 + radius, y2,
            x1, y2,
            x1, y2 - radius,
            x1, y1 + radius,
            x1, y1,
        ]
        self.create_polygon(points, smooth=True, splinesteps=16, **kwargs)


class RoundedPanel(tk.Canvas):
    def __init__(
        self,
        parent: tk.Misc,
        radius: int = 14,
        padx: int = 18,
        pady: int = 16,
    ) -> None:
        super().__init__(
            parent,
            bg=parent.cget("bg") if hasattr(parent, "cget") else BG_COLOR,
            highlightthickness=0,
            bd=0,
            height=100,
        )
        self.radius = radius
        self.padx = padx
        self.pady = pady
        self.content = tk.Frame(self, bg=CARD_COLOR)
        self.content_id = self.create_window(
            self.padx,
            self.pady,
            anchor="nw",
            window=self.content,
        )
        self.bind("<Configure>", self._on_configure)
        self.content.bind("<Configure>", self._sync_height)

    def _on_configure(self, _event=None) -> None:
        width = max(1, self.winfo_width())
        content_width = max(1, width - self.padx * 2)
        self.itemconfigure(self.content_id, width=content_width)
        self._draw(width, max(1, int(self["height"])))

    def _sync_height(self, _event=None) -> None:
        needed = self.content.winfo_reqheight() + self.pady * 2
        if needed > 0 and int(float(self["height"])) != needed:
            self.configure(height=needed)
        self._on_configure()

    def _draw(self, width: int, height: int) -> None:
        self.delete("panel")
        self._round_rect(
            4,
            5,
            width - 2,
            height - 1,
            self.radius,
            fill="#dbe3ee",
            outline="",
            tags="panel",
        )
        self._round_rect(
            1,
            1,
            width - 6,
            height - 5,
            self.radius,
            fill=CARD_COLOR,
            outline=BORDER_COLOR,
            tags="panel",
        )
        self.tag_lower("panel", self.content_id)

    def _round_rect(self, x1, y1, x2, y2, radius, **kwargs) -> None:
        points = [
            x1 + radius, y1,
            x2 - radius, y1,
            x2, y1,
            x2, y1 + radius,
            x2, y2 - radius,
            x2, y2,
            x2 - radius, y2,
            x1 + radius, y2,
            x1, y2,
            x1, y2 - radius,
            x1, y1 + radius,
            x1, y1,
        ]
        self.create_polygon(points, smooth=True, splinesteps=16, **kwargs)


def app_dir() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    if sys.platform.startswith("linux"):
        return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "txjx-sync-assistant"
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


BASE_DIR = app_dir()
CONFIG_PATH = BASE_DIR / "config.json"
LOG_PATH = BASE_DIR / "sync.log"


class SingleInstanceLock:
    def __init__(self) -> None:
        self.handle = None
        self.lock_file = None
        self.file_locking = False

    def acquire(self) -> bool:
        if sys.platform.startswith("win"):
            return self.acquire_windows_mutex()
        return self.acquire_lock_file()

    def acquire_windows_mutex(self) -> bool:
        try:
            import ctypes
            from ctypes import wintypes
        except Exception:
            return self.acquire_lock_file()

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        create_mutex = kernel32.CreateMutexW
        create_mutex.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
        create_mutex.restype = wintypes.HANDLE

        self.handle = create_mutex(None, True, SINGLE_INSTANCE_MUTEX)
        if not self.handle:
            return self.acquire_lock_file()
        if ctypes.get_last_error() == 183:
            kernel32.CloseHandle(self.handle)
            self.handle = None
            return False
        return True

    def acquire_lock_file(self) -> bool:
        try:
            BASE_DIR.mkdir(parents=True, exist_ok=True)
            lock_path = BASE_DIR / "app.lock"
            flags = os.O_CREAT | os.O_RDWR
            if not sys.platform.startswith("win"):
                flags |= os.O_EXCL
            fd = os.open(lock_path, flags)
            self.lock_file = fd
            if sys.platform.startswith("win"):
                import msvcrt

                os.lseek(fd, 0, os.SEEK_SET)
                try:
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                except OSError:
                    os.close(fd)
                    self.lock_file = None
                    return False
                self.file_locking = True
                os.ftruncate(fd, 0)
            os.write(fd, str(os.getpid()).encode("ascii"))
            return True
        except FileExistsError:
            return False
        except OSError:
            return False

    def release(self) -> None:
        if sys.platform.startswith("win") and self.handle:
            try:
                import ctypes

                ctypes.WinDLL("kernel32", use_last_error=True).CloseHandle(self.handle)
            except Exception:
                pass
            self.handle = None
            return
        if self.lock_file is not None:
            try:
                if self.file_locking and sys.platform.startswith("win"):
                    import msvcrt

                    os.lseek(self.lock_file, 0, os.SEEK_SET)
                    msvcrt.locking(self.lock_file, msvcrt.LK_UNLCK, 1)
                os.close(self.lock_file)
                (BASE_DIR / "app.lock").unlink(missing_ok=True)
            except OSError:
                pass
            self.lock_file = None
            self.file_locking = False


def enable_dpi_awareness() -> None:
    if not sys.platform.startswith("win"):
        return
    try:
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


class MirrorTrayApp:
    def __init__(self) -> None:
        self.stop_event = threading.Event()
        self.wake_event = threading.Event()
        self.change_event = threading.Event()
        self.immediate_sync_event = threading.Event()
        self.started = False
        self.paused = False
        self.initial_sync_pending = False
        self.status = "未启动"
        self.base_status = "未启动"
        self.flash_until = 0.0
        self.last_log_cleanup = 0.0
        self.lock = threading.Lock()
        self.operation_lock = threading.Lock()
        self.root: tk.Tk | None = None
        self.language = "en" if os.environ.get("FOLDER_SYNC_LANG") == "en" else "zh"
        self.language_var: tk.StringVar | None = None
        self.i18n_widgets: list[tuple[object, str]] = []
        self.status_var: tk.StringVar | None = None
        self.status_label: StatusPill | None = None
        self.source_var: tk.StringVar | None = None
        self.target_var: tk.StringVar | None = None
        self.source_entry: tk.Entry | None = None
        self.target_entry: tk.Entry | None = None
        self.interval_var: tk.StringVar | None = None
        self.zzc_merge_interval_var: tk.StringVar | None = None
        self.zzc_merge_unit_var: tk.StringVar | None = None
        self.zzc_merge_unit_select: ttk.Combobox | None = None
        self.startup_delay_var: tk.StringVar | None = None
        self.deploy_command_var: tk.StringVar | None = None
        self.task_name_var: tk.StringVar | None = None
        self.task_enabled_var: tk.BooleanVar | None = None
        self.deploy_command_entry: tk.Entry | None = None
        self.entry_placeholder_keys: dict[tk.Entry, str] = {}
        self.entry_placeholder_active: set[tk.Entry] = set()
        self.delete_extra_var: tk.BooleanVar | None = None
        self.startup_var: tk.BooleanVar | None = None
        self.auto_merge_zzc_var: tk.BooleanVar | None = None
        self.startup_auto_merge_var: tk.BooleanVar | None = None
        self.auto_deploy_after_merge_var: tk.BooleanVar | None = None
        self.include_text: tk.Text | None = None
        self.exclude_text: tk.Text | None = None
        self.target_protect_text: tk.Text | None = None
        self.target_clean_text: tk.Text | None = None
        self.zzc_target_dicts_text: tk.Text | None = None
        self.task_listbox: tk.Listbox | None = None
        self.tab_bar: tk.Frame | None = None
        self.sync_tab_button: tk.Label | None = None
        self.rules_tab_button: tk.Label | None = None
        self.merge_tab_button: tk.Label | None = None
        self.sync_tab: tk.Frame | None = None
        self.rules_tab: tk.Frame | None = None
        self.merge_tab: tk.Frame | None = None
        self.active_tab_name = "rules"
        self.rule_tab_buttons: dict[str, tk.Label] = {}
        self.rule_tab_frames: dict[str, tk.Frame] = {}
        self.rule_group_frames: dict[str, tk.Frame] = {}
        self.rule_group_active: dict[str, str] = {}
        self.active_rule_tab = "include"
        self.rule_placeholder_keys: dict[tk.Text, str] = {}
        self.rule_placeholder_active: set[tk.Text] = set()
        self.loading_form = False
        self.current_config: SyncConfig | None = None
        self.selected_task_id: str | None = None
        self.pause_button: RoundedButton | None = None
        self.observer: Observer | None = None
        self.observed_sources: tuple[Path, ...] = ()
        self.last_zzc_merge_at: dict[str, float] = {}
        self.startup_sync_started_at = 0.0
        self.startup_merge_done: set[str] = set()
        self.deploy_in_progress = False
        self.worker = threading.Thread(target=self.worker_loop, daemon=True)
        self.task_worker = threading.Thread(target=self.scheduled_task_loop, daemon=True)
        self.icon = pystray.Icon(
            APP_NAME,
            self.make_icon(),
            APP_NAME,
            self.build_menu(),
        )

    def build_menu(self) -> pystray.Menu:
        return pystray.Menu(
            pystray.MenuItem(lambda _: f"{self.t('status')}: {self.display_status(self.status)}", None, enabled=False),
            pystray.MenuItem(
                lambda _: self.sync_control_text(),
                self.toggle_sync,
            ),
            pystray.MenuItem(lambda _: self.t("sync_once"), self.sync_now),
            pystray.MenuItem(lambda _: self.t("merge_now"), self.merge_now),
            pystray.MenuItem(lambda _: self.t("show_window"), self.show_window, default=True),
            pystray.MenuItem(lambda _: self.t("deploy_now"), self.deploy_now),
            pystray.MenuItem(lambda _: self.t("exit"), self.quit),
        )

    def make_icon(self) -> Image.Image:
        image = Image.new("RGBA", (64, 64), (20, 24, 28, 255))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((10, 14, 54, 50), radius=10, fill=(55, 130, 220, 255))
        draw.polygon([(24, 25), (40, 32), (24, 39)], fill=(255, 255, 255, 255))
        draw.line((18, 32, 28, 32), fill=(255, 255, 255, 255), width=5)
        return image

    def log(self, message: str) -> None:
        self.cleanup_log_if_needed()
        line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}"
        with LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    def cleanup_log_if_needed(self, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self.last_log_cleanup < LOG_CLEAN_INTERVAL_SECONDS:
            return
        self.last_log_cleanup = now
        cleanup_log_file(LOG_PATH)

    def set_status(self, status: str, temporary: bool = False) -> None:
        with self.lock:
            now = time.monotonic()
            if not temporary:
                self.base_status = status
                if now < self.flash_until:
                    self.icon.update_menu()
                    return
            self.status = status
            if temporary:
                self.flash_until = now + 2.0
        if self.root and self.status_var:
            self.root.after(0, self.status_var.set, self.display_status(status))
            if self.status_label:
                self.root.after(0, self.status_label.configure, {"text": self.display_status(status)})
            self.root.after(0, self.update_status_color, status)
        self.icon.update_menu()

    def flash_status(self, message: str, timeout_ms: int = 2000) -> None:
        self.set_status(message, temporary=True)
        if self.root:
            self.root.after(
                timeout_ms,
                lambda: self.set_status(self.base_status)
                if self.status == message
                else None,
            )

    def status_colors(self, status: str) -> tuple[str, str]:
        if "未启动" in status or "失败" in status or "错误" in status:
            return "#fee2e2", "#b91c1c"
        if "暂停" in status:
            return "#fef3c7", "#92400e"
        return "#dcfce7", "#166534"

    def update_status_color(self, status: str | None = None) -> None:
        if not self.status_label:
            return
        bg, fg = self.status_colors(status or self.status)
        self.status_label.configure(bg_fill=bg, text_fill=fg)

    def sync_control_text(self) -> str:
        if not self.started:
            return self.t("start")
        return self.t("resume") if self.paused else self.t("pause")

    def t(self, key: str) -> str:
        return TRANSLATIONS.get(self.language, TRANSLATIONS["zh"]).get(key, key)

    def merge_unit_label(self, key: str) -> str:
        labels = {
            "minutes": self.t("merge_unit_minutes"),
            "hours": self.t("merge_unit_hours"),
            "days": self.t("merge_unit_days"),
        }
        return labels.get(key, labels["minutes"])

    def merge_unit_key(self, label: str) -> str:
        value = (label or "").strip()
        if value in MERGE_UNIT_KEYS:
            return value
        for key in MERGE_UNIT_KEYS:
            if value in {TRANSLATIONS["zh"].get(f"merge_unit_{key}"), TRANSLATIONS["en"].get(f"merge_unit_{key}")}:
                return key
        return "minutes"

    def refresh_merge_unit_options(self) -> None:
        if self.zzc_merge_unit_select is None or self.zzc_merge_unit_var is None:
            return
        unit = self.merge_unit_key(self.zzc_merge_unit_var.get())
        self.zzc_merge_unit_select.configure(values=tuple(self.merge_unit_label(item) for item in MERGE_UNIT_KEYS))
        self.zzc_merge_unit_var.set(self.merge_unit_label(unit))

    def display_status(self, status: str) -> str:
        if self.language == "en":
            return STATUS_TRANSLATIONS.get(status, status)
        return status

    def register_i18n(self, widget: object, key: str) -> None:
        self.i18n_widgets.append((widget, key))

    def set_language(self, _event=None) -> None:
        if not self.language_var:
            return
        self.language = "en" if self.language_var.get() == "English" else "zh"
        self.refresh_language()

    def refresh_language(self) -> None:
        for widget, key in self.i18n_widgets:
            try:
                widget.configure(text=self.t(key))
            except tk.TclError:
                pass
        for box in list(self.rule_placeholder_active):
            box.delete("1.0", "end")
            box.insert("1.0", self.t(self.rule_placeholder_keys[box]))
            box.tag_add("placeholder", "1.0", "end")
        for entry in list(self.entry_placeholder_active):
            entry.delete(0, "end")
            entry.insert(0, self.t(self.entry_placeholder_keys[entry]))
        if self.status_var and self.status_label:
            shown = self.display_status(self.status)
            self.status_var.set(shown)
            self.status_label.configure(text=shown)
        self.refresh_merge_unit_options()
        self.refresh_task_list(self.selected_task_id)
        self.select_rule_tab(self.active_rule_tab)
        self.update_sync_button()
        self.icon.update_menu()

    def update_sync_button(self) -> None:
        if self.root and self.pause_button:
            variant = "success" if not self.started or self.paused else "warning"
            self.root.after(
                0,
                self.pause_button.configure,
                {"text": self.sync_control_text(), "variant": variant},
            )

    def run(self) -> None:
        ensure_config_exists()
        self.cleanup_log_if_needed(force=True)
        self.worker.start()
        self.task_worker.start()
        self.icon.run_detached()
        self.create_window()
        if "--background" in sys.argv and self.root:
            self.root.after(0, self.root.withdraw)
            self.root.after(200, self.start_sync_from_saved_config)
        self.root.mainloop()

    def create_window(self) -> None:
        self.root = tk.Tk()
        self.root.title(f"{APP_NAME} {__version__}")
        self.center_window(WINDOW_WIDTH, WINDOW_HEIGHT)
        self.root.minsize(WINDOW_WIDTH, WINDOW_MIN_HEIGHT)
        self.root.resizable(True, True)
        self.root.configure(bg=BG_COLOR)
        self.root.protocol("WM_DELETE_WINDOW", self.hide_window)
        self.root.bind_all("<Button-1>", self.clear_focus_on_non_input_click, add="+")
        self.configure_style()

        outer = tk.Frame(self.root, bg=BG_COLOR)
        outer.pack(fill="both", expand=True, padx=18, pady=16)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(1, weight=1)

        header = tk.Frame(outer, bg=BG_COLOR)
        header.grid(row=0, column=0, sticky="ew")
        status_box = tk.Frame(header, bg=BG_COLOR)
        status_box.pack(side="left", anchor="n")
        self.status_var = tk.StringVar(value=self.display_status(self.status))
        self.status_label = StatusPill(
            status_box,
            self.display_status(self.status),
            min_width=132,
            height=42,
            radius=13,
            font_size=16,
        )
        self.status_label.pack(anchor="w")
        self.update_status_color(self.status)
        header_tools = tk.Frame(header, bg=BG_COLOR)
        header_tools.pack(side="right", anchor="ne")
        language_box = tk.Frame(header_tools, bg=BG_COLOR)
        language_box.pack(anchor="e")
        language_label = tk.Label(
            language_box,
            text=self.t("language"),
            bg=BG_COLOR,
            fg=TEXT_COLOR,
            font=(UI_FONT, 10, "bold"),
        )
        language_label.pack(side="left", padx=(0, 8))
        self.register_i18n(language_label, "language")
        self.language_var = tk.StringVar(value="English" if self.language == "en" else "中文")
        language_select = ttk.Combobox(
            language_box,
            textvariable=self.language_var,
            values=("中文", "English"),
            state="readonly",
            width=10,
            font=(UI_FONT, 10),
        )
        language_select.pack(side="left")
        language_select.bind("<<ComboboxSelected>>", self.set_language)

        content_host = tk.Frame(outer, bg=BG_COLOR)
        content_host.grid(row=1, column=0, sticky="nsew")

        button_panel = tk.Frame(
            outer,
            bg=CARD_COLOR,
            highlightthickness=1,
            highlightbackground=BORDER_COLOR,
            padx=12,
            pady=10,
        )
        button_panel.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        button_row = tk.Frame(button_panel, bg=CARD_COLOR)
        button_row.pack(fill="x")
        self.pause_button = self.make_button(
            button_row, "start", self.toggle_sync, variant="success"
        )
        self.pause_button.pack(side="left")
        self.make_button(
            button_row, "save", self.save_form_config, variant="primary"
        ).pack(side="left", padx=(8, 0))
        self.make_button(button_row, "sync_now", self.sync_now, variant="info").pack(
            side="left", padx=(8, 0)
        )
        self.make_button(button_row, "merge_now", self.merge_now, variant="success").pack(
            side="left", padx=(8, 0)
        )
        self.make_button(button_row, "deploy_now", self.deploy_now).pack(
            side="left", padx=(8, 0)
        )
        self.make_button(button_row, "exit", self.quit, variant="danger").pack(
            side="left", padx=(8, 0)
        )

        author_box = tk.Frame(button_row, bg=CARD_COLOR)
        author_box.pack(side="right", padx=(8, 0))
        author_label = tk.Label(
            author_box,
            text=self.t("author"),
            bg=CARD_COLOR,
            fg="#475467",
            font=(UI_FONT, 8),
        )
        author_label.pack(anchor="e")
        self.register_i18n(author_label, "author")
        email_label = tk.Label(
            author_box,
            text=self.t("email"),
            bg=CARD_COLOR,
            fg="#475467",
            font=(UI_FONT, 8),
        )
        email_label.pack(anchor="e")
        self.register_i18n(email_label, "email")
        self.create_config_form(content_host)
        self.load_config_into_form()

    def center_window(self, width: int, height: int) -> None:
        if self.root is None:
            return
        self.root.update_idletasks()
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x = max(0, (screen_width - width) // 2)
        y = max(0, (screen_height - height) // 2)
        self.root.geometry(f"{width}x{height}+{x}+{y}")

    def fit_window_height(self) -> None:
        if self.root is None:
            return
        self.root.update_idletasks()
        width = max(WINDOW_WIDTH, self.root.winfo_width())
        screen_height = self.root.winfo_screenheight()
        height = min(WINDOW_HEIGHT, max(WINDOW_MIN_HEIGHT, screen_height - 40))
        x = self.root.winfo_x()
        y = max(0, (screen_height - height) // 2)
        self.root.geometry(f"{width}x{height}+{x}+{y}")

    def configure_style(self) -> None:
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("App.TFrame", background="#f4f6fb")
        style.configure("TFrame", background="#ffffff")
        style.configure("Card.TLabelframe", background="#ffffff", bordercolor="#d8dee9")
        style.configure(
            "Card.TLabelframe.Label",
            background="#f4f6fb",
            foreground="#263445",
            font=(UI_FONT, 10, "bold"),
        )
        style.configure(
            "Title.TLabel",
            background="#f4f6fb",
            foreground="#162033",
            font=(UI_FONT, 16, "bold"),
        )
        style.configure(
            "Status.TLabel",
            background="#e8f1ff",
            foreground="#1d5fbf",
            padding=(10, 4),
            font=(UI_FONT, 10),
        )
        style.configure("Hint.TLabel", background="#f4f6fb", foreground="#647084")
        style.configure("TLabel", background="#ffffff", foreground="#263445")
        style.configure("TButton", padding=(9, 4), font=(UI_FONT, 10))
        style.configure("TEntry", padding=(4, 3))
        style.configure("TCheckbutton", background="#ffffff", foreground="#263445")
        style.configure("TNotebook", background=BG_COLOR, borderwidth=0, padding=0)
        style.configure(
            "TNotebook.Tab",
            padding=(18, 8),
            font=(UI_FONT, 10, "bold"),
            background="#e4ebf1",
            foreground=TEXT_COLOR,
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", CARD_COLOR), ("active", "#f3f7fa")],
            foreground=[("selected", PRIMARY_COLOR), ("active", TEXT_COLOR)],
        )

    def make_button(
        self,
        parent: tk.Misc,
        text_key: str,
        command,
        variant: str = "secondary",
        min_width: int = 72,
    ) -> RoundedButton:
        button = RoundedButton(
            parent, self.t(text_key), command, variant=variant, min_width=min_width
        )
        self.register_i18n(button, text_key)
        return button

    def create_config_form(self, parent: tk.Misc) -> None:
        self.source_var = tk.StringVar()
        self.target_var = tk.StringVar()
        self.interval_var = tk.StringVar(value="0")
        self.zzc_merge_interval_var = tk.StringVar(value="30")
        self.zzc_merge_unit_var = tk.StringVar(value="分钟")
        self.startup_delay_var = tk.StringVar(value="10")
        self.deploy_command_var = tk.StringVar()
        self.task_name_var = tk.StringVar(value="同步任务")
        self.delete_extra_var = tk.BooleanVar(value=True)
        self.task_enabled_var = tk.BooleanVar(value=True)
        self.startup_var = tk.BooleanVar(value=is_startup_enabled())
        self.auto_merge_zzc_var = tk.BooleanVar(value=False)
        self.startup_auto_merge_var = tk.BooleanVar(value=False)
        self.auto_deploy_after_merge_var = tk.BooleanVar(value=False)

        tasks_host = tk.Frame(parent, bg=BG_COLOR)
        tasks_host.pack(fill="both", expand=True, pady=(14, 0))
        tasks_host.columnconfigure(1, weight=1)
        tasks_host.rowconfigure(1, weight=1)

        task_panel = tk.Frame(tasks_host, bg=CARD_COLOR, highlightthickness=1, highlightbackground=BORDER_COLOR, padx=12, pady=12)
        task_panel.grid(row=0, column=0, sticky="nw", padx=(0, 10))
        self.section_title(task_panel, "tasks").pack(anchor="w", pady=(0, 8))
        task_list_frame = tk.Frame(task_panel, bg=CARD_COLOR)
        task_list_frame.pack(fill="x")
        self.task_listbox = tk.Listbox(
            task_list_frame,
            width=28,
            height=6,
            relief="flat",
            bd=0,
            bg="#fbfcff",
            fg=TEXT_COLOR,
            selectbackground=PRIMARY_COLOR,
            selectforeground="#ffffff",
            activestyle="none",
            font=(UI_FONT, 10),
            highlightthickness=1,
            highlightbackground=BORDER_COLOR,
            highlightcolor=PRIMARY_COLOR,
        )
        task_scrollbar = tk.Scrollbar(task_list_frame, orient="vertical", command=self.task_listbox.yview)
        self.task_listbox.configure(yscrollcommand=task_scrollbar.set)
        self.task_listbox.pack(side="left", fill="both", expand=True)
        task_scrollbar.pack(side="right", fill="y")
        self.task_listbox.bind("<<ListboxSelect>>", self.on_task_selected)
        task_buttons = tk.Frame(task_panel, bg=CARD_COLOR)
        task_buttons.pack(fill="x", pady=(10, 0))
        self.make_button(task_buttons, "add_task", self.add_task, min_width=56).pack(side="left")
        self.make_button(task_buttons, "duplicate_task", self.duplicate_task, min_width=56).pack(side="left", padx=(6, 0))
        self.make_button(task_buttons, "delete_task", self.delete_task, variant="danger", min_width=56).pack(side="left", padx=(6, 0))

        base_panel = tk.Frame(tasks_host, bg=CARD_COLOR, highlightthickness=1, highlightbackground=BORDER_COLOR, padx=18, pady=12)
        base_panel.grid(row=0, column=1, sticky="nsew")
        base_panel.columnconfigure(1, weight=1)
        self.section_title(base_panel, "task_base").grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 8))
        self.make_label(base_panel, "task_name").grid(row=1, column=0, sticky="w", pady=5)
        task_name_entry = self.make_entry(base_panel, self.task_name_var)
        task_name_entry.grid(row=1, column=1, sticky="ew", padx=(12, 12), pady=5)
        task_name_entry.bind("<FocusOut>", self.commit_task_name, add="+")
        task_name_entry.bind("<Return>", self.commit_task_name, add="+")
        task_enabled_check = tk.Checkbutton(
            base_panel,
            text=self.t("task_enabled"),
            variable=self.task_enabled_var,
            bg=CARD_COLOR,
            fg=TEXT_COLOR,
            activebackground=CARD_COLOR,
            font=(UI_FONT, 10),
            command=self.on_task_fields_changed,
        )
        task_enabled_check.grid(row=1, column=2, sticky="w", pady=5)
        self.register_i18n(task_enabled_check, "task_enabled")

        self.make_label(base_panel, "source").grid(row=2, column=0, sticky="w", pady=5)
        self.source_entry = self.make_path_entry(base_panel, self.source_var)
        self.source_entry.grid(row=2, column=1, sticky="ew", padx=(12, 12), pady=5)
        self.make_button(base_panel, "choose", self.choose_source, min_width=60).grid(row=2, column=2, pady=5)

        self.make_label(base_panel, "target").grid(row=3, column=0, sticky="w", pady=5)
        self.target_entry = self.make_path_entry(base_panel, self.target_var)
        self.target_entry.grid(row=3, column=1, sticky="ew", padx=(12, 12), pady=5)
        self.make_button(base_panel, "choose", self.choose_target, min_width=60).grid(row=3, column=2, pady=5)

        settings_host = tk.Frame(tasks_host, bg=BG_COLOR)
        settings_host.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(10, 0))

        self.tab_bar = tk.Frame(settings_host, bg=BG_COLOR)
        self.tab_bar.pack(fill="x", pady=(0, 8))
        tab_body = tk.Frame(settings_host, bg=CARD_COLOR, highlightthickness=1, highlightbackground=BORDER_COLOR)
        tab_body.pack(fill="both", expand=True)

        sync_tab = self.create_tab(tab_body)
        rules_tab = self.create_tab(tab_body)
        merge_tab = self.create_tab(tab_body)
        self.sync_tab = sync_tab
        self.rules_tab = rules_tab
        self.merge_tab = merge_tab
        self.create_segmented_tabs(self.tab_bar)
        self.select_task_tab(self.active_tab_name)

        sync_tab.columnconfigure(0, minsize=86)
        sync_tab.columnconfigure(1, weight=1)
        sync_tab.columnconfigure(2, minsize=64)

        settings_label = self.section_title(sync_tab, "settings")
        settings_label.grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 16))

        self.make_label(sync_tab, "delay").grid(row=1, column=0, sticky="w", pady=(4, 6))
        self.interval_spinbox = tk.Spinbox(
            sync_tab,
            from_=0,
            to=86400,
            textvariable=self.interval_var,
            width=10,
            relief="flat",
            bd=0,
            bg="#fbfcff",
            fg=TEXT_COLOR,
            font=(UI_FONT, 10),
            highlightthickness=1,
            highlightbackground=BORDER_COLOR,
            highlightcolor=PRIMARY_COLOR,
        )
        self.interval_spinbox.grid(row=1, column=1, sticky="w", padx=(10, 0), pady=(4, 6))
        self.interval_spinbox.bind("<FocusOut>", self.save_form_config_silent)
        self.make_hint(sync_tab, "seconds").grid(row=1, column=1, sticky="w", padx=(82, 0), pady=(4, 6))

        self.make_label(sync_tab, "options").grid(row=2, column=0, sticky="w", pady=(14, 0))
        option_row = tk.Frame(sync_tab, bg=CARD_COLOR)
        option_row.grid(row=2, column=1, columnspan=2, sticky="w", padx=(10, 0), pady=(14, 0))
        clean_check = tk.Checkbutton(
            option_row,
            text=self.t("clean_extra"),
            variable=self.delete_extra_var,
            bg=CARD_COLOR,
            fg=TEXT_COLOR,
            activebackground=CARD_COLOR,
            font=(UI_FONT, 10),
            command=self.save_form_config_silent,
        )
        clean_check.pack(side="left")
        self.register_i18n(clean_check, "clean_extra")
        startup_check = tk.Checkbutton(
            option_row,
            text=self.t("startup"),
            variable=self.startup_var,
            bg=CARD_COLOR,
            fg=TEXT_COLOR,
            activebackground=CARD_COLOR,
            font=(UI_FONT, 10),
            command=self.save_form_config_silent,
        )
        startup_check.pack(side="left", padx=(22, 0))
        self.register_i18n(startup_check, "startup")
        self.make_hint(sync_tab, "keep_hint").grid(
            row=3,
            column=1,
            columnspan=2,
            sticky="w",
            padx=(10, 0),
            pady=(2, 0),
        )

        merge_tab.columnconfigure(0, minsize=104)
        merge_tab.columnconfigure(1, weight=1)
        merge_tab.columnconfigure(2, minsize=64)
        self.section_title(merge_tab, "scheduled_tasks").grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 14))

        auto_merge_check = tk.Checkbutton(
            merge_tab,
            text=self.t("auto_merge_zzc"),
            variable=self.auto_merge_zzc_var,
            bg=CARD_COLOR,
            fg=TEXT_COLOR,
            activebackground=CARD_COLOR,
            font=(UI_FONT, 10),
            command=self.on_auto_merge_toggled,
        )
        auto_merge_check.grid(row=1, column=0, sticky="w", pady=(0, 8))
        self.register_i18n(auto_merge_check, "auto_merge_zzc")
        auto_merge_hint = self.make_hint(merge_tab, "auto_merge_zzc_hint")
        auto_merge_hint.configure(wraplength=560, justify="left")
        auto_merge_hint.grid(
            row=1,
            column=1,
            columnspan=2,
            sticky="w",
            padx=(10, 0),
            pady=(0, 8),
        )

        self.make_label(merge_tab, "zzc_target_dicts").grid(row=2, column=0, sticky="nw", pady=4)
        target_box = tk.Frame(merge_tab, bg=CARD_COLOR)
        target_box.grid(row=2, column=1, sticky="ew", padx=(10, 10), pady=4)
        self.zzc_target_dicts_text = self.create_rule_text(target_box, height=3)
        self.pack_rule_text(target_box, self.zzc_target_dicts_text, pady=(0, 6))
        target_buttons = tk.Frame(target_box, bg=CARD_COLOR)
        target_buttons.pack(anchor="w")
        self.make_button(target_buttons, "choose", self.add_zzc_target_dicts, min_width=76).pack(side="left")
        self.make_button(target_buttons, "clear", self.clear_zzc_target_dicts, min_width=62).pack(side="left", padx=(6, 0))

        self.make_label(merge_tab, "merge_interval").grid(row=3, column=0, sticky="w", pady=(8, 3))
        interval_row = tk.Frame(merge_tab, bg=CARD_COLOR)
        interval_row.grid(row=3, column=1, sticky="w", padx=(10, 0), pady=(8, 3))
        self.zzc_merge_interval_spinbox = tk.Spinbox(
            interval_row,
            from_=0,
            to=999,
            textvariable=self.zzc_merge_interval_var,
            width=10,
            relief="flat",
            bd=0,
            bg="#fbfcff",
            fg=TEXT_COLOR,
            font=(UI_FONT, 10),
            highlightthickness=1,
            highlightbackground=BORDER_COLOR,
            highlightcolor=PRIMARY_COLOR,
        )
        self.zzc_merge_interval_spinbox.pack(side="left")
        self.zzc_merge_interval_spinbox.bind("<FocusOut>", self.save_form_config_silent)
        self.zzc_merge_unit_select = ttk.Combobox(
            interval_row,
            textvariable=self.zzc_merge_unit_var,
            values=tuple(self.merge_unit_label(item) for item in MERGE_UNIT_KEYS),
            state="readonly",
            width=6,
            font=(UI_FONT, 10),
        )
        self.zzc_merge_unit_select.pack(side="left", padx=(8, 0))
        self.zzc_merge_unit_select.bind("<<ComboboxSelected>>", self.on_merge_unit_selected)

        self.make_label(merge_tab, "startup_delay").grid(row=4, column=0, sticky="w", pady=(8, 3))
        startup_delay_row = tk.Frame(merge_tab, bg=CARD_COLOR)
        startup_delay_row.grid(row=4, column=1, sticky="w", padx=(10, 0), pady=(8, 3))
        self.startup_delay_spinbox = tk.Spinbox(
            startup_delay_row,
            from_=0,
            to=1440,
            textvariable=self.startup_delay_var,
            width=10,
            relief="flat",
            bd=0,
            bg="#fbfcff",
            fg=TEXT_COLOR,
            font=(UI_FONT, 10),
            highlightthickness=1,
            highlightbackground=BORDER_COLOR,
            highlightcolor=PRIMARY_COLOR,
        )
        self.startup_delay_spinbox.pack(side="left")
        self.startup_delay_spinbox.bind("<FocusOut>", self.save_form_config_silent)
        self.make_hint(startup_delay_row, "minutes").pack(side="left", padx=(8, 0))

        checkbox_row = tk.Frame(merge_tab, bg=CARD_COLOR)
        checkbox_row.grid(row=5, column=0, columnspan=3, sticky="w", pady=(8, 0))
        startup_merge_check = tk.Checkbutton(
            checkbox_row,
            text=self.t("startup_auto_merge"),
            variable=self.startup_auto_merge_var,
            bg=CARD_COLOR,
            fg=TEXT_COLOR,
            activebackground=CARD_COLOR,
            font=(UI_FONT, 10),
            command=self.save_form_config_silent,
        )
        startup_merge_check.pack(side="left")
        self.register_i18n(startup_merge_check, "startup_auto_merge")

        deploy_check = tk.Checkbutton(
            checkbox_row,
            text=self.t("auto_deploy_after_merge"),
            variable=self.auto_deploy_after_merge_var,
            bg=CARD_COLOR,
            fg=TEXT_COLOR,
            activebackground=CARD_COLOR,
            font=(UI_FONT, 10),
            command=self.save_form_config_silent,
        )
        deploy_check.pack(side="left", padx=(24, 0))
        self.register_i18n(deploy_check, "auto_deploy_after_merge")
        self.make_label(merge_tab, "deploy_command").grid(row=6, column=0, sticky="w", pady=(8, 3))
        self.deploy_command_entry = self.make_entry(
            merge_tab,
            self.deploy_command_var,
            placeholder_key="deploy_command_hint",
        )
        self.deploy_command_entry.grid(row=6, column=1, columnspan=2, sticky="ew", padx=(10, 0), pady=(8, 3))

        rule_body = tk.Frame(rules_tab, bg=CARD_COLOR)
        rule_body.pack(fill="both", expand=True)
        rule_body.columnconfigure(0, weight=1)
        rule_body.columnconfigure(1, weight=1)
        rule_body.rowconfigure(1, weight=1)
        source_rule_bar = tk.Frame(rule_body, bg=CARD_COLOR)
        source_rule_bar.grid(row=0, column=0, sticky="w", padx=(0, 8), pady=(0, 12))
        target_rule_bar = tk.Frame(rule_body, bg=CARD_COLOR)
        target_rule_bar.grid(row=0, column=1, sticky="w", padx=(8, 0), pady=(0, 12))
        source_rule_body = tk.Frame(rule_body, bg=CARD_COLOR)
        source_rule_body.grid(row=1, column=0, sticky="nsew", padx=(0, 8))
        target_rule_body = tk.Frame(rule_body, bg=CARD_COLOR)
        target_rule_body.grid(row=1, column=1, sticky="nsew", padx=(8, 0))
        self.rule_group_frames = {
            "source": source_rule_body,
            "target": target_rule_body,
        }
        self.rule_group_active = {
            "source": "include",
            "target": "keep",
        }
        self.rule_tab_frames = {
            "include": tk.Frame(source_rule_body, bg=CARD_COLOR),
            "exclude": tk.Frame(source_rule_body, bg=CARD_COLOR),
            "keep": tk.Frame(target_rule_body, bg=CARD_COLOR),
            "clean": tk.Frame(target_rule_body, bg=CARD_COLOR),
        }
        self.rule_tab_buttons = {
            "include": self.create_rule_tab_button(source_rule_bar, "include"),
            "exclude": self.create_rule_tab_button(source_rule_bar, "exclude"),
            "keep": self.create_rule_tab_button(target_rule_bar, "keep"),
            "clean": self.create_rule_tab_button(target_rule_bar, "clean"),
        }
        for index, key in enumerate(("include", "exclude")):
            self.rule_tab_buttons[key].pack(side="left", padx=(0 if index == 0 else 8, 0))
        for index, key in enumerate(("keep", "clean")):
            self.rule_tab_buttons[key].pack(side="left", padx=(0 if index == 0 else 8, 0))

        include_panel = self.rule_tab_frames["include"]
        self.section_title(include_panel, "include").pack(anchor="w", pady=(0, 8))
        self.include_text = self.create_rule_text(include_panel, height=8, placeholder_key="include_rule_hint")
        self.pack_rule_text(include_panel, self.include_text, pady=(0, 6))
        include_buttons = tk.Frame(include_panel, bg=CARD_COLOR)
        include_buttons.pack(anchor="w")
        self.make_button(include_buttons, "choose", self.add_include_items, min_width=76).pack(side="left")
        self.make_button(include_buttons, "clear", self.clear_include, min_width=62).pack(side="left", padx=(6, 0))

        exclude_panel = self.rule_tab_frames["exclude"]
        self.section_title(exclude_panel, "exclude").pack(anchor="w", pady=(0, 8))
        self.exclude_text = self.create_rule_text(exclude_panel, height=8, placeholder_key="exclude_rule_hint")
        self.pack_rule_text(exclude_panel, self.exclude_text, pady=(0, 6))
        exclude_buttons = tk.Frame(exclude_panel, bg=CARD_COLOR)
        exclude_buttons.pack(anchor="w")
        self.make_button(exclude_buttons, "choose", self.add_exclude_items, min_width=76).pack(side="left")
        self.make_button(exclude_buttons, "clear", self.clear_exclude, min_width=62).pack(side="left", padx=(6, 0))

        protect_panel = self.rule_tab_frames["keep"]
        self.section_title(protect_panel, "keep").pack(anchor="w", pady=(0, 8))
        self.target_protect_text = self.create_rule_text(protect_panel, height=8, placeholder_key="keep_rule_hint")
        self.pack_rule_text(protect_panel, self.target_protect_text, pady=(0, 6))
        protect_buttons = tk.Frame(protect_panel, bg=CARD_COLOR)
        protect_buttons.pack(anchor="w")
        self.make_button(protect_buttons, "choose", self.add_target_protected_items, min_width=76).pack(side="left")
        self.make_button(protect_buttons, "clear", self.clear_target_protect, min_width=62).pack(side="left", padx=(6, 0))

        clean_panel = self.rule_tab_frames["clean"]
        self.section_title(clean_panel, "clean").pack(anchor="w", pady=(0, 8))
        self.target_clean_text = self.create_rule_text(clean_panel, height=8, placeholder_key="clean_rule_hint")
        self.pack_rule_text(clean_panel, self.target_clean_text, pady=(0, 6))
        clean_buttons = tk.Frame(clean_panel, bg=CARD_COLOR)
        clean_buttons.pack(anchor="w")
        self.make_button(clean_buttons, "choose", self.add_target_clean_items, min_width=76).pack(side="left")
        self.make_button(clean_buttons, "clear", self.clear_target_clean, min_width=62).pack(side="left", padx=(6, 0))
        self.select_rule_tab("include")
        self.select_rule_tab("keep")

    def create_segmented_tabs(self, parent: tk.Misc) -> None:
        self.sync_tab_button = self.create_tab_button(parent, "同步设置", "sync")
        self.rules_tab_button = self.create_tab_button(parent, "同步规则", "rules")
        self.merge_tab_button = self.create_tab_button(parent, "合并设置", "merge")
        for index, button in enumerate((self.sync_tab_button, self.rules_tab_button, self.merge_tab_button)):
            if button is not None:
                button.pack(side="left", padx=(0 if index == 0 else 8, 0))

    def create_tab_button(self, parent: tk.Misc, label: str, tab_name: str) -> tk.Label:
        return self.create_choice_button(parent, label, lambda: self.select_task_tab(tab_name))

    def create_choice_button(self, parent: tk.Misc, label: str, command) -> tk.Label:
        button = tk.Label(
            parent,
            text=label,
            bg="#e5ecf2",
            fg=TEXT_COLOR,
            font=(UI_FONT, 10, "bold"),
            padx=18,
            pady=8,
            cursor="hand2",
            bd=0,
        )
        button.bind("<Button-1>", lambda _event: command())
        return button

    def create_rule_tab_button(self, parent: tk.Misc, key: str) -> tk.Label:
        return self.create_choice_button(parent, self.t(key), lambda: self.select_rule_tab(key))

    def select_rule_tab(self, key: str) -> None:
        if key not in self.rule_tab_frames:
            key = "include"
        group_name = "target" if key in {"keep", "clean"} else "source"
        self.active_rule_tab = key
        self.rule_group_active[group_name] = key
        group_parent = self.rule_group_frames.get(group_name)
        for name, frame in self.rule_tab_frames.items():
            if frame.master is group_parent:
                frame.pack_forget()
        frame = self.rule_tab_frames.get(key)
        if frame is not None:
            frame.pack(fill="both", expand=True)
        for name, button in self.rule_tab_buttons.items():
            active = self.rule_group_active.get("target" if name in {"keep", "clean"} else "source") == name
            button.configure(
                bg=PRIMARY_COLOR if active else "#e5ecf2",
                fg="#ffffff" if active else TEXT_COLOR,
                text=self.t(name),
            )

    def select_task_tab(self, tab_name: str) -> None:
        if tab_name not in {"sync", "rules", "merge"}:
            tab_name = "sync"
        self.active_tab_name = tab_name
        for frame in (self.sync_tab, self.rules_tab, self.merge_tab):
            if frame is not None:
                frame.pack_forget()
        frame = {
            "sync": self.sync_tab,
            "rules": self.rules_tab,
            "merge": self.merge_tab,
        }.get(tab_name)
        if frame is not None:
            frame.pack(fill="both", expand=True)
        for name, button in (
            ("sync", self.sync_tab_button),
            ("rules", self.rules_tab_button),
            ("merge", self.merge_tab_button),
        ):
            if button is None:
                continue
            active = name == tab_name
            button.configure(
                bg=PRIMARY_COLOR if active else "#e5ecf2",
                fg="#ffffff" if active else TEXT_COLOR,
            )

    def create_tab(self, parent: tk.Misc) -> tk.Frame:
        frame = tk.Frame(parent, bg=CARD_COLOR, padx=20, pady=18)
        return frame

    def refresh_task_list(self, select_id: str | None = None) -> None:
        if self.task_listbox is None or self.current_config is None:
            return
        tasks = list(self.current_config.tasks)
        self.task_listbox.delete(0, "end")
        selected_index = 0
        for index, task in enumerate(tasks):
            label = task.name or task.id
            self.task_listbox.insert("end", label)
            if select_id and task.id == select_id:
                selected_index = index
        if tasks:
            selected_index = max(0, min(selected_index, len(tasks) - 1))
            self.task_listbox.selection_set(selected_index)
            self.task_listbox.activate(selected_index)
            self.selected_task_id = tasks[selected_index].id

    def selected_task(self) -> TaskSpec | None:
        config = self.current_config
        if config is None:
            return None
        if self.selected_task_id:
            for task in config.tasks:
                if task.id == self.selected_task_id:
                    return task
        return config.tasks[0] if config.tasks else None

    def on_task_selected(self, _event: tk.Event | None = None) -> None:
        if self.loading_form or self.task_listbox is None or self.current_config is None:
            return
        selection = self.task_listbox.curselection()
        if not selection:
            return
        index = selection[0]
        if index >= len(self.current_config.tasks):
            return
        self.apply_task_to_form(self.current_config.tasks[index])

    def apply_task_to_form(self, task: TaskSpec) -> None:
        if self.current_config is None:
            return
        scheduled = task.scheduled_tasks or self.current_config.scheduled_tasks
        self.selected_task_id = task.id
        self.loading_form = True
        try:
            self.set_text_var(self.task_name_var, task.name)
            if self.task_enabled_var is not None:
                self.task_enabled_var.set(task.enabled)
            self.set_text_var(self.source_var, "" if is_empty_path(task.source) else task.source.as_posix())
            self.set_text_var(self.target_var, "" if is_empty_path(task.target) else task.target.as_posix())
            self.show_path_entries_end()
            self.set_text_var(self.interval_var, f"{task.interval_seconds:g}")
            if self.delete_extra_var is not None:
                self.delete_extra_var.set(task.delete_extra)
            interval_value, interval_unit = self.display_merge_interval(scheduled.zzc_merge_interval_minutes)
            self.set_text_var(self.zzc_merge_interval_var, f"{interval_value:g}")
            self.set_text_var(self.zzc_merge_unit_var, interval_unit)
            self.set_text_var(self.startup_delay_var, f"{scheduled.startup_delay_minutes:g}")
            self.clear_entry_placeholder(self.deploy_command_entry)
            self.set_text_var(self.deploy_command_var, scheduled.deploy_command)
            self.restore_entry_placeholder(self.deploy_command_entry)
            if self.auto_merge_zzc_var is not None:
                self.auto_merge_zzc_var.set(scheduled.auto_merge_zzc)
            if self.startup_auto_merge_var is not None:
                self.startup_auto_merge_var.set(scheduled.startup_auto_merge)
            if self.auto_deploy_after_merge_var is not None:
                self.auto_deploy_after_merge_var.set(scheduled.auto_deploy_after_merge)
            self.set_text_box(self.include_text, task.include)
            self.set_text_box(self.exclude_text, task.exclude)
            self.set_text_box(self.target_protect_text, task.target_protect)
            self.set_text_box(self.target_clean_text, task.target_clean)
            self.set_text_box(self.zzc_target_dicts_text, scheduled.zzc_target_dicts)
        finally:
            self.loading_form = False

    def on_task_fields_changed(self, _event: tk.Event | None = None) -> None:
        if self.loading_form:
            return
        self.save_form_config_silent()

    def on_auto_merge_toggled(self) -> None:
        if self.loading_form:
            return
        self.save_form_config_silent()

    def commit_task_name(self, _event: tk.Event | None = None) -> None:
        if self.loading_form:
            return
        self.save_form_config_silent()
        if self.task_listbox is not None and self.selected_task_id is not None:
            self.refresh_task_list(self.selected_task_id)

    def add_task(self) -> None:
        config = self.config_from_form()
        task_id = self.unique_task_id(config.tasks, "task")
        source = config.source if not is_empty_path(config.source) else Path()
        target = config.target if not is_empty_path(config.target) else Path()
        task = TaskSpec(
            id=task_id,
            name="同步任务",
            enabled=False,
            source=source,
            target=target,
            interval_seconds=config.interval_seconds,
            delete_extra=config.delete_extra,
        )
        self.current_config = replace(config, tasks=tuple(config.tasks) + (task,))
        self.selected_task_id = task.id
        self.refresh_task_list(task.id)
        self.apply_task_to_form(task)
        self.save_form_config_silent()

    def duplicate_task(self) -> None:
        config = self.config_from_form()
        task = self.selected_task()
        if task is None:
            return
        task_id = self.unique_task_id(config.tasks, f"{task.id}-copy")
        copy = replace(task, id=task_id, name=f"{task.name or task.id} Copy")
        self.current_config = replace(config, tasks=tuple(config.tasks) + (copy,))
        self.selected_task_id = copy.id
        self.refresh_task_list(copy.id)
        self.apply_task_to_form(copy)
        self.save_form_config_silent()

    def delete_task(self) -> None:
        config = self.config_from_form()
        if len(config.tasks) <= 1:
            return
        task_id = self.selected_task_id
        tasks = tuple(task for task in config.tasks if task.id != task_id)
        self.current_config = replace(config, tasks=tasks)
        next_id = tasks[0].id if tasks else None
        self.refresh_task_list(next_id)
        if tasks:
            self.apply_task_to_form(tasks[0])
        save_config(CONFIG_PATH, self.current_config)
        self.apply_startup_setting()
        self.log("已删除任务")
        self.wake_event.set()

    def unique_task_id(self, tasks: tuple[TaskSpec, ...], prefix: str) -> str:
        used = {task.id for task in tasks}
        base = prefix or "task"
        if base not in used:
            return base
        index = 2
        while f"{base}-{index}" in used:
            index += 1
        return f"{base}-{index}"

    def section_title(self, parent: tk.Misc, text_key: str) -> tk.Label:
        label = tk.Label(
            parent,
            text=self.t(text_key),
            bg=CARD_COLOR,
            fg=TEXT_COLOR,
            font=(UI_FONT, 11, "bold"),
        )
        self.register_i18n(label, text_key)
        return label

    def make_label(self, parent: tk.Misc, text_key: str) -> tk.Label:
        label = tk.Label(
            parent,
            text=self.t(text_key),
            bg=CARD_COLOR,
            fg=TEXT_COLOR,
            font=(UI_FONT, 10, "bold"),
        )
        self.register_i18n(label, text_key)
        return label

    def make_hint(self, parent: tk.Misc, text_key: str) -> tk.Label:
        label = tk.Label(
            parent,
            text=self.t(text_key),
            bg=CARD_COLOR,
            fg="#475467",
            font=(UI_FONT, 9),
        )
        self.register_i18n(label, text_key)
        return label

    def make_entry(self, parent: tk.Misc, variable: tk.StringVar, placeholder_key: str | None = None) -> tk.Entry:
        entry = tk.Entry(
            parent,
            textvariable=variable,
            relief="flat",
            bd=0,
            bg="#fbfcff",
            fg=TEXT_COLOR,
            insertbackground=TEXT_COLOR,
            font=(UI_FONT, 10),
            highlightthickness=2,
            highlightbackground=BORDER_COLOR,
            highlightcolor=PRIMARY_COLOR,
        )
        if placeholder_key:
            self.entry_placeholder_keys[entry] = placeholder_key
            entry.bind("<FocusIn>", lambda _event, input_box=entry: self.clear_entry_placeholder(input_box))
            entry.bind("<FocusOut>", lambda _event, input_box=entry: self.restore_entry_placeholder(input_box))
        entry.bind("<FocusOut>", self.save_form_config_silent, add="+")
        return entry

    def make_path_entry(self, parent: tk.Misc, variable: tk.StringVar | None) -> tk.Entry:
        if variable is None:
            variable = tk.StringVar()
        entry = self.make_entry(parent, variable)
        entry.bind("<FocusOut>", lambda _event, input_box=entry: self.show_entry_end(input_box), add="+")
        return entry

    def create_rule_text(self, parent: ttk.Frame, height: int, placeholder_key: str | None = None) -> tk.Text:
        box = scrolledtext.ScrolledText(
            parent,
            height=height,
            width=20,
            wrap="word" if placeholder_key else "none",
            relief="flat",
            borderwidth=1,
            font=(MONO_FONT, 10),
            bg="#fbfcff",
            fg="#172033",
            insertbackground="#172033",
            highlightthickness=2,
            highlightbackground=BORDER_COLOR,
            highlightcolor=PRIMARY_COLOR,
        )
        if placeholder_key:
            self.rule_placeholder_keys[box] = placeholder_key
            box.bind("<FocusIn>", lambda _event, text_box=box: self.clear_rule_placeholder(text_box))
        box.bind("<FocusOut>", lambda _event, text_box=box: self.on_rule_text_focus_out(text_box))
        return box

    def pack_rule_text(
        self,
        parent: tk.Misc,
        text: tk.Text,
        pady: tuple[int, int] = (0, 0),
    ) -> None:
        text.pack(fill="both", expand=True, pady=pady)

    def choose_source(self) -> None:
        self.choose_folder(self.source_var, self.source_entry)

    def choose_target(self) -> None:
        self.choose_folder(self.target_var, self.target_entry)

    def choose_folder(self, variable: tk.StringVar | None, entry: tk.Entry | None = None) -> None:
        if variable is None:
            return
        folder = filedialog.askdirectory(initialdir=variable.get() or str(BASE_DIR))
        if folder:
            variable.set(folder.replace("\\", "/"))
            self.show_entry_end(entry)
            self.save_form_config_silent()

    def add_include_file(self) -> None:
        self.add_selected_file(self.include_text)

    def add_include_folder(self) -> None:
        self.add_selected_folder(self.include_text)

    def add_include_items(self) -> None:
        self.show_select_menu(self.include_text, self.get_source_path)

    def clear_include(self) -> None:
        self.clear_text_box(self.include_text)

    def add_exclude_file(self) -> None:
        self.add_selected_file(self.exclude_text)

    def add_exclude_folder(self) -> None:
        self.add_selected_folder(self.exclude_text)

    def add_exclude_items(self) -> None:
        self.show_select_menu(self.exclude_text, self.get_source_path)

    def add_target_protected_file(self) -> None:
        self.add_selected_target_file(self.target_protect_text)

    def add_target_protected_folder(self) -> None:
        self.add_selected_target_folder(self.target_protect_text)

    def add_target_protected_items(self) -> None:
        self.show_select_menu(self.target_protect_text, self.get_target_path)

    def add_target_clean_items(self) -> None:
        self.show_select_menu(self.target_clean_text, self.get_target_path)

    def clear_exclude(self) -> None:
        self.clear_text_box(self.exclude_text)

    def clear_target_protect(self) -> None:
        self.clear_text_box(self.target_protect_text)

    def clear_target_clean(self) -> None:
        self.clear_text_box(self.target_clean_text)

    def add_zzc_target_dicts(self) -> None:
        self.show_select_menu(self.zzc_target_dicts_text, self.get_target_path)

    def clear_zzc_target_dicts(self) -> None:
        self.clear_text_box(self.zzc_target_dicts_text)

    def show_select_menu(self, box: tk.Text | None, root_getter) -> None:
        if box is None:
            return
        menu = tk.Menu(self.root, tearoff=False)
        menu.add_command(
            label=self.t("select_file"),
            command=lambda: self.add_selected_files(box, root_getter),
        )
        menu.add_command(
            label=self.t("select_folder"),
            command=lambda: self.add_selected_folder_from_root(box, root_getter),
        )
        try:
            x = self.root.winfo_pointerx() if self.root else 0
            y = self.root.winfo_pointery() if self.root else 0
            menu.tk_popup(x, y)
        finally:
            menu.grab_release()

    def add_selected_files(self, box: tk.Text | None, root_getter) -> None:
        if box is None:
            return
        root_path = root_getter()
        if not root_path:
            return
        selected = filedialog.askopenfilenames(initialdir=str(root_path), parent=self.root)
        added = 0
        for path_text in selected:
            if self.add_rule_from_root(box, root_path, Path(path_text), as_folder=False):
                added += 1
            else:
                messagebox.showwarning(APP_NAME, "请选择同一根目录内部的文件。")
        if selected:
            self.log(f"选择文件: root={root_path} selected={len(selected)} added={added}")
        if added:
            self.save_form_config_silent()

    def add_selected_folder_from_root(self, box: tk.Text | None, root_getter) -> None:
        if box is None:
            return
        root_path = root_getter()
        if not root_path:
            return
        selected = filedialog.askdirectory(initialdir=str(root_path), parent=self.root)
        if not selected:
            return
        if self.add_rule_from_root(box, root_path, Path(selected), as_folder=True):
            self.log(f"选择文件夹: root={root_path} selected={selected} added=1")
            self.save_form_config_silent()
            return
        self.log(f"选择文件夹失败: root={root_path} selected={selected} added=0")
        messagebox.showwarning(APP_NAME, "请选择同一根目录内部的文件夹。")

    def add_selected_file(self, box: tk.Text | None) -> None:
        self.add_selected_files(box, self.get_source_path)

    def add_selected_folder(self, box: tk.Text | None) -> None:
        self.add_selected_folder_from_root(box, self.get_source_path)

    def add_selected_target_file(self, box: tk.Text | None) -> None:
        self.add_selected_files(box, self.get_target_path)

    def add_selected_target_folder(self, box: tk.Text | None) -> None:
        self.add_selected_folder_from_root(box, self.get_target_path)

    def get_source_path(self) -> Path | None:
        if self.source_var is None or not self.source_var.get().strip():
            messagebox.showwarning(APP_NAME, "请先选择来源文件夹。")
            return None
        source = Path(self.source_var.get().strip()).expanduser()
        if not source.exists() or not source.is_dir():
            messagebox.showwarning(APP_NAME, "来源文件夹不存在，请先选择有效的来源文件夹。")
            return None
        return Path(os.path.abspath(source))

    def get_target_path(self) -> Path | None:
        if self.target_var is None or not self.target_var.get().strip():
            messagebox.showwarning(APP_NAME, "请先选择目标文件夹。")
            return None
        target = Path(self.target_var.get().strip()).expanduser()
        if not target.exists() or not target.is_dir():
            messagebox.showwarning(APP_NAME, "目标文件夹不存在，请先选择有效的目标文件夹。")
            return None
        return Path(os.path.abspath(target))

    def add_relative_rule(self, box: tk.Text | None, selected: Path, as_folder: bool) -> None:
        if box is None:
            return
        source = self.get_source_path()
        if not source:
            return
        if not self.add_rule_from_root(box, source, selected, as_folder):
            messagebox.showwarning(APP_NAME, "请选择来源文件夹内部的文件或文件夹。")

    def add_target_relative_rule(
        self, box: tk.Text | None, selected: Path, as_folder: bool
    ) -> None:
        if box is None:
            return
        target = self.get_target_path()
        if not target:
            return
        if not self.add_rule_from_root(box, target, selected, as_folder):
            messagebox.showwarning(APP_NAME, "请选择目标文件夹内部的文件或文件夹。")

    def add_rule_from_root(
        self,
        box: tk.Text,
        root_path: Path,
        selected: Path,
        as_folder: bool | None = None,
    ) -> bool:
        rel = self.relative_rule_path(root_path, selected)
        if rel is None:
            self.log(f"[warn] 选择内容不在根目录内 root={root_path} selected={selected}")
            return False
        if as_folder is None:
            as_folder = selected.is_dir()
        if as_folder:
            rel = "**" if rel in {"", "."} else f"{rel.rstrip('/')}/**"
        self.clear_rule_placeholder(box)
        append_pattern(box, rel)
        self.root_update()
        self.log(f"已添加规则: {rel}")
        return True

    def relative_rule_path(self, root_path: Path, selected: Path) -> str | None:
        try:
            root_abs = Path(os.path.abspath(root_path))
            selected_abs = Path(os.path.abspath(selected))
            root_norm = os.path.normcase(str(root_abs))
            selected_norm = os.path.normcase(str(selected_abs))
            common = os.path.commonpath([root_norm, selected_norm])
            if common != root_norm:
                return None
            rel = os.path.relpath(selected_abs, root_abs)
            if rel == ".":
                return "."
            return Path(rel).as_posix()
        except (OSError, ValueError):
            return None

    def clear_text_box(self, box: tk.Text | None) -> None:
        if box is not None:
            self.clear_rule_placeholder(box)
            box.delete("1.0", "end")
            self.restore_rule_placeholder(box)
            self.root_update()
            if not self.loading_form:
                self.save_form_config_silent()

    def root_update(self) -> None:
        if self.root is None:
            return
        self.root.update_idletasks()

    def clear_focus_on_non_input_click(self, event: tk.Event) -> None:
        if self.root is None or self.is_input_widget(event.widget):
            return
        self.root.focus_set()

    def is_input_widget(self, widget: object) -> bool:
        if not isinstance(widget, tk.Widget):
            return False
        input_classes = {
            "Text",
            "Entry",
            "TEntry",
            "Spinbox",
            "TSpinbox",
            "Combobox",
            "TCombobox",
        }
        return widget.winfo_class() in input_classes

    def load_config_into_form(self) -> None:
        if not self.root:
            return
        try:
            config = load_config(CONFIG_PATH)
            config = self.migrate_old_delay_default(config)
        except BaseException as exc:
            self.log(f"[error] 加载配置失败 {CONFIG_PATH}: {exc}")
            messagebox.showerror(APP_NAME, f"加载配置失败：{exc}")
            return
        self.loading_form = True
        try:
            self.log(f"已加载配置: {CONFIG_PATH}")
            self.current_config = config
            selected_id = self.selected_task_id if self.selected_task_id else (config.tasks[0].id if config.tasks else None)
            self.refresh_task_list(selected_id)
            task = self.selected_task()
            if task is not None:
                self.apply_task_to_form(task)
        finally:
            self.loading_form = False

    def migrate_old_delay_default(self, config: SyncConfig) -> SyncConfig:
        if config.interval_seconds != 2:
            return config
        migrated = SyncConfig(
            source=config.source,
            target=config.target,
            include=config.include,
            exclude=config.exclude,
            target_protect=config.target_protect,
            target_clean=config.target_clean,
            interval_seconds=0,
            delete_extra=config.delete_extra,
            tasks=config.tasks,
            scheduled_tasks=config.scheduled_tasks,
        )
        try:
            save_config(CONFIG_PATH, migrated)
            self.log("已将旧默认触发延迟 2 秒迁移为 0 秒")
        except Exception as exc:
            self.log(f"[error] 迁移触发延迟失败: {exc}")
        return migrated

    def set_text_var(self, variable: tk.StringVar | None, value: str) -> None:
        if variable is not None:
            variable.set(value)

    def show_path_entries_end(self) -> None:
        self.show_entry_end(self.source_entry)
        self.show_entry_end(self.target_entry)

    def show_entry_end(self, entry: tk.Entry | None) -> None:
        if entry is None:
            return
        entry.icursor("end")
        entry.xview_moveto(1.0)

    def clear_entry_placeholder(self, entry: tk.Entry | None) -> None:
        if entry is None or entry not in self.entry_placeholder_active:
            return
        entry.delete(0, "end")
        entry.configure(fg=TEXT_COLOR)
        self.entry_placeholder_active.discard(entry)

    def restore_entry_placeholder(self, entry: tk.Entry | None) -> None:
        if entry is None or entry not in self.entry_placeholder_keys:
            return
        if entry.get().strip():
            return
        entry.delete(0, "end")
        entry.insert(0, self.t(self.entry_placeholder_keys[entry]))
        entry.configure(fg="#98a2b3")
        self.entry_placeholder_active.add(entry)

    def set_text_box(self, box: tk.Text | None, lines: tuple[str, ...]) -> None:
        if box is None:
            return
        self.clear_rule_placeholder(box)
        box.delete("1.0", "end")
        box.insert("1.0", "\n".join(lines))
        box.see("1.0")
        box.update_idletasks()
        self.restore_rule_placeholder(box)
        box.edit_modified(False)

    def on_rule_text_focus_out(self, box: tk.Text) -> None:
        self.restore_rule_placeholder(box)
        box.edit_modified(False)
        if self.loading_form:
            return
        self.save_form_config_silent()

    def clear_rule_placeholder(self, box: tk.Text | None) -> None:
        if box is None or box not in self.rule_placeholder_active:
            return
        box.delete("1.0", "end")
        box.tag_remove("placeholder", "1.0", "end")
        box.configure(fg="#172033")
        self.rule_placeholder_active.discard(box)

    def restore_rule_placeholder(self, box: tk.Text | None) -> None:
        if box is None or box not in self.rule_placeholder_keys:
            return
        if box.get("1.0", "end").strip():
            return
        box.delete("1.0", "end")
        box.insert("1.0", self.t(self.rule_placeholder_keys[box]))
        box.tag_add("placeholder", "1.0", "end")
        box.configure(fg="#98a2b3")
        self.rule_placeholder_active.add(box)

    def display_merge_interval(self, minutes: float) -> tuple[float, str]:
        if minutes > 0 and minutes % (24 * 60) == 0:
            return minutes / (24 * 60), self.merge_unit_label("days")
        if minutes > 0 and minutes % 60 == 0:
            return minutes / 60, self.merge_unit_label("hours")
        return minutes, self.merge_unit_label("minutes")

    def merge_interval_to_minutes(self, value: float, unit: str) -> float:
        unit_key = self.merge_unit_key(unit)
        if unit_key == "days":
            return value * 24 * 60
        if unit_key == "hours":
            return value * 60
        return value

    def on_merge_unit_selected(self, _event: tk.Event | None = None) -> None:
        if self.loading_form or self.root is None:
            return
        self.root.after_idle(self.save_form_config_silent)

    def save_form_config(self) -> None:
        try:
            config = self.config_from_form()
            self.current_config = config
            save_config(CONFIG_PATH, config)
            self.refresh_task_list(self.selected_task_id)
            self.apply_startup_setting()
            self.log("已从窗口保存配置")
            self.flash_status("已保存配置", 2000)
            self.request_sync_after_config_change()
        except Exception as exc:
            self.log(f"[error] 保存配置失败: {exc}")
            messagebox.showerror(APP_NAME, f"保存配置失败：{exc}")

    def save_form_config_silent(self, _event: tk.Event | None = None) -> None:
        if self.loading_form:
            return
        try:
            config = self.config_from_form()
            self.current_config = config
            save_config(CONFIG_PATH, config)
            self.refresh_task_list(self.selected_task_id)
            self.apply_startup_setting()
            self.log("已自动保存配置")
            self.request_sync_after_config_change()
        except BaseException as exc:
            self.log(f"[error] 自动保存配置失败: {exc}")

    def request_sync_after_config_change(self) -> None:
        if self.started and not self.paused:
            self.initial_sync_pending = True
            self.change_event.set()
        self.wake_event.set()

    def apply_startup_setting(self) -> None:
        if self.startup_var is None:
            return
        set_startup_enabled(bool(self.startup_var.get()))

    def config_from_form(self) -> SyncConfig:
        if any(
            item is None
            for item in (
                self.source_var,
                self.target_var,
                self.interval_var,
                self.task_name_var,
                self.zzc_merge_interval_var,
                self.zzc_merge_unit_var,
                self.startup_delay_var,
                self.deploy_command_var,
                self.delete_extra_var,
                self.task_enabled_var,
                self.startup_var,
                self.auto_merge_zzc_var,
                self.startup_auto_merge_var,
                self.auto_deploy_after_merge_var,
                self.include_text,
                self.exclude_text,
                self.target_protect_text,
                self.target_clean_text,
                self.zzc_target_dicts_text,
            )
        ):
            raise ValueError("配置窗口还未准备好。")

        source_text = self.source_var.get().strip()
        target_text = self.target_var.get().strip()
        source = Path(source_text).expanduser() if source_text else Path()
        target = Path(target_text).expanduser() if target_text else Path()
        include = tuple(read_patterns(self.include_text))
        exclude = tuple(read_patterns(self.exclude_text))
        target_protect = tuple(read_patterns(self.target_protect_text))
        target_clean = tuple(read_patterns(self.target_clean_text))
        interval_seconds = float(self.interval_var.get().strip())
        scheduled_tasks = self.scheduled_tasks_from_form()
        if interval_seconds < 0:
            raise ValueError("触发延迟不能小于 0 秒。")
        if scheduled_tasks.zzc_merge_interval_minutes < 0:
            raise ValueError("自造词合并间隔不能小于 0 分钟。")
        if scheduled_tasks.startup_delay_minutes < 0:
            raise ValueError("开机合并等待时间不能小于 0 分钟。")
        base_config = self.current_config
        task_id = self.selected_task_id or "sync"
        current_task = self.task_from_form(task_id)
        if base_config and base_config.tasks:
            tasks_list = []
            replaced = False
            for task in base_config.tasks:
                if task.id == task_id:
                    tasks_list.append(current_task)
                    replaced = True
                else:
                    tasks_list.append(task)
            if not replaced:
                tasks_list.append(current_task)
            tasks = tuple(tasks_list)
        else:
            tasks = (current_task,)
        return SyncConfig(
            source=source.resolve() if source_text else source,
            target=target.resolve() if target_text else target,
            include=include,
            exclude=exclude,
            target_protect=target_protect,
            target_clean=target_clean,
            interval_seconds=interval_seconds,
            delete_extra=bool(self.delete_extra_var.get()),
            tasks=tasks,
            scheduled_tasks=scheduled_tasks,
        )

    def task_from_form(self, task_id: str) -> TaskSpec:
        if any(
            item is None
            for item in (
                self.source_var,
                self.target_var,
                self.interval_var,
                self.task_name_var,
                self.task_enabled_var,
                self.delete_extra_var,
                self.include_text,
                self.exclude_text,
                self.target_protect_text,
                self.target_clean_text,
            )
        ):
            raise ValueError("配置窗口还未准备好。")
        source_text = self.source_var.get().strip()
        target_text = self.target_var.get().strip()
        source = Path(source_text).expanduser() if source_text else Path()
        target = Path(target_text).expanduser() if target_text else Path()
        scheduled = self.scheduled_tasks_from_form()
        return TaskSpec(
            id=task_id,
            name=self.task_name_var.get().strip() or task_id,
            enabled=bool(self.task_enabled_var.get()),
            source=source.resolve() if source_text else source,
            target=target.resolve() if target_text else target,
            include=tuple(read_patterns(self.include_text)),
            exclude=tuple(read_patterns(self.exclude_text)),
            target_protect=tuple(read_patterns(self.target_protect_text)),
            target_clean=tuple(read_patterns(self.target_clean_text)),
            delete_extra=bool(self.delete_extra_var.get()),
            interval_seconds=float(self.interval_var.get().strip()),
            scheduled_tasks=scheduled,
        )

    def scheduled_tasks_from_form(self) -> ScheduledTasksConfig:
        if any(
            item is None
            for item in (
                self.zzc_merge_interval_var,
                self.zzc_merge_unit_var,
                self.startup_delay_var,
                self.auto_merge_zzc_var,
                self.startup_auto_merge_var,
                self.auto_deploy_after_merge_var,
                self.zzc_target_dicts_text,
                self.deploy_command_var,
            )
        ):
            raise ValueError("配置窗口还未准备好。")
        return ScheduledTasksConfig(
            auto_merge_zzc=bool(self.auto_merge_zzc_var.get()),
            zzc_target_dicts=tuple(read_patterns(self.zzc_target_dicts_text)),
            zzc_merge_interval_minutes=self.merge_interval_to_minutes(
                float(self.zzc_merge_interval_var.get().strip()),
                self.zzc_merge_unit_var.get().strip(),
            ),
            startup_auto_merge=bool(self.startup_auto_merge_var.get()),
            startup_delay_minutes=float(self.startup_delay_var.get().strip()),
            auto_deploy_after_merge=bool(self.auto_deploy_after_merge_var.get()),
            deploy_command="" if self.deploy_command_entry in self.entry_placeholder_active else self.deploy_command_var.get().strip(),
        )

    def hide_window(self) -> None:
        if self.root:
            self.root.withdraw()

    def show_window(self, icon=None, item=None) -> None:
        if self.root:
            self.root.after(0, self._show_window)

    def _show_window(self) -> None:
        if not self.root:
            return
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def start_sync_from_saved_config(self) -> None:
        if self.started:
            return
        try:
            config = load_config(CONFIG_PATH)
            ensure_safe_config(config)
        except BaseException as exc:
            self.log(f"[error] 开机启用同步失败: {exc}")
            self.set_status("监听或同步失败")
            return
        self.started = True
        self.paused = False
        self.initial_sync_pending = True
        self.startup_sync_started_at = time.monotonic()
        self.startup_merge_done.clear()
        self.change_event.clear()
        self.log("开机启动并启用同步")
        self.set_status("启动中")
        self.update_sync_button()
        self.wake_event.set()
        self.icon.update_menu()

    def notify_source_changed(self, immediate: bool = False) -> None:
        if immediate:
            self.immediate_sync_event.set()
        self.change_event.set()
        self.wake_event.set()

    def stop_observer(self) -> None:
        observer = self.observer
        self.observer = None
        self.observed_sources = ()
        if observer:
            observer.stop()
            observer.join(timeout=2)

    def ensure_observer(self, sources: tuple[Path, ...]) -> None:
        sources = tuple(source.resolve() for source in sources)
        if not sources:
            self.stop_observer()
            return
        if self.observer and self.observed_sources == sources:
            return
        self.stop_observer()
        observer = Observer()
        for source in sources:
            immediate = any(task.enabled and source == task.source.resolve() for task in self.current_config.tasks) if self.current_config else False
            observer.schedule(SourceChangeHandler(self.notify_source_changed, immediate=immediate), str(source), recursive=True)
        observer.start()
        self.observer = observer
        self.observed_sources = sources
        self.log(f"开始监听来源: {', '.join(source.as_posix() for source in sources)}")

    def run_sync_from_config(self, config: SyncConfig) -> None:
        self.set_status("正在同步")
        with self.operation_lock:
            stats = sync_tasks_once(self.sync_config_with_auto_merge_protection(config), logger=self.log)
            if stats.has_changes():
                self.log(
                    f"同步完成 copied={stats.copied} "
                    f"deleted={stats.deleted} errors={stats.errors}"
                )
        self.set_status("同步完成")
        if self.root:
            self.root.after(1500, lambda: self.set_status("监听中") if self.started and not self.paused else None)

    def sync_config_with_auto_merge_protection(self, config: SyncConfig) -> SyncConfig:
        if not config.scheduled_tasks.auto_merge_zzc:
            return config
        protects = list(config.target_protect)
        append_auto_merge_protects(protects)
        return SyncConfig(
            source=config.source,
            target=config.target,
            include=config.include,
            exclude=config.exclude,
            target_protect=tuple(protects),
            target_clean=config.target_clean,
            interval_seconds=config.interval_seconds,
            delete_extra=config.delete_extra,
            tasks=config.tasks,
            scheduled_tasks=config.scheduled_tasks,
        )

    def zzc_merge_tasks(self, config: SyncConfig, manual: bool = False) -> tuple[TaskSpec, ...]:
        has_explicit_tasks = bool(config.tasks)
        enabled_tasks = tuple(task for task in config.tasks if task.enabled)
        selected = []
        for task in enabled_tasks:
            scheduled = task.scheduled_tasks or config.scheduled_tasks
            task = task if task.scheduled_tasks is not None else replace(task, scheduled_tasks=scheduled)
            if manual:
                if scheduled.zzc_target_dicts:
                    selected.append(task)
            elif task.enabled and scheduled.auto_merge_zzc:
                selected.append(task)
        if selected:
            return tuple(selected)
        if has_explicit_tasks:
            return ()
        if not config.scheduled_tasks.auto_merge_zzc and not (manual and config.scheduled_tasks.zzc_target_dicts):
            return ()
        return tuple(
            task
            for task in default_tasks_from_legacy(
                source=config.source,
                target=config.target,
                include=config.include,
                exclude=config.exclude,
                target_protect=config.target_protect,
                target_clean=config.target_clean,
                interval_seconds=config.interval_seconds,
                delete_extra=config.delete_extra,
                scheduled_tasks=config.scheduled_tasks,
            )
            if (
                (task.enabled or manual)
                and (
                    (manual and config.scheduled_tasks.zzc_target_dicts)
                    or config.scheduled_tasks.auto_merge_zzc
                )
            )
        )

    def zzc_task_config(self, config: SyncConfig, task: TaskSpec) -> SyncConfig:
        task_config = sync_config_for_task(config, task)
        return SyncConfig(
            source=task_config.source,
            target=task_config.target,
            include=task_config.include,
            exclude=task_config.exclude,
            target_protect=task_config.target_protect,
            target_clean=task_config.target_clean,
            interval_seconds=task_config.interval_seconds,
            delete_extra=task_config.delete_extra,
            tasks=config.tasks,
            scheduled_tasks=task.scheduled_tasks or config.scheduled_tasks,
        )

    def zzc_files_stable(self, config: SyncConfig) -> bool:
        scheme = find_scheme(config.target)
        target_scheme = find_scheme(config.source)
        paths = []
        if scheme:
            paths.append(scheme.ops)
        if target_scheme:
            paths.append(target_scheme.ops)
        if not paths:
            return False
        now = time.time()
        for path in paths:
            if path.exists() and now - path.stat().st_mtime < ZZC_STABLE_SECONDS:
                return False
        return True

    def run_zzc_merge_task(self, config: SyncConfig, task: TaskSpec, manual: bool = False) -> bool:
        task_config = self.zzc_task_config(config, task)
        scheduled = task_config.scheduled_tasks
        ensure_safe_task(replace(task, scheduled_tasks=scheduled))
        if not manual and not self.zzc_files_stable(task_config):
            self.log(f"[zzc] task {task.id} files still changing, skipped")
            return False
        zzc_root = task_config.target
        dict_root = task_config.source
        self.log(f"[zzc] 合并来源 zzc：{zzc_root}")
        self.log(f"[zzc] 合并目标码表目录：{dict_root}")
        reconcile_ops_between_roots(dict_root, zzc_root, logger=self.log)
        changed = merge_root(
            zzc_root,
            target_dicts=scheduled.zzc_target_dicts,
            dict_root=dict_root,
            logger=self.log,
        )
        if changed:
            copy_managed_files(
                zzc_root,
                dict_root,
                target_dicts=scheduled.zzc_target_dicts,
                logger=self.log,
                copy_target_dicts=False,
            )
            self.last_zzc_merge_at[task.id] = time.monotonic()
            if scheduled.auto_deploy_after_merge:
                self.run_deploy(task_config)
            return True
        source_scheme = find_scheme(zzc_root)
        if source_scheme:
            clear_ops(source_scheme)
        return False

    def run_zzc_merge_from_config(self, config: SyncConfig, manual: bool = False) -> bool:
        tasks = self.zzc_merge_tasks(config, manual=manual)
        if not tasks:
            self.log("[zzc] no enabled merge task")
            self.set_status("合并失败")
            return False
        merge_status_started = time.monotonic()
        self.set_status("正在合并")
        with self.operation_lock:
            changed_by_task: dict[str, bool] = {}
            task_by_id = {task.id: task for task in tasks}

            def run_task(task_def) -> bool:
                task = task_by_id[task_def.id]
                changed = self.run_zzc_merge_task(config, task, manual=manual)
                changed_by_task[task.id] = changed
                return True

            scheduler = TaskScheduler()
            scheduler.run(
                tuple(build_task_definition(task) for task in tasks),
                run_task,
            )
            remaining = 1.0 - (time.monotonic() - merge_status_started)
            if remaining > 0:
                time.sleep(remaining)
            self.set_status("合并成功")
            if self.root:
                next_status = "监听中" if self.started and not self.paused else self.base_status
                self.root.after(1000, lambda: self.set_status(next_status) if self.status == "合并成功" else None)
            return any(changed_by_task.values())

    def zzc_task_due(self, task: TaskSpec, now: float) -> tuple[bool, bool]:
        scheduled = task.scheduled_tasks
        if scheduled is None or not scheduled.auto_merge_zzc:
            return False, False
        startup_due = (
            scheduled.startup_auto_merge
            and task.id not in self.startup_merge_done
            and self.startup_sync_started_at > 0
            and now - self.startup_sync_started_at >= scheduled.startup_delay_minutes * 60
        )
        last_merge_at = self.last_zzc_merge_at.get(task.id, 0.0)
        interval_due = last_merge_at <= 0 or now - last_merge_at >= scheduled.zzc_merge_interval_minutes * 60
        return startup_due, interval_due

    def scheduled_task_loop(self) -> None:
        while not self.stop_event.is_set():
            self.stop_event.wait(30)
            if self.stop_event.is_set() or not self.started or self.paused:
                continue
            try:
                config = load_config(CONFIG_PATH)
                tasks = self.zzc_merge_tasks(config, manual=False)
                now = time.monotonic()
                due_tasks = []
                startup_due_ids = set()
                for task in tasks:
                    startup_due, interval_due = self.zzc_task_due(task, now)
                    if startup_due:
                        startup_due_ids.add(task.id)
                    if startup_due or interval_due:
                        due_tasks.append(task)
                if not due_tasks:
                    continue
                due_config = SyncConfig(
                    source=config.source,
                    target=config.target,
                    include=config.include,
                    exclude=config.exclude,
                    target_protect=config.target_protect,
                    target_clean=config.target_clean,
                    interval_seconds=config.interval_seconds,
                    delete_extra=config.delete_extra,
                    tasks=tuple(due_tasks),
                    scheduled_tasks=config.scheduled_tasks,
                )
                merged = self.run_zzc_merge_from_config(due_config, manual=False)
                self.startup_merge_done.update(startup_due_ids)
                if merged:
                    self.log("[zzc] 定时合并完成")
            except BaseException as exc:
                self.log(f"[error] 定时合并失败: {exc}")
                self.log(traceback.format_exc())
                self.set_status("合并失败")

    def resolve_deploy_command(self, config: SyncConfig) -> str:
        command = config.scheduled_tasks.deploy_command.strip()
        if not command:
            candidates = [
                Path(r"C:\Program Files (x86)\Rime\weasel-0.16.3\WeaselDeployer.exe"),
                Path(r"C:\Program Files (x86)\Rime\weasel\WeaselDeployer.exe"),
                Path(r"C:\Program Files\Rime\weasel\WeaselDeployer.exe"),
            ]
            for candidate in candidates:
                if candidate.exists():
                    command = f'"{candidate}" /deploy'
                    break
        return command

    def run_deploy(self, config: SyncConfig) -> bool:
        command = self.resolve_deploy_command(config)
        if not command:
            self.log("[zzc] 未找到部署程序，跳过自动重新部署")
            return False
        result = subprocess.run(command, shell=True, cwd=str(config.target), capture_output=True, text=True, timeout=120)
        if result.returncode == 0:
            self.log("[zzc] 已自动重新部署")
            return True
        self.log(f"[error] 自动重新部署失败 code={result.returncode} stdout={result.stdout} stderr={result.stderr}")
        return False

    def wait_until_change(self) -> bool:
        while not self.stop_event.is_set():
            if not self.started or self.paused:
                return False
            if self.change_event.is_set():
                return True
            self.wake_event.wait(1)
            self.wake_event.clear()
        return False

    def wait_delay_or_more_changes(self, delay_seconds: float) -> bool:
        deadline = time.monotonic() + max(0.0, delay_seconds)
        while not self.stop_event.is_set():
            if not self.started or self.paused:
                return False
            if self.immediate_sync_event.is_set():
                self.immediate_sync_event.clear()
                return True
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return True
            self.change_event.wait(min(remaining, 0.5))
            if self.change_event.is_set():
                self.change_event.clear()
                deadline = time.monotonic() + max(0.0, delay_seconds)
        return False

    def worker_loop(self) -> None:
        while not self.stop_event.is_set():
            if not self.started:
                self.stop_observer()
                self.set_status("未启动")
                self.wake_event.wait(1)
                self.wake_event.clear()
                continue

            if self.paused:
                self.stop_observer()
                self.set_status("已暂停")
                self.wake_event.wait(1)
                self.wake_event.clear()
                continue

            try:
                config = load_config(CONFIG_PATH)
                ensure_safe_config(config)
                self.current_config = config
                self.ensure_observer(sync_task_watch_paths(config))
                if self.initial_sync_pending:
                    self.initial_sync_pending = False
                    self.change_event.clear()
                    self.run_sync_from_config(config)
                    continue
                self.set_status("监听中")
                if not self.wait_until_change():
                    continue
                self.set_status("检测到变动")
                immediate_sync = self.immediate_sync_event.is_set()
                self.immediate_sync_event.clear()
                self.change_event.clear()
                if not immediate_sync and not self.wait_delay_or_more_changes(config.interval_seconds):
                    continue
                config = load_config(CONFIG_PATH)
                ensure_safe_config(config)
                self.current_config = config
                self.ensure_observer(sync_task_watch_paths(config))
                self.run_sync_from_config(config)
            except BaseException as exc:
                self.stop_observer()
                self.log(f"[error] {exc}")
                self.log(traceback.format_exc())
                self.set_status("监听或同步失败")

            self.wake_event.wait(1)
            self.wake_event.clear()

    def toggle_sync(self, icon=None, item=None) -> None:
        if not self.started:
            try:
                config = self.config_from_form()
                ensure_safe_config(config)
                save_config(CONFIG_PATH, config)
            except BaseException as exc:
                self.log(f"[error] 启动失败: {exc}")
                messagebox.showerror(APP_NAME, f"启动失败：{exc}")
                return
            self.started = True
            self.paused = False
            self.initial_sync_pending = True
            self.startup_sync_started_at = time.monotonic()
            self.startup_merge_done.clear()
            self.change_event.clear()
            self.log("启动同步")
            self.set_status("启动中")
        else:
            self.paused = not self.paused
            if not self.paused:
                self.initial_sync_pending = True
            self.log("暂停同步" if self.paused else "继续同步")
            self.set_status("已暂停" if self.paused else "运行中")

        self.update_sync_button()
        self.wake_event.set()
        self.icon.update_menu()

    def sync_now(self, icon=None, item=None) -> None:
        try:
            config = self.config_from_form()
            ensure_safe_config(config)
            save_config(CONFIG_PATH, config)
            self.set_status("正在同步")
            with self.operation_lock:
                stats = sync_tasks_once(self.sync_config_with_auto_merge_protection(config), logger=self.log)
            self.set_status("同步完成")
            if self.root:
                next_status = "监听中" if self.started and not self.paused else self.base_status
                self.root.after(1500, lambda: self.set_status(next_status))
            self.log(
                f"手动同步完成 copied={stats.copied} "
                f"deleted={stats.deleted} errors={stats.errors}"
            )
        except BaseException as exc:
            self.log(f"[error] 手动同步失败: {exc}")
            messagebox.showerror(APP_NAME, f"手动同步失败：{exc}")

    def merge_now(self, icon=None, item=None) -> None:
        try:
            config = self.config_from_form()
            save_config(CONFIG_PATH, config)
            changed = self.run_zzc_merge_from_config(config, manual=True)
            self.log("手动合并完成" + ("，有写入" if changed else "，无待合并操作"))
        except BaseException as exc:
            self.set_status("合并失败")
            self.log(f"[error] 手动合并失败: {exc}")
            self.log(traceback.format_exc())
            messagebox.showerror(APP_NAME, f"手动合并失败：{exc}")

    def deploy_now(self, icon=None, item=None) -> None:
        if self.deploy_in_progress:
            self.flash_status("部署中")
            return
        try:
            if threading.current_thread() is threading.main_thread():
                config = self.config_from_form()
                ensure_safe_config(config)
                save_config(CONFIG_PATH, config)
            else:
                config = load_config(CONFIG_PATH)
                ensure_safe_config(config)
            self.deploy_in_progress = True
            self.set_status("部署中")
            threading.Thread(target=self.deploy_now_worker, args=(config,), daemon=True).start()
        except BaseException as exc:
            self.set_status("部署失败")
            self.log(f"[error] 手动部署失败: {exc}")
            self.log(traceback.format_exc())
            messagebox.showerror(APP_NAME, f"部署失败：{exc}")

    def deploy_now_worker(self, config: SyncConfig) -> None:
        try:
            with self.operation_lock:
                deployed = self.run_deploy(config)
            if deployed:
                self.log("手动部署完成")
                self.run_on_ui_thread(lambda: self.finish_deploy(success=True, message=None))
                return
            self.run_on_ui_thread(
                lambda: self.finish_deploy(
                    success=False,
                    message="部署失败：未找到小狼毫部署程序，或部署命令执行失败。",
                )
            )
        except BaseException as exc:
            self.log(f"[error] 手动部署失败: {exc}")
            self.log(traceback.format_exc())
            self.run_on_ui_thread(lambda: self.finish_deploy(success=False, message=f"部署失败：{exc}"))

    def run_on_ui_thread(self, callback) -> None:
        if self.root:
            self.root.after(0, callback)
            return
        callback()

    def finish_deploy(self, success: bool, message: str | None) -> None:
        self.deploy_in_progress = False
        if success:
            self.set_status("部署完成")
            if self.root:
                next_status = "监听中" if self.started and not self.paused else self.base_status
                self.root.after(1500, lambda: self.set_status(next_status))
            return
        self.set_status("部署失败")
        if message:
            messagebox.showerror(APP_NAME, message)

    def open_log(self, icon=None, item=None) -> None:
        if not LOG_PATH.exists():
            LOG_PATH.write_text("", encoding="utf-8")
        open_path(LOG_PATH)

    def quit(self, icon=None, item=None) -> None:
        self.log("退出程序")
        self.stop_event.set()
        self.wake_event.set()
        self.change_event.set()
        self.stop_observer()
        self.icon.stop()
        if self.root:
            self.root.after(0, self.root.destroy)


def ensure_config_exists() -> None:
    BASE_DIR.mkdir(parents=True, exist_ok=True)
    if CONFIG_PATH.exists():
        return
    create_default_config(CONFIG_PATH)
    LOG_PATH.write_text(
        "首次启动已创建 config.json，请在程序窗口中设置 source 和 target。\n",
        encoding="utf-8",
    )


def startup_args() -> list[str]:
    if getattr(sys, "frozen", False):
        return [str(Path(sys.executable).resolve()), "--background"]
    return [sys.executable, str(Path(__file__).resolve()), "--background"]


def quote_command_arg(arg: str) -> str:
    return '"' + arg.replace('"', r'\"') + '"'


def startup_command() -> str:
    if sys.platform.startswith("win"):
        return subprocess.list2cmdline(startup_args())
    return " ".join(quote_command_arg(arg) for arg in startup_args())


def windows_startup_value() -> str | None:
    if winreg is None:
        return None
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_READ,
        ) as key:
            value, _ = winreg.QueryValueEx(key, STARTUP_VALUE_NAME)
    except FileNotFoundError:
        return None
    except OSError:
        return None
    return str(value).strip()


def is_startup_enabled() -> bool:
    if sys.platform == "darwin":
        return macos_startup_plist_path().exists()
    return bool(windows_startup_value())


def set_startup_enabled(enabled: bool) -> None:
    if sys.platform == "darwin":
        set_macos_startup_enabled(enabled)
        return
    if winreg is None:
        return
    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Run",
        0,
        winreg.KEY_SET_VALUE,
    ) as key:
        if enabled:
            winreg.SetValueEx(key, STARTUP_VALUE_NAME, 0, winreg.REG_SZ, startup_command())
        else:
            try:
                winreg.DeleteValue(key, STARTUP_VALUE_NAME)
            except FileNotFoundError:
                pass


def macos_startup_plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{MACOS_LAUNCH_AGENT_ID}.plist"


def set_macos_startup_enabled(enabled: bool) -> None:
    plist_path = macos_startup_plist_path()
    if enabled:
        plist_path.parent.mkdir(parents=True, exist_ok=True)
        plist = {
            "Label": MACOS_LAUNCH_AGENT_ID,
            "ProgramArguments": startup_args(),
            "RunAtLoad": True,
            "KeepAlive": False,
        }
        with plist_path.open("wb") as handle:
            plistlib.dump(plist, handle)
        return
    try:
        plist_path.unlink()
    except FileNotFoundError:
        pass


def open_path(path: Path) -> None:
    if sys.platform.startswith("win"):
        os.startfile(path)
        return
    command = ["open", str(path)] if sys.platform == "darwin" else ["xdg-open", str(path)]
    try:
        subprocess.Popen(command)
    except OSError:
        pass


def cleanup_log_file(log_path: Path) -> None:
    if not log_path.exists():
        return
    try:
        if log_path.stat().st_size <= LOG_MAX_BYTES:
            return
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return

    kept = lines[-LOG_MAX_LINES:]
    text = "\n".join(kept)
    if text:
        text += "\n"

    try:
        log_path.write_text(text, encoding="utf-8")
    except OSError:
        return


def read_patterns(box: tk.Text) -> list[str]:
    if box.tag_ranges("placeholder"):
        return []
    lines = box.get("1.0", "end").splitlines()
    return [line.strip().replace("\\", "/") for line in lines if line.strip()]


def append_pattern(box: tk.Text, pattern: str) -> None:
    existing = read_patterns(box)
    if pattern in existing:
        box.see(f"{existing.index(pattern) + 1}.0")
        box.focus_set()
        box.update_idletasks()
        return
    next_lines = [*existing, pattern]
    box.delete("1.0", "end")
    box.insert("1.0", "\n".join(next_lines))
    if existing:
        box.see("end")
    else:
        box.see("1.0")
    box.focus_set()
    box.update_idletasks()
    box.update()


def main() -> int:
    enable_dpi_awareness()
    single_instance = SingleInstanceLock()
    if not single_instance.acquire():
        return 0
    try:
        MirrorTrayApp().run()
        return 0
    finally:
        single_instance.release()


if __name__ == "__main__":
    raise SystemExit(main())
