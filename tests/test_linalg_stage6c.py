"""Stage 6C: اعتبارسنجی جواب solve_dense روی ماتریس بد مقیاس با مرجع Fraction.

اجرا (در ریشهٔ مخزن):
    PYTHONPATH=src python -m unittest discover -s tests -p "test_linalg_stage6c.py" -v

وضعیت این فایل:
    - این فایل اجرا نشده است. هیچ نتیجه‌ای موفق یا ناموفق اعلام نمی‌شود.
    - متن واقعی linalg.py در مخزن بررسی نشده است؛ فقط نسخهٔ ارسالی در گفتگو مبنا است.

آنچه تست‌ها اثبات می‌کنند:
    - (01–03، 06) ورودی float دقیق است؛ det، معکوس، ‖·‖∞ و κ∞ هر دو ماتریس با Fraction؛
      حل مرجع Fraction با حذف گاوسی مستقل از solve_dense برابر [1,1] است.
    - (04، 05) بازسازی مستقل الگوی مقیاس‌بندی توانی دو و ریاضیات A_s در Fraction.
      این‌ها آزمون مستقیم کد داخلی linalg.py نیستند؛ فقط نشان می‌دهند الگوی بازسازی‌شده
      با تعریف مقیاس‌بندی این مثال سازگار است.
    - (07–10) رفتار خروجی solve_dense: متناهی بودن، η، خطای جلو، و سازگاری با مرجع Fraction.

آنچه تست‌ها اثبات نمی‌کنند:
    - پیاده‌سازی داخلی solve_dense به‌طور مستقیم (تست‌های 04 و 05 آن را فراخوانی نمی‌کنند).
    - برتری مقیاس‌بندی نسبت به حل بدون مقیاس (عمداً مقایسه عملکرد ادعا نشده).
    - پایداری عمومی solve_dense برای همهٔ ماتریس‌ها یا مدل‌های سازه‌ای بزرگ.
    - صحت آستانه‌های ETA_TOL و FWD_TOL؛ این‌ها معیارهای تجربی پیشنهادی‌اند، نه تضمین نظری
      و تا مشاهدهٔ خروجی واقعی اجرا تأییدشده نیستند.
"""

import math
import unittest
from fractions import Fraction

from structpin.fem.linalg import solve_dense


# ---------------------------------------------------------------------------
# داده‌های دقیق مثال
# ---------------------------------------------------------------------------

TWO20 = Fraction(2) ** 20
TWO_M20 = Fraction(1, 2 ** 20)
TWO_M21 = Fraction(1, 2 ** 21)

# A = [[2^20, 1], [1, 1 + 2^-20]]؛ همه درایه‌ها دقیقاً در float قابل نمایش‌اند.
A = [[float(TWO20), 1.0], [1.0, 1.0 + 2.0 ** -20]]
A_FRAC = [[TWO20, Fraction(1)], [Fraction(1), Fraction(1) + TWO_M20]]

X_STAR = [Fraction(1), Fraction(1)]
B_FRAC = [TWO20 + 1, Fraction(2) + TWO_M20]
B = [float(v) for v in B_FRAC]


# ---------------------------------------------------------------------------
# معیارهای تجربی پیشنهادی (تأییدنشده با اجرای واقعی)
# ---------------------------------------------------------------------------

# ETA_TOL: معیار تجربی پیشنهادی برای backward error نرمال‌شده.
# مبنای پیشنهاد: ماشین float64 و مرتبهٔ ε·(ضرایب کوچک). این یک تضمین نظری نیست.
ETA_TOL = Fraction(1, 10 ** 12)

# FWD_TOL: معیار تجربی پیشنهادی برای خطای جلو نسبت به [1,1].
# مبنای پیشنهاد: مرتبهٔ κ·u با κ≈1e6 و u≈1.1e-16 که حدود 1e-10 است؛ 1e-8 حاشیهٔ محافظه‌کارانه.
# این یک کران نظری قطعی نیست.
FWD_TOL = Fraction(1, 10 ** 8)


# ---------------------------------------------------------------------------
# ابزارهای حساب دقیق (مستقل از solve_dense)
# ---------------------------------------------------------------------------

def _mat_norm_inf(M):
    return max(sum((abs(v) for v in row), Fraction(0)) for row in M)


def _vec_norm_inf(v):
    return max(abs(x) for x in v)


def _mat_vec(M, x):
    return [sum((a * xi for a, xi in zip(row, x)), Fraction(0)) for row in M]


def _det2(M):
    return M[0][0] * M[1][1] - M[0][1] * M[1][0]


def _inv2(M):
    d = _det2(M)
    return [
        [M[1][1] / d, -M[0][1] / d],
        [-M[1][0] / d, M[0][0] / d],
    ]


def _kappa_inf_2(M):
    return _mat_norm_inf(M) * _mat_norm_inf(_inv2(M))


def _exact_gauss_solve(M, b):
    """حذف گاوسی با پیوت جزئی روی Fraction (مرجع مستقل، بدون solve_dense)."""
    n = len(b)
    T = [row[:] + [bi] for row, bi in zip(M, b)]
    for k in range(n):
        p = max(range(k, n), key=lambda r: abs(T[r][k]))
        if T[p][k] == 0:
            raise ValueError("ماتریس در حساب دقیق تکین است")
        T[k], T[p] = T[p], T[k]
        for r in range(k + 1, n):
            f = T[r][k] / T[k][k]
            for c in range(k, n + 1):
                T[r][c] -= f * T[k][c]
    x = [Fraction(0)] * n
    for r in range(n - 1, -1, -1):
        s = T[r][n] - sum((T[r][c] * x[c] for c in range(r + 1, n)), Fraction(0))
        x[r] = s / T[r][r]
    return x


def _frexp_exp(v):
    """توان e در v = m·2^e با m ∈ [1/2, 1)، برای Fraction مثبت (بازسازی frexp)."""
    e = 0
    m = v
    while m >= 1:
        m /= 2
        e += 1
    while m < Fraction(1, 2):
        m *= 2
        e -= 1
    return e


def _reference_scaling_exponents(M):
    """بازسازی مستقل الگوی مقیاس‌بندی solve_dense با Fraction.

    این یک بازسازی از روی تعریف است، نه فراخوانی کد linalg.py.

    row_exp[i] = frexp(max_j |a_ij|)[1]
    col_exp[j] = max_i (frexp(|a_ij|)[1] − row_exp[i]) روی a_ij ≠ 0
    """
    n = len(M)
    row_exp = [_frexp_exp(max(abs(v) for v in M[i])) for i in range(n)]
    col_exp = []
    for j in range(n):
        best = None
        for i in range(n):
            if M[i][j] != 0:
                q = _frexp_exp(abs(M[i][j])) - row_exp[i]
                if best is None or q > best:
                    best = q
        col_exp.append(best)
    return row_exp, col_exp


def _scaled_matrix_exact(M, row_exp, col_exp):
    """A_s[i][j] = a_ij · 2^{−(row_exp[i] + col_exp[j])} با Fraction (بدون float)."""
    n = len(M)
    return [
        [M[i][j] * (Fraction(2) ** (-(row_exp[i] + col_exp[j]))) for j in range(n)]
        for i in range(n)
    ]


def _eta_exact(M, x, b):
    """η = ‖b − A x‖∞ / (‖A‖∞‖x‖∞ + ‖b‖∞) با Fraction."""
    r = [bi - ax for bi, ax in zip(b, _mat_vec(M, x))]
    denom = _mat_norm_inf(M) * _vec_norm_inf(x) + _vec_norm_inf(b)
    return _vec_norm_inf(r) / denom


def _fwd_error_exact(x_float, x_ref):
    diff = [Fraction(a) - b for a, b in zip(x_float, x_ref)]
    return _vec_norm_inf(diff) / _vec_norm_inf(x_ref)


# ---------------------------------------------------------------------------
# تست‌ها
# ---------------------------------------------------------------------------

class Stage6CExactReferenceTest(unittest.TestCase):
    """اثبات‌های مستقل روی ماتریس و بردار (بدون solve_dense)."""

    def test_01_input_is_exact_in_float(self):
        """اثبات: ورودی float همان ماتریس Fraction است.

        دلیل: 2^20، 1 و 1+2^-20 در float64 دقیق‌اند.
        اثبات نمی‌کند: چیزی درباره دقت solve_dense.
        """
        self.assertEqual([[Fraction(v) for v in row] for row in A], A_FRAC)
        self.assertEqual([Fraction(v) for v in B], B_FRAC)

    def test_02_determinant_and_inverse_exact(self):
        """اثبات: det(A) = 2^20 و A·A^{-1} = I با Fraction."""
        self.assertEqual(_det2(A_FRAC), TWO20)
        inv = _inv2(A_FRAC)
        prod = [
            [sum(A_FRAC[i][k] * inv[k][j] for k in range(2)) for j in range(2)]
            for i in range(2)
        ]
        self.assertEqual(prod, [[Fraction(1), Fraction(0)], [Fraction(0), Fraction(1)]])

    def test_03_kappa_inf_original_exact(self):
        """اثبات: κ∞(A) = (2^20+1)²/2^20 با Fraction.

        ‖A‖∞ = 2^20+1، ‖A^{-1}‖∞ = (2^20+1)/2^20.
        """
        expected = (TWO20 + 1) ** 2 / TWO20
        self.assertEqual(_mat_norm_inf(A_FRAC), TWO20 + 1)
        self.assertEqual(_kappa_inf_2(A_FRAC), expected)

    def test_04_reconstructed_scaling_exponents(self):
        """بازسازی مستقل (نه آزمون linalg.py): row_exp = [21, 1]، col_exp = [0, 0].

        سطر ۱: frexp(2^20) = (0.5, 21). سطر ۲: frexp(1+2^-20) = (0.5+2^-21, 1).
        ستون ۱: max(21−21, 1−1) = 0. ستون ۲: max(1−21, 1−1) = 0.
        """
        row_exp, col_exp = _reference_scaling_exponents(A_FRAC)
        self.assertEqual(row_exp, [21, 1])
        self.assertEqual(col_exp, [0, 0])

    def test_05_reconstructed_scaled_matrix_and_its_kappa(self):
        """بازسازی مستقل ریاضیات A_s (نه آزمون linalg.py).

        A_s = [[1/2, 2^-21], [1/2, 1/2 + 2^-21]]، det(A_s) = 1/4، κ∞(A_s) = 4 + 2^-19.
        """
        row_exp, col_exp = _reference_scaling_exponents(A_FRAC)
        A_s = _scaled_matrix_exact(A_FRAC, row_exp, col_exp)
        expected = [
            [Fraction(1, 2), TWO_M21],
            [Fraction(1, 2), Fraction(1, 2) + TWO_M21],
        ]
        self.assertEqual(A_s, expected)
        self.assertEqual(_det2(A_s), Fraction(1, 4))
        self.assertEqual(_kappa_inf_2(A_s), 4 + Fraction(1, 2 ** 19))

    def test_06_exact_reference_solution_is_one_one(self):
        """اثبات: حل دقیق Gauss-Fraction روی A و b برابر [1,1] است (مستقل از solve_dense)."""
        x = _exact_gauss_solve(A_FRAC, B_FRAC)
        self.assertEqual(x, X_STAR)


class Stage6CSolverBehaviourTest(unittest.TestCase):
    """رفتار خروجی solve_dense روی همین ماتریس (تست رفتار، نه تست داخلی)."""

    def test_07_solver_returns_finite_list_of_length_two(self):
        """solve_dense یک list با دو مؤلفهٔ متناهی برمی‌گرداند. دقت را نمی‌سنجد."""
        x = solve_dense(A, B)
        self.assertIsInstance(x, list)
        self.assertEqual(len(x), 2)
        for v in x:
            self.assertTrue(math.isfinite(v))

    def test_08_solver_backward_error_against_pilot_threshold(self):
        """η خروجی solve_dense با Fraction، در برابر معیار تجربی پیشنهادی ETA_TOL.

        ETA_TOL تأییدشده با اجرای واقعی نیست؛ این تست فقط آن را به‌عنوان معیار پیشنهادی
        به کار می‌برد و هیچ ادعای نظری ندارد.
        """
        x = solve_dense(A, B)
        eta = _eta_exact(A_FRAC, [Fraction(v) for v in x], B_FRAC)
        self.assertLessEqual(eta, ETA_TOL, msg=f"η={float(eta):.3e} از ETA_TOL پیشنهادی بیشتر است")

    def test_09_solver_forward_error_against_pilot_threshold(self):
        """‖x_solver − [1,1]‖∞ در برابر معیار تجربی پیشنهادی FWD_TOL.

        FWD_TOL تأییدشده با اجرای واقعی نیست و کران نظری نیست.
        """
        x = solve_dense(A, B)
        fwd = _fwd_error_exact(x, X_STAR)
        self.assertLessEqual(fwd, FWD_TOL, msg=f"خطای جلو={float(fwd):.3e} از FWD_TOL پیشنهادی بیشتر است")

    def test_10_solver_agrees_with_exact_gauss_reference(self):
        """سازگاری solve_dense با مرجع Fraction حذف گاوسی، در برابر FWD_TOL پیشنهادی.

        این مقایسه با مرجع Fraction است، نه مقایسه عملکرد دو حل‌گر float.
        """
        x = solve_dense(A, B)
        x_ref = _exact_gauss_solve(A_FRAC, B_FRAC)
        fwd = _fwd_error_exact(x, x_ref)
        self.assertLessEqual(fwd, FWD_TOL, msg=f"اختلاف با مرجع Fraction={float(fwd):.3e}")


if __name__ == "__main__":
    unittest.main()
