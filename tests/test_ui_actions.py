"""تست‌های واحد structpin.ui.actions بدون ساخت پنجرهٔ واقعی Tkinter.

پنجرهٔ ساختگی و messagebox/filedialog با unittest.mock جایگزین می‌شوند.
mockها در محل import واقعی در structpin.ui.actions patch می‌شوند.
رفتار و متن‌ها از نسخهٔ actions.py استخراج شده‌اند؛ هیچ پیام یا رفتار فرضی نیست.

گزارش‌های تحلیل موفق با AnalysisReport واقعی ساخته می‌شوند تا اعتبارسنجی مشترک
validate_report_numbers در actions.py روی داده‌های معتبر اجرا شود.

اعتبارسنجی مدل بارگذاری‌شده (build_structural_model در actions) در تست‌های
مربوط به رفتار transactional با mock جایگزین شده است تا رفتار فرم و نتایج
به‌صورت مستقل آزموده شود؛ تست مستقل برای شکست آن در LoadTest وجود دارد.

اجرا (ریشهٔ مخزن):
    PYTHONPATH=src python -m unittest discover -s tests -p "test_ui_actions.py" -v
"""

import unittest
from unittest import mock

from structpin.services.analysis_service import AnalysisInputError, AnalysisReport
from structpin.services.model_builder import ModelBuildError
from structpin.services.project_io import ProjectFileError
from structpin.ui import actions as actions_module
from structpin.ui.actions import ClearResultsError, MainWindowActions


def _valid_report():
    """گزارش معتبر با ساختار واقعی AnalysisReport (بدون محاسبهٔ مهندسی؛ مقادیر نمونه)."""
    return AnalysisReport(
        displacements={1: (0.0, 0.0, 0.0), 2: (0.001, -0.002, 0.0005)},
        reactions={1: (-10.0, 5.0, 2.5)},
        member_end_actions={
            1: ((10.0, 5.0, 0.0), (-10.0, -5.0, 12.5)),
        },
        internal_forces={
            1: {
                "x": (0.0, 1.0, 2.0),
                "N": (10.0, 10.0, 10.0),
                "V": (5.0, 5.0, -5.0),
                "M": (0.0, 5.0, 0.0),
            },
        },
        n_points=3,
        warnings=(),
    )


class _FakeInputTabs:
    def __init__(self, model=None, build_error=None, form=None, set_error=None, get_error=None):
        self.model = model
        self.build_error = build_error
        self.form = form if form is not None else {"name": "old"}
        self.set_error = set_error
        self.get_error = get_error
        self.build_calls = 0
        self.get_calls = 0
        self.set_calls = []

    def build_model(self):
        self.build_calls += 1
        if self.build_error is not None:
            raise self.build_error
        return self.model

    def get_form_data(self):
        self.get_calls += 1
        if self.get_error is not None:
            raise self.get_error
        return dict(self.form)

    def set_form_data(self, data):
        self.set_calls.append(data)
        if self.set_error is not None:
            raise self.set_error
        self.form = dict(data)


class _FakeView:
    def __init__(self, clear_error=None, show_error=None):
        self.clear_error = clear_error
        self.show_error = show_error
        self.clear_calls = 0
        self.show_calls = []

    def clear(self):
        self.clear_calls += 1
        if self.clear_error is not None:
            raise self.clear_error

    def show_report(self, report):
        self.show_calls.append(report)
        if self.show_error is not None:
            raise self.show_error


class _FakeWindow:
    def __init__(self, input_tabs=None, results_view=None, plot_canvas=None, current_model=None):
        self.input_tabs = input_tabs if input_tabs is not None else _FakeInputTabs()
        self.results_view = results_view if results_view is not None else _FakeView()
        self.plot_canvas = plot_canvas if plot_canvas is not None else _FakeView()
        self.current_model = current_model
        self.statuses = []

    def set_status(self, text):
        self.statuses.append(text)


class _ActionsTestBase(unittest.TestCase):
    """messagebox و filedialog را در محل واقعی import در actions patch می‌کند."""

    def setUp(self):
        self.messagebox = self._patch("messagebox")
        self.filedialog = self._patch("filedialog")

    def _patch(self, name, **kwargs):
        patcher = mock.patch.object(actions_module, name, **kwargs)
        mocked = patcher.start()
        self.addCleanup(patcher.stop)
        return mocked

    def _patch_service(self, name, **kwargs):
        return self._patch(name, **kwargs)

    @staticmethod
    def _actions(window):
        return MainWindowActions(window)


# ----------------------------------------------------------------------
# ساخت مدل
# ----------------------------------------------------------------------


class BuildModelTest(_ActionsTestBase):

    def test_success_sets_model_status_and_info(self):
        """فرم معتبر: current_model تنظیم، وضعیت «مدل ساخته شد»، پیام موفقیت بدون پاک‌سازی ناموفق."""
        model = object()
        window = _FakeWindow(input_tabs=_FakeInputTabs(model=model))
        result = self._actions(window).build_model()
        self.assertIs(result, model)
        self.assertIs(window.current_model, model)
        self.assertEqual(window.statuses, ["مدل ساخته شد"])
        self.messagebox.showinfo.assert_called_once_with(
            "ساخت مدل", "مدل با موفقیت ساخته شد.", parent=window
        )
        self.messagebox.showerror.assert_not_called()

    def test_clears_previous_model_and_results_before_building(self):
        """پیش از ساخت، مدل قبلی None و هر ویو یک بار پاک می‌شود."""
        window = _FakeWindow(
            input_tabs=_FakeInputTabs(build_error=ModelBuildError("بد")),
            current_model=object(),
        )
        self._actions(window).build_model()
        self.assertIsNone(window.current_model)
        self.assertEqual(window.results_view.clear_calls, 1)
        self.assertEqual(window.plot_canvas.clear_calls, 1)

    def test_model_build_error_shows_message_and_keeps_none(self):
        """ModelBuildError: وضعیت «خطای ورودی»، پیام خطا شامل متن استثنا، current_model=None."""
        window = _FakeWindow(input_tabs=_FakeInputTabs(build_error=ModelBuildError("ردیف ۱ نامعتبر")))
        self.assertIsNone(self._actions(window).build_model())
        self.assertIsNone(window.current_model)
        self.assertEqual(window.statuses, ["خطای ورودی"])
        message = self.messagebox.showerror.call_args[0][1]
        self.assertEqual(self.messagebox.showerror.call_args[0][0], "خطای ورودی")
        self.assertIn("ردیف ۱ نامعتبر", message)

    def test_unexpected_build_error_appends_clear_failure_note(self):
        """خطای غیرمنتظره ساخت مدل و خطای پاک‌سازی: هر دو در پیام آمده‌اند (خطای پاک‌سازی گم نمی‌شود)."""
        window = _FakeWindow(
            input_tabs=_FakeInputTabs(build_error=RuntimeError("ناشناخته")),
            results_view=_FakeView(clear_error=RuntimeError("جدول قفل")),
        )
        self.assertIsNone(self._actions(window).build_model())
        self.assertIn("خطای غیرمنتظره", window.statuses)
        message = self.messagebox.showerror.call_args[0][1]
        self.assertIn("ناشناخته", message)
        self.assertIn("جدول قفل", message)


# ----------------------------------------------------------------------
# تحلیل
# ----------------------------------------------------------------------


class AnalyzeTest(_ActionsTestBase):

    def setUp(self):
        super().setUp()
        self.run_analysis = self._patch_service("run_frame_analysis")

    def test_success_passes_report_to_both_views_and_reports_success(self):
        """موفق: گزارش معتبر AnalysisReport به هر دو ویو می‌رسد، وضعیت «تحلیل انجام شد»، پیام موفقیت."""
        model = object()
        report = _valid_report()
        self.run_analysis.return_value = report
        window = _FakeWindow(input_tabs=_FakeInputTabs(model=model))
        self._actions(window).analyze()
        self.run_analysis.assert_called_once_with(model)
        self.assertIs(window.current_model, model)
        self.assertEqual(len(window.results_view.show_calls), 1)
        self.assertIs(window.results_view.show_calls[0], report)
        self.assertEqual(len(window.plot_canvas.show_calls), 1)
        self.assertIs(window.plot_canvas.show_calls[0], report)
        self.assertEqual(window.statuses, ["تحلیل انجام شد"])
        self.messagebox.showinfo.assert_called_once_with(
            "تحلیل سازه", "تحلیل با موفقیت انجام شد.", parent=window
        )

    def test_build_input_error_clears_once_and_skips_analysis(self):
        """خطای ورودی: پاک‌سازی یک بار، بدون تحلیل، وضعیت «خطای ورودی»."""
        window = _FakeWindow(input_tabs=_FakeInputTabs(build_error=ModelBuildError("بد")))
        self._actions(window).analyze()
        self.run_analysis.assert_not_called()
        self.assertIsNone(window.current_model)
        self.assertEqual(window.results_view.clear_calls, 1)
        self.assertEqual(window.plot_canvas.clear_calls, 1)
        self.assertEqual(window.statuses, ["خطای ورودی"])
        self.messagebox.showerror.assert_called_once()

    def test_analysis_input_error_sets_model_error_status(self):
        """AnalysisInputError: مدل ذخیره‌شده، وضعیت «خطای مدل»، پاک‌سازی یک بار."""
        self.run_analysis.side_effect = AnalysisInputError("ناپایدار")
        model = object()
        window = _FakeWindow(input_tabs=_FakeInputTabs(model=model))
        self._actions(window).analyze()
        self.assertIs(window.current_model, model)
        self.assertEqual(window.statuses, ["خطای مدل"])
        self.assertEqual(window.results_view.clear_calls, 1)
        self.assertEqual(window.plot_canvas.clear_calls, 1)
        self.messagebox.showerror.assert_called_once()

    def test_analysis_value_error_sets_analysis_error_status(self):
        """ValueError سرویس: وضعیت «خطای تحلیل»."""
        self.run_analysis.side_effect = ValueError("بد")
        window = _FakeWindow(input_tabs=_FakeInputTabs(model=object()))
        self._actions(window).analyze()
        self.assertEqual(window.statuses, ["خطای تحلیل"])
        self.assertEqual(window.results_view.clear_calls, 1)

    def test_arithmetic_error_sets_numeric_status(self):
        """ArithmeticError: وضعیت «خطای عددی»، بدون نمایش نتایج، پاک‌سازی یک بار."""
        self.run_analysis.side_effect = ArithmeticError("تکین")
        window = _FakeWindow(input_tabs=_FakeInputTabs(model=object()))
        self._actions(window).analyze()
        self.assertEqual(window.statuses, ["خطای عددی"])
        self.assertEqual(window.results_view.show_calls, [])
        self.assertEqual(window.results_view.clear_calls, 1)

    def test_unexpected_analysis_error_clears_and_reports(self):
        """خطای غیرمنتظره تحلیل: پاک‌سازی یک بار، وضعیت «خطای غیرمنتظره»، یک پیام خطا."""
        self.run_analysis.side_effect = RuntimeError("ناشناخته")
        window = _FakeWindow(input_tabs=_FakeInputTabs(model=object()))
        self._actions(window).analyze()
        self.assertEqual(window.statuses, ["خطای غیرمنتظره"])
        self.assertEqual(window.results_view.clear_calls, 1)
        self.assertEqual(self.messagebox.showerror.call_count, 1)

    def test_results_view_value_error_triggers_display_error_path(self):
        """شکست results_view.show_report با ValueError: وضعیت «خطای نمایش»، پاک‌سازی هر دو ویو.

        گزارش معتبر است؛ خود show_report توسط mock مسیر خطای ValueError را ایجاد می‌کند.
        پس از شکست ویوی اول، ویوی دوم نباید نمایش داده شود.
        """
        self.run_analysis.return_value = _valid_report()
        results_view = _FakeView()
        results_view.show_report = mock.Mock(side_effect=ValueError("جدول بد"))
        window = _FakeWindow(
            input_tabs=_FakeInputTabs(model=object()),
            results_view=results_view,
        )
        self._actions(window).analyze()
        results_view.show_report.assert_called_once()
        self.assertEqual(window.plot_canvas.show_calls, [])
        self.assertEqual(window.statuses, ["خطای نمایش"])
        self.assertEqual(window.results_view.clear_calls, 1)
        self.assertEqual(window.plot_canvas.clear_calls, 1)
        self.messagebox.showerror.assert_called_once()
        self.assertIn("جدول بد", self.messagebox.showerror.call_args[0][1])

    def test_plot_canvas_unexpected_error_clears_and_reports(self):
        """شکست غیر ValueError در plot_canvas.show_report: مسیر «خطای غیرمنتظره» و پاک‌سازی هر دو ویو.

        گزارش معتبر است و results_view آن را پذیرفته؛ خود plot_canvas.show_report
        توسط mock یک RuntimeError (غیر از ValueError) ایجاد می‌کند.
        """
        self.run_analysis.return_value = _valid_report()
        plot_canvas = _FakeView()
        plot_canvas.show_report = mock.Mock(side_effect=RuntimeError("نمودار"))
        window = _FakeWindow(
            input_tabs=_FakeInputTabs(model=object()),
            plot_canvas=plot_canvas,
        )
        self._actions(window).analyze()
        plot_canvas.show_report.assert_called_once()
        self.assertEqual(len(window.results_view.show_calls), 1)
        self.assertEqual(window.statuses, ["خطای غیرمنتظره"])
        self.assertEqual(window.results_view.clear_calls, 1)
        self.assertEqual(window.plot_canvas.clear_calls, 1)
        self.assertEqual(self.messagebox.showerror.call_count, 1)
        self.assertIn("نمودار", self.messagebox.showerror.call_args[0][1])

    def test_plot_canvas_value_error_triggers_display_error_path(self):
        """plot_canvas.show_report با ValueError شکست می‌خورد: وضعیت «خطای نمایش»، پاک‌سازی هر دو ویو و متن خطا در پیام."""
        self.run_analysis.return_value = _valid_report()
        window = _FakeWindow(
            input_tabs=_FakeInputTabs(model=object()),
            plot_canvas=_FakeView(show_error=ValueError("نمودار بد")),
        )
        self._actions(window).analyze()
        self.assertEqual(len(window.results_view.show_calls), 1)
        self.assertEqual(window.statuses, ["خطای نمایش"])
        self.assertEqual(window.results_view.clear_calls, 1)
        self.assertEqual(window.plot_canvas.clear_calls, 1)
        self.messagebox.showerror.assert_called_once()
        self.assertIn("نمودار بد", self.messagebox.showerror.call_args[0][1])

    def test_results_view_unexpected_error_skips_plot_and_clears_both(self):
        """results_view.show_report خطای غیرمنتظره می‌دهد: نمودار نمایش داده نمی‌شود، وضعیت «خطای غیرمنتظره»، هر دو ویو پاک می‌شوند."""
        self.run_analysis.return_value = _valid_report()
        window = _FakeWindow(
            input_tabs=_FakeInputTabs(model=object()),
            results_view=_FakeView(show_error=RuntimeError("جدول غیرمنتظره")),
        )
        self._actions(window).analyze()
        self.assertEqual(window.plot_canvas.show_calls, [])
        self.assertEqual(window.statuses, ["خطای غیرمنتظره"])
        self.assertEqual(window.results_view.clear_calls, 1)
        self.assertEqual(window.plot_canvas.clear_calls, 1)
        self.assertEqual(self.messagebox.showerror.call_count, 1)
        self.assertEqual(self.messagebox.showerror.call_args[0][0], "خطای غیرمنتظره")
        self.assertIn("جدول غیرمنتظره", self.messagebox.showerror.call_args[0][1])

    def test_plot_failure_preserves_cleanup_failure_in_error_message(self):
        """نمایش نمودار شکست می‌خورد و پاک‌سازی جدول هم خطا می‌دهد: هر دو خطا در پیام نهایی باشند و پاک‌سازی نمودار انجام شود."""
        self.run_analysis.return_value = _valid_report()
        window = _FakeWindow(
            input_tabs=_FakeInputTabs(model=object()),
            results_view=_FakeView(clear_error=RuntimeError("جدول قفل")),
            plot_canvas=_FakeView(show_error=ValueError("نمودار بد")),
        )
        self._actions(window).analyze()
        self.assertEqual(window.statuses, ["خطای نمایش"])
        self.assertEqual(window.results_view.clear_calls, 1)
        self.assertEqual(window.plot_canvas.clear_calls, 1)
        self.messagebox.showerror.assert_called_once()
        message = self.messagebox.showerror.call_args[0][1]
        self.assertIn("نمودار بد", message)
        self.assertIn("جدول قفل", message)


# ----------------------------------------------------------------------
# پاک‌سازی نتایج
# ----------------------------------------------------------------------


class ClearResultsTest(_ActionsTestBase):

    def test_both_views_cleared_once_when_successful(self):
        window = _FakeWindow()
        self._actions(window)._clear_results()
        self.assertEqual(window.results_view.clear_calls, 1)
        self.assertEqual(window.plot_canvas.clear_calls, 1)

    def test_results_view_failure_does_not_block_plot_clear(self):
        window = _FakeWindow(results_view=_FakeView(clear_error=RuntimeError("جدول")))
        with self.assertRaises(ClearResultsError) as ctx:
            self._actions(window)._clear_results()
        self.assertEqual(window.plot_canvas.clear_calls, 1)
        self.assertEqual(len(ctx.exception.failures), 1)
        self.assertIn("جدول", ctx.exception.failures[0])

    def test_plot_canvas_failure_does_not_block_results_clear(self):
        """ترتیب: ابتدا results_view و سپس plot_canvas؛ شکست دومی مانع اولی نیست."""
        window = _FakeWindow(plot_canvas=_FakeView(clear_error=RuntimeError("نمودار")))
        with self.assertRaises(ClearResultsError) as ctx:
            self._actions(window)._clear_results()
        self.assertEqual(window.results_view.clear_calls, 1)
        self.assertIn("نمودار", ctx.exception.failures[0])

    def test_clear_results_safely_returns_empty_when_no_failure(self):
        window = _FakeWindow()
        self.assertEqual(self._actions(window)._clear_results_safely(), "")

    def test_clear_results_safely_returns_failure_text_without_raising(self):
        window = _FakeWindow(plot_canvas=_FakeView(clear_error=RuntimeError("نمودار")))
        note = self._actions(window)._clear_results_safely()
        self.assertTrue(note.startswith("\n"))
        self.assertIn("نمودار", note)


# ----------------------------------------------------------------------
# ذخیره
# ----------------------------------------------------------------------


class SaveTest(_ActionsTestBase):

    def setUp(self):
        super().setUp()
        self.save_project = self._patch_service("save_project")

    def test_success_sets_model_clears_results_and_reports(self):
        model = object()
        self.filedialog.asksaveasfilename.return_value = "/tmp/p.structpin"
        window = _FakeWindow(input_tabs=_FakeInputTabs(model=model))
        self._actions(window).save()
        self.save_project.assert_called_once_with(model, "/tmp/p.structpin")
        self.assertIs(window.current_model, model)
        self.assertEqual(window.results_view.clear_calls, 1)
        self.assertEqual(window.plot_canvas.clear_calls, 1)
        self.assertEqual(window.statuses, ["پروژه ذخیره شد"])
        self.messagebox.showinfo.assert_called_once_with(
            "ذخیره پروژه", "پروژه با موفقیت ذخیره شد.", parent=window
        )

    def test_success_with_clear_failure_keeps_success_message(self):
        """ذخیره موفق و خطای پاک‌سازی: موفقیت و خطای پاک‌سازی هر دو در پیام اطلاعات."""
        model = object()
        self.filedialog.asksaveasfilename.return_value = "/tmp/p.structpin"
        window = _FakeWindow(
            input_tabs=_FakeInputTabs(model=model),
            results_view=_FakeView(clear_error=RuntimeError("جدول قفل")),
        )
        self._actions(window).save()
        self.assertIs(window.current_model, model)
        self.assertEqual(window.statuses, ["پروژه ذخیره شد"])
        message = self.messagebox.showinfo.call_args[0][1]
        self.assertIn("با موفقیت ذخیره شد", message)
        self.assertIn("جدول قفل", message)

    def test_cancel_changes_nothing_and_does_not_call_save(self):
        self.filedialog.asksaveasfilename.return_value = ""
        old_model = object()
        window = _FakeWindow(input_tabs=_FakeInputTabs(model=object()), current_model=old_model)
        self._actions(window).save()
        self.save_project.assert_not_called()
        self.assertIs(window.current_model, old_model)
        self.assertEqual(window.results_view.clear_calls, 0)
        self.assertEqual(window.plot_canvas.clear_calls, 0)
        self.assertEqual(window.statuses, ["ذخیره لغو شد"])

    def test_cancel_does_not_clear_results_even_if_they_exist(self):
        """لغو ذخیره، نتایج موجود را دست نمی‌زند (کد save در مسیر لغو پاک‌سازی ندارد)."""
        self.filedialog.asksaveasfilename.return_value = ""
        window = _FakeWindow(input_tabs=_FakeInputTabs(model=object()))
        self._actions(window).save()
        self.assertEqual(window.results_view.clear_calls, 0)

    def test_project_file_error_keeps_previous_model(self):
        self.save_project.side_effect = ProjectFileError("نوشتن ممکن نیست")
        self.filedialog.asksaveasfilename.return_value = "/tmp/p.json"
        old_model = object()
        window = _FakeWindow(input_tabs=_FakeInputTabs(model=object()), current_model=old_model)
        self._actions(window).save()
        self.assertIs(window.current_model, old_model)
        self.assertEqual(window.statuses, ["خطای ذخیره"])
        self.messagebox.showerror.assert_called_once()

    def test_build_error_before_dialog_keeps_state_and_skips_dialog(self):
        """خطای ساخت مدل در save: پنجره ذخیره باز نمی‌شود، وضعیت «ذخیره انجام نشد»، مدل قبلی حفظ."""
        old_model = object()
        window = _FakeWindow(
            input_tabs=_FakeInputTabs(build_error=ModelBuildError("بد")),
            current_model=old_model,
        )
        self._actions(window).save()
        self.filedialog.asksaveasfilename.assert_not_called()
        self.save_project.assert_not_called()
        self.assertIs(window.current_model, old_model)
        self.assertEqual(window.statuses, ["ذخیره انجام نشد"])
        self.assertEqual(window.results_view.clear_calls, 0)


# ----------------------------------------------------------------------
# بارگذاری
# ----------------------------------------------------------------------


class LoadTest(_ActionsTestBase):

    def setUp(self):
        super().setUp()
        self.load_project = self._patch_service("load_project")
        self.model_to_dict = self._patch_service("model_to_dict", return_value={"name": "loaded"})
        # اعتبارسنجی مدل بارگذاری‌شده در actions با build_structural_model انجام می‌شود.
        # در تست‌های رفتار transactional، این اعتبارسنجی موفق فرض می‌شود؛ شکست آن در تست مستقل آزموده می‌شود.
        self.build_structural_model = self._patch_service(
            "build_structural_model", return_value=object()
        )

    def test_success_reads_snapshot_applies_form_and_clears_results(self):
        """ترتیب: model_to_dict، اعتبارسنجی، get_form_data (یک بار)، set_form_data (یک بار)، سپس مدل و پاک‌سازی."""
        loaded = object()
        self.load_project.return_value = loaded
        self.filedialog.askopenfilename.return_value = "/tmp/p.structpin"
        tabs = _FakeInputTabs(form={"name": "old"})
        window = _FakeWindow(input_tabs=tabs, current_model=object())
        self._actions(window).load()
        self.load_project.assert_called_once_with("/tmp/p.structpin")
        self.model_to_dict.assert_called_once_with(loaded)
        self.build_structural_model.assert_called_once_with({"name": "loaded"})
        self.assertEqual(tabs.get_calls, 1)
        self.assertEqual(tabs.set_calls, [{"name": "loaded"}])
        self.assertIs(window.current_model, loaded)
        self.assertEqual(window.results_view.clear_calls, 1)
        self.assertEqual(window.plot_canvas.clear_calls, 1)
        self.assertEqual(window.statuses, ["پروژه بارگذاری شد"])
        self.messagebox.showinfo.assert_called_once_with(
            "بارگذاری پروژه", "پروژه با موفقیت بارگذاری شد.", parent=window
        )

    def test_validation_runs_with_exact_payload_before_form_is_touched(self):
        """payload دقیقاً خروجی model_to_dict است و اعتبارسنجی پیش از get_form_data و set_form_data اجرا می‌شود."""
        loaded = object()
        payload = {"name": "loaded", "materials": [{"name": "فولاد", "E": 200.0}]}
        self.model_to_dict.return_value = payload
        self.load_project.return_value = loaded
        self.filedialog.askopenfilename.return_value = "/tmp/p.structpin"

        order = []
        tabs = _FakeInputTabs(form={"name": "old"})
        original_get = tabs.get_form_data
        original_set = tabs.set_form_data

        def tracked_get():
            order.append("get_form_data")
            return original_get()

        def tracked_set(data):
            order.append("set_form_data")
            return original_set(data)

        tabs.get_form_data = tracked_get
        tabs.set_form_data = tracked_set
        self.build_structural_model.side_effect = lambda data: order.append("validate") or object()

        window = _FakeWindow(input_tabs=tabs, current_model=object())
        self._actions(window).load()

        self.build_structural_model.assert_called_once_with(payload)
        self.assertEqual(order, ["validate", "get_form_data", "set_form_data"])
        self.assertEqual(tabs.set_calls, [payload])

    def test_validation_failure_touches_nothing(self):
        """build_structural_model با ModelBuildError شکست می‌خورد.

        get_form_data و set_form_data صفر بار فراخوانی شوند، current_model و نتایج
        دست‌نخورده بمانند، و پیام خطای اعتبارسنجی نمایش داده شود.
        """
        self.load_project.return_value = object()
        self.filedialog.askopenfilename.return_value = "/tmp/p.structpin"
        self.build_structural_model.side_effect = ModelBuildError("تکیه‌گاه متناقض روی گره «1»")
        tabs = _FakeInputTabs(form={"name": "old"})
        old_model = object()
        window = _FakeWindow(input_tabs=tabs, current_model=old_model)

        self._actions(window).load()

        self.assertEqual(tabs.get_calls, 0)
        self.assertEqual(tabs.set_calls, [])
        self.assertEqual(tabs.form, {"name": "old"})
        self.assertIs(window.current_model, old_model)
        self.assertEqual(window.results_view.clear_calls, 0)
        self.assertEqual(window.plot_canvas.clear_calls, 0)
        self.assertEqual(window.statuses, ["خطای بارگذاری"])
        self.messagebox.showerror.assert_called_once()
        title, message = self.messagebox.showerror.call_args[0]
        self.assertEqual(title, "بارگذاری پروژه")
        self.assertIn("قواعد فرم", message)
        self.assertIn("تکیه‌گاه متناقض روی گره «1»", message)
        self.messagebox.showinfo.assert_not_called()

    def test_unexpected_validation_error_touches_nothing_and_reports(self):
        """خطای غیرمنتظره در اعتبارسنجی: فرم و نتایج دست‌نخورده، وضعیت «خطای غیرمنتظره»."""
        self.load_project.return_value = object()
        self.filedialog.askopenfilename.return_value = "/tmp/p.structpin"
        self.build_structural_model.side_effect = RuntimeError("ناشناخته")
        tabs = _FakeInputTabs(form={"name": "old"})
        old_model = object()
        window = _FakeWindow(input_tabs=tabs, current_model=old_model)

        self._actions(window).load()

        self.assertEqual(tabs.get_calls, 0)
        self.assertEqual(tabs.set_calls, [])
        self.assertIs(window.current_model, old_model)
        self.assertEqual(window.results_view.clear_calls, 0)
        self.assertEqual(window.statuses, ["خطای غیرمنتظره"])
        self.assertIn("ناشناخته", self.messagebox.showerror.call_args[0][1])

    def test_cancel_changes_nothing_and_does_not_read_form(self):
        self.filedialog.askopenfilename.return_value = ""
        tabs = _FakeInputTabs()
        old_model = object()
        window = _FakeWindow(input_tabs=tabs, current_model=old_model)
        self._actions(window).load()
        self.load_project.assert_not_called()
        self.build_structural_model.assert_not_called()
        self.assertEqual(tabs.get_calls, 0)
        self.assertEqual(tabs.set_calls, [])
        self.assertIs(window.current_model, old_model)
        self.assertEqual(window.statuses, ["بارگذاری لغو شد"])

    def test_project_file_error_does_not_touch_form(self):
        self.load_project.side_effect = ProjectFileError("خراب")
        self.filedialog.askopenfilename.return_value = "/tmp/bad.json"
        tabs = _FakeInputTabs()
        old_model = object()
        window = _FakeWindow(input_tabs=tabs, current_model=old_model)
        self._actions(window).load()
        self.build_structural_model.assert_not_called()
        self.assertEqual(tabs.get_calls, 0)
        self.assertEqual(tabs.set_calls, [])
        self.assertIs(window.current_model, old_model)
        self.assertEqual(window.statuses, ["خطای بارگذاری"])

    def test_apply_failure_restores_snapshot_without_clearing_results(self):
        """set_form_data(داده جدید) شکست؛ بازگردانی موفق. ترتیب: [جدید، snapshot]؛
        current_model بدون تغییر؛ پاک‌سازی نتایج در این مسیر اجرا نمی‌شود."""
        self.filedialog.askopenfilename.return_value = "/tmp/p.structpin"
        self.load_project.return_value = object()
        tabs = _FakeInputTabs(form={"name": "snap"})
        apply_error = ValueError("ناسازگار")

        def flaky_set(data):
            tabs.set_calls.append(data)
            if data == {"name": "loaded"}:
                raise apply_error
            tabs.form = dict(data)

        tabs.set_form_data = flaky_set
        old_model = object()
        window = _FakeWindow(input_tabs=tabs, current_model=old_model)
        self._actions(window).load()
        self.assertEqual(tabs.set_calls, [{"name": "loaded"}, {"name": "snap"}])
        self.assertIs(window.current_model, old_model)
        self.assertEqual(window.results_view.clear_calls, 0)
        self.assertEqual(window.plot_canvas.clear_calls, 0)
        self.assertEqual(window.statuses, ["بارگذاری ناموفق؛ فرم قبلی بازگردانده شد"])
        message = self.messagebox.showerror.call_args[0][1]
        self.assertIn("فرم قبلی بازگردانده شد", message)
        self.assertIn("ناسازگار", message)

    def test_rollback_failure_reports_both_errors_and_clears_results(self):
        """هر دو set_form_data شکست؛ هر دو خطا در پیام، پاک‌سازی نتایج، current_model بدون تغییر."""
        self.filedialog.askopenfilename.return_value = "/tmp/p.structpin"
        self.load_project.return_value = object()
        tabs = _FakeInputTabs(form={"name": "snap"})
        calls = {"n": 0}

        def always_fail(data):
            calls["n"] += 1
            raise RuntimeError(f"خطای فرم {calls['n']}")

        tabs.set_form_data = always_fail
        old_model = object()
        window = _FakeWindow(input_tabs=tabs, current_model=old_model)
        self._actions(window).load()
        self.assertIs(window.current_model, old_model)
        self.assertEqual(window.statuses, ["بازگردانی فرم ناموفق بود"])
        self.assertEqual(window.results_view.clear_calls, 1)
        message = self.messagebox.showerror.call_args[0][1]
        self.assertIn("خطای بارگذاری: خطای فرم 1", message)
        self.assertIn("خطای بازگردانی: خطای فرم 2", message)

    def test_rollback_failure_with_clear_failure_appends_clear_note(self):
        """بازگردانی شکست و پاک‌سازی هم شکست: خطای پاک‌سازی به پیام الحاق می‌شود."""
        self.filedialog.askopenfilename.return_value = "/tmp/p.structpin"
        self.load_project.return_value = object()
        tabs = _FakeInputTabs()
        tabs.set_form_data = mock.Mock(side_effect=RuntimeError("فرم"))
        window = _FakeWindow(
            input_tabs=tabs,
            current_model=object(),
            plot_canvas=_FakeView(clear_error=RuntimeError("نمودار قفل")),
        )
        self._actions(window).load()
        message = self.messagebox.showerror.call_args[0][1]
        self.assertIn("نمودار قفل", message)


if __name__ == "__main__":
    unittest.main()
