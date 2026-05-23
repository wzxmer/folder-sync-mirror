#!/usr/bin/env python3
"""Desktop tray app for Folder Sync Mirror."""

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
    SyncConfig,
    create_default_config,
    ensure_safe_config,
    is_empty_path,
    load_config,
    save_config,
    sync_once,
)
from version import __version__

if sys.platform.startswith("win"):
    import winreg
else:
    winreg = None


APP_NAME = "Folder Sync Mirror"
STARTUP_VALUE_NAME = "FolderSyncMirror"
MACOS_LAUNCH_AGENT_ID = "com.fusheng.foldersyncmirror"
WINDOW_WIDTH = 820
WINDOW_HEIGHT = 860
BG_COLOR = "#edf2f7"
CARD_COLOR = "#ffffff"
TEXT_COLOR = "#1f2a37"
MUTED_COLOR = "#667085"
PRIMARY_COLOR = "#2563eb"
PRIMARY_HOVER = "#1d4ed8"
BORDER_COLOR = "#d8dee8"
BUTTON_BG = "#eef3f8"
BUTTON_HOVER = "#dde7f2"
BUTTON_ACTIVE = "#cbd8e6"
UI_FONT = "Microsoft YaHei UI"
MONO_FONT = "Consolas"
LOG_MAX_BYTES = 1024 * 1024
LOG_MAX_LINES = 1000
LOG_CLEAN_INTERVAL_SECONDS = 24 * 60 * 60


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
    ) -> None:
        self.text = text
        self.min_width = min_width
        self.pill_height = height
        self.radius = radius
        self.font = tkfont.Font(family=UI_FONT, size=10, weight="bold")
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
        return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "folder-sync-mirror"
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


BASE_DIR = app_dir()
CONFIG_PATH = BASE_DIR / "config.json"
LOG_PATH = BASE_DIR / "sync.log"


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
        self.root: tk.Tk | None = None
        self.status_var: tk.StringVar | None = None
        self.status_label: StatusPill | None = None
        self.source_var: tk.StringVar | None = None
        self.target_var: tk.StringVar | None = None
        self.interval_var: tk.StringVar | None = None
        self.delete_extra_var: tk.BooleanVar | None = None
        self.startup_var: tk.BooleanVar | None = None
        self.include_text: tk.Text | None = None
        self.exclude_text: tk.Text | None = None
        self.target_protect_text: tk.Text | None = None
        self.pause_button: RoundedButton | None = None
        self.observer: Observer | None = None
        self.observed_source: Path | None = None
        self.worker = threading.Thread(target=self.worker_loop, daemon=True)
        self.icon = pystray.Icon(
            APP_NAME,
            self.make_icon(),
            APP_NAME,
            self.build_menu(),
        )

    def build_menu(self) -> pystray.Menu:
        return pystray.Menu(
            pystray.MenuItem(lambda _: f"状态: {self.status}", None, enabled=False),
            pystray.MenuItem(
                lambda _: self.sync_control_text(),
                self.toggle_sync,
            ),
            pystray.MenuItem("立即同步一次", self.sync_now),
            pystray.MenuItem("显示窗口", self.show_window, default=True),
            pystray.MenuItem("打开日志", self.open_log),
            pystray.MenuItem("退出", self.quit),
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
            self.root.after(0, self.status_var.set, status)
            if self.status_label:
                self.root.after(0, self.status_label.configure, {"text": status})
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
            return "启动同步"
        return "继续同步" if self.paused else "暂停同步"

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
        self.root.resizable(False, False)
        self.root.configure(bg=BG_COLOR)
        self.root.protocol("WM_DELETE_WINDOW", self.hide_window)
        self.configure_style()

        outer = tk.Frame(self.root, bg=BG_COLOR)
        outer.pack(fill="both", expand=True, padx=16, pady=16)

        header = tk.Frame(outer, bg=BG_COLOR)
        header.pack(fill="x")
        title_box = tk.Frame(header, bg=BG_COLOR)
        title_box.pack(side="left")
        tk.Label(
            title_box,
            text=f"{APP_NAME} {__version__}",
            bg=BG_COLOR,
            fg=TEXT_COLOR,
            font=(UI_FONT, 17, "bold"),
        ).pack(anchor="w")
        self.status_var = tk.StringVar(value=self.status)
        self.status_label = StatusPill(header, self.status)
        self.status_label.pack(side="right", anchor="n", pady=(4, 0))
        self.update_status_color(self.status)
        self.create_config_form(outer)

        button_panel = RoundedPanel(outer, radius=12, padx=12, pady=10)
        button_panel.pack(fill="x", pady=(8, 0))
        button_row = tk.Frame(button_panel.content, bg=CARD_COLOR)
        button_row.pack(fill="x")
        self.pause_button = self.make_button(
            button_row, "启动同步", self.toggle_sync, variant="success"
        )
        self.pause_button.pack(side="left")
        self.make_button(
            button_row, "保存配置", self.save_form_config, variant="primary"
        ).pack(side="left", padx=(8, 0))
        self.make_button(button_row, "立即同步", self.sync_now, variant="info").pack(
            side="left", padx=(8, 0)
        )
        self.make_button(button_row, "打开日志", self.open_log).pack(
            side="left", padx=(8, 0)
        )
        self.make_button(button_row, "退出", self.quit, variant="danger").pack(
            side="left", padx=(8, 0)
        )

        author_box = tk.Frame(button_row, bg=CARD_COLOR)
        author_box.pack(side="right", padx=(8, 0))
        tk.Label(
            author_box,
            text="作者：浮生",
            bg=CARD_COLOR,
            fg="#475467",
            font=(UI_FONT, 8),
        ).pack(anchor="e")
        tk.Label(
            author_box,
            text="邮箱：wzxmer@outlook.com",
            bg=CARD_COLOR,
            fg="#475467",
            font=(UI_FONT, 8),
        ).pack(anchor="e")
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

    def make_button(
        self,
        parent: tk.Misc,
        text: str,
        command,
        variant: str = "secondary",
        min_width: int = 72,
    ) -> RoundedButton:
        return RoundedButton(parent, text, command, variant=variant, min_width=min_width)

    def create_config_form(self, parent: tk.Misc) -> None:
        panel = RoundedPanel(parent, radius=14, padx=18, pady=16)
        panel.pack(fill="x", pady=(20, 0))
        form = panel.content
        form.columnconfigure(0, minsize=78)
        form.columnconfigure(1, weight=1)
        form.columnconfigure(2, minsize=64)

        tk.Label(
            form,
            text="同步设置",
            bg=CARD_COLOR,
            fg=TEXT_COLOR,
            font=(UI_FONT, 11, "bold"),
        ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 14))

        self.source_var = tk.StringVar()
        self.target_var = tk.StringVar()
        self.interval_var = tk.StringVar(value="0")
        self.delete_extra_var = tk.BooleanVar(value=True)
        self.startup_var = tk.BooleanVar(value=is_startup_enabled())

        self.make_label(form, "来源").grid(row=1, column=0, sticky="w", pady=5)
        self.make_entry(form, self.source_var).grid(
            row=1, column=1, sticky="ew", padx=(10, 10), pady=5
        )
        self.make_button(form, "选择", self.choose_source, min_width=60).grid(
            row=1, column=2, pady=5
        )

        self.make_label(form, "目标").grid(row=2, column=0, sticky="w", pady=5)
        self.make_entry(form, self.target_var).grid(
            row=2, column=1, sticky="ew", padx=(10, 10), pady=5
        )
        self.make_button(form, "选择", self.choose_target, min_width=60).grid(
            row=2, column=2, pady=5
        )

        rules = tk.Frame(form, bg=CARD_COLOR)
        rules.grid(row=3, column=0, columnspan=3, sticky="nsew", pady=(16, 0))
        rules.columnconfigure(0, weight=1)
        rules.columnconfigure(1, weight=1)

        source_rules = tk.Frame(rules, bg=CARD_COLOR)
        source_rules.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        source_rules.columnconfigure(0, weight=1)
        self.make_label(source_rules, "同步内容").grid(
            row=0, column=0, sticky="w"
        )

        include_panel = tk.Frame(source_rules, bg=CARD_COLOR)
        include_panel.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        self.include_text = self.create_rule_text(include_panel, height=5)
        self.pack_rule_text(include_panel, self.include_text, pady=(0, 6))
        include_buttons = tk.Frame(include_panel, bg=CARD_COLOR)
        include_buttons.pack(anchor="w")
        self.make_button(
            include_buttons,
            "选择",
            self.add_include_items,
            min_width=76,
        ).pack(side="left")
        self.make_button(
            include_buttons,
            "清空",
            self.clear_include,
            min_width=62,
        ).pack(side="left", padx=(6, 0))

        source_exclude_panel = tk.Frame(source_rules, bg=CARD_COLOR)
        source_exclude_panel.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        self.make_label(source_exclude_panel, "排除内容").pack(anchor="w", pady=(0, 8))
        self.exclude_text = self.create_rule_text(source_exclude_panel, height=5)
        self.pack_rule_text(source_exclude_panel, self.exclude_text, pady=(0, 6))
        source_exclude_buttons = tk.Frame(source_exclude_panel, bg=CARD_COLOR)
        source_exclude_buttons.pack(anchor="w")
        self.make_button(
            source_exclude_buttons,
            "选择",
            self.add_exclude_items,
            min_width=76,
        ).pack(side="left")
        self.make_button(
            source_exclude_buttons,
            "清空",
            self.clear_exclude,
            min_width=62,
        ).pack(side="left", padx=(6, 0))

        protect_panel = tk.Frame(rules, bg=CARD_COLOR)
        protect_panel.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        self.make_label(protect_panel, "保留内容").pack(anchor="w")
        self.target_protect_text = self.create_rule_text(protect_panel, height=13)
        self.pack_rule_text(protect_panel, self.target_protect_text, pady=(8, 6))
        protect_buttons = tk.Frame(protect_panel, bg=CARD_COLOR)
        protect_buttons.pack(anchor="w")
        self.make_button(
            protect_buttons,
            "选择",
            self.add_target_protected_items,
            min_width=76,
        ).pack(side="left")
        self.make_button(
            protect_buttons,
            "清空",
            self.clear_target_protect,
            min_width=62,
        ).pack(side="left", padx=(6, 0))

        self.make_label(form, "触发延迟").grid(row=4, column=0, sticky="w", pady=(14, 3))
        tk.Spinbox(
            form,
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
        ).grid(row=4, column=1, sticky="w", padx=(10, 0), pady=(14, 3))
        self.make_hint(form, "秒").grid(row=4, column=1, sticky="w", padx=(82, 0), pady=(14, 3))

        self.make_label(form, "同步选项").grid(row=5, column=0, sticky="w", pady=(12, 0))
        option_row = tk.Frame(form, bg=CARD_COLOR)
        option_row.grid(row=5, column=1, columnspan=2, sticky="w", padx=(10, 0), pady=(12, 0))
        tk.Checkbutton(
            option_row,
            text="清理目标多余文件",
            variable=self.delete_extra_var,
            bg=CARD_COLOR,
            fg=TEXT_COLOR,
            activebackground=CARD_COLOR,
            font=(UI_FONT, 10),
        ).pack(side="left")
        tk.Checkbutton(
            option_row,
            text="开机启动并启用同步",
            variable=self.startup_var,
            bg=CARD_COLOR,
            fg=TEXT_COLOR,
            activebackground=CARD_COLOR,
            font=(UI_FONT, 10),
        ).pack(side="left", padx=(22, 0))
        self.make_hint(form, "保留内容会保留，并且不会覆盖").grid(
            row=6,
            column=1,
            columnspan=2,
            sticky="w",
            padx=(10, 0),
            pady=(2, 0),
        )

    def make_label(self, parent: tk.Misc, text: str) -> tk.Label:
        return tk.Label(
            parent,
            text=text,
            bg=CARD_COLOR,
            fg=TEXT_COLOR,
            font=(UI_FONT, 10, "bold"),
        )

    def make_hint(self, parent: tk.Misc, text: str) -> tk.Label:
        return tk.Label(
            parent,
            text=text,
            bg=CARD_COLOR,
            fg="#475467",
            font=(UI_FONT, 9),
        )

    def make_entry(self, parent: tk.Misc, variable: tk.StringVar) -> tk.Entry:
        return tk.Entry(
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

    def create_rule_text(self, parent: ttk.Frame, height: int) -> tk.Text:
        return scrolledtext.ScrolledText(
            parent,
            height=height,
            width=20,
            wrap="none",
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

    def pack_rule_text(
        self,
        parent: tk.Misc,
        text: tk.Text,
        pady: tuple[int, int] = (0, 0),
    ) -> None:
        text.pack(fill="both", expand=True, pady=pady)

    def choose_source(self) -> None:
        self.choose_folder(self.source_var)

    def choose_target(self) -> None:
        self.choose_folder(self.target_var)

    def choose_folder(self, variable: tk.StringVar | None) -> None:
        if variable is None:
            return
        folder = filedialog.askdirectory(initialdir=variable.get() or str(BASE_DIR))
        if folder:
            variable.set(folder.replace("\\", "/"))

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

    def show_select_menu(self, box: tk.Text | None, root_getter) -> None:
        if box is None:
            return
        menu = tk.Menu(self.root, tearoff=False)
        menu.add_command(
            label="选择文件",
            command=lambda: self.add_selected_files(box, root_getter),
        )
        menu.add_command(
            label="选择文件夹",
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
            box.delete("1.0", "end")
            self.root_update()

    def root_update(self) -> None:
        if self.root is None:
            return
        self.root.update_idletasks()

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
        self.log(f"已加载配置: {CONFIG_PATH}")
        self.set_text_var(self.source_var, "" if is_empty_path(config.source) else config.source.as_posix())
        self.set_text_var(self.target_var, "" if is_empty_path(config.target) else config.target.as_posix())
        self.set_text_var(self.interval_var, f"{config.interval_seconds:g}")
        if self.delete_extra_var is not None:
            self.delete_extra_var.set(config.delete_extra)
        self.set_text_box(self.include_text, config.include)
        self.set_text_box(self.exclude_text, config.exclude)
        self.set_text_box(self.target_protect_text, config.target_protect)

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

    def set_text_box(self, box: tk.Text | None, lines: tuple[str, ...]) -> None:
        if box is None:
            return
        box.delete("1.0", "end")
        box.insert("1.0", "\n".join(lines))
        box.see("1.0")
        box.update_idletasks()

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
                self.delete_extra_var,
                self.startup_var,
                self.include_text,
                self.exclude_text,
                self.target_protect_text,
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
        interval_seconds = float(self.interval_var.get().strip())
        if interval_seconds < 0:
            raise ValueError("触发延迟不能小于 0 秒。")
        return SyncConfig(
            source=source.resolve() if source_text else source,
            target=target.resolve() if target_text else target,
            include=include,
            exclude=exclude,
            target_protect=target_protect,
            interval_seconds=interval_seconds,
            delete_extra=bool(self.delete_extra_var.get()),
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
        stats = sync_once(config, logger=self.log)
        if stats.has_changes():
            self.log(
                f"同步完成 copied={stats.copied} "
                f"deleted={stats.deleted} errors={stats.errors}"
            )
        self.set_status("同步完成")
        if self.root:
            self.root.after(1500, lambda: self.set_status("监听中") if self.started and not self.paused else None)

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
            stats = sync_once(config, logger=self.log)
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
    MirrorTrayApp().run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
