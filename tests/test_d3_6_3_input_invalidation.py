"""تست‌های D3-6.3: نامعتبرشدن نتایج پس از تغییر واقعی ورودی.

- MainWindowInvalidationTest: منطق MainWindow با FakeWindow و MainWindowActions واقعی.
  به نمایشگر نیاز ندارد؛ messagebox و run_frame_analysis با mock جایگزین شده‌اند.
  گزارش‌های تحلیل موفق، AnalysisReport معتبر هستند تا اعتبارسنجی مشترک
  validate_report_numbers در actions روی داده واقعی اجرا شود.
- InputTabsCallbackTest: کد واقعی InputTabs با Tk. بدون نمایشگر کل کلاس SkipTest می‌دهد.
  Skip موفقیت حساب نمی‌شود.

اجرا (ریشهٔ مخزن):
    $env:PYTHONPATH="src"; python -m unittest discover -s tests -p "test_d3_6_3_input_invalidation.py" -v
"""

import inspect
import tkinter as tk
import unittest
from unittest import mock

from structpin.services.analysis_service import AnalysisInputError, AnalysisReport
from structpin.ui import actions as actions_module
from structpin.ui import main_window as main_window_module
from structpin.ui.actions import MainWindowActions
from structpin.ui.main_window import MainWindow

_STATUS_INVALIDATED = "ورودی تغییر کرد؛ نتایج قبلی پاک شدند"
_STATUS_STALE = "ورودی تغییر کرد؛ پاک‌سازی نتایج ناکامل بود"
_STATUS_ANALYSIS_OK = "تحلیل انجام شد"
_STATUS_NEW_PROJECT = "پروژه جدید"
_STATUS_NEW_PROJECT_STALE = "پروژه جدید؛ پاک‌سازی نتایج ناکامل بود"


def _valid_report():
    """گزارش معتبر با ساختار واقعی AnalysisReport (مقادیر نمونه، بدون محاسبهٔ مهندسی)."""
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


class _FakeVar:
    def __init__(self, value=""):
        self._value = value

    def get(self):
        return self._value

    def set(self, value):
        self._value = value


class _FakeView:
    """ویو ساختگی. هر فراخوانی clear یک عنصر از clear_errors را مصرف می‌کند."""

    def __init__(self, clear_errors=None):
        self.clear_errors = list(clear_errors or [])
        self.clear_calls = 0
        self.show_calls = []

    def clear(self):
        self.clear_calls += 1
        if self.clear_errors:
            error = self.clear_errors.pop(0)
            if error is not None:
                raise error

    def show_report(self, report):
        self.show_calls.append(report)


class _FakeInputTabs:
    def __init__(self, model=None):
        self.model = model
        self.clear_form_calls = 0

    def build_model(self):
        return self.model

    def clear_form(self):
        self.clear_form_calls += 1


class _FakeWindow:
    def __init__(self, input_tabs=None, results_view=None, plot_canvas=None):
        self.current_model = None
        self.input_tabs = input_tabs if input_tabs is not None else _FakeInputTabs(model=object())
        self.results_view = results_view if results_view is not None else _FakeView()
        self.plot_canvas = plot_canvas if plot_canvas is not None else _FakeView()
        self.status_var = _FakeVar("آماده")
        self._input_change_invalidated = False
        self._results_stale = False
        self._stale_error_reported = False
        self._actions = MainWindowActions(self)

    def set_status(self, text):
        self.status_var.set(text)

    def _reset_invalidation_flags(self):
        self._input_change_invalidated = False
        self._results_stale = False
        self._stale_error_reported = False


class _Base(unittest.TestCase):
    def setUp(self):
        self.askyesno = self._patch(main_window_module.messagebox, "askyesno", return_value=True)
        self.showerror = self._patch(main_window_module.messagebox, "showerror")
        self.showinfo = self._patch(actions_module.messagebox, "showinfo")
        self.run_analysis = self._patch(actions_module, "run_frame_analysis", return_value=_valid_report())

    def _patch(self, target, name, **kwargs):
        patcher = mock.patch.object(target, name, **kwargs)
        mocked = patcher.start()
        self.addCleanup(patcher.stop)
        return mocked


class MainWindowInvalidationTest(_Base):

    def test_first_change_with_model_invalidates_and_clears_both_views(self):
        window = _FakeWindow()
        window.current_model = object()
        MainWindow._on_input_changed(window)
        self.assertIsNone(window.current_model)
        self.assertEqual(window.results_view.clear_calls, 1)
        self.assertEqual(window.plot_canvas.clear_calls, 1)
        self.assertEqual(window.status_var.get(), _STATUS_INVALIDATED)
        self.assertTrue(window._input_change_invalidated)

    def test_first_change_without_model_or_stale_does_nothing(self):
        window = _FakeWindow()
        MainWindow._on_input_changed(window)
        self.assertEqual(window.results_view.clear_calls, 0)
        self.assertEqual(window.plot_canvas.clear_calls, 0)
        self.assertEqual(window.status_var.get(), "آماده")
        self.assertFalse(window._input_change_invalidated)

    def test_later_changes_after_successful_clear_do_not_clear_again(self):
        window = _FakeWindow()
        window.current_model = object()
        MainWindow._on_input_changed(window)
        MainWindow._on_input_changed(window)
        MainWindow._on_input_changed(window)
        self.assertEqual(window.results_view.clear_calls, 1)
        self.assertEqual(window.plot_canvas.clear_calls, 1)

    def test_failed_clear_is_retried_on_next_change(self):
        window = _FakeWindow(results_view=_FakeView(clear_errors=[RuntimeError("قفل")]))
        window.current_model = object()
        MainWindow._on_input_changed(window)
        self.assertTrue(window._results_stale)
        self.assertEqual(window.status_var.get(), _STATUS_STALE)

        MainWindow._on_input_changed(window)
        self.assertEqual(window.results_view.clear_calls, 2)
        self.assertFalse(window._results_stale)
        self.assertEqual(window.status_var.get(), _STATUS_INVALIDATED)

    def test_error_dialog_is_shown_once_per_failure_episode(self):
        window = _FakeWindow(results_view=_FakeView(
            clear_errors=[RuntimeError("قفل"), RuntimeError("قفل"), RuntimeError("قفل")]
        ))
        window.current_model = object()
        MainWindow._on_input_changed(window)
        MainWindow._on_input_changed(window)
        MainWindow._on_input_changed(window)
        self.assertEqual(window.results_view.clear_calls, 3)
        self.assertEqual(self.showerror.call_count, 1)
        self.assertEqual(window.status_var.get(), _STATUS_STALE)

    def test_success_ends_episode_and_new_failure_reports_again(self):
        # مصرف خطاها: تغییر اول شکست، تغییر دوم موفق، ساخت مدل (موفق)، تغییر سوم شکست
        window = _FakeWindow(results_view=_FakeView(
            clear_errors=[RuntimeError("اول"), None, None, RuntimeError("دوم")]
        ))
        window.current_model = object()
        MainWindow._on_input_changed(window)
        self.assertEqual(self.showerror.call_count, 1)

        MainWindow._on_input_changed(window)
        self.assertFalse(window._stale_error_reported)

        MainWindow._on_build_model(window)
        self.assertIsNotNone(window.current_model)

        MainWindow._on_input_changed(window)
        self.assertEqual(self.showerror.call_count, 2)

    def test_new_project_cancel_changes_nothing(self):
        self.askyesno.return_value = False
        window = _FakeWindow()
        model = object()
        window.current_model = model
        MainWindow._on_new_project(window)
        self.assertIs(window.current_model, model)
        self.assertEqual(window.input_tabs.clear_form_calls, 0)
        self.assertEqual(window.results_view.clear_calls, 0)
        self.assertEqual(window.plot_canvas.clear_calls, 0)

    def test_new_project_success_clears_form_model_and_views(self):
        window = _FakeWindow()
        window.current_model = object()
        MainWindow._on_new_project(window)
        self.assertEqual(window.input_tabs.clear_form_calls, 1)
        self.assertIsNone(window.current_model)
        self.assertEqual(window.results_view.clear_calls, 1)
        self.assertEqual(window.plot_canvas.clear_calls, 1)
        self.assertEqual(window.status_var.get(), _STATUS_NEW_PROJECT)
        self.showerror.assert_not_called()

    def test_new_project_clear_failure_reports_once_and_marks_stale(self):
        window = _FakeWindow(results_view=_FakeView(clear_errors=[RuntimeError("قفل")]))
        window.current_model = object()
        MainWindow._on_new_project(window)
        self.assertIsNone(window.current_model)
        self.assertTrue(window._results_stale)
        self.assertEqual(window.status_var.get(), _STATUS_NEW_PROJECT_STALE)
        self.assertEqual(self.showerror.call_count, 1)

    def test_save_and_load_buttons_use_real_action_names(self):
        source = inspect.getsource(MainWindow._build_toolbar)
        self.assertIn("command=self._actions.save,", source)
        self.assertIn("command=self._actions.load,", source)
        self.assertNotIn("save_project", source)
        self.assertNotIn("load_project", source)

    def test_successful_analyze_after_stale_failure_resets_all_flags(self):
        """تحلیل موفق با گزارش معتبر AnalysisReport پس از شکست stale.

        گزارش معتبر از run_frame_analysis برمی‌گردد، از validate_report_numbers
        عبور می‌کند و به results_view.show_report می‌رسد. سپس هر سه فلگ بازنشانی می‌شوند.
        """
        report = _valid_report()
        self.run_analysis.return_value = report
        window = _FakeWindow(input_tabs=_FakeInputTabs(model=object()))
        window._results_stale = True
        window._stale_error_reported = True
        window._input_change_invalidated = True
        MainWindow._on_analyze(window)
        self.assertEqual(len(window.results_view.show_calls), 1)
        self.assertIs(window.results_view.show_calls[0], report)
        self.assertEqual(window.status_var.get(), _STATUS_ANALYSIS_OK)
        self.assertFalse(window._results_stale)
        self.assertFalse(window._stale_error_reported)
        self.assertFalse(window._input_change_invalidated)

    def test_failed_analyze_keeps_stale_flags(self):
        self.run_analysis.side_effect = AnalysisInputError("ناپایدار")
        window = _FakeWindow(input_tabs=_FakeInputTabs(model=object()))
        window._results_stale = True
        window._stale_error_reported = True
        MainWindow._on_analyze(window)
        self.assertNotEqual(window.status_var.get(), _STATUS_ANALYSIS_OK)
        self.assertTrue(window._results_stale)
        self.assertTrue(window._stale_error_reported)

    def test_successful_build_only_rearms_change_detection(self):
        # توجه: این تست هنوز انتظار رفتار قبلی (حفظ فلگ‌های stale پس از ساخت موفق) را دارد.
        # طبق تصمیم تأییدشده، با جایگزینی main_window.py این انتظار باید به رفتار جدید تغییر کند.
        window = _FakeWindow(input_tabs=_FakeInputTabs(model=object()))
        window._results_stale = True
        window._stale_error_reported = True
        window._input_change_invalidated = True
        MainWindow._on_build_model(window)
        self.assertIsNotNone(window.current_model)
        self.assertFalse(window._input_change_invalidated)
        self.assertTrue(window._results_stale)
        self.assertTrue(window._stale_error_reported)


def _make_root():
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        raise unittest.SkipTest(f"نمایشگر در دسترس نیست: {exc}")
    root.withdraw()
    return root


class _FakeEntry:
    def __init__(self, value):
        self._value = value

    def get(self):
        return self._value

    def destroy(self):
        pass


def _open_editor(table, index, key, value):
    table._editor = _FakeEntry(value)
    table._edit_index = index
    table._edit_key = key


def _row_iid(table, index):
    return table._tree.get_children()[index]


class InputTabsCallbackTest(unittest.TestCase):
    """کد واقعی InputTabs با Tk. نیاز به نمایشگر."""

    @classmethod
    def setUpClass(cls):
        from structpin.ui.input_tabs import InputTabs
        cls.InputTabs = InputTabs
        cls.root = _make_root()

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def setUp(self):
        self.calls = []
        self.tabs = self.InputTabs(self.root)
        self.tabs.set_on_change(lambda: self.calls.append(1))

    def tearDown(self):
        self.tabs.destroy()

    def test_project_name_change_fires_once_and_same_value_does_not(self):
        self.tabs._project_name.set("الف")
        self.assertEqual(len(self.calls), 1)
        self.tabs._project_name.set("الف")
        self.assertEqual(len(self.calls), 1)

    def test_add_row_fires_once(self):
        self.tabs._tables["nodes"].add_row()
        self.assertEqual(len(self.calls), 1)

    def test_add_row_with_open_editor_keeps_pending_edit_and_fires_once(self):
        table = self.tabs._tables["nodes"]
        table.add_row()
        self.calls.clear()
        _open_editor(table, 0, "id", "7")
        table.add_row()
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(table._rows[0]["id"], "7")
        self.assertEqual(len(table._rows), 2)

    def test_delete_row_with_open_editor_keeps_pending_edit_and_fires_once(self):
        table = self.tabs._tables["nodes"]
        table.add_row()
        table.add_row()
        self.calls.clear()
        _open_editor(table, 1, "id", "9")
        table._tree.selection_set([_row_iid(table, 0)])
        table.delete_selected()
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(len(table._rows), 1)
        self.assertEqual(table._rows[0]["id"], "9")

    def test_commit_changed_value_fires_once(self):
        table = self.tabs._tables["nodes"]
        table.add_row()
        self.calls.clear()
        _open_editor(table, 0, "id", "7")
        table._commit_edit()
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(table._rows[0]["id"], "7")

    def test_commit_same_value_does_not_fire(self):
        table = self.tabs._tables["nodes"]
        table.add_row()
        self.calls.clear()
        _open_editor(table, 0, "id", "")
        table._commit_edit()
        self.assertEqual(self.calls, [])

    def test_commit_twice_as_focusout_after_return_fires_once(self):
        table = self.tabs._tables["nodes"]
        table.add_row()
        self.calls.clear()
        _open_editor(table, 0, "id", "5")
        table._commit_edit()
        table._commit_edit()
        self.assertEqual(len(self.calls), 1)

    def test_cancel_edit_fires_nothing_and_keeps_value(self):
        table = self.tabs._tables["nodes"]
        table.add_row()
        self.calls.clear()
        _open_editor(table, 0, "id", "zzz")
        table._cancel_edit()
        self.assertEqual(self.calls, [])
        self.assertEqual(table._rows[0]["id"], "")

    def test_bool_double_click_fires_once_and_returns_real_bool(self):
        table = self.tabs._tables["restraints"]
        table.add_row()
        self.calls.clear()
        iid = _row_iid(table, 0)
        event = mock.Mock(x=1, y=1)
        with mock.patch.object(table._tree, "identify_region", return_value="cell"), \
                mock.patch.object(table._tree, "identify_row", return_value=iid), \
                mock.patch.object(table._tree, "identify_column", return_value="#2"):
            table._on_double_click(event)
        self.assertEqual(len(self.calls), 1)
        self.assertIsInstance(table._rows[0]["ux"].get(), bool)
        self.assertIs(table.get_rows()[0]["ux"], True)

    def test_bool_double_click_with_open_editor_keeps_pending_edit_and_fires_once(self):
        table = self.tabs._tables["restraints"]
        table.add_row()
        self.calls.clear()
        _open_editor(table, 0, "node", "3")
        iid = _row_iid(table, 0)
        event = mock.Mock(x=1, y=1)
        with mock.patch.object(table._tree, "identify_region", return_value="cell"), \
                mock.patch.object(table._tree, "identify_row", return_value=iid), \
                mock.patch.object(table._tree, "identify_column", return_value="#3"):
            table._on_double_click(event)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(table._rows[0]["node"], "3")
        self.assertIs(table._rows[0]["uy"].get(), True)

    def test_set_form_data_is_quiet(self):
        self.tabs.set_form_data({"name": "P", "nodes": [{"id": 1, "x": 0.0, "y": 0.0}]})
        self.assertEqual(self.calls, [])

    def test_clear_form_is_quiet(self):
        self.tabs._project_name.set("الف")
        self.tabs._tables["nodes"].add_row()
        self.calls.clear()
        self.tabs.clear_form()
        self.assertEqual(self.calls, [])

    def test_get_form_data_is_quiet_and_applies_open_edit(self):
        table = self.tabs._tables["nodes"]
        table.add_row()
        self.calls.clear()
        _open_editor(table, 0, "x", "3.5")
        data = self.tabs.get_form_data()
        self.assertEqual(self.calls, [])
        self.assertEqual(data["nodes"][0]["x"], "3.5")

    def test_clear_button_with_data_fires_exactly_once(self):
        self.tabs._project_name.set("الف")
        self.calls.clear()
        self.tabs._on_clear_button()
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.tabs.get_form_data()["name"], "")

    def test_clear_button_on_empty_form_fires_nothing(self):
        self.tabs.clear_form()
        self.calls.clear()
        self.tabs._on_clear_button()
        self.assertEqual(self.calls, [])

    def test_set_on_change_after_construction_and_disable(self):
        tabs = self.InputTabs(self.root)
        try:
            calls = []
            tabs.set_on_change(lambda: calls.append(1))
            tabs._project_name.set("الف")
            self.assertEqual(len(calls), 1)
            tabs.set_on_change(None)
            tabs._project_name.set("ب")
            self.assertEqual(len(calls), 1)
        finally:
            tabs.destroy()

    def test_set_on_change_rejects_non_callable(self):
        with self.assertRaises(TypeError):
            self.tabs.set_on_change("not callable")


if __name__ == "__main__":
    unittest.main()
