"""تست‌های MainWindow._on_new_project بدون ساخت پنجرهٔ واقعی Tkinter.

FakeWindow جای MainWindow را می‌گیرد. توابع فلگ و _on_new_project مستقیم از MainWindow
به‌عنوان ویژگی کلاس روی FakeWindow قرار می‌گیرند، تا همان کدِ واقعی اجرا شود.
MainWindowActions واقعی با ویوهای ساختگی استفاده می‌شود.
messagebox در ماژول main_window patch می‌شود. هیچ نمایشگری لازم نیست.

اجرا (ریشهٔ مخزن):
    $env:PYTHONPATH="src"; python -m unittest discover -s tests -p "test_main_window_new_project.py" -v
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
    """جایگزین ساختگی MainWindow.

    توابع فلگ و _on_new_project از MainWindow به‌عنوان ویژگی کلاس قرار گرفته‌اند
    تا همان کد واقعی روی این شیء اجرا شود.
    """

    _read_stale = MainWindow._read_stale
    _write_stale = MainWindow._write_stale
    _clear_outcome_of = MainWindow._clear_outcome_of
    _status_is = MainWindow._status_is
    _on_new_project = MainWindow._on_new_project

    def __init__(self, input_tabs=None, results_view=None, plot_canvas=None, current_model=None):
        self.input_tabs = input_tabs if input_tabs is not None else _FakeInputTabs()
        self.results_view = results_view if results_view is not None else _FakeView()
        self.plot_canvas = plot_canvas if plot_canvas is not None else _FakeView()
        self.current_model = current_model
        self._input_change_invalidated = False
        self._results_stale = False
        self._stale_error_reported = False
        self.statuses = []
        self._actions = MainWindowActions(self)

    def set_status(self, text):
        self.statuses.append(text)


class NewProjectTest(unittest.TestCase):

    def setUp(self):
        self.askyesno = self._patch(main_window_module.messagebox, "askyesno", return_value=True)
        self.showerror = self._patch(main_window_module.messagebox, "showerror")

    def _patch(self, target, name, **kwargs):
        patcher = mock.patch.object(target, name, **kwargs)
        mocked = patcher.start()
        self.addCleanup(patcher.stop)
        return mocked

    def _run(self, window):
        window._on_new_project()

    def test_cancel_changes_nothing(self):
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
        window = _FakeWindow(current_model=object())
        self._run(window)
        self.assertEqual(window.input_tabs.clear_calls, 1)
        self.assertIsNone(window.current_model)
        self.assertEqual(window.results_view.clear_calls, 1)
        self.assertEqual(window.plot_canvas.clear_calls, 1)
        self.assertEqual(window.statuses, ["پروژه جدید"])
        self.assertEqual(
            (window._input_change_invalidated, window._results_stale, window._stale_error_reported),
            (True, False, False),
        )
        self.showerror.assert_not_called()

    def test_results_view_failure_still_clears_plot_and_reports(self):
        window = _FakeWindow(
            current_model=object(),
            results_view=_FakeView(clear_error=RuntimeError("جدول قفل")),
        )
        self._run(window)
        self.assertEqual(window.plot_canvas.clear_calls, 1)
        self.assertIsNone(window.current_model)
        self.assertEqual(window.statuses, ["پروژه جدید؛ پاک‌سازی نتایج ناکامل بود"])
        self.assertTrue(window._results_stale)
        self.showerror.assert_called_once()
        self.assertEqual(self.showerror.call_args[0][0], "پروژه جدید")
        self.assertIn("جدول قفل", self.showerror.call_args[0][1])

    def test_plot_canvas_failure_still_clears_results_and_reports(self):
        window = _FakeWindow(
            current_model=object(),
            plot_canvas=_FakeView(clear_error=RuntimeError("نمودار قفل")),
        )
        self._run(window)
        self.assertEqual(window.results_view.clear_calls, 1)
        self.assertIsNone(window.current_model)
        self.assertEqual(window.statuses, ["پروژه جدید؛ پاک‌سازی نتایج ناکامل بود"])
        self.assertTrue(window._results_stale)
        self.showerror.assert_called_once()
        self.assertIn("نمودار قفل", self.showerror.call_args[0][1])

    def test_both_views_failing_reports_both_errors(self):
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
        window = _FakeWindow()
        self._run(window)
        self.askyesno.assert_called_once_with(
            "پروژه جدید", main_window_module._MSG_NEW_PROJECT_CONFIRM, parent=window
        )


if __name__ == "__main__":
    unittest.main()
