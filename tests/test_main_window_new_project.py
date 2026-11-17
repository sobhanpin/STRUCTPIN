"""تست‌های MainWindow._on_new_project بدون ساخت پنجرهٔ واقعی Tkinter.

FakeWindow جای MainWindow را می‌گیرد و MainWindow._on_new_project مستقیم با آن
فراخوانی می‌شود. MainWindowActions واقعی با ویوهای ساختگی استفاده می‌شود.

هر دو ماژول main_window و actions از یک شیء مشترک tkinter.messagebox استفاده می‌کنند،
بنابراین patch یک‌باره روی main_window_module.messagebox برای هر دو مسیر کافی است.

اجرا (ریشهٔ مخزن):
    PYTHONPATH=src python -m unittest discover -s tests -p "test_main_window_new_project.py" -v
"""

import unittest
from unittest import mock

from structpin.ui import main_window as main_window_module
from structpin.ui.actions import MainWindowActions
from structpin.ui.main_window import MainWindow


class _FakeInputTabs:
    def __init__(self, clear_error=None):
        self.clear_error = clear_error
        self.clear_calls = 0

    def clear_form(self):
        self.clear_calls += 1
        if self.clear_error is not None:
            raise self.clear_error


class _FakeView:
    def __init__(self, clear_error=None):
        self.clear_error = clear_error
        self.clear_calls = 0

    def clear(self):
        self.clear_calls += 1
        if self.clear_error is not None:
            raise self.clear_error


class _FakeWindow:
    """جایگزین ساختگی MainWindow با ویژگی‌های لازم برای _on_new_project و MainWindowActions."""

    def __init__(self, input_tabs=None, results_view=None, plot_canvas=None, current_model=None):
        self.input_tabs = input_tabs if input_tabs is not None else _FakeInputTabs()
        self.results_view = results_view if results_view is not None else _FakeView()
        self.plot_canvas = plot_canvas if plot_canvas is not None else _FakeView()
        self.current_model = current_model
        self.statuses = []
        self._actions = MainWindowActions(self)

    def set_status(self, text):
        self.statuses.append(text)


class NewProjectTest(unittest.TestCase):

    def setUp(self):
        # messagebox مشترک است؛ یک patch برای askyesno و یک patch برای showerror کافی است.
        askyesno_patcher = mock.patch.object(main_window_module.messagebox, "askyesno", return_value=True)
        self.askyesno = askyesno_patcher.start()
        self.addCleanup(askyesno_patcher.stop)

        showerror_patcher = mock.patch.object(main_window_module.messagebox, "showerror")
        self.showerror = showerror_patcher.start()
        self.addCleanup(showerror_patcher.stop)

    def _run(self, window):
        MainWindow._on_new_project(window)

    def test_cancel_changes_nothing(self):
        """۱. لغو تأیید: فرم، مدل، نتایج و نمودار بدون تغییر؛ هیچ پیام خطا؛ وضعیتی ثبت نمی‌شود."""
        self.askyesno.return_value = False
        old_model = object()
        window = _FakeWindow(current_model=old_model)
        self._run(window)
        self.assertEqual(window.input_tabs.clear_calls, 0)
        self.assertIs(window.current_model, old_model)
        self.assertEqual(window.results_view.clear_calls, 0)
        self.assertEqual(window.plot_canvas.clear_calls, 0)
        self.assertEqual(window.statuses, [])
        self.showerror.assert_not_called()

    def test_confirm_clears_form_model_and_both_views_once(self):
        """۲. تأیید و پاک‌سازی موفق: فرم پاک، current_model=None، هر ویو یک بار، وضعیت «پروژه جدید»."""
        window = _FakeWindow(current_model=object())
        self._run(window)
        self.assertEqual(window.input_tabs.clear_calls, 1)
        self.assertIsNone(window.current_model)
        self.assertEqual(window.results_view.clear_calls, 1)
        self.assertEqual(window.plot_canvas.clear_calls, 1)
        self.assertEqual(window.statuses, ["پروژه جدید"])
        self.showerror.assert_not_called()

    def test_results_view_failure_still_clears_plot_and_reports(self):
        """۳. شکست results_view.clear: plot_canvas همچنان پاک می‌شود و خطا گزارش می‌شود."""
        window = _FakeWindow(
            current_model=object(),
            results_view=_FakeView(clear_error=RuntimeError("جدول قفل")),
        )
        self._run(window)
        self.assertEqual(window.plot_canvas.clear_calls, 1)
        self.assertIsNone(window.current_model)
        self.assertEqual(window.statuses, ["پروژه جدید؛ پاک‌سازی نتایج ناکامل بود"])
        self.showerror.assert_called_once()
        self.assertEqual(self.showerror.call_args[0][0], "پروژه جدید")
        self.assertIn("جدول قفل", self.showerror.call_args[0][1])

    def test_plot_canvas_failure_still_clears_results_and_reports(self):
        """۴. شکست plot_canvas.clear: results_view پاک شده و خطا گزارش می‌شود."""
        window = _FakeWindow(
            current_model=object(),
            plot_canvas=_FakeView(clear_error=RuntimeError("نمودار قفل")),
        )
        self._run(window)
        self.assertEqual(window.results_view.clear_calls, 1)
        self.assertIsNone(window.current_model)
        self.assertEqual(window.statuses, ["پروژه جدید؛ پاک‌سازی نتایج ناکامل بود"])
        self.showerror.assert_called_once()
        self.assertIn("نمودار قفل", self.showerror.call_args[0][1])

    def test_both_views_failing_reports_both_errors(self):
        """۵. شکست هم‌زمان هر دو ویو: هر دو خطا در پیام گزارش و فرم و مدل پاک می‌شوند."""
        window = _FakeWindow(
            current_model=object(),
            results_view=_FakeView(clear_error=RuntimeError("خطای الف")),
            plot_canvas=_FakeView(clear_error=RuntimeError("خطای ب")),
        )
        self._run(window)
        self.assertEqual(window.input_tabs.clear_calls, 1)
        self.assertIsNone(window.current_model)
        self.showerror.assert_called_once()
        message = self.showerror.call_args[0][1]
        self.assertIn("خطای الف", message)
        self.assertIn("خطای ب", message)

    def test_clear_form_failure_skips_results_and_keeps_model(self):
        """۶. شکست clear_form: گزارش غیرمنتظره از طریق actions با همان mock مشترک؛ نتایج پاک نمی‌شوند و مدل حفظ می‌شود."""
        old_model = object()
        window = _FakeWindow(
            input_tabs=_FakeInputTabs(clear_error=RuntimeError("فرم قفل")),
            current_model=old_model,
        )
        self._run(window)
        self.assertIs(window.current_model, old_model)
        self.assertEqual(window.results_view.clear_calls, 0)
        self.assertEqual(window.plot_canvas.clear_calls, 0)
        self.assertEqual(window.statuses, ["خطای غیرمنتظره"])
        self.showerror.assert_called_once()
        self.assertEqual(self.showerror.call_args[0][0], "خطای غیرمنتظره")
        self.assertIn("فرم قفل", self.showerror.call_args[0][1])

    def test_confirmation_dialog_receives_expected_title_and_text(self):
        """۷. بررسی پیام‌های دیالوگ: عنوان و متن تأیید با مقدار ثابت ماژول یکسان است."""
        window = _FakeWindow()
        self._run(window)
        self.askyesno.assert_called_once_with(
            "پروژه جدید", main_window_module._MSG_NEW_PROJECT_CONFIRM, parent=window
        )


if __name__ == "__main__":
    unittest.main()
