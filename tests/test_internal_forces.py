"""تست‌های تحلیلی و کنترل علامت برای member_internal_forces.

اجرا (ریشهٔ مخزن):
    PYTHONPATH=src python -m unittest discover -s tests -p "test_internal_forces.py" -v

این فایل اجرا نشده است. نتیجه فقط از GitHub Actions معتبر است.

هر تست:
    - داده‌ها را با solve_frame تولید می‌کند.
    - مقادیر مرجع را از تعادل استاتیکی یا تعریف قرارداد محاسبه می‌کند.
    - علامت را فقط در جایی کنترل می‌کند که از قرارداد تعریف‌شده قابل استخراج است.
"""

import unittest
from fractions import Fraction

from structpin.model.structural_model import StructuralModel
from structpin.fem.frame2d import solve_frame
from structpin.fem.internal_forces import member_internal_forces


E = 200.0
A = 0.01
I = 2e-4


def _base():
    m = StructuralModel("ifm")
    m.add_material("mat", E)
    m.add_section("sec", A, I)
    return m


def _simply_supported(L, q):
    m = _base()
    m.add_node(1, 0.0, 0.0)
    m.add_node(2, L, 0.0)
    m.add_member(1, 1, 2, "mat", "sec")
    m.add_restraint(1, ux=True, uy=True)
    m.add_restraint(2, uy=True)
    m.add_member_udl(1, q)
    return m


def _cantilever(L, q):
    m = _base()
    m.add_node(1, 0.0, 0.0)
    m.add_node(2, L, 0.0)
    m.add_member(1, 1, 2, "mat", "sec")
    m.add_restraint(1, ux=True, uy=True, rz=True)
    m.add_member_udl(1, q)
    return m


class EndpointConsistencyTest(unittest.TestCase):
    """مقایسهٔ مستقل N، V، M در دو انتها با member_end_actions (تعریف قرارداد)."""

    def _check(self, model):
        results = solve_frame(model)
        forces = member_internal_forces(model, results, n_points=4)[1]
        qi, qj = results.member_end_actions[1]
        # انتهای i (x=0)
        self.assertAlmostEqual(forces["N"][0], -qi[0], places=9)
        self.assertAlmostEqual(forces["V"][0], qi[1], places=9)
        self.assertAlmostEqual(forces["M"][0], -qi[2], places=9)
        # انتهای j (x=L)
        self.assertAlmostEqual(forces["N"][-1], qj[0], places=9)
        self.assertAlmostEqual(forces["V"][-1], -qj[1], places=9)
        self.assertAlmostEqual(forces["M"][-1], qj[2], places=9)
        return forces

    def test_endpoints_match_member_end_actions_simply_supported(self):
        self._check(_simply_supported(4.0, -3.0))

    def test_endpoints_match_member_end_actions_cantilever(self):
        self._check(_cantilever(3.0, -2.0))


class SimplySupportedUDLTest(unittest.TestCase):
    """تیر ساده، بار رو به پایین q=-3، L=4.

    مرجع استاتیکی: R_A = R_B = |q|L/2 = 6.
    علامت مهندسی: V(0) = +6، V(L) = -6؛ M(L/2) = +|q|L²/8 = 6 (تار پایینی کشیده).
    علامت V و M در این مرجع از تعریف قرارداد ماژول گرفته شده، نه از کد.
    """

    def setUp(self):
        self.L = 4.0
        self.q = -3.0
        self.results = solve_frame(_simply_supported(self.L, self.q))
        self.forces = member_internal_forces(
            _simply_supported(self.L, self.q), self.results, n_points=20
        )[1]

    def test_axial_zero(self):
        for n in self.forces["N"]:
            self.assertAlmostEqual(n, 0.0, places=9)

    def test_shear_at_supports_signed(self):
        self.assertAlmostEqual(self.forces["V"][0], 6.0, places=8)
        self.assertAlmostEqual(self.forces["V"][-1], -6.0, places=8)

    def test_shear_zero_midspan(self):
        mid = len(self.forces["V"]) // 2
        self.assertAlmostEqual(self.forces["V"][mid], 0.0, places=8)

    def test_moment_zero_at_pins(self):
        self.assertAlmostEqual(self.forces["M"][0], 0.0, places=8)
        self.assertAlmostEqual(self.forces["M"][-1], 0.0, places=8)

    def test_midspan_moment_signed(self):
        mid = len(self.forces["M"]) // 2
        self.assertAlmostEqual(self.forces["M"][mid], 6.0, places=8)


class CantileverUDLTest(unittest.TestCase):
    """طره، بار رو به پایین q=-2، L=3.

    مرجع استاتیکی: برش در گیردار = |q|L = 6 (مثبت در قرارداد)، لنگر در گیردار = |q|L²/2 = 9.
    انتهای آزاد: V=0، M=0.
    """

    def setUp(self):
        self.L = 3.0
        self.q = -2.0
        model = _cantilever(self.L, self.q)
        self.results = solve_frame(model)
        self.forces = member_internal_forces(model, self.results, n_points=20)[1]

    def test_free_end_zero(self):
        self.assertAlmostEqual(self.forces["V"][-1], 0.0, places=8)
        self.assertAlmostEqual(self.forces["M"][-1], 0.0, places=8)

    def test_fixed_end_shear_signed(self):
        self.assertAlmostEqual(self.forces["V"][0], 6.0, places=8)

    def test_fixed_end_moment_magnitude_and_sign(self):
        self.assertAlmostEqual(abs(self.forces["M"][0]), 9.0, places=8)
        # علامت لنگر گیردار: با قرارداد M مثبت وقتی تار پایینی کشیده شود، در طره با بار
        # رو به پایین تار بالایی کشیده است، پس M(0) منفی است.
        self.assertLess(self.forces["M"][0], 0.0)


class AxialOnlyTest(unittest.TestCase):
    """عضو با نیروی محوری P=5 در انتهای j، گیردار در i."""

    def setUp(self):
        self.L = 2.0
        self.P = 5.0
        m = _base()
        m.add_node(1, 0.0, 0.0)
        m.add_node(2, self.L, 0.0)
        m.add_member(1, 1, 2, "mat", "sec")
        m.add_restraint(1, ux=True, uy=True, rz=True)
        m.add_nodal_load(2, fx=self.P)
        self.results = solve_frame(m)
        self.forces = member_internal_forces(m, self.results, n_points=10)[1]

    def test_shear_and_moment_zero(self):
        for v in self.forces["V"]:
            self.assertAlmostEqual(v, 0.0, places=8)
        for mo in self.forces["M"]:
            self.assertAlmostEqual(mo, 0.0, places=8)

    def test_axial_tension_positive_sign(self):
        """بار محوری +P در انتهای j، عضو در کشش است؛ N باید +P باشد."""
        for n in self.forces["N"]:
            self.assertAlmostEqual(n, self.P, places=8)


class IncrementConsistencyTest(unittest.TestCase):
    """بررسی تعادل داخلی: V(L)−V(0)=qy·L و M(L)−M(0)−V(0)·L=qy·L²/2."""

    def test_increments_udl(self):
        L, q = 4.0, -3.0
        model = _simply_supported(L, q)
        f = member_internal_forces(model, solve_frame(model), n_points=20)[1]
        self.assertAlmostEqual(f["V"][-1] - f["V"][0], q * L, places=8)
        self.assertAlmostEqual(f["M"][-1] - f["M"][0] - f["V"][0] * L, q * L * L / 2.0, places=8)


class NPointsValidationTest(unittest.TestCase):
    """n_points فقط عدد صحیح مثبت."""

    def setUp(self):
        self.model = _simply_supported(4.0, -3.0)
        self.results = solve_frame(self.model)

    def test_zero_rejected(self):
        with self.assertRaises(ValueError):
            member_internal_forces(self.model, self.results, n_points=0)

    def test_negative_rejected(self):
        with self.assertRaises(ValueError):
            member_internal_forces(self.model, self.results, n_points=-3)

    def test_float_rejected(self):
        with self.assertRaises(ValueError):
            member_internal_forces(self.model, self.results, n_points=2.0)

    def test_bool_rejected(self):
        with self.assertRaises(ValueError):
            member_internal_forces(self.model, self.results, n_points=True)

    def test_string_rejected(self):
        with self.assertRaises(ValueError):
            member_internal_forces(self.model, self.results, n_points="5")

    def test_point_count(self):
        f = member_internal_forces(self.model, self.results, n_points=7)[1]
        self.assertEqual(len(f["x"]), 8)


if __name__ == "__main__":
    unittest.main()
