
"""تست‌های ایجاد پروژه جدید در پنجره اصلی STRUCTPIN."""

import unittest
from unittest import mock

from structpin.ui import main_window as main_window_module
from structpin.ui.actions import MainWindowActions
from structpin.ui.main_window import MainWindow


class FakeInputTabs:
    def __init__(self, clear_error=None):
        self.clear_error = clear_error
        self.clear_calls = 0

    def clear_form(self):
        self.clear_calls += 1
        if self.clear_error is not None:
            raise self.clear_error


class FakeView:
    def __init__(self, clear_error=None):
        self.clear_error = clear_error
        self.clear_calls = 0

    def clear(self):
        self.clear_calls += 1
        if self.clear_error is not None:
            raise self.clear_error


class FakeWindow:
    def __init__(
        self,
        results_error=None,
        plot_error=None,
        form_error=None,
    ):
        self.input_tabs = FakeInputTabs(form_error)
        self.results_view = FakeView(results_error)
        self.plot_canvas = FakeView(plot_error)

        self.current_model = object()
        self.status = "وضعیت قبلی"

        # همان Actions واقعی برنامه با پنجره آزمایشی
        self._actions = MainWindowActions(self)

    def set_status(self, message):
        self.status = str(message)


class NewProjectTest(unittest.TestCase):
    def setUp(self):
        self.askyesno_patcher = mock.patch.object(
            main_window_module.messagebox,
            "askyesno",
            return_value=True,
        )
        self.showerror_patcher = mock.patch.object(
            main_window_module.messagebox,
            "showerror",
        )

        self.askyesno = self.askyesno_patcher.start()
        self.showerror = self.showerror_patcher.start()

        self.addCleanup(self.askyesno_patcher.stop)
        self.addCleanup(self.showerror_patcher.stop)

    def _run(self, window):
        MainWindow._on_new_project(window)

    def test_cancel_changes_nothing(self):
        """۱. لغو پروژه جدید هیچ تغییری ایجاد نمی‌کند."""
        self.askyesno.return_value = False

        window = FakeWindow()
        previous_model = window.current_model

        self._run(window)

        self.assertEqual(window.input_tabs.clear_calls, 0)
        self.assertIs(window.current_model, previous_model)
        self.assertEqual(window.results_view.clear_calls, 0)
        self.assertEqual(window.plot_canvas.clear_calls, 0)
        self.assertEqual(window.status, "وضعیت قبلی")
        self.showerror.assert_not_called()

    def test_confirm_clears_form_model_and_both_views_once(self):
        """۲. تأیید، فرم و مدل و هر دو ویو را پاک می‌کند."""
        window = FakeWindow()

        self._run(window)

        self.assertEqual(window.input_tabs.clear_calls, 1)
        self.assertIsNone(window.current_model)
        self.assertEqual(window.results_view.clear_calls, 1)
        self.assertEqual(window.plot_canvas.clear_calls, 1)
        self.assertEqual(window.status, "پروژه جدید")
        self.showerror.assert_not_called()

    def test_results_view_failure_still_clears_plot_and_reports(self):
        """۳. شکست پاک‌سازی نتایج مانع پاک‌سازی نمودار نمی‌شود."""
        window = FakeWindow(
            results_error=RuntimeError("خطای پاک‌سازی نتایج")
        )

        self._run(window)

        self.assertEqual(window.results_view.clear_calls, 1)
        self.assertEqual(window.plot_canvas.clear_calls, 1)
        self.assertIsNone(window.current_model)
        self.assertEqual(window.input_tabs.clear_calls, 1)
        self.assertEqual(self.showerror.call_count, 1)

        error_text = self.showerror.call_args.args[1]
        self.assertIn("خطای پاک‌سازی نتایج", error_text)

    def test_plot_canvas_failure_still_clears_results_and_reports(self):
        """۴. شکست پاک‌سازی نمودار مانع پاک‌سازی نتایج نمی‌شود."""
        window = FakeWindow(
            plot_error=RuntimeError("خطای پاک‌سازی نمودار")
        )

        self._run(window)

        self.assertEqual(window.results_view.clear_calls, 1)
        self.assertEqual(window.plot_canvas.clear_calls, 1)
        self.assertIsNone(window.current_model)
        self.assertEqual(window.input_tabs.clear_calls, 1)
        self.assertEqual(self.showerror.call_count, 1)

        error_text = self.showerror.call_args.args[1]
        self.assertIn("خطای پاک‌سازی نمودار", error_text)

    def test_both_views_failing_reports_both_errors(self):
        """۵. شکست هم‌زمان هر دو ویو، هر دو خطا را گزارش می‌کند."""
        window = FakeWindow(
            results_error=RuntimeError("خطای نتایج"),
            plot_error=RuntimeError("خطای نمودار"),
        )

        self._run(window)

        self.assertEqual(window.results_view.clear_calls, 1)
        self.assertEqual(window.plot_canvas.clear_calls, 1)
        self.assertEqual(window.input_tabs.clear_calls, 1)
        self.assertIsNone(window.current_model)
        self.assertEqual(self.showerror.call_count, 1)

        error_text = self.showerror.call_args.args[1]
        self.assertIn("خطای نتایج", error_text)
        self.assertIn("خطای نمودار", error_text)

    def test_clear_form_failure_keeps_model_and_skips_results(self):
        """۶. شکست پاک‌سازی فرم، مدل و نتایج را حفظ می‌کند."""
        window = FakeWindow(
            form_error=RuntimeError("فرم قفل است")
        )
        previous_model = window.current_model

        self._run(window)

        self.assertEqual(window.input_tabs.clear_calls, 1)
        self.assertIs(window.current_model, previous_model)
        self.assertEqual(window.results_view.clear_calls, 0)
        self.assertEqual(window.plot_canvas.clear_calls, 0)
        self.assertEqual(self.showerror.call_count, 1)

        error_text = self.showerror.call_args.args[1]
        self.assertIn("فرم قفل است", error_text)

    def test_confirmation_dialog_receives_expected_title_and_text(self):
        """۷. عنوان و متن پنجره تأیید بررسی می‌شود."""
        window = FakeWindow()

        self._run(window)

        self.askyesno.assert_called_once_with(
            "پروژه جدید",
            main_window_module._MSG_NEW_PROJECT_CONFIRM,
            parent=window,
        )


if __name__ == "__main__":
    unittest.main()
