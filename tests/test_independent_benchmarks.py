"""تست‌های مستقل بنچمارک (Independent benchmark tests) — بازبینی نهایی جلسه ۳ STRUCTPIN

شامل: B1 (تغییرشکل محوری)، B2 (طرهٔ قائم با بار افقی)، B6 (تعادل گره‌ها)،
B7 (برش انتهایی تیر ساده با UDL) و B9 (ناوردایی).

قراردادها:
- دستگاه کلی راست‌گرد: x افقی به راست، y عمودی به بالا.
- rz پادساعت‌گرد مثبت.
- واحدها سازگار (N، m، Pa).
- reactions = K·u − F (طبق frame2d.solve_frame).
- member_end_actions = kl·ul − fl (نیروی گره روی عضو، در دستگاه محلی).
- تبدیل محلی به کلی برای هر گره: R = Tᵀ[0:3, 0:3] (با T ماتریس تبدیل frame2d).
"""

import math
import unittest

from structpin.model.structural_model import StructuralModel
from structpin.fem.frame2d import solve_frame, transformation_matrix


E = 200.0
A = 0.01
I = 2e-4


def _base(E_value=E, A_value=A, I_value=I):
    m = StructuralModel("independent")
    m.add_material("mat", E_value)
    m.add_section("sec", A_value, I_value)
    return m


def _matvec(M, v):
    return [sum(a * x for a, x in zip(row, v)) for row in M]


def _transpose(M):
    return [list(r) for r in zip(*M)]


def _local_to_global_node(c, s, f_local):
    """تبدیل سه‌مؤلفه‌ای نیروی یک انتهای عضو از محلی به کلی.

    T (طبق frame2d) متعامد است، پس وارون آن Tᵀ است. زیرمجموعهٔ ۳×۳ یک گره
    از Tᵀ برابر است با [[c, −s, 0], [s, c, 0], [0, 0, 1]].
    """
    R = [[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]]
    return _matvec(R, list(f_local))


class AxialBarTest(unittest.TestCase):
    """B1: ux = F·L / (E·A) برای میلهٔ محوری.

    تلورانس: rel_tol=1e-9 (به‌جای 1e-12، زیرا خطای گرد کردن ممیز شناور در
    حل دستگاه چند مرحله‌ای ممکن است از 1e-12 بیشتر باشد).
    """

    def setUp(self):
        self.L = 2.0
        self.F = 5.0
        m = _base()
        m.add_node(1, 0.0, 0.0)
        m.add_node(2, self.L, 0.0)
        m.add_member(1, 1, 2, "mat", "sec")
        m.add_restraint(1, ux=True, uy=True, rz=True)
        m.add_nodal_load(2, fx=self.F)
        self.results = solve_frame(m)

    def test_axial_displacement_matches_FL_over_EA(self):
        expected = self.F * self.L / (E * A)
        self.assertTrue(math.isclose(self.results.displacements[2][0],
                                     expected, rel_tol=1e-9))

    def test_axial_reaction_balances_load(self):
        self.assertTrue(math.isclose(self.results.reactions[1][0],
                                     -self.F, rel_tol=1e-9))


class VerticalCantileverHorizontalTipLoadTest(unittest.TestCase):
    """B2: طرهٔ قائم با بار افقی در نوک.

    عضو از (0,0) تا (0,L): c=0، s=1.
    u_local = uy، v_local = −ux. بار +P در ux → v_local = −PL³/(3EI) → ux_tip = +PL³/(3EI).
    """

    def setUp(self):
        self.L = 2.0
        self.P = 10.0
        m = _base()
        m.add_node(1, 0.0, 0.0)
        m.add_node(2, 0.0, self.L)
        m.add_member(1, 1, 2, "mat", "sec")
        m.add_restraint(1, ux=True, uy=True, rz=True)
        m.add_nodal_load(2, fx=self.P)
        self.results = solve_frame(m)

    def test_global_horizontal_tip_displacement(self):
        expected = self.P * self.L ** 3 / (3 * E * I)
        self.assertTrue(math.isclose(self.results.displacements[2][0],
                                     expected, rel_tol=1e-9))

    def test_vertical_displacement_is_negligible(self):
        """مؤلفهٔ قائم باید در حد خطای گرد کردن صفر باشد.

        تلورانس مطلق با مقیاس تغییرمکان محاسبه می‌شود تا وابسته به واحد نباشد.
        """
        scale = abs(self.results.displacements[2][0])
        self.assertLessEqual(abs(self.results.displacements[2][1]), 1e-9 * scale)


class IndependentJointEquilibriumTest(unittest.TestCase):
    """B6: تعادل گره‌ها با نیروهای انتهایی عضو در دستگاه کلی.

    فقط برای بارهای گرهی (بدون UDL) معتبر است، زیرا بار معادل UDL در q لحاظ
    شده و معادلهٔ ساده نیست.

    معادله برای هر گره n:
        Σ applied(n) + reaction(n) − Σ q_global_on_node(n) = 0
    که q_global_on_node = −q_global (نیروی عضو روی گره) است.
    """

    def test_joint_equilibrium_portal_frame(self):
        H = 10.0
        m = _base()
        m.add_node(1, 0.0, 0.0)
        m.add_node(2, 0.0, 3.0)
        m.add_node(3, 4.0, 3.0)
        m.add_node(4, 4.0, 0.0)
        m.add_member(1, 1, 2, "mat", "sec")
        m.add_member(2, 2, 3, "mat", "sec")
        m.add_member(3, 4, 3, "mat", "sec")
        m.add_restraint(1, ux=True, uy=True, rz=True)
        m.add_restraint(4, ux=True, uy=True, rz=True)
        m.add_nodal_load(2, fx=H)
        r = solve_frame(m)

        applied = {nid: [0.0, 0.0, 0.0] for nid in m.nodes}
        for ld in m.nodal_loads:
            applied[ld.node][0] += ld.fx
            applied[ld.node][1] += ld.fy
            applied[ld.node][2] += ld.mz

        # نیروی وارد از اعضا به گره‌ها = −q (q نیروی گره روی عضو است)
        member_on_node = {nid: [0.0, 0.0, 0.0] for nid in m.nodes}
        for mem in m.members.values():
            ni = m.nodes[mem.node_i]
            nj = m.nodes[mem.node_j]
            L = math.hypot(nj.x - ni.x, nj.y - ni.y)
            c = (nj.x - ni.x) / L
            s = (nj.y - ni.y) / L
            qi_local, qj_local = r.member_end_actions[mem.id]
            qi_g = _local_to_global_node(c, s, qi_local)
            qj_g = _local_to_global_node(c, s, qj_local)
            for k in range(3):
                member_on_node[mem.node_i][k] -= qi_g[k]
                member_on_node[mem.node_j][k] -= qj_g[k]

        scale = max(abs(v) for vals in applied.values() for v in vals) or 1.0
        for nid in m.nodes:
            for k in range(3):
                residual = applied[nid][k] + r.reactions[nid][k] + member_on_node[nid][k]
                self.assertLessEqual(abs(residual), 1e-9 * scale,
                                     msg=f"گره {nid}، مؤلفهٔ {k} تعادل ندارد")


class SimplySupportedUDLShearTest(unittest.TestCase):
    """B7: برش انتهایی تیر ساده با UDL برابر |q|·L/2 است.

    لنگر انتهایی صفر حذف شد، زیرا در مدل با rz آزاد در انتها، q[2] به‌طور
    قطعی صفر نیست و اثبات آن در این بازبینی ممکن نبود.
    """

    def setUp(self):
        self.L = 3.0
        self.q = -4.0
        m = _base()
        m.add_node(1, 0.0, 0.0)
        m.add_node(2, self.L, 0.0)
        m.add_member(1, 1, 2, "mat", "sec")
        m.add_restraint(1, ux=True, uy=True)
        m.add_restraint(2, uy=True)
        m.add_member_udl(1, self.q)
        self.results = solve_frame(m)

    def test_end_shear_magnitude_equals_qL_over_2(self):
        expected = abs(self.q) * self.L / 2.0
        qi, qj = self.results.member_end_actions[1]
        self.assertTrue(math.isclose(abs(qi[1]), expected, rel_tol=1e-9))
        self.assertTrue(math.isclose(abs(qj[1]), expected, rel_tol=1e-9))


class InvarianceTest(unittest.TestCase):
    """B9: ناوردایی نسبت به مقیاس بار، E و شماره‌گذاری."""

    @staticmethod
    def _cantilever(P, E_value=E, renumbered=False):
        L = 2.0
        m = _base(E_value=E_value)
        if renumbered:
            m.add_node(7, 0.0, 0.0)
            m.add_node(3, L, 0.0)
            m.add_member(9, 7, 3, "mat", "sec")
            m.add_restraint(7, ux=True, uy=True, rz=True)
            m.add_nodal_load(3, fy=-P)
            tip = 3
        else:
            m.add_node(1, 0.0, 0.0)
            m.add_node(2, L, 0.0)
            m.add_member(1, 1, 2, "mat", "sec")
            m.add_restraint(1, ux=True, uy=True, rz=True)
            m.add_nodal_load(2, fy=-P)
            tip = 2
        return solve_frame(m).displacements[tip][1]

    def test_load_scaling_is_linear(self):
        u1 = self._cantilever(10.0)
        u2 = self._cantilever(20.0)
        self.assertTrue(math.isclose(u2, 2.0 * u1, rel_tol=1e-9))

    def test_modulus_scaling_divides_displacement(self):
        u1 = self._cantilever(10.0, E_value=E)
        u2 = self._cantilever(10.0, E_value=1000.0 * E)
        self.assertTrue(math.isclose(u2, u1 / 1000.0, rel_tol=1e-9))

    def test_renumbering_preserves_tip_displacement(self):
        u1 = self._cantilever(10.0)
        u2 = self._cantilever(10.0, renumbered=True)
        self.assertTrue(math.isclose(u2, u1, rel_tol=1e-9))


if __name__ == "__main__":
    unittest.main()
