"""کنترل‌کنندهٔ عملیات رابط اصلی STRUCTPIN (tkinter و ttk استاندارد).

مسئولیت:
    - هماهنگ‌کردن دکمه‌های ساخت مدل، تحلیل، ذخیره و بارگذاری بین فرم، سرویس‌ها و ویوها.
    - تفکیک خطاهای ورودی (ModelBuildError، AnalysisInputError)، خطاهای تحلیل، خطاهای
      عددی (ArithmeticError)، خطاهای نمایش و خطاهای غیرمنتظره.
    - اعتبارسنجی مشترک عددی گزارش (validate_report_numbers) پیش از نمایش در هر دو ویو.
    - بارگذاری transactional:
        * مدل بارگذاری‌شده پیش از دست‌زدن به فرم با قواعد فرم اعتبارسنجی می‌شود.
        * snapshot فرم گرفته می‌شود و در شکست اعمال، بازگردانی می‌شود.
        * rollback موفق: نتایج و current_model حفظ می‌شوند و فقط خطای بارگذاری گزارش می‌شود.
        * rollback ناموفق: نتایج پاک می‌شوند، current_model حفظ می‌شود و هر دو خطا گزارش می‌شوند.

صفت last_clear_ok نتیجهٔ آخرین تلاش پاک‌سازی نتایج را نگه می‌دارد تا MainWindow
بتواند فلگ‌های stale را بر اساس آن به‌روز کند. actions هیچ فلگی را تغییر نمی‌دهد.

این ماژول هیچ محاسبهٔ مهندسی انجام نمی‌دهد و فایل‌های FEM را import نمی‌کند.
خطاهای عددی سرویس تحلیل از ArithmeticError ارث می‌برند، بنابراین با گرفتن این کلاس
نیازی به import مستقیم از structpin.fem نیست.
"""

from __future__ import annotations

from tkinter import filedialog, messagebox
from typing import TYPE_CHECKING

from structpin.model.structural_model import StructuralModel
from structpin.services.analysis_service import (
    AnalysisError,
    AnalysisInputError,
    run_frame_analysis,
)
from structpin.services.model_builder import ModelBuildError
from structpin.services.model_builder import build_model as build_structural_model
from structpin.services.project_io import (
    ProjectFileError,
    load_project,
    model_to_dict,
    save_project,
)
from structpin.services.report_validation import validate_report_numbers

if TYPE_CHECKING:
    from structpin.ui.main_window import MainWindow

__all__ = [
    "MainWindowActions",
    "ClearResultsError",
    "PROJECT_EXTENSION",
    "PROJECT_FILE_TYPES",
]


PROJECT_EXTENSION = ".structpin"
PROJECT_FILE_TYPES = (
    ("پروژه STRUCTPIN", "*.structpin"),
    ("فایل JSON", "*.json"),
    ("همه فایل‌ها", "*.*"),
)


class ClearResultsError(RuntimeError):
    """پاک‌سازی یک یا هر دو ویوی نتایج با خطا مواجه شد.

    ویژگی failures فهرست پیام‌های خطای هر ویو را نگه می‌دارد.
    """

    def __init__(self, failures: list[str]) -> None:
        self.failures = list(failures)
        super().__init__("؛ ".join(self.failures))


class MainWindowActions:
    """عملیات دکمه‌های پنجرهٔ اصلی.

    این کلاس پنجرهٔ اصلی را از طریق ویژگی‌های عمومی آن (input_tabs، results_view،
    plot_canvas، current_model و set_status) به‌کار می‌گیرد.
    """

    def __init__(self, window: MainWindow) -> None:
        self._window = window
        # نتیجهٔ آخرین تلاش پاک‌سازی نتایج؛ MainWindow برای به‌روزرسانی فلگ‌ها می‌خواند.
        self.last_clear_ok: bool | None = True

    # ------------------------------------------------------------------
    # ابزارهای داخلی
    # ------------------------------------------------------------------

    def _show_error(self, title: str, message: str) -> None:
        messagebox.showerror(title, message, parent=self._window)

    def _show_info(self, title: str, message: str) -> None:
        messagebox.showinfo(title, message, parent=self._window)

    def _clear_results(self) -> None:
        """پاک‌کردن نتایج و نمودار؛ هر ویو مستقل پاک می‌شود.

        خطای یک ویو مانع پاک‌سازی ویوی دیگر نمی‌شود. خطاها جمع‌آوری و در پایان
        به‌صورت ClearResultsError پرتاب می‌شوند.
        """
        failures: list[str] = []
        try:
            self._window.results_view.clear()
        except Exception as exc:
            failures.append(f"پاک‌سازی جدول نتایج ناموفق بود: {exc}")
        try:
            self._window.plot_canvas.clear()
        except Exception as exc:
            failures.append(f"پاک‌سازی نمودار ناموفق بود: {exc}")
        if failures:
            raise ClearResultsError(failures)

    def _clear_results_safely(self) -> str:
        """پاک‌سازی نتایج؛ خطا پرتاب نمی‌شود، بلکه متن گزارش خطا برگردانده می‌شود.

        نتیجه در last_clear_ok ثبت می‌شود.
        """
        try:
            self._clear_results()
        except ClearResultsError as exc:
            self.last_clear_ok = False
            return "\n" + "\n".join(exc.failures)
        self.last_clear_ok = True
        return ""

    def _analysis_failed(self, status: str, message: str, exc: BaseException) -> None:
        clear_note = self._clear_results_safely()
        self._window.set_status(status)
        self._show_error("تحلیل سازه", f"{message}\n{exc}{clear_note}")

    def report_unexpected(self, action: str, exc: BaseException, extra: str = "") -> None:
        """گزارش خطای غیرمنتظره؛ بی‌صدا نادیده گرفته نمی‌شود.

        extra برای الحاق خطای پاک‌سازی یا سایر یادداشت‌های مرتبط به پیام است.
        """
        self._window.set_status("خطای غیرمنتظره")
        self._show_error(
            "خطای غیرمنتظره",
            f"در عملیات «{action}» خطای غیرمنتظره رخ داد:\n{exc}{extra}",
        )

    # ------------------------------------------------------------------
    # ساخت مدل
    # ------------------------------------------------------------------

    def build_model(self) -> StructuralModel | None:
        """ساخت مدل از فرم فعلی و نگهداری آن به‌عنوان current_model.

        پیش از ساخت، نتایج و نمودار قبلی و current_model پاک می‌شوند تا گزارش یا مدل
        قدیمی پس از تغییر ورودی باقی نماند.
        """
        window = self._window
        window.current_model = None
        clear_note = self._clear_results_safely()

        try:
            model = window.input_tabs.build_model()
        except ModelBuildError as exc:
            window.set_status("خطای ورودی")
            self._show_error("خطای ورودی", f"{exc}{clear_note}")
            return None
        except Exception as exc:
            self.report_unexpected("ساخت مدل", exc, extra=clear_note)
            return None

        window.current_model = model
        window.set_status("مدل ساخته شد")
        self._show_info("ساخت مدل", "مدل با موفقیت ساخته شد." + clear_note)
        return model

    # ------------------------------------------------------------------
    # تحلیل
    # ------------------------------------------------------------------

    def analyze(self) -> None:
        """ساخت مدل از فرم فعلی، تحلیل، اعتبارسنجی عددی و نمایش نتایج.

        هر بار مدل از نو ساخته می‌شود. در هر شکست، نتایج قبلی پاک می‌شوند تا گزارش
        قدیمی به‌عنوان نتیجهٔ جدید نمایش داده نشود.
        """
        window = self._window
        window.current_model = None

        try:
            model = window.input_tabs.build_model()
        except ModelBuildError as exc:
            window.set_status("خطای ورودی")
            clear_note = self._clear_results_safely()
            self._show_error("خطای ورودی", f"{exc}{clear_note}")
            return
        except Exception as exc:
            clear_note = self._clear_results_safely()
            self.report_unexpected("ساخت مدل برای تحلیل", exc, extra=clear_note)
            return

        window.current_model = model

        try:
            report = run_frame_analysis(model)
        except AnalysisInputError as exc:
            self._analysis_failed("خطای مدل", "مدل برای تحلیل معتبر نیست:", exc)
            return
        except (AnalysisError, ValueError) as exc:
            self._analysis_failed("خطای تحلیل", "تحلیل انجام نشد:", exc)
            return
        except ArithmeticError as exc:
            self._analysis_failed(
                "خطای عددی",
                "حل عددی دستگاه ممکن نیست (ناپایداری، تکینگی یا سرریز عددی):",
                exc,
            )
            return
        except Exception as exc:
            clear_note = self._clear_results_safely()
            self.report_unexpected("تحلیل", exc, extra=clear_note)
            return

        try:
            validate_report_numbers(report)
            window.results_view.show_report(report)
            window.plot_canvas.show_report(report)
        except ValueError as exc:
            self._analysis_failed("خطای نمایش", "نمایش نتایج انجام نشد:", exc)
            return
        except Exception as exc:
            clear_note = self._clear_results_safely()
            self.report_unexpected("نمایش نتایج", exc, extra=clear_note)
            return

        window.set_status("تحلیل انجام شد")
        self._show_info("تحلیل سازه", "تحلیل با موفقیت انجام شد.")

    # ------------------------------------------------------------------
    # ذخیره
    # ------------------------------------------------------------------

    def save(self) -> None:
        """ذخیرهٔ مدل فرم فعلی.

        - لغو انتخاب فایل: هیچ تغییری در current_model، فرم، نتایج و نمودار ایجاد نمی‌شود.
        - ذخیرهٔ موفق: فقط پس از موفقیت، current_model به مدل ذخیره‌شده تنظیم و نتایج
          و نمودار قبلی پاک می‌شوند. خطای پاک‌سازی جداگانه گزارش می‌شود و موفقیت ذخیره
          را پنهان نمی‌کند.
        - خطای ساخت مدل یا ذخیره: current_model تغییر نمی‌کند.
        """
        window = self._window

        try:
            model = window.input_tabs.build_model()
        except ModelBuildError as exc:
            window.set_status("ذخیره انجام نشد")
            self._show_error("ذخیره پروژه", f"پروژه قابل ذخیره نیست:\n{exc}")
            return
        except Exception as exc:
            self.report_unexpected("ساخت مدل برای ذخیره", exc)
            return

        try:
            path = filedialog.asksaveasfilename(
                parent=window,
                title="ذخیره پروژه",
                defaultextension=PROJECT_EXTENSION,
                filetypes=PROJECT_FILE_TYPES,
            )
        except Exception as exc:
            self.report_unexpected("انتخاب فایل ذخیره", exc)
            return

        if not path:
            window.set_status("ذخیره لغو شد")
            return

        try:
            save_project(model, path)
        except ProjectFileError as exc:
            window.set_status("خطای ذخیره")
            self._show_error("ذخیره پروژه", f"ذخیرهٔ پروژه انجام نشد:\n{exc}")
            return
        except Exception as exc:
            self.report_unexpected("ذخیره پروژه", exc)
            return

        # ذخیرهٔ موفق: اکنون وضعیت به مدل ذخیره‌شده به‌روز می‌شود.
        window.current_model = model
        clear_note = self._clear_results_safely()
        window.set_status("پروژه ذخیره شد")
        self._show_info("ذخیره پروژه", "پروژه با موفقیت ذخیره شد." + clear_note)

    # ------------------------------------------------------------------
    # بارگذاری (transactional)
    # ------------------------------------------------------------------

    def load(self) -> None:
        """بارگذاری پروژه و انتقال آن به فرم با اعتبارسنجی و امکان بازگردانی.

        ترتیب کار:
            1. انتخاب فایل (لغو = بدون تغییر).
            2. خواندن فایل با load_project.
            3. تبدیل یک‌باره به دیکشنری فرم با model_to_dict.
            4. اعتبارسنجی دیکشنری با قواعد فرم (build_model)؛ در شکست، هیچ چیز تغییر نمی‌کند.
            5. snapshot فرم فعلی با get_form_data.
            6. اعمال دیکشنری با set_form_data؛ در شکست، بازگردانی snapshot.
               - بازگردانی موفق: نتایج و current_model حفظ؛ فقط خطای بارگذاری گزارش.
               - بازگردانی ناموفق: نتایج پاک؛ current_model حفظ؛ هر دو خطا گزارش.
            7. فقط پس از موفقیت کامل: تنظیم current_model، پاک‌سازی نتایج و پیام موفقیت.
        """
        window = self._window

        try:
            path = filedialog.askopenfilename(
                parent=window,
                title="بارگذاری پروژه",
                filetypes=PROJECT_FILE_TYPES,
            )
        except Exception as exc:
            self.report_unexpected("انتخاب فایل بارگذاری", exc)
            return

        if not path:
            window.set_status("بارگذاری لغو شد")
            return

        try:
            model = load_project(path)
        except ProjectFileError as exc:
            window.set_status("خطای بارگذاری")
            self._show_error("بارگذاری پروژه", f"فایل پروژه بارگذاری نشد:\n{exc}")
            return
        except Exception as exc:
            self.report_unexpected("بارگذاری پروژه", exc)
            return

        try:
            payload = model_to_dict(model)
        except Exception as exc:
            self.report_unexpected("تبدیل مدل بارگذاری‌شده", exc)
            return

        try:
            build_structural_model(payload)
        except ModelBuildError as exc:
            window.set_status("خطای بارگذاری")
            self._show_error(
                "بارگذاری پروژه",
                f"فایل پروژه با قواعد فرم سازگار نیست؛ بارگذاری انجام نشد:\n{exc}",
            )
            return
        except Exception as exc:
            self.report_unexpected("اعتبارسنجی پروژه بارگذاری‌شده", exc)
            return

        try:
            snapshot = window.input_tabs.get_form_data()
        except Exception as exc:
            self.report_unexpected("خواندن فرم فعلی", exc)
            return

        try:
            window.input_tabs.set_form_data(payload)
        except Exception as apply_exc:
            self._restore_snapshot(snapshot, apply_exc)
            return

        window.current_model = model
        clear_note = self._clear_results_safely()
        window.set_status("پروژه بارگذاری شد")
        self._show_info("بارگذاری پروژه", "پروژه با موفقیت بارگذاری شد." + clear_note)

    def _restore_snapshot(self, snapshot: dict, apply_exc: BaseException) -> None:
        """بازگردانی فرم به snapshot پس از شکست انتقال داده.

        current_model در این مسیر تغییر نمی‌کند.
        - بازگردانی موفق: نتایج قبلی حفظ می‌شوند و فقط خطای بارگذاری گزارش می‌شود.
        - بازگردانی ناموفق: وضعیت فرم نامطمئن است؛ نتایج پاک می‌شوند و هر دو خطا
          (خطای بارگذاری و خطای بازگردانی) گزارش می‌شوند. خطای پاک‌سازی نیز به پیام
          الحاق می‌شود و خطای اصلی را پنهان نمی‌کند.
        """
        window = self._window
        try:
            window.input_tabs.set_form_data(snapshot)
        except Exception as rollback_exc:
            clear_note = self._clear_results_safely()
            window.set_status("بازگردانی فرم ناموفق بود")
            self._show_error(
                "بارگذاری پروژه",
                "بارگذاری ناموفق بود و بازگردانی فرم نیز شکست خورد؛ "
                "وضعیت فرم ممکن است نامعتبر باشد.\n"
                f"خطای بارگذاری: {apply_exc}\n"
                f"خطای بازگردانی: {rollback_exc}"
                f"{clear_note}",
            )
            return

        window.set_status("بارگذاری ناموفق؛ فرم قبلی بازگردانده شد")
        self._show_error(
            "بارگذاری پروژه",
            f"فایل پروژه با داده‌های فرم سازگار نبود؛ فرم قبلی بازگردانده شد:\n{apply_exc}",
                         )
