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
from pathlib import Path

import pystray
from PIL import Image, ImageDraw
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from sync_mirror import (
    ScheduledTasksConfig,
    SyncConfig,
    create_default_config,
    ensure_safe_config,
    is_empty_path,
    load_config,
    save_config,
    sync_once,
)
from version import __version__
from zzc_merge import clear_ops, copy_managed_files, find_scheme, merge_root, reconcile_ops_between_roots

if sys.platform.startswith("win"):
    import winreg
else:
    winreg = None


APP_NAME = "天行键同步助手"
STARTUP_VALUE_NAME = "TxjxSyncAssistant"
MACOS_LAUNCH_AGENT_ID = "com.fusheng.txjxsync"
WINDOW_WIDTH = 833
WINDOW_HEIGHT = 846
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
SINGLE_INSTANCE_MUTEX = "Global\\TxjxSyncAssistant"

TRANSLATIONS = {
    "zh": {
        "language": "语言",
        "status": "状态",
        "settings": "同步设置",
        "source": "来源",
        "target": "目标",
        "choose": "选择",
        "clear": "清空",
        "include": "同步内容",
        "exclude": "排除内容",
        "keep": "保留内容",
        "delay": "触发延迟",
        "seconds": "秒",
        "options": "同步选项",
        "clean_extra": "清理目标多余文件",
        "startup": "开机启动并启用同步",
        "keep_hint": "保留内容会保留，并且不会覆盖",
        "include_rule_hint": "控制来源文件夹中哪些文件/文件夹会上传或同步。\n留空表示同步全部。\n点击编辑会直接覆盖。",
        "exclude_rule_hint": "控制来源文件夹中哪些文件/文件夹不上传或同步。\n优先级高于同步内容。\n点击编辑会直接覆盖。",
        "keep_rule_hint": "控制目标文件夹中哪些文件/文件夹必须保留。\n这些内容不会删除，也不会被覆盖。\n点击编辑会直接覆盖。",
        "start": "启动同步",
        "pause": "暂停同步",
        "resume": "继续同步",
        "save": "保存配置",
        "sync_now": "立即同步",
        "merge_now": "立即合并",
        "sync_once": "立即同步一次",
        "show_window": "显示窗口",
        "open_log": "打开日志",
        "exit": "退出",
        "author": "作者：浮生",
        "email": "邮箱：wzxmer@outlook.com",
        "select_file": "选择文件",
        "select_folder": "选择文件夹",
        "saved": "已保存配置",
        "scheduled_tasks": "定时任务",
        "auto_merge_zzc": "自动合并自造词",
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
        "target_dict_hint": "路径相对 iCloud 方案目录；留空默认写入主码表。",
    },
    "en": {
        "language": "Language",
        "status": "Status",
        "settings": "Sync Settings",
        "source": "Source",
        "target": "Target",
        "choose": "Choose",
        "clear": "Clear",
        "include": "Sync Content",
        "exclude": "Exclude",
        "keep": "Keep Content",
        "delay": "Trigger Delay",
        "seconds": "sec",
        "options": "Options",
        "clean_extra": "Clean extra target files",
        "startup": "Start with system and sync",
        "keep_hint": "Kept content will not be deleted or overwritten",
        "include_rule_hint": "Controls which files/folders in the source folder are uploaded or synced.\nEmpty means sync all.\nEditing overwrites directly.",
        "exclude_rule_hint": "Controls which files/folders in the source folder are not uploaded or synced.\nTakes priority over sync content.\nEditing overwrites directly.",
        "keep_rule_hint": "Controls which files/folders in the target folder must be kept.\nThey are not deleted or overwritten.\nEditing overwrites directly.",
        "start": "Start Sync",
        "pause": "Pause Sync",
        "resume": "Resume Sync",
        "save": "Save",
        "sync_now": "Sync Now",
        "merge_now": "Merge Now",
        "sync_once": "Sync once now",
        "show_window": "Show window",
        "open_log": "Open Log",
        "exit": "Exit",
        "author": "Author: Fusheng",
        "email": "Email: wzxmer@outlook.com",
        "select_file": "Select files",
        "select_folder": "Select folder",
        "saved": "Saved",
        "scheduled_tasks": "Scheduled Tasks",
        "auto_merge_zzc": "Auto merge zzc",
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
        "target_dict_hint": "Paths relative to iCloud scheme folder. Empty means main dict.",
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
    "合并完成": "Merge Complete",
    "监听或同步失败": "Sync Failed",
    "已保存配置": "Saved",
}


class SourceChangeHandler(FileSystemEventHandler):
    def __init__(self, callback) -> None:
        super().__init__()
        self.callback = callback

    def on_any_event(self, event: FileSystemEvent) -> None:
        if event.is_directory and event.event_type == "opened":
            return
        self.callback()


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

    def acquire(self) -> bool:
        if sys.platform.startswith("win"):
            return self.acquire_windows_mutex()
        return self.acquire_lock_file()

    def acquire_windows_mutex(self) -> bool:
        try:
            import ctypes
            from ctypes import wintypes
        except Exception:
            return True

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        create_mutex = kernel32.CreateMutexW
        create_mutex.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
        create_mutex.restype = wintypes.HANDLE

        self.handle = create_mutex(None, True, SINGLE_INSTANCE_MUTEX)
        if not self.handle:
            return True
        return ctypes.get_last_error() != 183

    def acquire_lock_file(self) -> bool:
        try:
            BASE_DIR.mkdir(parents=True, exist_ok=True)
            lock_path = BASE_DIR / "app.lock"
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            self.lock_file = fd
            os.write(fd, str(os.getpid()).encode("ascii"))
            return True
        except FileExistsError:
            return False
        except OSError:
            return True

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
                os.close(self.lock_file)
                (BASE_DIR / "app.lock").unlink(missing_ok=True)
            except OSError:
                pass
            self.lock_file = None


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
        self.startup_delay_var: tk.StringVar | None = None
        self.deploy_command_var: tk.StringVar | None = None
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
        self.zzc_target_dicts_text: tk.Text | None = None
        self.rule_placeholder_keys: dict[tk.Text, str] = {}
        self.rule_placeholder_active: set[tk.Text] = set()
        self.loading_form = False
        self.pause_button: RoundedButton | None = None
        self.observer: Observer | None = None
        self.observed_source: Path | None = None
        self.last_zzc_merge_at = 0.0
        self.startup_sync_started_at = 0.0
        self.startup_merge_done = False
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
            pystray.MenuItem(lambda _: self.t("open_log"), self.open_log),
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
        self.root.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")
        self.root.minsize(820, 760)
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
        self.make_button(button_row, "open_log", self.open_log).pack(
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
        self.delete_extra_var = tk.BooleanVar(value=True)
        self.startup_var = tk.BooleanVar(value=is_startup_enabled())
        self.auto_merge_zzc_var = tk.BooleanVar(value=False)
        self.startup_auto_merge_var = tk.BooleanVar(value=False)
        self.auto_deploy_after_merge_var = tk.BooleanVar(value=False)

        tabs_host = tk.Frame(parent, bg=BG_COLOR)
        tabs_host.pack(fill="x", expand=False, pady=(14, 0))
        tab_bar = tk.Frame(tabs_host, bg=BG_COLOR)
        tab_bar.pack(fill="x", pady=(0, 8))
        tab_body = tk.Frame(tabs_host, bg=CARD_COLOR, highlightthickness=1, highlightbackground=BORDER_COLOR)
        tab_body.pack(fill="x", expand=False)

        sync_tab = self.create_tab(tab_body)
        rules_tab = self.create_tab(tab_body)
        merge_tab = self.create_tab(tab_body)
        self.create_segmented_tabs(
            tab_bar,
            [
                ("同步目录", sync_tab),
                ("同步规则", rules_tab),
                ("自造词合并", merge_tab),
            ],
        )

        sync_tab.columnconfigure(0, minsize=86)
        sync_tab.columnconfigure(1, weight=1)
        sync_tab.columnconfigure(2, minsize=64)

        settings_label = self.section_title(sync_tab, "settings")
        settings_label.grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 16))

        self.make_label(sync_tab, "source").grid(row=1, column=0, sticky="w", pady=8)
        self.source_entry = self.make_path_entry(sync_tab, self.source_var)
        self.source_entry.grid(
            row=1, column=1, sticky="ew", padx=(10, 10), pady=8
        )
        self.make_button(sync_tab, "choose", self.choose_source, min_width=60).grid(
            row=1, column=2, pady=8
        )

        self.make_label(sync_tab, "target").grid(row=2, column=0, sticky="w", pady=8)
        self.target_entry = self.make_path_entry(sync_tab, self.target_var)
        self.target_entry.grid(
            row=2, column=1, sticky="ew", padx=(10, 10), pady=8
        )
        self.make_button(sync_tab, "choose", self.choose_target, min_width=60).grid(
            row=2, column=2, pady=8
        )

        self.make_label(sync_tab, "delay").grid(row=3, column=0, sticky="w", pady=(16, 6))
        tk.Spinbox(
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
        ).grid(row=3, column=1, sticky="w", padx=(10, 0), pady=(16, 6))
        self.make_hint(sync_tab, "seconds").grid(row=3, column=1, sticky="w", padx=(82, 0), pady=(16, 6))

        self.make_label(sync_tab, "options").grid(row=4, column=0, sticky="w", pady=(14, 0))
        option_row = tk.Frame(sync_tab, bg=CARD_COLOR)
        option_row.grid(row=4, column=1, columnspan=2, sticky="w", padx=(10, 0), pady=(14, 0))
        clean_check = tk.Checkbutton(
            option_row,
            text=self.t("clean_extra"),
            variable=self.delete_extra_var,
            bg=CARD_COLOR,
            fg=TEXT_COLOR,
            activebackground=CARD_COLOR,
            font=(UI_FONT, 10),
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
        )
        startup_check.pack(side="left", padx=(22, 0))
        self.register_i18n(startup_check, "startup")
        self.make_hint(sync_tab, "keep_hint").grid(
            row=5,
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
        )
        auto_merge_check.grid(row=1, column=0, columnspan=3, sticky="w", pady=(0, 8))
        self.register_i18n(auto_merge_check, "auto_merge_zzc")

        self.make_label(merge_tab, "zzc_target_dicts").grid(row=2, column=0, sticky="nw", pady=4)
        target_box = tk.Frame(merge_tab, bg=CARD_COLOR)
        target_box.grid(row=2, column=1, sticky="ew", padx=(10, 10), pady=4)
        self.zzc_target_dicts_text = self.create_rule_text(target_box, height=1)
        self.pack_rule_text(target_box, self.zzc_target_dicts_text, pady=(0, 6))
        target_buttons = tk.Frame(target_box, bg=CARD_COLOR)
        target_buttons.pack(anchor="w")
        self.make_button(target_buttons, "choose", self.add_zzc_target_dicts, min_width=76).pack(side="left")
        self.make_button(target_buttons, "clear", self.clear_zzc_target_dicts, min_width=62).pack(side="left", padx=(6, 0))

        self.make_label(merge_tab, "merge_interval").grid(row=3, column=0, sticky="w", pady=(8, 3))
        interval_row = tk.Frame(merge_tab, bg=CARD_COLOR)
        interval_row.grid(row=3, column=1, sticky="w", padx=(10, 0), pady=(8, 3))
        tk.Spinbox(
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
        ).pack(side="left")
        unit_select = ttk.Combobox(
            interval_row,
            textvariable=self.zzc_merge_unit_var,
            values=("分钟", "小时", "天"),
            state="readonly",
            width=6,
            font=(UI_FONT, 10),
        )
        unit_select.pack(side="left", padx=(8, 0))

        self.make_label(merge_tab, "startup_delay").grid(row=3, column=1, sticky="w", padx=(210, 0), pady=(8, 3))
        tk.Spinbox(
            merge_tab,
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
        ).grid(row=3, column=1, sticky="w", padx=(300, 0), pady=(8, 3))
        self.make_hint(merge_tab, "minutes").grid(row=3, column=1, sticky="w", padx=(372, 0), pady=(8, 3))

        checkbox_row = tk.Frame(merge_tab, bg=CARD_COLOR)
        checkbox_row.grid(row=4, column=0, columnspan=3, sticky="w", pady=(8, 0))
        startup_merge_check = tk.Checkbutton(
            checkbox_row,
            text=self.t("startup_auto_merge"),
            variable=self.startup_auto_merge_var,
            bg=CARD_COLOR,
            fg=TEXT_COLOR,
            activebackground=CARD_COLOR,
            font=(UI_FONT, 10),
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
        )
        deploy_check.pack(side="left", padx=(24, 0))
        self.register_i18n(deploy_check, "auto_deploy_after_merge")
        self.make_label(merge_tab, "deploy_command").grid(row=5, column=0, sticky="w", pady=(8, 3))
        self.deploy_command_entry = self.make_entry(
            merge_tab,
            self.deploy_command_var,
            placeholder_key="deploy_command_hint",
        )
        self.deploy_command_entry.grid(row=5, column=1, columnspan=2, sticky="ew", padx=(10, 0), pady=(8, 3))

        rules_tab.columnconfigure(0, weight=1)
        rules_tab.columnconfigure(1, weight=1)
        self.section_title(rules_tab, "include").grid(row=0, column=0, sticky="w")
        include_panel = tk.Frame(rules_tab, bg=CARD_COLOR)
        include_panel.grid(row=1, column=0, sticky="nsew", padx=(0, 8), pady=(8, 0))
        self.include_text = self.create_rule_text(include_panel, height=8, placeholder_key="include_rule_hint")
        self.pack_rule_text(include_panel, self.include_text, pady=(0, 6))
        include_buttons = tk.Frame(include_panel, bg=CARD_COLOR)
        include_buttons.pack(anchor="w")
        self.make_button(include_buttons, "choose", self.add_include_items, min_width=76).pack(side="left")
        self.make_button(include_buttons, "clear", self.clear_include, min_width=62).pack(side="left", padx=(6, 0))

        self.section_title(rules_tab, "exclude").grid(row=2, column=0, sticky="w", pady=(14, 0))
        exclude_panel = tk.Frame(rules_tab, bg=CARD_COLOR)
        exclude_panel.grid(row=3, column=0, sticky="nsew", padx=(0, 8), pady=(8, 0))
        self.exclude_text = self.create_rule_text(exclude_panel, height=8, placeholder_key="exclude_rule_hint")
        self.pack_rule_text(exclude_panel, self.exclude_text, pady=(0, 6))
        exclude_buttons = tk.Frame(exclude_panel, bg=CARD_COLOR)
        exclude_buttons.pack(anchor="w")
        self.make_button(exclude_buttons, "choose", self.add_exclude_items, min_width=76).pack(side="left")
        self.make_button(exclude_buttons, "clear", self.clear_exclude, min_width=62).pack(side="left", padx=(6, 0))

        self.section_title(rules_tab, "keep").grid(row=0, column=1, sticky="w", padx=(8, 0))
        protect_panel = tk.Frame(rules_tab, bg=CARD_COLOR)
        protect_panel.grid(row=1, column=1, rowspan=3, sticky="nsew", padx=(8, 0), pady=(8, 0))
        self.target_protect_text = self.create_rule_text(protect_panel, height=19, placeholder_key="keep_rule_hint")
        self.pack_rule_text(protect_panel, self.target_protect_text, pady=(0, 6))
        protect_buttons = tk.Frame(protect_panel, bg=CARD_COLOR)
        protect_buttons.pack(anchor="w")
        self.make_button(protect_buttons, "choose", self.add_target_protected_items, min_width=76).pack(side="left")
        self.make_button(protect_buttons, "clear", self.clear_target_protect, min_width=62).pack(side="left", padx=(6, 0))

    def create_segmented_tabs(self, parent: tk.Misc, tabs: list[tuple[str, tk.Frame]]) -> None:
        buttons: list[tk.Label] = []

        def select(index: int) -> None:
            for _, frame in tabs:
                frame.pack_forget()
            tabs[index][1].pack(fill="x", expand=False)
            for idx, button in enumerate(buttons):
                active = idx == index
                button.configure(
                    bg=PRIMARY_COLOR if active else "#e5ecf2",
                    fg="#ffffff" if active else TEXT_COLOR,
                    relief="flat",
                )

        for index, (label, _) in enumerate(tabs):
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
            button.pack(side="left", padx=(0 if index == 0 else 8, 0))
            button.bind("<Button-1>", lambda _event, idx=index: select(idx))
            buttons.append(button)
        select(0)

    def create_tab(self, parent: tk.Misc) -> tk.Frame:
        frame = tk.Frame(parent, bg=CARD_COLOR, padx=20, pady=18)
        return frame

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

    def clear_exclude(self) -> None:
        self.clear_text_box(self.exclude_text)

    def clear_target_protect(self) -> None:
        self.clear_text_box(self.target_protect_text)

    def add_zzc_target_dicts(self) -> None:
        self.show_select_menu(self.zzc_target_dicts_text, self.get_source_path)

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
            self.set_text_var(self.source_var, "" if is_empty_path(config.source) else config.source.as_posix())
            self.set_text_var(self.target_var, "" if is_empty_path(config.target) else config.target.as_posix())
            self.show_path_entries_end()
            self.set_text_var(self.interval_var, f"{config.interval_seconds:g}")
            interval_value, interval_unit = self.display_merge_interval(config.scheduled_tasks.zzc_merge_interval_minutes)
            self.set_text_var(self.zzc_merge_interval_var, f"{interval_value:g}")
            self.set_text_var(self.zzc_merge_unit_var, interval_unit)
            self.set_text_var(self.startup_delay_var, f"{config.scheduled_tasks.startup_delay_minutes:g}")
            self.clear_entry_placeholder(self.deploy_command_entry)
            self.set_text_var(self.deploy_command_var, config.scheduled_tasks.deploy_command)
            self.restore_entry_placeholder(self.deploy_command_entry)
            if self.delete_extra_var is not None:
                self.delete_extra_var.set(config.delete_extra)
            if self.auto_merge_zzc_var is not None:
                self.auto_merge_zzc_var.set(config.scheduled_tasks.auto_merge_zzc)
            if self.startup_auto_merge_var is not None:
                self.startup_auto_merge_var.set(config.scheduled_tasks.startup_auto_merge)
            if self.auto_deploy_after_merge_var is not None:
                self.auto_deploy_after_merge_var.set(config.scheduled_tasks.auto_deploy_after_merge)
            self.set_text_box(self.include_text, config.include)
            self.set_text_box(self.exclude_text, config.exclude)
            self.set_text_box(self.target_protect_text, config.target_protect)
            self.set_text_box(self.zzc_target_dicts_text, config.scheduled_tasks.zzc_target_dicts)
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
            interval_seconds=0,
            delete_extra=config.delete_extra,
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
            return minutes / (24 * 60), "天"
        if minutes > 0 and minutes % 60 == 0:
            return minutes / 60, "小时"
        return minutes, "分钟"

    def merge_interval_to_minutes(self, value: float, unit: str) -> float:
        if unit == "天":
            return value * 24 * 60
        if unit == "小时":
            return value * 60
        return value

    def save_form_config(self) -> None:
        try:
            config = self.config_from_form()
            save_config(CONFIG_PATH, config)
            self.apply_startup_setting()
            self.log("已从窗口保存配置")
            self.flash_status("已保存配置", 2000)
            self.wake_event.set()
        except Exception as exc:
            self.log(f"[error] 保存配置失败: {exc}")
            messagebox.showerror(APP_NAME, f"保存配置失败：{exc}")

    def save_form_config_silent(self) -> None:
        try:
            config = self.config_from_form()
            save_config(CONFIG_PATH, config)
            self.apply_startup_setting()
            self.log("已自动保存配置")
            self.wake_event.set()
        except BaseException as exc:
            self.log(f"[error] 自动保存配置失败: {exc}")

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
                self.zzc_merge_interval_var,
                self.zzc_merge_unit_var,
                self.startup_delay_var,
                self.deploy_command_var,
                self.delete_extra_var,
                self.startup_var,
                self.auto_merge_zzc_var,
                self.startup_auto_merge_var,
                self.auto_deploy_after_merge_var,
                self.include_text,
                self.exclude_text,
                self.target_protect_text,
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
        zzc_target_dicts = tuple(read_patterns(self.zzc_target_dicts_text))
        interval_seconds = float(self.interval_var.get().strip())
        zzc_merge_interval_minutes = self.merge_interval_to_minutes(
            float(self.zzc_merge_interval_var.get().strip()),
            self.zzc_merge_unit_var.get().strip(),
        )
        startup_delay_minutes = float(self.startup_delay_var.get().strip())
        if interval_seconds < 0:
            raise ValueError("触发延迟不能小于 0 秒。")
        if zzc_merge_interval_minutes < 0:
            raise ValueError("自造词合并间隔不能小于 0 分钟。")
        if startup_delay_minutes < 0:
            raise ValueError("开机合并等待时间不能小于 0 分钟。")
        return SyncConfig(
            source=source.resolve() if source_text else source,
            target=target.resolve() if target_text else target,
            include=include,
            exclude=exclude,
            target_protect=target_protect,
            interval_seconds=interval_seconds,
            delete_extra=bool(self.delete_extra_var.get()),
            scheduled_tasks=ScheduledTasksConfig(
                auto_merge_zzc=bool(self.auto_merge_zzc_var.get()),
                zzc_target_dicts=zzc_target_dicts,
                zzc_merge_interval_minutes=zzc_merge_interval_minutes,
                startup_auto_merge=bool(self.startup_auto_merge_var.get()),
                startup_delay_minutes=startup_delay_minutes,
                auto_deploy_after_merge=bool(self.auto_deploy_after_merge_var.get()),
                deploy_command="" if self.deploy_command_entry in self.entry_placeholder_active else self.deploy_command_var.get().strip(),
            ),
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
        self.startup_merge_done = False
        self.change_event.clear()
        self.log("开机启动并启用同步")
        self.set_status("启动中")
        self.update_sync_button()
        self.wake_event.set()
        self.icon.update_menu()

    def notify_source_changed(self) -> None:
        self.change_event.set()
        self.wake_event.set()

    def stop_observer(self) -> None:
        observer = self.observer
        self.observer = None
        self.observed_source = None
        if observer:
            observer.stop()
            observer.join(timeout=2)

    def ensure_observer(self, source: Path) -> None:
        source = source.resolve()
        if self.observer and self.observed_source == source:
            return
        self.stop_observer()
        observer = Observer()
        observer.schedule(
            SourceChangeHandler(self.notify_source_changed),
            str(source),
            recursive=True,
        )
        observer.start()
        self.observer = observer
        self.observed_source = source
        self.log(f"开始监听来源: {source}")

    def run_sync_from_config(self, config: SyncConfig) -> None:
        config.target.mkdir(parents=True, exist_ok=True)
        self.set_status("正在同步")
        with self.operation_lock:
            stats = sync_once(self.sync_config_with_zzc_protected(config), logger=self.log)
        if stats.has_changes():
            self.log(
                f"同步完成 copied={stats.copied} "
                f"deleted={stats.deleted} errors={stats.errors}"
            )
        self.set_status("同步完成")
        if self.root:
                self.root.after(1500, lambda: self.set_status("监听中") if self.started and not self.paused else None)

    def sync_config_with_zzc_protected(self, config: SyncConfig) -> SyncConfig:
        protects = list(config.target_protect)
        for pattern in ("*.zzc.dict.yaml",):
            if pattern not in protects:
                protects.append(pattern)
        return SyncConfig(
            source=config.source,
            target=config.target,
            include=config.include,
            exclude=config.exclude,
            target_protect=tuple(protects),
            interval_seconds=config.interval_seconds,
            delete_extra=config.delete_extra,
            scheduled_tasks=config.scheduled_tasks,
        )

    def zzc_files_stable(self, config: SyncConfig) -> bool:
        scheme = find_scheme(config.source)
        target_scheme = find_scheme(config.target)
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

    def run_zzc_merge_from_config(self, config: SyncConfig, manual: bool = False) -> bool:
        ensure_safe_config(config)
        self.set_status("正在合并")
        with self.operation_lock:
            if not manual and not self.zzc_files_stable(config):
                self.log("[zzc] 文件仍在变化，跳过本次自动合并")
                self.set_status("监听中" if self.started and not self.paused else self.base_status)
                return False
            reconcile_ops_between_roots(config.source, config.target, logger=self.log)
            changed = merge_root(
                config.source,
                target_dicts=config.scheduled_tasks.zzc_target_dicts,
                logger=self.log,
            )
            if changed:
                copy_managed_files(
                    config.source,
                    config.target,
                    target_dicts=config.scheduled_tasks.zzc_target_dicts,
                    logger=self.log,
                )
                self.last_zzc_merge_at = time.monotonic()
                if config.scheduled_tasks.auto_deploy_after_merge:
                    self.run_deploy(config)
                self.set_status("合并完成")
                return True
            source_scheme = find_scheme(config.source)
            target_scheme = find_scheme(config.target)
            if source_scheme and target_scheme:
                clear_ops(target_scheme)
                copy_managed_files(
                    config.source,
                    config.target,
                    target_dicts=config.scheduled_tasks.zzc_target_dicts,
                    logger=self.log,
                )
            self.set_status("合并完成")
            return False

    def scheduled_task_loop(self) -> None:
        while not self.stop_event.is_set():
            self.stop_event.wait(30)
            if self.stop_event.is_set() or not self.started or self.paused:
                continue
            try:
                config = load_config(CONFIG_PATH)
                tasks = config.scheduled_tasks
                if not tasks.auto_merge_zzc:
                    continue
                now = time.monotonic()
                startup_due = (
                    tasks.startup_auto_merge
                    and not self.startup_merge_done
                    and self.startup_sync_started_at > 0
                    and now - self.startup_sync_started_at >= tasks.startup_delay_minutes * 60
                )
                interval_due = (
                    self.last_zzc_merge_at <= 0
                    or now - self.last_zzc_merge_at >= tasks.zzc_merge_interval_minutes * 60
                )
                if not startup_due and not interval_due:
                    continue
                merged = self.run_zzc_merge_from_config(config, manual=False)
                if startup_due:
                    self.startup_merge_done = True
                if merged:
                    self.log("[zzc] 定时合并完成")
            except BaseException as exc:
                self.log(f"[error] 定时合并失败: {exc}")
                self.log(traceback.format_exc())
                self.set_status("监听或同步失败")

    def run_deploy(self, config: SyncConfig) -> None:
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
        if not command:
            self.log("[zzc] 未找到部署程序，跳过自动重新部署")
            return
        result = subprocess.run(command, shell=True, cwd=str(config.target), capture_output=True, text=True, timeout=120)
        if result.returncode == 0:
            self.log("[zzc] 已自动重新部署")
            return
        self.log(f"[error] 自动重新部署失败 code={result.returncode} stdout={result.stdout} stderr={result.stderr}")

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
                self.ensure_observer(config.source)
                if self.initial_sync_pending:
                    self.initial_sync_pending = False
                    self.change_event.clear()
                    self.run_sync_from_config(config)
                    continue
                self.set_status("监听中")
                if not self.wait_until_change():
                    continue
                self.set_status("检测到变动")
                self.change_event.clear()
                if not self.wait_delay_or_more_changes(config.interval_seconds):
                    continue
                config = load_config(CONFIG_PATH)
                ensure_safe_config(config)
                self.ensure_observer(config.source)
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
            self.startup_merge_done = False
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
                stats = sync_once(self.sync_config_with_zzc_protected(config), logger=self.log)
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
            self.log(f"[error] 手动合并失败: {exc}")
            self.log(traceback.format_exc())
            messagebox.showerror(APP_NAME, f"手动合并失败：{exc}")

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


def is_startup_enabled() -> bool:
    if sys.platform == "darwin":
        return macos_startup_plist_path().exists()
    if winreg is None:
        return False
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_READ,
        ) as key:
            value, _ = winreg.QueryValueEx(key, STARTUP_VALUE_NAME)
    except FileNotFoundError:
        return False
    except OSError:
        return False
    return str(value).strip() == startup_command()


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
