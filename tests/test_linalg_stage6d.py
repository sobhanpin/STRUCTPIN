"""Stage 6D: آزمون‌های تکمیلی پایداری عددی و حساسیت solve_dense.

اجرا (ریشهٔ مخزن):
    PYTHONPATH=src python -m unittest discover -s tests -p "test_linalg_stage6d.py" -v

وضعیت:
    - این فایل در این گفتگو اجرا نشده است. نتیجهٔ اجرا فقط از CI گزارش می‌شود.
    - linalg.py در مخزن در این گفتگو بررسی نشده؛ مبنا متن ارسالی است.

مرجع‌ها:
    همه مرجع‌های دقیق با fractions.Fraction و حذف گاوسی مستقل از solve_dense محاسبه می‌شوند.

آستانه‌ها (تجربی، پیش از اجرا توجیه‌شده، بدون تغییر پس از مشاهده):
    FWD_TOL_* معیارهای تجربی پیشنهادی‌اند؛ تضمین نظری نیستند.

آنچه تست‌ها نشان می‌دهند:
    - کران‌های ریاضی حساسیت (با شرط κε<1 و مخرج 1−κε) روی مثال‌های مشخص.
    - رفتار solve_dense روی ورودی‌های مشخص نسبت به مرجع Fraction.

آنچه تست‌ها نشان نمی‌دهند:
    - پایداری عمومی solve_dense برای همهٔ ماتریس‌ها.
    - برتری نسبت به روش‌های دیگر.
"""

import math
import unittest
from fractions import Fraction

from structpin.fem.linalg import solve_dense, SingularSystemError


# ---------------------------------------------------------------------------
# آستانه‌های تجربی (بدون تغییر)
# ---------------------------------------------------------------------------

FWD_TOL_3_1 = Fraction(1, 10 ** 10)   # ۳.۱ و ۳.۲ و ۳.۳ و ۳.۵
FWD_TOL_3_4A = Fraction(1, 10 ** 6)   # ۳.۴الف
FWD_TOL_3_6 = Fraction(1, 10 ** 7)    # ۳.۶
FWD_TOL_3_9 = Fraction(1, 10 ** 12)   # ۳.۹


# ---------------------------------------------------------------------------
# ابزارهای حساب دقیق (مستقل از solve_dense)
# ---------------------------------------------------------------------------

def _F(M):
    return [[Fraction(v) for v in row] for row in M]


def _Fv(v):
    return [Fraction(x) for x in v]


def _vec_inf(v):
    return max(abs(x) for x in v)


def _mat_inf(M):
    return max(sum((abs(a) for a in row), Fraction(0)) for row in M)


def _mat_vec(M, x):
    return [sum((a * xi for a, xi in zip(row, x)), Fraction(0)) for row in M]


def _vec_sub(a, b):
    return [x - y for x, y in zip(a, b)]


def _vec_sub_mat(A, B):
    return [[a - b for a, b in zip(ra, rb)] for ra, rb in zip(A, B)]


def _gauss_solve(M, b):
    """حل دقیق M x = b با حذف گاوسی و پیوت جزئی روی Fraction (مستقل از solve_dense)."""
    n = len(b)
    T = [row[:] + [bi] for row, bi in zip(_F(M), _Fv(b))]
    for k in range(n):
        p = max(range(k, n), key=lambda r: abs(T[r][k]))
        if T[p][k] == 0:
            raise ValueError("تکین در حساب دقیق")
        T[k], T[p] = T[p], T[k]
        for r in range(k + 1, n):
            f = T[r][k] / T[k][k]
            if f != 0:
                for c in range(k, n + 1):
                    T[r][c] -= f * T[k][c]
    x = [Fraction(0)] * n
    for r in range(n - 1, -1, -1):
        s = T[r][n] - sum((T[r][c] * x[c] for c in range(r + 1, n)), Fraction(0))
        x[r] = s / T[r][r]
    return x


def _inverse(M):
    n = len(M)
    cols = [_gauss_solve(M, [Fraction(int(i == j)) for i in range(n)]) for j in range(n)]
    return [[cols[j][i] for j in range(n)] for i in range(n)]


def _det(M):
    """دترمینان دقیق با حذف گاوسی روی Fraction."""
    n = len(M)
    T = _F(M)
    det = Fraction(1)
    for k in range(n):
        p = next((r for r in range(k, n) if T[r][k] != 0), None)
        if p is None:
            return Fraction(0)
        if p != k:
            T[k], T[p] = T[p], T[k]
            det = -det
        det *= T[k][k]
        for r in range(k + 1, n):
            f = T[r][k] / T[k][k]
            for c in range(k, n):
                T[r][c] -= f * T[k][c]
    return det


def _kappa_inf(M):
    Mf = _F(M)
    return _mat_inf(Mf) * _mat_inf(_inverse(Mf))


def _rel_fwd(x_float, x_ref):
    diff = _vec_sub(_Fv(x_float), _Fv(x_ref))
    return _vec_inf(diff) / _vec_inf(_Fv(x_ref))


# ---------------------------------------------------------------------------
# کلاس‌ها و تست‌ها
# ---------------------------------------------------------------------------

class SensitivityRhsTest(unittest.TestCase):
    """۳.۱: اغتشاش بردار b. کران ریاضی ‖Δx‖/‖x*‖ ≤ κ·ε_b (با ε_A=0)."""

    def test_3_1_rhs_perturbation_bound_and_solver(self):
        """A=[[3,1],[1,2]]، det=5، ‖A‖∞=4، A⁻¹=(1/5)[[2,−1],[−1,3]]، ‖A⁻¹‖∞=4/5، κ∞=16/5.

        x*=[1,−1]، b=A x*=[2,−1]، b̃=b+[δ,0]، δ=2^{-30}.
        ε_b = ‖Δb‖∞/‖b‖∞ = δ/2. کران ریاضی: κ·ε_b = 8δ/5.
        مقدار واقعی: ‖x̃−x*‖∞ = 2δ/5 (نسبت به ‖x*‖∞=1).
        """
        A = [[3.0, 1.0], [1.0, 2.0]]
        delta = Fraction(1, 2 ** 30)
        x_star = [Fraction(1), Fraction(-1)]
        b_exact = _mat_vec(_F(A), x_star)
        self.assertEqual(b_exact, [Fraction(2), Fraction(-1)])
        self.assertEqual(_det(A), Fraction(5))
        self.assertEqual(_kappa_inf(A), Fraction(16, 5))

        b_tilde = [b_exact[0] + delta, b_exact[1]]
        b_float = [float(v) for v in b_tilde]
        x_tilde_exact = _gauss_solve(_F(A), b_tilde)

        eps_b = _vec_inf(_vec_sub(b_tilde, b_exact)) / _vec_inf(b_exact)
        bound = _kappa_inf(A) * eps_b
        self.assertEqual(bound, Fraction(8, 5) * delta)
        actual = _vec_inf(_vec_sub(x_tilde_exact, x_star)) / _vec_inf(x_star)
        self.assertEqual(actual, Fraction(2, 5) * delta)
        self.assertLessEqual(actual, bound)

        x = solve_dense(A, b_float)
        self.assertEqual(len(x), 2)
        self.assertTrue(all(math.isfinite(v) for v in x))
        x_ref = _gauss_solve(_F(A), _Fv(b_float))
        self.assertLessEqual(_rel_fwd(x, x_ref), FWD_TOL_3_1)


class SensitivityMatrixTest(unittest.TestCase):
    """۳.۲: اغتشاش ماتریس. کران ریاضی با شرط κε<1 و مخرج 1−κε، و اجرای solve_dense."""

    def test_3_2_matrix_perturbation_bound_and_solver(self):
        """A=[[4,1],[2,3]]:
            det(A)=10
            ‖A‖∞=max(4+1, 2+3)=5
            A⁻¹=(1/10)[[3,−1],[−2,4]]، ‖A⁻¹‖∞=max(4, 6)/10=6/10
            κ∞(A)=5·6/10=3

        b=[5,5]، x*=[1,1] (A·x*=[5,5]).

        Ã = A + E، E=[[0,0],[δ,0]]، δ=2^{-30}.
        ‖E‖∞ = δ، ε_A = ‖E‖∞/‖A‖∞ = δ/5، κ·ε_A = 3δ/5 < 1.
        کران ریاضی: ‖x̃−x*‖∞/‖x*‖∞ ≤ κε_A/(1−κε_A) = (3δ/5)/(1−3δ/5).

        مقدار واقعی: x̃ = [10/(10−δ), (10−5δ)/(10−δ)]،
        ‖x̃−x*‖∞/‖x*‖∞ = 4δ/(10−δ).
        """
        A = [[4.0, 1.0], [2.0, 3.0]]
        delta = Fraction(1, 2 ** 30)
        b = [Fraction(5), Fraction(5)]
        x_star = [Fraction(1), Fraction(1)]
        self.assertEqual(_mat_vec(_F(A), x_star), b)
        self.assertEqual(_det(A), Fraction(10))
        self.assertEqual(_mat_inf(_F(A)), Fraction(5))
        self.assertEqual(_mat_inf(_inverse(_F(A))), Fraction(6, 10))
        self.assertEqual(_kappa_inf(A), Fraction(3))

        A_tilde = [[Fraction(4), Fraction(1)], [Fraction(2) + delta, Fraction(3)]]
        eps_A = _mat_inf(_vec_sub_mat(A_tilde, _F(A))) / _mat_inf(_F(A))
        self.assertEqual(eps_A, delta / 5)
        kappa_eps = _kappa_inf(A) * eps_A
        self.assertEqual(kappa_eps, Fraction(3, 5) * delta)
        self.assertLess(kappa_eps, 1)
        bound = kappa_eps / (1 - kappa_eps)

        x_tilde_exact = _gauss_solve(A_tilde, b)
        self.assertEqual(x_tilde_exact[0], Fraction(10) / (10 - delta))
        self.assertEqual(x_tilde_exact[1], (Fraction(10) - 5 * delta) / (10 - delta))
        actual = _vec_inf(_vec_sub(x_tilde_exact, x_star)) / _vec_inf(x_star)
        self.assertEqual(actual, 4 * delta / (10 - delta))
        self.assertLessEqual(actual, bound)

        A_float = [[4.0, 1.0], [2.0 + 2.0 ** -30, 3.0]]
        x = solve_dense(A_float, [5.0, 5.0])
        self.assertTrue(all(math.isfinite(v) for v in x))
        x_ref = _gauss_solve(_F(A_float), [Fraction(5), Fraction(5)])
        self.assertLessEqual(_rel_fwd(x, x_ref), FWD_TOL_3_1)


class RowPermutationTest(unittest.TestCase):
    """۳.۳: جابه‌جایی سطرها باید جواب را تغییر ندهد."""

    def test_3_3_row_permutation_invariance(self):
        """A=[[0,2,1],[3,0,4],[1,5,0]]، x*=[1,2,1]، b=A x*=[5,7,11].

        det(A)=23 (بسط سطر ۱: 0·(0−20) − 2·(0−4) + 1·(15−0) = 8+15).
        """
        A = [[0.0, 2.0, 1.0], [3.0, 0.0, 4.0], [1.0, 5.0, 0.0]]
        x_star = [Fraction(1), Fraction(2), Fraction(1)]
        b_exact = _mat_vec(_F(A), x_star)
        self.assertEqual(_det(A), Fraction(23))
        self.assertEqual(b_exact, [Fraction(5), Fraction(7), Fraction(11)])

        b = [float(v) for v in b_exact]
        x = solve_dense(A, b)
        self.assertLessEqual(_rel_fwd(x, x_star), FWD_TOL_3_1)

        A_perm = [A[2], A[0], A[1]]
        b_perm = [b[2], b[0], b[1]]
        x_perm = solve_dense(A_perm, b_perm)
        self.assertLessEqual(_rel_fwd(x_perm, x_star), FWD_TOL_3_1)


class RejectionBoundaryTest(unittest.TestCase):
    """۳.۴: مرز rel_tol. پیوت مقیاس‌شده برای [[1,1],[1,1+δ]] برابر δ/2 است."""

    def test_3_4a_accept_pivot_above_rel_tol(self):
        """δ=2^{-28}: پیوت مقیاس‌شده = δ/2 = 2^{-29} ≈ 1.86e-9 > 1e-9 ⇒ پذیرش."""
        delta = Fraction(1, 2 ** 28)
        pivot = (Fraction(1, 2) + delta / 2) - Fraction(1, 2)
        self.assertEqual(pivot, Fraction(1, 2 ** 29))
        self.assertGreater(pivot, Fraction(1, 10 ** 9))

        A = [[1.0, 1.0], [1.0, 1.0 + 2.0 ** -28]]
        b = [2.0, 2.0 + 2.0 ** -28]
        x = solve_dense(A, b)
        self.assertEqual(len(x), 2)
        self.assertTrue(all(math.isfinite(v) for v in x))
        self.assertLessEqual(_rel_fwd(x, [Fraction(1), Fraction(1)]), FWD_TOL_3_4A)

    def test_3_4b_reject_pivot_below_rel_tol(self):
        """δ=2^{-29}: پیوت مقیاس‌شده = 2^{-30} ≈ 9.31e-10 < 1e-9 ⇒ رد SingularSystemError."""
        delta = Fraction(1, 2 ** 29)
        pivot = (Fraction(1, 2) + delta / 2) - Fraction(1, 2)
        self.assertEqual(pivot, Fraction(1, 2 ** 30))
        self.assertLess(pivot, Fraction(1, 10 ** 9))

        A = [[1.0, 1.0], [1.0, 1.0 + 2.0 ** -29]]
        b = [2.0, 2.0 + 2.0 ** -29]
        with self.assertRaises(SingularSystemError):
            solve_dense(A, b)


class ScalingEquivalenceTest(unittest.TestCase):
    """۳.۵: مقیاس‌بندی توانی دو هم‌ارز."""

    def test_3_5_power_of_two_equivalent_scaling(self):
        """A=[[3,1],[1,2]]، x*=[1,1]، b=[4,3].

        D1=diag(16, 1/4)، D2=diag(1/8, 4).
        A_t = D1 A D2 = [[6,64],[1/32,2]]، b_t=D1 b=[64,3/4]، y=D2⁻¹ x* = [8,1/4].
        """
        D1 = [Fraction(16), Fraction(1, 4)]
        D2 = [Fraction(1, 8), Fraction(4)]
        A = [[Fraction(3), Fraction(1)], [Fraction(1), Fraction(2)]]
        A_t = [[D1[i] * A[i][j] * D2[j] for j in range(2)] for i in range(2)]
        self.assertEqual(A_t, [[Fraction(6), Fraction(64)], [Fraction(1, 32), Fraction(2)]])
        b = [Fraction(4), Fraction(3)]
        b_t = [D1[i] * b[i] for i in range(2)]
        self.assertEqual(b_t, [Fraction(64), Fraction(3, 4)])
        y_ref = _gauss_solve(A_t, b_t)
        self.assertEqual(y_ref, [Fraction(8), Fraction(1, 4)])

        x = solve_dense([[6.0, 64.0], [1.0 / 32.0, 2.0]], [64.0, 0.75])
        self.assertLessEqual(_rel_fwd(x, y_ref), FWD_TOL_3_1)


class SmallPerturbedRowTest(unittest.TestCase):
    """۳.۶: سطر تقریباً تکراری. κ∞ دقیق = (6+δ)(2/δ+3) ≈ 1.2583e7."""

    def test_3_6_near_duplicate_row(self):
        """A=[[1,2,3],[1,2,3+δ],[0,1,1]]، δ=2^{-20}.

        det(A) = −δ.
        A⁻¹ سطر ۱ = [(1+δ)/δ, −1/δ, −2]، مجموع قدرمطلق = 2/δ + 3.
        ‖A‖∞ = 6+δ.
        κ∞ = (6+δ)(2/δ+3).
        """
        delta = Fraction(1, 2 ** 20)
        A_exact = [
            [Fraction(1), Fraction(2), Fraction(3)],
            [Fraction(1), Fraction(2), Fraction(3) + delta],
            [Fraction(0), Fraction(1), Fraction(1)],
        ]
        self.assertEqual(_det(A_exact), -delta)
        self.assertEqual(_mat_inf(A_exact), 6 + delta)
        inv = _inverse(A_exact)
        self.assertEqual(inv[0][0], (1 + delta) / delta)
        self.assertEqual(inv[0][1], -1 / delta)
        self.assertEqual(inv[0][2], Fraction(-2))
        self.assertEqual(_mat_inf(inv), 2 / delta + 3)

        kappa = (6 + delta) * (2 / delta + 3)
        self.assertEqual(_kappa_inf(A_exact), kappa)
        self.assertAlmostEqual(float(kappa), 1.2583e7, delta=1e4)

        A_float = [[1.0, 2.0, 3.0], [1.0, 2.0, 3.0 + 2.0 ** -20], [0.0, 1.0, 1.0]]
        x_star = [Fraction(1), Fraction(1), Fraction(1)]
        b = [float(v) for v in _mat_vec(_F(A_float), x_star)]
        x = solve_dense(A_float, b)
        self.assertEqual(len(x), 3)
        self.assertTrue(all(math.isfinite(v) for v in x))
        x_ref = _gauss_solve(_F(A_float), _Fv(b))
        self.assertLessEqual(_rel_fwd(x, x_ref), FWD_TOL_3_6)


class FloatInputErrorTest(unittest.TestCase):
    """۳.۹: ماتریس ناتکین با درایه‌های غیرقابل نمایش دقیق در float."""

    def test_3_9_float_input_error_and_bound(self):
        """A=[[1,1/3],[1/3,1]]، b=[4/3,4/3]، x*=[1,1].

        det(A)=8/9، A⁻¹=[[9/8,−3/8],[−3/8,9/8]]، ‖A‖∞=4/3، ‖A⁻¹‖∞=3/2، κ∞=2.
        ورودی float: fl(1/3) و fl(4/3). ε_A و ε_b با Fraction محاسبه می‌شوند.
        کران: اگر κε_A<1 آنگاه ‖x_fl−x*‖/‖x*‖ ≤ κ(ε_A+ε_b)/(1−κε_A).
        """
        A = [[Fraction(1), Fraction(1, 3)], [Fraction(1, 3), Fraction(1)]]
        b = [Fraction(4, 3), Fraction(4, 3)]
        x_star = [Fraction(1), Fraction(1)]
        self.assertEqual(_det(A), Fraction(8, 9))
        self.assertEqual(_inverse(A), [[Fraction(9, 8), Fraction(-3, 8)], [Fraction(-3, 8), Fraction(9, 8)]])
        self.assertEqual(_kappa_inf(A), Fraction(2))
        self.assertEqual(_mat_vec(A, x_star), b)

        A_fl_f = [[float(v) for v in row] for row in A]
        b_fl_f = [float(v) for v in b]
        A_fl = [[Fraction(v) for v in row] for row in A_fl_f]
        b_fl = [Fraction(v) for v in b_fl_f]

        eps_A = _mat_inf(_vec_sub_mat(A_fl, A)) / _mat_inf(A)
        eps_b = _vec_inf(_vec_sub(b_fl, b)) / _vec_inf(b)
        kappa = _kappa_inf(A)
        self.assertLess(kappa * eps_A, 1)

        x_fl_exact = _gauss_solve(A_fl, b_fl)
        rel = _vec_inf(_vec_sub(x_fl_exact, x_star)) / _vec_inf(x_star)
        bound = kappa * (eps_A + eps_b) / (1 - kappa * eps_A)
        self.assertLessEqual(rel, bound)

        x = solve_dense(A_fl_f, b_fl_f)
        self.assertTrue(all(math.isfinite(v) for v in x))
        self.assertLessEqual(_rel_fwd(x, x_fl_exact), FWD_TOL_3_9)


if __name__ == "__main__":
    unittest.main()
