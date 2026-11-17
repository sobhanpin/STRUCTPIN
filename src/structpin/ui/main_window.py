
"""پنجرهٔ اصلی رابط دسکتاپ STRUCTPIN."""

import tkinter as tk
from tkinter import messagebox, ttk

from structpin.model.structural_model import StructuralModel
from structpin.ui.actions import MainWindowActions
from structpin.ui.input_tabs import InputTabs
from structpin.ui.plot_canvas import PlotCanvas
from structpin.ui.results_view import ResultsView


_MSG_NEW_PROJECT_CONFIRM = (
    "آیا مطمئن هستید که می‌خواهید پروژهٔ فعلی را ببندید "
    "و یک پروژهٔ جدید ایجاد کنید؟"
)


class MainWindow(tk.Tk):
    """پنجرهٔ اصلی برنامه."""

    def __init__(self) -> None:
        super().__init__()

        self.title("STRUCTPIN | تحلیل سازه")
        self.geometry("1280x800")
        self.minsize(960, 600)

        self.current_model: StructuralModel | None = None

        # جلوگیری از پاک‌سازی تکراری هنگام تایپ چند کاراکتر.
        self._input_change_invalidated = False

        self._actions = MainWindowActions(self)

        self._configure_style()
        self._build_ui()

        # اتصال پس از ساخته‌شدن تمام نماهای وابسته.
        self.input_tabs.set_on_change(self._on_input_changed)

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
        """ساخت نوار ابزار."""
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
            command=self._actions.save_project,
        ).pack(side=tk.LEFT, padx=3)

        ttk.Button(
            toolbar,
            text="بارگذاری",
            command=self._actions.load_project,
        ).pack(side=tk.LEFT, padx=3)

    def set_status(self, message: str) -> None:
        """به‌روزرسانی پیام نوار وضعیت."""
        self.status_var.set(str(message))

    def _on_input_changed(self) -> None:
        """ابطال نتایج قبلی پس از تغییر واقعی ورودی‌ها."""
        if self._input_change_invalidated:
            return

        self._input_change_invalidated = True
        self.current_model = None

        clear_note = self._actions._clear_results_safely()

        if clear_note:
            self.set_status(
                "ورودی تغییر کرد؛ پاک‌سازی نتایج ناکامل بود"
            )
            messagebox.showerror(
                "تغییر ورودی",
                "ورودی‌ها تغییر کردند، اما پاک‌سازی کامل نتایج "
                "موفق نبود:" + clear_note,
                parent=self,
            )
        else:
            self.set_status("ورودی تغییر کرد؛ نتایج قبلی پاک شدند")

    def _on_build_model(self) -> None:
        """اجرای ساخت مدل و آماده‌سازی برای تغییرات بعدی."""
        self._input_change_invalidated = False
        self._actions.build_model()

    def _on_analyze(self) -> None:
        """اجرای تحلیل و آماده‌سازی برای تغییرات بعدی."""
        self._input_change_invalidated = False
        self._actions.analyze()

    def _on_new_project(self) -> None:
        """تأیید و پاک‌سازی پروژهٔ فعلی.

        در صورت لغو، هیچ تغییری ایجاد نمی‌شود.
        پاک‌سازی دو نمای نتایج از طریق Actions انجام می‌شود تا
        شکست پاک‌سازی یکی مانع تلاش برای پاک‌سازی دیگری نشود.
        """
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

            # فرم و نماها اکنون پاک هستند؛ تغییرات بعدی نباید
            # باعث پاک‌سازی تکراری شوند.
            self._input_change_invalidated = True

        except Exception as exc:
            self._actions.report_unexpected("پروژه جدید", exc)
            return

        if clear_note:
            self.set_status("پروژه جدید؛ پاک‌سازی نتایج ناکامل بود")
            messagebox.showerror(
                "پروژه جدید",
                "فرم پاک شد، اما پاک‌سازی نتایج ناموفق بود:" + clear_note,
                parent=self,
            )
        else:
            self.set_status("پروژه جدید")


def main() -> None:
    """نقطهٔ ورود رابط گرافیکی."""
    app = MainWindow()
    app.mainloop()


if __name__ == "__main__":
    main()
