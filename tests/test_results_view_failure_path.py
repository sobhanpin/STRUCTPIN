"""تست رگرسیون: ResultsView.show_report باید خطای اصلی را حفظ کند.

سناریو: خطای درج گزارش، سپس خطای clear() در مسیر پاک‌سازی.
انتظار: خطای اصلی همان شیء پرتاب‌شده باشد و خطای پاک‌سازی به‌عنوان توضیح
(note) به آن افزوده شده و قابل تشخیص باشد.

این تست‌ها پنجرهٔ Tk نمی‌سازند؛ show_report را روی یک شیء ساختگی اجرا می‌کنند.
فقط به ماژول tkinter نیاز دارند. اگر tkinter نصب نباشد، تست‌ها Skip می‌شوند و
Skip موفقیت حساب نمی‌شود.

اجرا (ریشهٔ مخزن):
    PYTHONPATH=src python -m unittest discover -s tests -p "test_results_view_failure_path.py" -v
"""

import unittest

from structpin.services.analysis_service import AnalysisReport

try:
    from structpin.ui import results_view as _results_view
except ModuleNotFoundError as _import_error:
    # فقط نبود واقعی tkinter (یا زیرماژول‌ها و بخش بومی آن، _tkinter) مجاز به Skip است.
    # هر خطای دیگر، از جمله نبود وابستگی‌های خود پروژه، دوباره پرتاب می‌شود.
    _missing = _import_error.name or ""
    if _missing not in ("tkinter", "_tkinter") and not _missing.startswith("tkinter."):
        raise
    _results_view = None
    _IMPORT_ERROR_TEXT = str(_import_error)


def _valid_report():
    """گزارش معتبر کوچک با ساختار واقعی AnalysisReport."""
    return AnalysisReport(
        displacements={1: (0.0, 0.0, 0.0)},
        reactions={1: (0.0, 0.0, 0.0)},
        member_end_actions={1: ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0))},
        internal_forces={
            1: {
                "x": (0.0, 1.0),
                "N": (0.0, 0.0),
                "V": (0.0, 0.0),
                "M": (0.0, 0.0),
            },
        },
        n_points=1,
        warnings=(),
    )


class _FakeResultsView:
    """ResultsView ساختگی: فقط متدهایی را دارد که show_report به آن‌ها نیاز دارد.

    insert_error: خطایی که مرحلهٔ درج هشدارها پرتاب می‌کند.
    clear_outcomes: نتیجهٔ هر فراخوانی clear به ترتیب؛ None یعنی موفق، در غیر این
    صورت همان استثنا پرتاب می‌شود.
    """

    def __init__(self, insert_error, clear_outcomes):
        self._insert_error = insert_error
        self._clear_outcomes = list(clear_outcomes)
        self.clear_calls = 0
        self._displacement_tree = None
        self._reaction_tree = None
        self._end_action_tree = None
        self._internal_tree = None
        self._fill_tree = lambda tree, rows: None
        self._fill_summary = lambda report, warning_count: None

    def clear(self):
        self.clear_calls += 1
        outcome = self._clear_outcomes.pop(0)
        if outcome is not None:
            raise outcome

    def _fill_warnings(self, warnings):
        raise self._insert_error


class ResultsViewShowReportFailurePathTest(unittest.TestCase):

    def setUp(self):
        if _results_view is None:
            self.skipTest(f"tkinter در دسترس نیست: {_IMPORT_ERROR_TEXT}")
        self.show_report = _results_view.ResultsView.show_report

    def test_original_insert_error_survives_failing_cleanup(self):
        insert_error = ValueError("خطای درج تستی")
        cleanup_error = RuntimeError("خطای پاک‌سازی تستی")
        fake = _FakeResultsView(insert_error, clear_outcomes=[None, cleanup_error])

        with self.assertRaises(ValueError) as ctx:
            self.show_report(fake, _valid_report())

        self.assertIs(ctx.exception, insert_error)
        self.assertEqual(fake.clear_calls, 2)

    def test_cleanup_error_is_attached_as_note_and_is_identifiable(self):
        insert_error = ValueError("خطای درج تستی")
        cleanup_error = RuntimeError("خطای پاک‌سازی تستی")
        fake = _FakeResultsView(insert_error, clear_outcomes=[None, cleanup_error])

        with self.assertRaises(ValueError) as ctx:
            self.show_report(fake, _valid_report())

        notes = getattr(ctx.exception, "__notes__", [])
        self.assertEqual(len(notes), 1, msg=f"notes={notes!r}")
        self.assertIn("RuntimeError", notes[0])
        self.assertIn("خطای پاک‌سازی تستی", notes[0])

    def test_no_note_when_cleanup_succeeds(self):
        insert_error = ValueError("خطای درج تستی")
        fake = _FakeResultsView(insert_error, clear_outcomes=[None, None])

        with self.assertRaises(ValueError) as ctx:
            self.show_report(fake, _valid_report())

        self.assertIs(ctx.exception, insert_error)
        self.assertEqual(getattr(ctx.exception, "__notes__", []), [])


if __name__ == "__main__":
    unittest.main()
