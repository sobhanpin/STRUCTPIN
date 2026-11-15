"""تست‌های ممیزی عددی Stage 6A برای solve_dense.

این فایل مستقل است و فایل‌های تست موجود را تغییر نمی‌دهد.

قواعد:
    - مرجع دقیق با fractions.Fraction محاسبه می‌شود.
    - محاسبه مرجع هرگز solve_dense را فراخوانی نمی‌کند.
    - هیچ expectedFailure و هیچ skip پنهان وجود ندارد.
    - فقط کتابخانه استاندارد Python (unittest, fractions, math) استفاده می‌شود.

API واقعی بررسی‌شده (بر اساس linalg.py ارسالی):
    solve_dense(A, b, rel_tol=1e-9) -> list[float]
    SingularSystemError, NumericalOverflowError, NumericalUnderflowError (زیرکلاس ArithmeticError)
    ValueError برای ورودی نامعتبر.

اجرا:
    PYTHONPATH=src python -m unittest tests.test_linalg_stage6a -v
"""

import math
import unittest
from fractions import Fraction

from structpin.fem.linalg import solve_dense


# ---------------------------------------------------------------------------
# آستانه‌ها (با دلیل)
# ---------------------------------------------------------------------------

# خطای نسبی float64 برای دستگاه‌های با κ کوچک‌تر از ~10^4 در حد ~10^{-12} است.
# ۱۰^{-10} حاشیهٔ حدود صد برابری می‌دهد و خطای گرد کردن را پنهان نمی‌کند.
REL_TOL_WELL_CONDITIONED = Fraction(1, 10 ** 10)

# برای مقیاس‌بندی توانی دو، ضرب دقیق است؛ خطای فقط از حل گاوسی می‌آید.
REL_TOL_POWER_OF_TWO = Fraction(1, 10 ** 12)


# ---------------------------------------------------------------------------
# ابزارهای حساب دقیق (مستقل از solve_dense)
# ---------------------------------------------------------------------------

def _to_frac_matrix(A):
    return [[Fraction(v) for v in row] for row in A]


def _to_frac_vector(v):
    return [Fraction(x) for x in v]


def _mat_vec_frac(A, x):
    return [sum(a * xi for a, xi in zip(row, x)) for row in A]


def _norm_inf_vec(v):
    return max(abs(x) for x in v)


def _norm_inf_mat(A):
    return max(sum(abs(a) for a in row) for row in A)


def _exact_solve(A, b):
    """حل دقیق A x = b با حذف گاوسی و پیوت جزئی روی Fraction (مستقل از solve_dense)."""
    n = len(b)
    M = [row[:] + [bi] for row, bi in zip(_to_frac_matrix(A), _to_frac_vector(b))]
    for k in range(n):
        p = max(range(k, n), key=lambda r: abs(M[r][k]))
        if M[p][k] == 0:
            raise ValueError("ماتریس در حساب دقیق تکین است")
        M[k], M[p] = M[p], M[k]
        for r in range(k + 1, n):
            f = M[r][k] / M[k][k]
            if f != 0:
                for c in range(k, n + 1):
                    M[r][c] -= f * M[k][c]
    x = [Fraction(0)] * n
    for r in range(n - 1, -1, -1):
        s = M[r][n] - sum(M[r][c] * x[c] for c in range(r + 1, n))
        x[r] = s / M[r][r]
    return x


def _exact_inverse(A):
    n = len(A)
    cols = [
        _exact_solve(A, [Fraction(int(i == j)) for i in range(n)])
        for j in range(n)
    ]
    return [[cols[j][i] for j in range(n)] for i in range(n)]


def _rel_err_inf(x, x_ref):
    """خطای نسبی بی‌نهایت ‖x − x_ref‖∞ / ‖x_ref‖∞ با حساب دقیق.

    x می‌تواند float باشد؛ Fraction(float) دقیق است. قبل از فراخوانی باید
    متناهی بودن x بررسی شده باشد.
    """
    xf = _to_frac_vector(x)
    rf = _to_frac_vector(x_ref)
    diff = [a - b for a, b in zip(xf, rf)]
    return _norm_inf_vec(diff) / _norm_inf_vec(rf)


def _assert_finite_vector(tc, x, label):
    tc.assertIsInstance(x, list, msg=f"{label}: خروجی باید list باشد")
    for i, v in enumerate(x):
        tc.assertTrue(math.isfinite(v), msg=f"{label}: مؤلفهٔ {i} غیرمتناهی است")


def _assert_close_exact(tc, x, x_ref, tol, label):
    _assert_finite_vector(tc, x, label)
    tc.assertEqual(len(x), len(x_ref), msg=f"{label}: طول خروجی نادرست است")
    err = _rel_err_inf(x, x_ref)
    tc.assertLessEqual(
        err, tol,
        msg=f"{label}: خطای نسبی {float(err):.3e} بیشتر از حد {float(tol):.3e} است",
    )


# ---------------------------------------------------------------------------
# ساخت ماتریس‌ها و داده‌های مرجع
# ---------------------------------------------------------------------------

def _hilbert_frac(n):
    return [[Fraction(1, i + j + 1) for j in range(n)] for i in range(n)]


def _hilbert_float(n):
    return [[float(Fraction(1, i + j + 1)) for j in range(n)] for i in range(n)]


def _poisson_matrix(n):
    A = [[0.0] * n for _ in range(n)]
    for i in range(n):
        A[i][i] = 2.0
        if i > 0:
            A[i][i - 1] = -1.0
        if i < n - 1:
            A[i][i + 1] = -1.0
    return A


def _poisson_exact(n):
    """جواب دقیق x_i = i(n+1−i)/2 برای b = [1,…,1] (اندیس‌ها از ۱)."""
    return [Fraction((i + 1) * (n - i), 2) for i in range(n)]


def _tridiag_ones_matrix(n):
    """A_11 = 1، A_nn = 2، میانی = 2، آف‌دیاگونال = 1."""
    if n == 1:
        return [[1.0]]
    A = [[0.0] * n for _ in range(n)]
    for i in range(n):
        A[i][i] = 1.0 if i == 0 else 2.0
        if i > 0:
            A[i][i - 1] = 1.0
        if i < n - 1:
            A[i][i + 1] = 1.0
    return A


def _row_sums(A):
    return [sum(row) for row in A]


# داده‌های تست ۳ و ۴ (مقیاس‌بندی غیرقطری)
A_BASE = [[2.0, 1.0], [1.0, 3.0]]
B_BASE = [3.0, 5.0]
X_BASE = [Fraction(4, 5), Fraction(7, 5)]


def _diag_scale_transform(A, b, d_left, d_right):
    """ماتریس و بردار تبدیل‌شده را واقعاً می‌سازد: A' = D1·A·D2، b' = D1·b.

    d_left و d_right لیست‌های Fraction هستند. خروجی Fraction است؛ تبدیل به float
    بعداً و صریح انجام می‌شود.
    """
    n = len(A)
    A_t = [[d_left[i] * Fraction(A[i][j]) * d_right[j] for j in range(n)] for i in range(n)]
    b_t = [d_left[i] * Fraction(b[i]) for i in range(n)]
    return A_t, b_t


def _float_matrix(A_frac):
    return [[float(v) for v in row] for row in A_frac]


def _float_vector(v_frac):
    return [float(v) for v in v_frac]


# ---------------------------------------------------------------------------
# تست‌های Stage 6A
# ---------------------------------------------------------------------------

class HilbertInverseAndConditionTest(unittest.TestCase):
    """تست‌های ۱ و ۲: معکوس دقیق Hilbert 4×4 و عدد شرط بی‌نهایت."""

    def test_01_hilbert4_inverse_exact_identity(self):
        """Stage 6A-۱: H_4 · H_4⁻¹ = I با Fraction (بدون solve_dense)."""
        H = _hilbert_frac(4)
        inv = _exact_inverse(H)
        prod = [
            [sum(H[i][k] * inv[k][j] for k in range(4)) for j in range(4)]
            for i in range(4)
        ]
        identity = [[Fraction(int(i == j)) for j in range(4)] for i in range(4)]
        self.assertEqual(prod, identity)

    def test_01b_hilbert4_inverse_matches_known_integer_matrix(self):
        """Stage 6A-۱ب: معکوس H_4 با مقدار شناخته‌شدهٔ صحیح مطابقت دارد."""
        expected = [
            [16, -120, 240, -140],
            [-120, 1200, -2700, 1680],
            [240, -2700, 6480, -4200],
            [-140, 1680, -4200, 2800],
        ]
        inv = _exact_inverse(_hilbert_frac(4))
        self.assertEqual(inv, [[Fraction(v) for v in row] for row in expected])

    def test_02_hilbert4_infinity_condition_number_exact(self):
        """Stage 6A-۲: κ∞(H_4) = ‖H_4‖∞ · ‖H_4⁻¹‖∞ = 28375 با Fraction."""
        H = _hilbert_frac(4)
        inv = _exact_inverse(H)
        kappa = _norm_inf_mat(H) * _norm_inf_mat(inv)
        self.assertEqual(_norm_inf_mat(H), Fraction(25, 12))
        self.assertEqual(_norm_inf_mat(inv), Fraction(13620))
        self.assertEqual(kappa, Fraction(28375))


class OffDiagonalPowerOfTwoScalingTest(unittest.TestCase):
    """تست‌های ۳ و ۴: ناوردایی تحت مقیاس‌بندی غیرقطری با توان دو."""

    def _run_scaling(self, d_left, d_right, y_expected, label):
        """A' و b' را می‌سازد؛ solve_dense را روی float آن‌ها اجرا و با y_expected مقایسه می‌کند.

        y_expected از رابطهٔ y = D2⁻¹ x محاسبه شده است و باید با حل دقیق Fraction
        روی ماتریس تبدیل‌شده همخوان باشد. هر دو بررسی انجام می‌شود.
        """
        A_t, b_t = _diag_scale_transform(A_BASE, B_BASE, d_left, d_right)

        # مرجع مستقل: حل دقیق ماتریس تبدیل‌شده روی Fraction
        y_exact = _exact_solve(A_t, b_t)
        self.assertEqual(
            y_exact, y_expected,
            msg=f"{label}: y محاسبه‌شده با D2⁻¹x همخوان نیست",
        )

        # ورودی واقعی solve_dense
        A_f = _float_matrix(A_t)
        b_f = _float_vector(b_t)
        y_solver = solve_dense(A_f, b_f)

        # مقایسه با مرجع دقیق ماتریس float واقعی (نه ماتریس گویای ساده‌شده)
        y_ref_float_system = _exact_solve(_to_frac_matrix(A_f), _to_frac_vector(b_f))
        _assert_close_exact(
            self, y_solver, y_ref_float_system, REL_TOL_POWER_OF_TWO,
            f"{label} (مرجع float)",
        )

        # بررسی تکمیلی با جواب تحلیلی گویا (تبدیل پایه به دستگاه اصلی)
        inv_d2 = [1 / d for d in d_right]
        x_back = [y * d for y, d in zip(y_solver, d_right)]
        _assert_close_exact(
            self, x_back, X_BASE, REL_TOL_WELL_CONDITIONED,
            f"{label} (بازگردانی x)",
        )
        self.assertEqual(len(inv_d2), 2)

    def test_03_offdiag_scaling_first_pair(self):
        """Stage 6A-۳: D1=diag(4,1/2)، D2=diag(1/8,2)، y=[32/5, 7/10]."""
        d1 = [Fraction(4), Fraction(1, 2)]
        d2 = [Fraction(1, 8), Fraction(2)]
        y_expected = [Fraction(32, 5), Fraction(7, 10)]
        self._run_scaling(d1, d2, y_expected, "Stage6A-۳")

    def test_04_offdiag_scaling_second_pair(self):
        """Stage 6A-۴: D1=diag(8,1/2)، D2=diag(1/4,2)، y=[16/5, 7/10]."""
        d1 = [Fraction(8), Fraction(1, 2)]
        d2 = [Fraction(1, 4), Fraction(2)]
        y_expected = [Fraction(16, 5), Fraction(7, 10)]
        self._run_scaling(d1, d2, y_expected, "Stage6A-۴")


class PoissonTest(unittest.TestCase):
    """تست‌های ۵ و ۶: پواسون یک‌بعدی با جواب تحلیلی."""

    def _run_poisson(self, n):
        A = _poisson_matrix(n)
        x_exact = _poisson_exact(n)

        # بررسی تحلیلی مستقل: A·x_exact = 1 روی همهٔ سطرها
        A_frac = _to_frac_matrix(A)
        residual_exact = _mat_vec_frac(A_frac, x_exact)
        self.assertEqual(residual_exact, [Fraction(1)] * n)

        x = solve_dense(A, [1.0] * n)
        _assert_close_exact(
            self, x, x_exact, REL_TOL_WELL_CONDITIONED,
            f"Poisson n={n}",
        )

    def test_05_poisson_n5(self):
        """Stage 6A-۵: Poisson n=5، x = [5/2, 4, 9/2, 4, 5/2]."""
        self.assertEqual(
            _poisson_exact(5),
            [Fraction(5, 2), Fraction(4), Fraction(9, 2), Fraction(4), Fraction(5, 2)],
        )
        self._run_poisson(5)

    def test_06_poisson_n50(self):
        """Stage 6A-۶: Poisson n=50، x_25 = 325."""
        self.assertEqual(_poisson_exact(50)[24], Fraction(325))
        self._run_poisson(50)


class Hilbert4FloatReferenceTest(unittest.TestCase):
    """تست ۷: مرجع Hilbert 4 از روی ورودی float واقعی، نه فرض دقت گویا."""

    def test_07_hilbert4_float_reference(self):
        """Stage 6A-۷: A_fl = float(H_4)، b_fl = float(H_4·1)، مرجع R_fl از همین ورودی."""
        H = _hilbert_frac(4)
        ones = [Fraction(1)] * 4
        b_exact_frac = _mat_vec_frac(H, ones)

        # بردار صحیح مطابق بخش ۲ گزارش
        self.assertEqual(
            b_exact_frac,
            [Fraction(25, 12), Fraction(77, 60), Fraction(57, 60), Fraction(319, 420)],
        )

        A_fl = _float_matrix(H)
        b_fl = _float_vector(b_exact_frac)

        x = solve_dense(A_fl, b_fl)

        # مرجع مستقل: حل دقیق دستگاه float واقعی ورودی
        R_fl = _exact_solve(_to_frac_matrix(A_fl), _to_frac_vector(b_fl))

        # آستانهٔ قطعی: مقایسه با R_fl (ورودی دقیقاً همین است)
        # κ(H_4) = 28375، κ·u ≈ 3·10^{-12}؛ حد 10^{-10} حاشیهٔ حدود ۳۰ برابری دارد.
        _assert_close_exact(
            self, x, R_fl, REL_TOL_WELL_CONDITIONED,
            "Hilbert4 (مرجع R_fl)",
        )


class TridiagonalTest(unittest.TestCase):
    """تست‌های ۸ و ۹: سه‌قطری با جواب تمام‌یک."""

    def _run_tridiag(self, n):
        A = _tridiag_ones_matrix(n)
        b = _row_sums(A)  # b = A·1 با جمع سطرها

        # بررسی تحلیلی: مرزها و میانی
        self.assertEqual(b[0], 2.0 if n > 1 else 1.0)
        if n > 1:
            self.assertEqual(b[-1], 3.0)
        for i in range(1, n - 1):
            self.assertEqual(b[i], 4.0)

        x_exact = [Fraction(1)] * n
        # مرجع مستقل روی همان ماتریس
        self.assertEqual(_mat_vec_frac(_to_frac_matrix(A), x_exact), _to_frac_vector(b))

        x = solve_dense(A, b)
        _assert_close_exact(
            self, x, x_exact, REL_TOL_WELL_CONDITIONED,
            f"Tridiag n={n}",
        )

    def test_08_tridiagonal_n3(self):
        """Stage 6A-۸: n=3، A = [[1,1,0],[1,2,1],[0,1,2]]، b = [2,4,3]، x = [1,1,1]."""
        A = _tridiag_ones_matrix(3)
        self.assertEqual(A, [[1.0, 1.0, 0.0], [1.0, 2.0, 1.0], [0.0, 1.0, 2.0]])
        self.assertEqual(_row_sums(A), [2.0, 4.0, 3.0])
        self._run_tridiag(3)

    def test_09_tridiagonal_n20(self):
        """Stage 6A-۹: n=20، b = A·1، x = [1,…,1]."""
        self._run_tridiag(20)


class LargeScalarMatrixTest(unittest.TestCase):
    """تست ۱۰: 1e300·I با جواب معلوم."""

    def test_10_huge_scalar_identity(self):
        """Stage 6A-۱۰: A = 1e300·I_2، b = 1e300·[1,1]، x = [1,1].

        این تست فقط ماتریس قطری یکنواخت با مقیاس بزرگ را پوشش می‌دهد.
        پوشش نمی‌دهد: ماتریس غیرقطری، اختلاف مقیاس بین سطرها، سرریز میانی در حذف.
        """
        A = [[1e300, 0.0], [0.0, 1e300]]
        b = [1e300, 1e300]
        x = solve_dense(A, b)
        _assert_finite_vector(self, x, "1e300·I")
        self.assertEqual(x, [1.0, 1.0])


if __name__ == "__main__":
    unittest.main()
