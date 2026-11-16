"""تست‌های D2: سرویس تحلیل قاب دوبعدی (analysis_service).

اجرا (ریشهٔ مخزن):
    PYTHONPATH=src python -m unittest discover -s tests -p "test_analysis_service.py" -v

این فایل در این گفتگو اجرا نشده است. نتیجه فقط از GitHub Actions معتبر است.

قرارداد علامت (از کد واقعی internal_forces و frame2d):
    N(0) = −q_i[0]، V(0) = q_i[1]، M(0) = −q_i[2]
    V(x) = V(0) + qy·x،  M(x) = M(0) + V(0)·x + qy·x²/2
    بار گسترده رو به پایین (q<0) ⇒ جابه‌جایی قائم در محور کلی y منفی.

مرجع‌های تحلیلی (اویلر-برنولی):
    تیر دوسر ساده، بار گسترده q، L:
        V(0)=+|q|L/2، V(L)=−|q|L/2، M(L/2)=+|q|L²/8
        خیز بیشینهٔ وسط: δ_max = 5|q|L⁴/(384EI)  (در تست بار گسترده با یک المان
        اندازه‌گیری نمی‌شود، زیرا یک المان گره وسط ندارد.)
    تیر دوسر ساده، بار متمرکز P در وسط (دو المان، گره وسط):
        δ_mid = P·L³/(48EI)
    طره، بار گسترده q، L (یک المان):
        V(0)=+|q|L، M(0)=−|q|L²/2، δ_tip = q·L⁴/(8EI)

دقت خیز طره در یک المان:
    انتهای آزاد طره یک گره است. جابه‌جایی گره دقیقاً از معادلات گره‌ای به دست می‌آید،
    که بردار بار معادل [qL/2, qL²/12] (حاصل از کار مجازی با توابع شکل کوبیک) در آن‌ها
    استفاده می‌شود. دقت این مقدار گره‌ای ناشی از سازگاری بردار بار معادل و معادلات گره‌ای
    است، نه از اینکه تابع شکل کوبیک شکل تغییرمکان واقعی درجه چهار بین گره‌ها را دقیق بازنمایی
    کند. شکل تغییرمکان بین گره‌ها در این مدل تقریبی است و در این تست بررسی نمی‌شود.
"""

import unittest
from dataclasses import FrozenInstanceError
from types import MappingProxyType

from structpin.model.structural_model import StructuralModel
from structpin.fem.linalg import SingularSystemError
from structpin.services.analysis_service import (
    AnalysisInputError,
    AnalysisReport,
    run_frame_analysis,
)


E = 200.0
A = 0.01
I = 2e-4
EI = E * I


def _base():
    m = StructuralModel("analysis")
    m.add_material("mat", E)
    m.add_section("sec", A, I)
    return m


def _simply_supported_udl(L, q):
    """تیر دوسر ساده، یک المان، بار گسترده یکنواخت."""
    m = _base()
    m.add_node(1, 0.0, 0.0)
    m.add_node(2, L, 0.0)
    m.add_member(1, 1, 2, "mat", "sec")
    m.add_restraint(1, ux=True, uy=True)
    m.add_restraint(2, uy=True)
    m.add_member_udl(1, q)
    return m


def _simply_supported_midpoint_load(L, P):
    """تیر دوسر ساده، دو المان، بار متمرکز P در گره وسط."""
    m = _base()
    m.add_node(1, 0.0, 0.0)
    m.add_node(2, L / 2.0, 0.0)
    m.add_node(3, L, 0.0)
    m.add_member(1, 1, 2, "mat", "sec")
    m.add_member(2, 2, 3, "mat", "sec")
    m.add_restraint(1, ux=True, uy=True)
    m.add_restraint(3, uy=True)
    m.add_nodal_load(2, fy=P)
    return m


def _cantilever_udl(L, q):
    """طره، یک المان، بار گسترده یکنواخت."""
    m = _base()
    m.add_node(1, 0.0, 0.0)
    m.add_node(2, L, 0.0)
    m.add_member(1, 1, 2, "mat", "sec")
    m.add_restraint(1, ux=True, uy=True, rz=True)
    m.add_member_udl(1, q)
    return m


class DeflectionClosedFormTest(unittest.TestCase):
    """خیز تحلیلی با قرارداد علامت واقعی (جابه‌جایی قائم در محور y)."""

    def test_simply_supported_midpoint_load_deflection(self):
        """δ_mid = P·L³/(48EI). L=4، P=-10 ⇒ δ = -10·64/(48·0.04) = -333.333…"""
        L, P = 4.0, -10.0
        report = run_frame_analysis(_simply_supported_midpoint_load(L, P))
        expected = P * L ** 3 / (48.0 * EI)
        self.assertAlmostEqual(report.displacements[2][1], expected, places=6)

    def test_cantilever_tip_deflection_udl(self):
        """δ_tip = q·L⁴/(8EI). L=3، q=-2 ⇒ δ = -506.25."""
        L, q = 3.0, -2.0
        report = run_frame_analysis(_cantilever_udl(L, q))
        expected = q * L ** 4 / (8.0 * EI)
        self.assertAlmostEqual(report.displacements[2][1], expected, places=6)

    def test_cantilever_tip_deflection_sign_is_downward(self):
        report = run_frame_analysis(_cantilever_udl(3.0, -2.0))
        self.assertLess(report.displacements[2][1], 0.0)


class SimplySupportedTest(unittest.TestCase):
    """تیر دوسر ساده، q=-3، L=4 (تحلیلی: V0=+6، V(L)=-6، M(L/2)=+6)."""

    def setUp(self):
        self.report = run_frame_analysis(_simply_supported_udl(4.0, -3.0), n_points=20)
        self.forces = self.report.internal_forces[1]

    def test_shear_at_supports_matches_closed_form(self):
        self.assertAlmostEqual(self.forces["V"][0], 6.0, places=8)
        self.assertAlmostEqual(self.forces["V"][-1], -6.0, places=8)

    def test_shear_zero_at_midspan(self):
        mid = len(self.forces["V"]) // 2
        self.assertAlmostEqual(self.forces["V"][mid], 0.0, places=8)

    def test_moment_zero_at_pins_and_positive_midspan(self):
        self.assertAlmostEqual(self.forces["M"][0], 0.0, places=8)
        self.assertAlmostEqual(self.forces["M"][-1], 0.0, places=8)
        mid = len(self.forces["M"]) // 2
        self.assertAlmostEqual(self.forces["M"][mid], 6.0, places=8)

    def test_axial_zero(self):
        for n in self.forces["N"]:
            self.assertAlmostEqual(n, 0.0, places=9)

    def test_reactions_balance_load(self):
        """مجموع عکس‌العمل‌های قائم = |q|L = 12."""
        ry = self.report.reactions[1][1] + self.report.reactions[2][1]
        self.assertAlmostEqual(ry, 12.0, places=8)


class CantileverTest(unittest.TestCase):
    """طره، q=-2، L=3 (تحلیلی: V0=+6، M0=-9، V(L)=M(L)=0)."""

    def setUp(self):
        self.report = run_frame_analysis(_cantilever_udl(3.0, -2.0), n_points=20)
        self.forces = self.report.internal_forces[1]

    def test_fixed_end_shear_signed(self):
        self.assertAlmostEqual(self.forces["V"][0], 6.0, places=8)

    def test_fixed_end_moment_signed(self):
        self.assertAlmostEqual(self.forces["M"][0], -9.0, places=8)

    def test_free_end_zero(self):
        self.assertAlmostEqual(self.forces["V"][-1], 0.0, places=8)
        self.assertAlmostEqual(self.forces["M"][-1], 0.0, places=8)


class EndJConsistencyTest(unittest.TestCase):
    """تست انتهای j: N(L)=q_j[0]، V(L)=−q_j[1]، M(L)=q_j[2]. حذف یا دور زده نشده است."""

    def test_end_j_matches_member_end_actions(self):
        from structpin.fem.frame2d import solve_frame

        model = _simply_supported_udl(4.0, -3.0)
        results = solve_frame(model)
        _qi, qj = results.member_end_actions[1]
        f = run_frame_analysis(model, n_points=20).internal_forces[1]
        self.assertAlmostEqual(f["N"][-1], qj[0], places=8)
        self.assertAlmostEqual(f["V"][-1], -qj[1], places=8)
        self.assertAlmostEqual(f["M"][-1], qj[2], places=8)


class EquilibriumTest(unittest.TestCase):
    """تعادل کلی: مجموع عکس‌العمل‌های قائم برابر مجموع بار، و لنگر حول گره ۱ صفر."""

    def test_global_vertical_and_moment_equilibrium(self):
        L, q = 4.0, -3.0
        report = run_frame_analysis(_simply_supported_udl(L, q))
        ry = report.reactions[1][1] + report.reactions[2][1]
        self.assertAlmostEqual(ry, -q * L, places=8)
        mz1 = report.reactions[1][2]
        moment_about_1 = report.reactions[2][1] * L + mz1 + (q * L) * (L / 2.0)
        self.assertAlmostEqual(moment_about_1, 0.0, places=8)


class ImmutabilityTest(unittest.TestCase):
    """گزارش کاملاً مستقل و غیرقابل‌تغییر است."""

    def setUp(self):
        self.model = _simply_supported_udl(4.0, -3.0)
        self.report = run_frame_analysis(self.model)

    def test_report_is_frozen_dataclass(self):
        with self.assertRaises(FrozenInstanceError):
            self.report.n_points = 5

    def test_top_level_mappings_are_read_only(self):
        self.assertIsInstance(self.report.displacements, MappingProxyType)
        with self.assertRaises(TypeError):
            self.report.displacements[99] = (0.0, 0.0, 0.0)

    def test_nested_force_mapping_is_read_only(self):
        self.assertIsInstance(self.report.internal_forces[1], MappingProxyType)
        with self.assertRaises(TypeError):
            self.report.internal_forces[1]["V"] = ()

    def test_numeric_values_are_tuples(self):
        self.assertIsInstance(self.report.internal_forces[1]["V"], tuple)
        self.assertIsInstance(self.report.displacements[1], tuple)

    def test_warnings_is_empty_tuple(self):
        self.assertEqual(self.report.warnings, ())
        self.assertIsInstance(self.report.warnings, tuple)

    def test_warnings_elements_are_immutable_strings(self):
        """عناصر warnings باید رشته باشند؛ تغییر لیست ورودی روی گزارش اثری ندارد."""
        mutable_item = ["هشدار"]
        rep = AnalysisReport(
            displacements={},
            reactions={},
            member_end_actions={},
            internal_forces={},
            n_points=1,
            warnings=[mutable_item, 42],
        )
        self.assertIsInstance(rep.warnings, tuple)
        for w in rep.warnings:
            self.assertIsInstance(w, str)
        original = rep.warnings[0]
        mutable_item.append("تغییر")
        self.assertEqual(rep.warnings[0], original)

    def test_direct_construction_with_mutable_input_is_frozen(self):
        mutable = {1: (0.0, 1.0, 2.0)}
        rep = AnalysisReport(
            displacements=mutable,
            reactions={},
            member_end_actions={},
            internal_forces={},
            n_points=1,
        )
        self.assertIsInstance(rep.displacements, MappingProxyType)
        with self.assertRaises(TypeError):
            rep.displacements[1] = (9.0, 9.0, 9.0)
        mutable[1] = (7.0, 7.0, 7.0)
        self.assertEqual(rep.displacements[1], (0.0, 1.0, 2.0))

    def test_direct_construction_rejects_invalid_n_points(self):
        """n_points در سازندهٔ مستقیم باید همان قاعدهٔ run_frame_analysis را داشته باشد."""
        for bad in (True, 2.0, "5", 0, -1):
            with self.subTest(n_points=bad):
                with self.assertRaises(ValueError):
                    AnalysisReport(
                        displacements={},
                        reactions={},
                        member_end_actions={},
                        internal_forces={},
                        n_points=bad,
                    )

    def test_report_independent_of_model_change(self):
        before = self.report.internal_forces[1]["V"][0]
        self.model.member_udls[0] = type(self.model.member_udls[0])(1, -100.0)
        self.assertEqual(self.report.internal_forces[1]["V"][0], before)


class ErrorPathTest(unittest.TestCase):
    """مسیرهای خطا: مدل نامعتبر، ناپایدار، و n_points نامعتبر."""

    def test_invalid_model_raises_analysis_input_error_with_cause(self):
        m = StructuralModel("bad")
        m.add_node(1, 0.0, 0.0)
        with self.assertRaises(AnalysisInputError) as ctx:
            run_frame_analysis(m)
        self.assertIsNotNone(ctx.exception.__cause__)
        self.assertIn("مدل نامعتبر", str(ctx.exception))

    def test_unstable_model_exposes_singular_error(self):
        m = _base()
        m.add_node(1, 0.0, 0.0)
        m.add_node(2, 2.0, 0.0)
        m.add_member(1, 1, 2, "mat", "sec")
        m.add_nodal_load(2, fy=-1.0)
        with self.assertRaises(SingularSystemError) as ctx:
            run_frame_analysis(m)
        self.assertIn("unstable", str(ctx.exception))

    def test_n_points_rejects_bool_float_string_and_nonpositive(self):
        model = _simply_supported_udl(4.0, -3.0)
        for bad in (True, 2.0, "5", 0, -3):
            with self.subTest(n_points=bad):
                with self.assertRaises(ValueError):
                    run_frame_analysis(model, n_points=bad)

    def test_point_count_is_n_plus_one(self):
        report = run_frame_analysis(_simply_supported_udl(4.0, -3.0), n_points=7)
        self.assertEqual(len(report.internal_forces[1]["x"]), 8)
        self.assertEqual(report.n_points, 7)


if __name__ == "__main__":
    unittest.main()
