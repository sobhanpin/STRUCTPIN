"""Tests for structpin.ui.plot_canvas.

- Numeric and validation tests run without any display.
- Tk tests require a display. When none is available they are SKIPPED with a
  reason. A skip is not a pass and is reported explicitly by unittest.
"""

from __future__ import annotations

import math
import sys
import tkinter as tk
import unittest
from pathlib import Path
from unittest import mock

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from structpin.services.analysis_service import AnalysisReport  # noqa: E402
from structpin.ui import plot_canvas as pc  # noqa: E402

MAX = sys.float_info.max


def make_report(internal_forces, n_points=3):
    return AnalysisReport(
        displacements={},
        reactions={},
        member_end_actions={},
        internal_forces=internal_forces,
        n_points=n_points,
        warnings=(),
    )


def member(
    x=(0.0, 1.0, 2.0),
    n=(1.0, 1.0, 1.0),
    v=(0.0, 1.0, 2.0),
    m=(0.0, -1.0, 0.0),
):
    return {"x": x, "N": n, "V": v, "M": m}


class _Plain:
    """Helper class used to build ambiguous member labels."""

    def __str__(self):
        return "A"


# ----------------------------------------------------------------------
# Validation of input data (no display required)
# ----------------------------------------------------------------------


class ValidationTests(unittest.TestCase):
    def test_nan_value_is_rejected(self):
        report = make_report({1: member(n=(float("nan"), 1.0, 1.0))})
        with self.assertRaises(ValueError):
            pc._prepare(report)

    def test_positive_infinity_is_rejected(self):
        report = make_report({1: member(v=(0.0, math.inf, 2.0))})
        with self.assertRaises(ValueError):
            pc._prepare(report)

    def test_negative_infinity_is_rejected(self):
        report = make_report({1: member(m=(-math.inf, 0.0, 0.0))})
        with self.assertRaises(ValueError):
            pc._prepare(report)

    def test_bool_value_is_rejected_by_series_validator(self):
        # AnalysisReport converts values with float(), so bool is only
        # reachable through the validator itself.
        data = {"x": [0.0, 1.0], "N": [True, 1.0], "V": [0.0, 0.0], "M": [0.0, 0.0]}
        with self.assertRaises(ValueError):
            pc._validate_series(1, data)

    def test_integer_beyond_float_range_is_rejected(self):
        data = {
            "x": [0.0, 1.0],
            "N": [10 ** 400, 1.0],
            "V": [0.0, 0.0],
            "M": [0.0, 0.0],
        }
        with self.assertRaises(ValueError):
            pc._validate_series(1, data)

    def test_string_series_is_rejected(self):
        data = {"x": "abc", "N": [1.0], "V": [1.0], "M": [1.0]}
        with self.assertRaises(ValueError):
            pc._validate_series(1, data)

    def test_non_mapping_series_is_rejected(self):
        with self.assertRaises(ValueError):
            pc._validate_series(1, [1, 2, 3])

    def test_missing_key_is_rejected(self):
        data = {"x": [0.0], "N": [1.0], "V": [1.0]}
        with self.assertRaises(ValueError):
            pc._validate_series(1, data)

    def test_length_mismatch_is_rejected(self):
        data = {"x": [0.0, 1.0], "N": [1.0], "V": [1.0, 2.0], "M": [0.0, 0.0]}
        with self.assertRaises(ValueError):
            pc._validate_series(1, data)

    def test_empty_arrays_are_rejected(self):
        report = make_report({1: member(x=(), n=(), v=(), m=())})
        with self.assertRaises(ValueError):
            pc._prepare(report)

    def test_non_increasing_x_is_rejected(self):
        report = make_report({1: member(x=(0.0, 2.0, 1.0))})
        with self.assertRaises(ValueError):
            pc._prepare(report)

    def test_duplicate_x_is_rejected(self):
        report = make_report({1: member(x=(0.0, 1.0, 1.0))})
        with self.assertRaises(ValueError):
            pc._prepare(report)

    def test_non_analysis_report_is_rejected(self):
        with self.assertRaises(ValueError):
            pc._validate_report({})

    def test_ambiguous_member_labels_are_rejected(self):
        a = _Plain()
        b = _Plain()
        report = make_report({a: member(), b: member()})
        with self.assertRaises(ValueError):
            pc._prepare(report)

    def test_int_and_str_member_ids_are_distinct(self):
        report = make_report({1: member(), "1": member()})
        prepared = pc._prepare(report)
        self.assertEqual(len(prepared.label_map), 2)

    def test_empty_report_prepares_without_members(self):
        prepared = pc._prepare(make_report({}))
        self.assertEqual(prepared.plots, {})
        self.assertEqual(prepared.label_map, {})


# ----------------------------------------------------------------------
# Numeric range, tick and fraction behaviour (no display required)
# ----------------------------------------------------------------------


class NumericTests(unittest.TestCase):
    def test_zero_constant_range(self):
        rng = pc._safe_range((0.0, 0.0), "z")
        self.assertEqual(rng, pc._Range(-1.0, 1.0))

    def test_nonzero_constant_range_contains_value(self):
        rng = pc._safe_range((5.0, 5.0), "c")
        self.assertLess(rng.lo, 5.0)
        self.assertGreater(rng.hi, 5.0)

    def test_normal_range_contains_data_with_margin(self):
        rng = pc._safe_range((1.0, 3.0), "n")
        self.assertLess(rng.lo, 1.0)
        self.assertGreater(rng.hi, 3.0)

    def test_range_near_float_max_stays_finite(self):
        rng = pc._safe_range((MAX * 0.5, MAX * 0.9), "big")
        self.assertTrue(math.isfinite(rng.lo))
        self.assertTrue(math.isfinite(rng.hi))
        self.assertLess(rng.lo, MAX * 0.5)
        self.assertLessEqual(rng.hi, MAX)

    def test_range_spanning_full_float_domain(self):
        rng = pc._safe_range((-MAX, MAX), "full")
        self.assertTrue(math.isfinite(rng.lo))
        self.assertTrue(math.isfinite(rng.hi))
        self.assertLess(rng.lo, rng.hi)

    def test_subnormal_range_has_positive_width(self):
        rng = pc._safe_range((5e-324, 1e-323), "sub")
        self.assertLess(rng.lo, rng.hi)
        self.assertLessEqual(rng.lo, 5e-324)

    def test_single_subnormal_value_has_positive_width(self):
        rng = pc._safe_range((5e-324,), "one")
        self.assertLess(rng.lo, rng.hi)

    def test_ticks_are_monotone_and_inside_range(self):
        rng = pc._Range(-2.0, 3.0)
        ticks = pc._make_ticks(rng, "t")
        self.assertEqual(len(ticks), pc._GRID_DIVISIONS + 1)
        self.assertEqual(ticks[0].value, -2.0)
        self.assertEqual(ticks[-1].value, 3.0)
        values = [t.value for t in ticks]
        self.assertTrue(all(a < b for a, b in zip(values, values[1:])))
        fractions = [t.t for t in ticks]
        self.assertEqual(fractions[0], 0.0)
        self.assertEqual(fractions[-1], 1.0)

    def test_ticks_on_full_domain_are_finite(self):
        rng = pc._safe_range((-MAX, MAX), "full")
        ticks = pc._make_ticks(rng, "full")
        self.assertTrue(all(math.isfinite(t.value) for t in ticks))

    def test_scaled_fraction_endpoints_and_midpoint(self):
        rng = pc._Range(0.0, 10.0)
        self.assertEqual(pc._scaled_fraction(0.0, rng), 0.0)
        self.assertEqual(pc._scaled_fraction(10.0, rng), 1.0)
        self.assertAlmostEqual(pc._scaled_fraction(5.0, rng), 0.5)

    def test_scaled_fraction_clamps_outside_range(self):
        rng = pc._Range(0.0, 10.0)
        self.assertEqual(pc._scaled_fraction(-5.0, rng), 0.0)
        self.assertEqual(pc._scaled_fraction(50.0, rng), 1.0)

    def test_prepared_fractions_are_within_unit_interval(self):
        report = make_report(
            {1: member(n=(-MAX, 0.0, MAX), v=(-1e300, 1e-300, 1e300))}
        )
        prepared = pc._prepare(report)
        plot = prepared.plots[1]
        for key in ("N", "V", "M"):
            for t in plot.y_points[key]:
                self.assertTrue(0.0 <= t <= 1.0)
                self.assertTrue(math.isfinite(t))

    def test_zero_crossing_marks_zero_line(self):
        report = make_report({1: member(n=(-1.0, 0.0, 2.0))})
        plot = pc._prepare(report).plots[1]
        zt = plot.zero_t["N"]
        self.assertIsNotNone(zt)
        self.assertTrue(0.0 < zt < 1.0)

    def test_no_zero_crossing_has_no_zero_line(self):
        report = make_report({1: member(n=(1.0, 2.0, 3.0))})
        plot = pc._prepare(report).plots[1]
        self.assertIsNone(plot.zero_t["N"])

    def test_x_points_span_zero_to_one(self):
        # Contract: x_points are fractions of the padded display range that
        # _safe_range builds around the data. The range is extended by the
        # symmetric margin _RANGE_MARGIN_RATIO on each side of the data span,
        # so the first data point maps to m / (1 + 2m) and the last to
        # 1 - m / (1 + 2m). The endpoints are NOT 0.0 and 1.0 by design.
        plot = pc._prepare(make_report({1: member()})).plots[1]
        xs = plot.x_points

        m = pc._RANGE_MARGIN_RATIO
        expected_first = m / (1.0 + 2.0 * m)
        expected_last = 1.0 - expected_first

        self.assertGreaterEqual(len(xs), 2)

        for value in xs:
            self.assertTrue(math.isfinite(value))
            self.assertTrue(0.0 <= value <= 1.0)

        for previous, current in zip(xs, xs[1:]):
            self.assertLess(previous, current)

        self.assertAlmostEqual(xs[0], expected_first, places=9)
        self.assertAlmostEqual(xs[-1], expected_last, places=9)

    def test_build_plan_coordinates_are_finite(self):
        plot = pc._prepare(make_report({1: member()})).plots[1]
        ops = pc._build_plan(plot, "M", "t", 640.0, 420.0, "TkDefaultFont")
        self.assertTrue(ops)
        for op in ops:
            _, coords, _ = op
            self.assertTrue(all(math.isfinite(c) for c in coords))

    def test_build_plan_tiny_canvas_returns_message(self):
        plot = pc._prepare(make_report({1: member()})).plots[1]
        ops = pc._build_plan(plot, "M", "t", 10.0, 10.0, "TkDefaultFont")
        self.assertEqual(len(ops), 1)
        self.assertEqual(ops[0][0], "text")


# ----------------------------------------------------------------------
# Tk-dependent behaviour
# ----------------------------------------------------------------------


class _FaultyCanvas:
    """Wraps a real tk.Canvas and raises TclError on the Nth call of a method.

    Call counts are reset by arm(). Every method call, including delete,
    find_withtag and create_*, is counted and can be forced to fail.
    """

    def __init__(self, real):
        self._real = real
        self.fail = {}
        self.calls = {}

    def arm(self, fail):
        self.fail = dict(fail)
        self.calls = {}

    def __getattr__(self, name):
        attr = getattr(self._real, name)
        if not callable(attr):
            return attr

        def wrapper(*args, **kwargs):
            count = self.calls.get(name, 0) + 1
            self.calls[name] = count
            if self.fail.get(name) == count:
                raise tk.TclError(f"injected failure in {name}")
            return attr(*args, **kwargs)

        return wrapper


class TkPlotTestCase(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"Tk display unavailable: {exc}")
        self.root.geometry("640x420")
        self.plot = pc.PlotCanvas(self.root)
        self.plot.pack(fill="both", expand=True)
        self.root.update()
        self.faulty = _FaultyCanvas(self.plot._canvas)
        self.plot._canvas = self.faulty

    def tearDown(self):
        self.root.destroy()

    def count(self, tag):
        return len(self.faulty.find_withtag(tag))

    def show(self, report):
        self.plot.show_report(report)
        self.root.update()

    def add_unrelated_item(self):
        """Creates an item that is not part of the plot and returns its id."""
        item = self.faulty.create_rectangle(
            1, 1, 5, 5, tags=("unrelated_marker",)
        )
        return item

    def unrelated_items(self):
        return self.faulty.find_withtag("unrelated_marker")

    def assert_only_empty_message_drawn(self):
        items = self.faulty.find_withtag(pc._DRAW_TAG)
        self.assertEqual(len(items), 1)
        self.assertEqual(self.faulty.type(items[0]), "text")
        self.assertEqual(
            self.faulty.itemcget(items[0], "text"),
            pc._EMPTY_MESSAGE,
        )

    def line_items(self):
        return [
            item
            for item in self.faulty.find_withtag(pc._DRAW_TAG)
            if self.faulty.type(item) == "line"
        ]


class TkBehaviourTests(TkPlotTestCase):
    def test_show_report_draws_and_sets_state(self):
        self.show(make_report({1: member()}))
        self.assertGreater(self.count(pc._DRAW_TAG), 0)
        self.assertEqual(self.count(pc._STAGE_TAG), 0)
        self.assertIsNotNone(self.plot._prepared)
        self.assertEqual(self.plot._member_var.get(), "1 (int)")

    def test_show_report_with_nan_keeps_previous_state(self):
        self.show(make_report({1: member()}))
        before_items = self.count(pc._DRAW_TAG)
        before_prepared = self.plot._prepared
        before_member = self.plot._member_var.get()

        bad = make_report({2: member(n=(float("nan"), 1.0, 1.0))})
        with self.assertRaises(ValueError):
            self.plot.show_report(bad)

        self.assertIs(self.plot._prepared, before_prepared)
        self.assertEqual(self.plot._member_var.get(), before_member)
        self.assertEqual(self.count(pc._DRAW_TAG), before_items)
        self.assertEqual(self.count(pc._STAGE_TAG), 0)

    def test_show_report_wrong_type_raises_and_keeps_state(self):
        self.show(make_report({1: member()}))
        before = self.plot._prepared
        with self.assertRaises(ValueError):
            self.plot.show_report({})
        self.assertIs(self.plot._prepared, before)

    def test_unrelated_item_survives_successful_draw(self):
        marker = self.add_unrelated_item()
        self.show(make_report({1: member()}))
        self.assertEqual(self.unrelated_items(), (marker,))

    def test_unrelated_item_survives_failed_staging(self):
        self.show(make_report({1: member()}))
        marker = self.add_unrelated_item()
        before_items = self.count(pc._DRAW_TAG)

        self.faulty.arm({"create_line": 1})
        with self.assertRaises(tk.TclError) as ctx:
            self.plot.show_report(make_report({2: member()}))

        self.assertIn("create_line", str(ctx.exception))
        self.assertEqual(self.unrelated_items(), (marker,))
        self.assertEqual(self.count(pc._DRAW_TAG), before_items)
        self.assertEqual(self.count(pc._STAGE_TAG), 0)

    def test_unrelated_item_survives_tag_switch_failure_with_restore(self):
        self.show(make_report({1: member()}))
        marker = self.add_unrelated_item()
        before_items = self.count(pc._DRAW_TAG)
        before_prepared = self.plot._prepared

        # Tag switch fails once; restore is allowed to succeed.
        self.faulty.arm({"addtag_withtag": 1})
        with self.assertRaises(tk.TclError) as ctx:
            self.plot.show_report(make_report({2: member()}))

        self.assertIn("addtag_withtag", str(ctx.exception))
        self.assertEqual(self.unrelated_items(), (marker,))
        self.assertEqual(self.count(pc._DRAW_TAG), before_items)
        self.assertEqual(self.count(pc._STAGE_TAG), 0)
        self.assertIs(self.plot._prepared, before_prepared)
    def test_unrelated_item_survives_failed_restore_and_original_error_kept(self):
        self.show(make_report({1: member()}))
        marker = self.add_unrelated_item()

        # Count the create_line calls needed for one complete chart.
        restore_create_line_call = (
            sum(
                1
                for kind, _, _ in self.plot._last_draw_ops
                if pc._CREATE_METHODS.get(kind) == "create_line"
            )
            + 1
        )

        # The staged draw succeeds, but restoring the previous chart fails.
        # The original addtag_withtag error must remain the reported error.
        self.faulty.arm({
            "addtag_withtag": 1,
            "create_line": restore_create_line_call,
        })

        with self.assertRaises(tk.TclError) as ctx:
            self.plot.show_report(make_report({2: member()}))

        self.assertIn("addtag_withtag", str(ctx.exception))
        self.assertEqual(self.unrelated_items(), (marker,))
        self.assertEqual(self.count(pc._STAGE_TAG), 0)
        self.assertEqual(self.plot._last_draw_ops, ())

    def test_restore_from_ops_failure_falls_back_to_prepared_data(self):
        # Step 1: show a two-member report and select member 2.
        self.show(make_report({1: member(), 2: member(m=(0.0, 2.0, 0.0))}))
        self.plot._member_var.set("2 (int)")
        self.plot._redraw()
        self.root.update()

        # Step 2: record the previous state, the chart and an unrelated item.
        marker = self.add_unrelated_item()
        before_prepared = self.plot._prepared
        before_member = self.plot._member_var.get()
        self.assertEqual(before_member, "2 (int)")
        before_chart = [
            (self.faulty.type(item), tuple(self.faulty.coords(item)))
            for item in self.faulty.find_withtag(pc._DRAW_TAG)
        ]
        self.assertGreater(len(before_chart), 0)

        # Step 3: the Combobox configuration fails on the first call only.
        real_configure = self.plot._member_box.configure
        configure_calls = {"n": 0}

        def configure_failing_once(*args, **kwargs):
            configure_calls["n"] += 1
            if configure_calls["n"] == 1:
                raise tk.TclError("injected combobox failure")
            return real_configure(*args, **kwargs)

        # Step 4: wrap _draw.
        # Call 1: drawing the new report inside show_report -> succeeds.
        # Call 2: restoring from state.ops -> fails with TclError.
        # Call 3 onward: real execution, so the rebuild from state.prepared runs.
        real_draw = self.plot._draw
        draw_calls = {"n": 0}
        draw_outcomes = []

        def draw_scripted(ops):
            draw_calls["n"] += 1
            call_index = draw_calls["n"]
            if call_index == 2:
                draw_outcomes.append(("restore_from_ops", "failed"))
                raise tk.TclError("injected restore-from-ops failure")
            result = real_draw(ops)
            draw_outcomes.append((f"call_{call_index}", "ok"))
            return result

        new_report = make_report({5: member()})

        with mock.patch.object(
            self.plot._member_box,
            "configure",
            side_effect=configure_failing_once,
        ), mock.patch.object(
            self.plot,
            "_draw",
            side_effect=draw_scripted,
        ):
            with self.assertRaises(tk.TclError) as ctx:
                self.plot.show_report(new_report)

        self.root.update()

        # Verify the original error is the one propagated to the caller.
        self.assertIn("injected combobox failure", str(ctx.exception))

        # Verify that the restore from state.ops failed.
        self.assertIn(
            ("restore_from_ops", "failed"),
            draw_outcomes,
        )

        # Verify that the fallback rebuild from state.prepared ran and succeeded.
        self.assertGreaterEqual(draw_calls["n"], 3)
        self.assertIn(("call_3", "ok"), draw_outcomes)

        # Verify that the previous chart is back, with identical geometry.
        after_chart = [
            (self.faulty.type(item), tuple(self.faulty.coords(item)))
            for item in self.faulty.find_withtag(pc._DRAW_TAG)
        ]
        self.assertEqual(after_chart, before_chart)
        self.assertEqual(self.count(pc._STAGE_TAG), 0)

        # Verify the internal state was restored to the previous values.
        self.assertIs(self.plot._prepared, before_prepared)
        self.assertEqual(self.plot._member_var.get(), before_member)

        # Verify the unrelated canvas item was not deleted.
        self.assertEqual(self.unrelated_items(), (marker,))

        # Verify that _last_draw_ops still describes a real chart.
        self.assertGreater(len(self.plot._last_draw_ops), 0)

    def test_first_show_report_combobox_failure_restores_initial_state(self):
        self.assertIsNone(self.plot._prepared)
        marker = self.add_unrelated_item()
        real_configure = self.plot._member_box.configure
        calls = {"n": 0}

        def failing_once(*args, **kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                raise tk.TclError("injected combobox failure")
            return real_configure(*args, **kwargs)

        with mock.patch.object(
            self.plot._member_box,
            "configure",
            side_effect=failing_once,
        ):
            with self.assertRaises(tk.TclError) as ctx:
                self.plot.show_report(make_report({1: member()}))

        self.assertIn("injected combobox failure", str(ctx.exception))
        self.assertIsNone(self.plot._prepared)
        self.assertEqual(self.plot._member_var.get(), "")
        self.assertEqual(self.line_items(), [])
        self.assert_only_empty_message_drawn()
        self.assertEqual(self.unrelated_items(), (marker,))

    def test_first_show_report_var_failure_restores_initial_state(self):
        self.assertIsNone(self.plot._prepared)
        marker = self.add_unrelated_item()
        real_set = self.plot._member_var.set
        calls = {"n": 0}

        def failing_once(value):
            calls["n"] += 1
            if calls["n"] == 1:
                raise tk.TclError("injected var failure")
            return real_set(value)

        with mock.patch.object(
            self.plot._member_var,
            "set",
            side_effect=failing_once,
        ):
            with self.assertRaises(tk.TclError) as ctx:
                self.plot.show_report(make_report({1: member()}))

        self.assertIn("injected var failure", str(ctx.exception))
        self.assertIsNone(self.plot._prepared)
        self.assertEqual(self.plot._member_var.get(), "")
        self.assertEqual(self.line_items(), [])
        self.assert_only_empty_message_drawn()
        self.assertEqual(self.unrelated_items(), (marker,))

    def test_first_show_report_recovers_when_last_ops_is_empty(self):
        # Simulates the state after a failed restore: no recorded ops.
        self.plot._last_draw_ops = ()
        self.assertIsNone(self.plot._prepared)
        real_configure = self.plot._member_box.configure
        calls = {"n": 0}

        def failing_once(*args, **kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                raise tk.TclError("injected combobox failure")
            return real_configure(*args, **kwargs)

        with mock.patch.object(
            self.plot._member_box,
            "configure",
            side_effect=failing_once,
        ):
            with self.assertRaises(tk.TclError):
                self.plot.show_report(make_report({1: member()}))

        self.assertIsNone(self.plot._prepared)
        self.assertEqual(self.line_items(), [])
        self.assert_only_empty_message_drawn()
        self.assertEqual(len(self.plot._last_draw_ops), 1)

    def test_clear_resets_state_and_shows_message(self):
        self.show(make_report({1: member()}))
        self.plot.clear()
        self.root.update()
        self.assertIsNone(self.plot._prepared)
        self.assertEqual(self.plot._member_var.get(), "")
        self.assertGreater(self.count(pc._DRAW_TAG), 0)

    def test_clear_combobox_failure_keeps_chart_and_unrelated_item(self):
        self.show(make_report({1: member()}))
        marker = self.add_unrelated_item()
        before_prepared = self.plot._prepared
        before_member = self.plot._member_var.get()
        before_items = self.count(pc._DRAW_TAG)

        with mock.patch.object(
            self.plot._member_box,
            "configure",
            side_effect=tk.TclError("injected combobox failure"),
        ):
            with self.assertRaises(tk.TclError) as ctx:
                self.plot.clear()

        self.assertIn("injected combobox failure", str(ctx.exception))
        self.assertIs(self.plot._prepared, before_prepared)
        self.assertEqual(self.plot._member_var.get(), before_member)
        self.assertEqual(self.unrelated_items(), (marker,))
        self.assertEqual(self.count(pc._DRAW_TAG), before_items)

    def test_clear_failure_with_empty_ops_rebuilds_chart_from_data(self):
        self.show(make_report({1: member()}))
        self.plot._last_draw_ops = ()
        before_prepared = self.plot._prepared

        with mock.patch.object(
            self.plot._member_box,
            "configure",
            side_effect=tk.TclError("injected combobox failure"),
        ):
            with self.assertRaises(tk.TclError):
                self.plot.clear()

        self.assertIs(self.plot._prepared, before_prepared)
        self.assertEqual(self.plot._member_var.get(), "1 (int)")
        self.assertGreater(len(self.line_items()), 0)

    def test_show_report_combobox_failure_keeps_previous_state(self):
        self.show(make_report({1: member()}))
        marker = self.add_unrelated_item()
        before_prepared = self.plot._prepared
        before_member = self.plot._member_var.get()

        with mock.patch.object(
            self.plot._member_box,
            "configure",
            side_effect=tk.TclError("injected combobox failure"),
        ):
            with self.assertRaises(tk.TclError) as ctx:
                self.plot.show_report(make_report({2: member()}))

        self.assertIn("injected combobox failure", str(ctx.exception))
        self.assertIs(self.plot._prepared, before_prepared)
        self.assertEqual(self.plot._member_var.get(), before_member)
        self.assertEqual(self.unrelated_items(), (marker,))
        self.assertGreater(self.count(pc._DRAW_TAG), 0)

    def test_empty_report_shows_message_without_members(self):
        self.show(make_report({}))
        self.assertEqual(self.plot._member_var.get(), "")
        self.assertEqual(self.plot._prepared.plots, {})

    def test_redraw_failure_keeps_chart_and_shows_error(self):
        self.show(make_report({1: member()}))
        before_items = self.count(pc._DRAW_TAG)

        with mock.patch.object(pc, "_build_plan", side_effect=ValueError("injected")):
            self.plot._redraw()

        self.assertEqual(self.plot._last_redraw_error, "injected")
        self.assertEqual(self.count(pc._DRAW_TAG), before_items)
        self.assertGreaterEqual(self.count(pc._ERROR_TAG), 1)

    def test_redraw_tcl_failure_keeps_chart(self):
        self.show(make_report({1: member()}))
        before_items = self.count(pc._DRAW_TAG)

        self.faulty.arm({"create_line": 1})
        self.plot._redraw()

        self.assertIsNotNone(self.plot._last_redraw_error)
        self.assertEqual(self.count(pc._DRAW_TAG), before_items)

    def test_member_switch_redraws_without_error(self):
        self.show(make_report({1: member(), 2: member(m=(0.0, 2.0, 0.0))}))
        self.plot._member_var.set("2 (int)")
        self.plot._redraw()
        self.assertIsNone(self.plot._last_redraw_error)
        self.assertGreater(self.count(pc._DRAW_TAG), 0)

    def test_no_canvas_wide_delete_is_issued(self):
        # Guard against regressions: the plot must never call delete("all").
        self.show(make_report({1: member()}))
        self.faulty.arm({})
        self.plot.show_report(make_report({2: member()}))
        self.plot.clear()
        self.plot._redraw()
        for args_tag in self._delete_arguments():
            self.assertNotEqual(args_tag, "all")

    def _delete_arguments(self):
        # Records delete() arguments by wrapping the real canvas method.
        seen = []
        real_delete = self.plot._canvas._real.delete

        def recording_delete(*args):
            seen.append(args[0] if args else None)
            return real_delete(*args)

        self.plot._canvas._real.delete = recording_delete
        try:
            self.plot.show_report(make_report({3: member()}))
            self.plot.clear()
        finally:
            del self.plot._canvas._real.delete
        return seen


if __name__ == "__main__":
    unittest.main()
