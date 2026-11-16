"""پنجرهٔ اصلی رابط دسکتاپ STRUCTPIN (tkinter و ttk استاندارد).

این ماژول فقط لایهٔ رابط اصلی است:
    - فرم ورودی را از input_tabs.InputTabs نمایش می‌دهد.
    - ساخت مدل را از طریق InputTabs.build_model انجام می‌دهد.
    - هیچ محاسبهٔ مهندسی، تحلیل یا فراخوانی موتور FEM در این ماژول نیست.
    - تحلیل، ذخیره و بارگذاری در این مرحله فعال نیستند.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import Optional

from structpin.model.structural_model import StructuralModel
from structpin.ui.input_tabs import InputTabs, ModelBuildError

__all__ = ["MainWindow", "main"]


_APP_TITLE = "STRUCTPIN | تحلیل سازه"
_WINDOW_SIZE = "1280x800"
_MIN_SIZE = (960, 600)

_FONT_CANDIDATES = ("Tahoma", "Segoe UI")

_COLOR_BG = "#141B2D"
_COLOR_PANEL = "#1F2A44"
_COLOR_TITLEBAR = "#0E1526"
_COLOR_TEXT = "#E6E9EF"
_COLOR_MUTED = "#9AA4B8"
_COLOR_ACCENT = "#2F6DB5"
_COLOR_GOLD = "#C9A227"

_MSG_NEW_PROJECT_CONFIRM = (
    "اطلاعات فعلی فرم پاک می‌شود. آیا ادامه می‌دهید؟"
)
_MSG_PENDING = "این قابلیت در مرحلهٔ بعد فعال می‌شود."


def _pick_font_family(root: tk.Misc) -> str:
    """انتخاب اولین فونت موجود از میان گزینه‌ها؛ در صورت نبود، فونت پیش‌فرض Tk."""
    try:
        available = set(_font_families(root))
    except tk.TclError:
        return "TkDefaultFont"
    for name in _FONT_CANDIDATES:
        if name in available:
            return name
    return "TkDefaultFont"


def _font_families(root: tk.Misc) -> tuple[str, ...]:
    from tkinter import font as tkfont

    return tuple(tkfont.families(root))


class MainWindow(tk.Tk):
    """پنجرهٔ اصلی STRUCTPIN.

    ویژگی current_model آخرین مدل ساخته‌شده توسط «ساخت مدل» را نگه می‌دارد.
    توجه: InputTabs فعلی هیچ callback یا رویداد اختصاصی برای اطلاع‌رسانی
    تغییرات فرم ندارد. بنابراین current_model پس از ویرایش ورودی‌ها به‌صورت
    خودکار پاک نمی‌شود و ممکن است با اطلاعات فعلی فرم مطابقت نداشته باشد.
    کاربر باید پس از هر تغییر ورودی، دوباره «ساخت مدل» را اجرا کند.

    current_model فقط در موارد زیر مقدار می‌گیرد یا پاک می‌شود:
        - شروع «ساخت مدل»: ابتدا None می‌شود و تنها در صورت موفقیت مدل جدید ذخیره می‌شود.
        - «پروژه جدید» پس از تأیید کاربر: فرم پاک و current_model None می‌شود.
    """

    def __init__(self) -> None:
        super().__init__()
        self.current_model: Optional[StructuralModel] = None
        self._font_family = _pick_font_family(self)

        self.title(_APP_TITLE)
        self.geometry(_WINDOW_SIZE)
        self.minsize(*_MIN_SIZE)
        self.configure(background=_COLOR_BG)

        self._configure_styles()
        self._build_title_bar()
        self._build_toolbar()
        self._build_body()
        self._build_status_bar()
        self._set_status("آماده")

    # ------------------------------------------------------------------
    # ساخت رابط
    # ------------------------------------------------------------------

    def _configure_styles(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        font = (self._font_family, 10)
        style.configure("Main.TFrame", background=_COLOR_BG)
        style.configure("Title.TFrame", background=_COLOR_TITLEBAR)
        style.configure("Toolbar.TFrame", background=_COLOR_PANEL)
        style.configure("Status.TFrame", background=_COLOR_TITLEBAR)
        style.configure("Title.TLabel", background=_COLOR_TITLEBAR,
                        foreground=_COLOR_GOLD, font=(self._font_family, 12, "bold"))
        style.configure("Status.TLabel", background=_COLOR_TITLEBAR,
                        foreground=_COLOR_MUTED, font=font)
        style.configure("Toolbar.TButton", background=_COLOR_PANEL,
                        foreground=_COLOR_TEXT, padding=(12, 5), font=font)
        style.map("Toolbar.TButton",
                  background=[("active", _COLOR_ACCENT), ("disabled", _COLOR_PANEL)],
                  foreground=[("active", "#FFFFFF"), ("disabled", _COLOR_MUTED)])
        style.configure("Accent.Toolbar.TButton", background=_COLOR_ACCENT,
                        foreground="#FFFFFF", padding=(12, 5), font=font)
        style.map("Accent.Toolbar.TButton",
                  background=[("active", _COLOR_GOLD)],
                  foreground=[("active", "#141B2D")])

    def _build_title_bar(self) -> None:
        bar = ttk.Frame(self, style="Title.TFrame", padding=(14, 8))
        bar.pack(side=tk.TOP, fill=tk.X)
        ttk.Label(bar, text="STRUCTPIN", style="Title.TLabel").pack(side=tk.RIGHT)
        ttk.Label(bar, text="تحلیل سازه — قاب دوبعدی", style="Status.TLabel").pack(side=tk.LEFT)

    def _build_toolbar(self) -> None:
        bar = ttk.Frame(self, style="Toolbar.TFrame", padding=(10, 8))
        bar.pack(side=tk.TOP, fill=tk.X)
        buttons = (
            ("پروژه جدید", self._on_new_project, "Toolbar.TButton", tk.NORMAL),
            ("ساخت مدل", self._on_build_model, "Accent.Toolbar.TButton", tk.NORMAL),
            ("تحلیل", self._on_analyze, "Toolbar.TButton", tk.DISABLED),
            ("ذخیره پروژه", self._on_save_project, "Toolbar.TButton", tk.DISABLED),
            ("بارگذاری پروژه", self._on_load_project, "Toolbar.TButton", tk.DISABLED),
        )
        for text, command, style_name, state in buttons:
            button = ttk.Button(bar, text=text, command=command, style=style_name)
            button.pack(side=tk.RIGHT, padx=(6, 0))
            if state == tk.DISABLED:
                button.state(["disabled"])

    def _build_body(self) -> None:
        body = ttk.Frame(self, style="Main.TFrame", padding=(8, 8))
        body.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)
        self.input_tabs = InputTabs(body)
        self.input_tabs.grid(row=0, column=0, sticky="nsew")

    def _build_status_bar(self) -> None:
        bar = ttk.Frame(self, style="Status.TFrame", padding=(10, 4))
        bar.pack(side=tk.BOTTOM, fill=tk.X)
        self._status_var = tk.StringVar(master=self, value="")
        ttk.Label(bar, textvariable=self._status_var, style="Status.TLabel").pack(side=tk.RIGHT)

    # ------------------------------------------------------------------
    # وضعیت و پیام
    # ------------------------------------------------------------------

    def _set_status(self, text: str) -> None:
        self._status_var.set(text)

    def _show_error(self, title: str, message: str) -> None:
        messagebox.showerror(title, message, parent=self)

    def _show_info(self, title: str, message: str) -> None:
        messagebox.showinfo(title, message, parent=self)

    def _report_unexpected(self, action: str, exc: Exception) -> None:
        """گزارش خطای غیرمنتظره؛ بی‌صدا نادیده گرفته نمی‌شود."""
        self._set_status("خطای غیرمنتظره")
        self._show_error(
            "خطای غیرمنتظره",
            f"در عملیات «{action}» خطای غیرمنتظره رخ داد:\n{exc}",
        )

    # ------------------------------------------------------------------
    # رویدادها
    # ------------------------------------------------------------------

    def _on_new_project(self) -> None:
        try:
            confirmed = messagebox.askyesno(
                "پروژه جدید", _MSG_NEW_PROJECT_CONFIRM, parent=self
            )
            if not confirmed:
                return
            self.input_tabs.clear_form()
            self.current_model = None
            self._set_status("پروژه جدید")
        except Exception as exc:  # noqa: BLE001 — گزارش خطای غیرمنتظره به کاربر
            self._report_unexpected("پروژه جدید", exc)

    def _on_build_model(self) -> None:
        self.current_model = None
        try:
            model = self.input_tabs.build_model()
        except ModelBuildError as exc:
            self._set_status("خطای ورودی")
            self._show_error("خطای ورودی", str(exc))
            return
        except Exception as exc:  # noqa: BLE001 — گزارش خطای غیرمنتظره به کاربر
            self._report_unexpected("ساخت مدل", exc)
            return
        self.current_model = model
        self._set_status("مدل ساخته شد")
        self._show_info("ساخت مدل", "مدل با موفقیت ساخته شد.")

    def _on_analyze(self) -> None:
        self._set_status("قابلیت در دست توسعه")
        self._show_info("تحلیل", _MSG_PENDING)

    def _on_save_project(self) -> None:
        self._set_status("قابلیت در دست توسعه")
        self._show_info("ذخیره پروژه", _MSG_PENDING)

    def _on_load_project(self) -> None:
        self._set_status("قابلیت در دست توسعه")
        self._show_info("بارگذاری پروژه", _MSG_PENDING)


def main() -> None:
    """نقطهٔ ورود: ساخت یک نمونه MainWindow و اجرای حلقهٔ رویدادها."""
    window = MainWindow()
    window.mainloop()


if __name__ == "__main__":
    main()
