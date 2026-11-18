"""پنجرهٔ اصلی رابط دسکتاپ STRUCTPIN.

مالکیت فلگ‌های stale:
    - تنها منبع قاعدهٔ انتقال سه فلگ، ماشین حالت StaleState در stale_state.py است.
    - MainWindow وضعیت سه فلگ را از ویژگی‌های خود می‌خواند، توسط StaleState
      به‌روز می‌کند و پیام و پاک‌سازی را انجام می‌دهد.
    - actions هیچ فلگی را تغییر نمی‌دهد؛ فقط last_clear_ok را به‌روز می‌کند.

ذخیره و بارگذاری:
    دکمه‌های Toolbar به wrapperهای _save و _load متصل‌اند. هر wrapper:
        1. پیش از عملیات، last_clear_ok را None می‌کند تا نتیجهٔ قدیمی
           با نتیجهٔ عملیات جدید اشتباه گرفته نشود.
        2. عملیات actions.save یا actions.load را فراخوانی می‌کند.
        3. موفقیت را از وضعیت موفقیت عملیات (متن status) تشخیص می‌دهد.
        4. فقط اگر پاک‌سازی واقعاً انجام شده باشد (last_clear_ok از None خارج شده)،
           نتیجه را به StaleState می‌دهد. در غیر این صورت فلگ‌ها بدون تغییر می‌مانند.
    پاک‌سازی ناموفق موفقیت عملیات را پنهان نمی‌کند؛ فقط وضعیت stale ثبت می‌شود.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from structpin.model.structural_model import StructuralModel
from structpin.ui.actions import MainWindowActions
from structpin.ui.input_tabs import InputTabs
from structpin.ui.plot_canvas import PlotCanvas
from structpin.ui.results_view import ResultsView
from structpin.ui.stale_state import StaleState


_MSG_NEW_PROJECT_CONFIRM = (
    "آیا مطمئن هستید که می‌خواهید پروژهٔ فعلی را ببندید "
    "و یک پروژهٔ جدید ایجاد کنید؟"
)

_STATUS_BUILD_OK = "مدل ساخته شد"
_STATUS_SAVE_OK = "پروژه ذخیره شد"
_STATUS_LOAD_OK = "پروژه بارگذاری شد"
_STATUS_ANALYSIS_OK = "تحلیل انجام شد"
_STATUS_INVALIDATED = "ورودی تغییر کرد؛ نتایج قبلی پاک شدند"
_STATUS_STALE = "ورودی تغییر کرد؛ پاک‌سازی نتایج ناکامل بود"
_STATUS_NEW_PROJECT = "پروژه جدید"
_STATUS_NEW_PROJECT_STALE = "پروژه جدید؛ پاک‌سازی نتایج ناکامل بود"


class MainWindow(tk.Tk):
    """پنجرهٔ اصلی برنامه."""

    def __init__(self) -> None:
        super().__init__()

        self.title("STRUCTPIN | تحلیل سازه")
        self.geometry("1280x800")
        self.minsize(960, 600)

        self.current_model: StructuralModel | None = None

        # سه فلگ stale. تغییر آن‌ها فقط از طریق _read_stale / _write_stale و StaleState انجام می‌شود.
        self._input_change_invalidated = False
        self._results_stale = False
        self._stale_error_reported = False

        self._actions = MainWindowActions(self)

        self._configure_style()
        self._build_ui()

        self.input_tabs.set_on_change(self._on_input_changed)

    # ------------------------------------------------------------------
    # ابزارهای فلگ (تنها پل بین سه ویژگی و StaleState)
    # ------------------------------------------------------------------

    def _read_stale(self) -> StaleState:
        return StaleState(
            input_change_invalidated=self._input_change_invalidated,
            results_stale=self._results_stale,
            stale_error_reported=self._stale_error_reported,
        )

    def _write_stale(self, state: StaleState) -> None:
        self._input_change_invalidated = state.input_change_invalidated
        self._results_stale = state.results_stale
        self._stale_error_reported = state.stale_error_reported

    def _clear_outcome_of(self, operation_succeeded: bool) -> None:
        """انتقال فلگ‌ها پس از یک عملیات که ممکن است پاک‌سازی انجام داده باشد.

        اگر last_clear_ok هنوز None است، یعنی عملیات به مرحلهٔ پاک‌سازی نرسیده،
        هیچ انتقالی انجام نمی‌شود.
        """
        clear_ok = self._actions.last_clear_ok
        if clear_ok is None:
            return
        self._write_stale(self._read_stale().on_clear_attempt(clear_ok, operation_succeeded))

    def _status_is(self, text: str) -> bool:
        """آیا نوار وضعیت دقیقاً متن موفقیت یک عملیات را دارد؟"""
        return self.status_var.get() == text

    # ------------------------------------------------------------------
    # ساخت رابط
    # ------------------------------------------------------------------

    def _configure_style(self) -> None:
        """تنظیم ظاهر پایهٔ رابط کاربری."""
        style = ttk.Style(self)

        available_themes = style.theme_names()
        if "clam" in available_themes:
            style.theme_use("clam")

        style.configure("TButton", padding=(10, 6))
        style.configure("TNotebook.Tab", padding=(12, 7))

    def _build_ui(self) -> None:
        """ساخت اجزای اصلی پنجره."""
        self._build_toolbar()

        self.main_container = ttk.Frame(self, padding=8)
        self.main_container.pack(fill=tk.BOTH, expand=True)

        self.notebook = ttk.Notebook(self.main_container)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        self.input_tabs = InputTabs(self.notebook)
        self.notebook.add(self.input_tabs, text="ورودی مدل")

        self.results_view = ResultsView(self.notebook)
        self.notebook.add(self.results_view, text="نتایج تحلیل")

        self.plot_canvas = PlotCanvas(self.notebook)
        self.notebook.add(self.plot_canvas, text="نمودارهای N / V / M")

        self.status_var = tk.StringVar(value="آماده")
        self.status_bar = ttk.Label(
            self,
            textvariable=self.status_var,
            anchor=tk.W,
            padding=(10, 5),
        )
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)

    def _build_toolbar(self) -> None:
        """ساخت نوار ابزار. ذخیره و بارگذاری به wrapperهای MainWindow متصل‌اند."""
        toolbar = ttk.Frame(self, padding=(8, 6))
        toolbar.pack(side=tk.TOP, fill=tk.X)

        ttk.Button(
            toolbar,
            text="پروژه جدید",
            command=self._on_new_project,
        ).pack(side=tk.LEFT, padx=3)

        ttk.Button(
            toolbar,
            text="ساخت مدل",
            command=self._on_build_model,
        ).pack(side=tk.LEFT, padx=3)

        ttk.Button(
            toolbar,
            text="تحلیل",
            command=self._on_analyze,
        ).pack(side=tk.LEFT, padx=3)

        ttk.Button(
            toolbar,
            text="ذخیره",
            command=self._save,
        ).pack(side=tk.LEFT, padx=3)

        ttk.Button(
            toolbar,
            text="بارگذاری",
            command=self._load,
        ).pack(side=tk.LEFT, padx=3)

    def set_status(self, message: str) -> None:
        """به‌روزرسانی پیام نوار وضعیت."""
        self.status_var.set(str(message))

    # ------------------------------------------------------------------
    # تغییر ورودی
    # ------------------------------------------------------------------

    def _on_input_changed(self) -> None:
        """ابطال نتایج قبلی پس از تغییر واقعی ورودی.

        - اگر StaleState پاک‌سازی لازم نمی‌بیند، هیچ کاری نمی‌شود.
        - در غیر این صورت مدل نامعتبر و نتایج پاک می‌شوند.
        - پیام خطای پاک‌سازی فقط در اولین شکست هر دوره نمایش داده می‌شود.
        """
        state = self._read_stale()

        if not state.input_change_needs_clear(self.current_model is not None):
            return

        self.current_model = None
        # باید پیش از انتقال خوانده شود، چون انتقال stale_error_reported را تغییر می‌دهد.
        should_notify = state.should_notify_clear_failure()

        clear_note = self._actions._clear_results_safely()
        clear_ok = self._actions.last_clear_ok

        self._write_stale(state.on_results_invalidated(clear_ok))

        if clear_ok:
            self.set_status(_STATUS_INVALIDATED)
            return

        self.set_status(_STATUS_STALE)
        if should_notify:
            messagebox.showerror(
                "تغییر ورودی",
                "ورودی‌ها تغییر کردند، اما پاک‌سازی کامل نتایج "
                "موفق نبود:" + clear_note,
                parent=self,
            )

    # ------------------------------------------------------------------
    # ساخت مدل و تحلیل
    # ------------------------------------------------------------------

    def _on_build_model(self) -> None:
        """ساخت مدل.

        پیش از عملیات last_clear_ok ریست می‌شود. actions.build_model همیشه
        پیش از ساخت پاک‌سازی می‌کند، پس نتیجهٔ پاک‌سازی معتبر است.
        موفقیت فقط با وضعیت «مدل ساخته شد» تشخیص داده می‌شود.
        """
        self._actions.last_clear_ok = None
        self._actions.build_model()
        built = self._status_is(_STATUS_BUILD_OK)
        self._clear_outcome_of(operation_succeeded=built)

    def _on_analyze(self) -> None:
        """تحلیل.

        - موفق: گزارش تازه نتایج قبلی را جایگزین کرده؛ همهٔ فلگ‌ها Reset می‌شوند.
        - ناموفق: پاک‌سازی (در صورت انجام) بر فلگ‌ها اثر می‌گذارد؛ در غیر این صورت وضعیت حفظ می‌شود.
        """
        self._actions.last_clear_ok = None
        self._actions.analyze()

        if self._status_is(_STATUS_ANALYSIS_OK):
            self._write_stale(self._read_stale().on_analysis_succeeded())
        else:
            self._clear_outcome_of(operation_succeeded=False)

    # ------------------------------------------------------------------
    # ذخیره و بارگذاری (wrapperهای اختصاصی)
    # ------------------------------------------------------------------

    def _save(self) -> None:
        """ذخیره با wrapper: موفقیت از وضعیت، پاک‌سازی از last_clear_ok جدا بررسی می‌شود."""
        self._actions.last_clear_ok = None
        self._actions.save()
        saved = self._status_is(_STATUS_SAVE_OK)
        self._clear_outcome_of(operation_succeeded=saved)

    def _load(self) -> None:
        """بارگذاری با wrapper: موفقیت از وضعیت، پاک‌سازی از last_clear_ok جدا بررسی می‌شود."""
        self._actions.last_clear_ok = None
        self._actions.load()
        loaded = self._status_is(_STATUS_LOAD_OK)
        self._clear_outcome_of(operation_succeeded=loaded)

    # ------------------------------------------------------------------
    # پروژه جدید
    # ------------------------------------------------------------------

    def _on_new_project(self) -> None:
        """تأیید و پاک‌سازی پروژهٔ فعلی. در لغو هیچ تغییری ایجاد نمی‌شود."""
        try:
            confirmed = messagebox.askyesno(
                "پروژه جدید",
                _MSG_NEW_PROJECT_CONFIRM,
                parent=self,
            )
            if not confirmed:
                return

            self.input_tabs.clear_form()
            self.current_model = None
            clear_note = self._actions._clear_results_safely()
            clear_ok = self._actions.last_clear_ok

        except Exception as exc:
            self._actions.report_unexpected("پروژه جدید", exc)
            return

        self._write_stale(self._read_stale().on_results_invalidated(clear_ok))

        if clear_ok:
            self.set_status(_STATUS_NEW_PROJECT)
            return

        self.set_status(_STATUS_NEW_PROJECT_STALE)
        messagebox.showerror(
            "پروژه جدید",
            "فرم پاک شد، اما پاک‌سازی نتایج ناموفق بود:" + clear_note,
            parent=self,
        )


def main() -> None:
    """نقطهٔ ورود رابط گرافیکی."""
    app = MainWindow()
    app.mainloop()


if __name__ == "__main__":
    main()
