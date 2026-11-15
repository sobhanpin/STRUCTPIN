"""Stage 6B (نسخه اصلاح‌شده): بررسی باقیمانده، خطای عقب‌گرد و خطای جلو برای solve_dense.

قراردادها:
    - فقط از API عمومی solve_dense(A, b, rel_tol=1e-9) استفاده می‌شود.
    - همه مرجع‌ها و مقادیر (det، معکوس، κ∞، η، خطای جلو) با fractions.Fraction
      از خود ورودی float محاسبه می‌شوند، نه از اعداد اعشاری ایده‌آل.
    - ورودی float ایده‌آل فقط وقتی مجاز است که اعداد دقیقاً قابل نمایش باشند
      (اعداد صحیح یا توان‌های دو). در غیر این صورت، مرجع از ورودی float گرفته می‌شود.
    - κ∞ و η تعریف مستقیم دارند؛ هیچ کران نظری (مثل κη/(1−κη)) به‌عنوان قطعی استفاده نمی‌شود.
    - هیچ مقدار hard-coded برای κ یا det از ماتریس‌های float غیرصحیح ادعا نمی‌شود.

اجرا:
    PYTHONPATH=src python -m unittest tests.test_linalg_stage6b -v
"""

import math
import random
import unittest
from fractions import Fraction

from structpin.fem.linalg import solve_dense, SingularSystemError


# ---------------------------------------------------------------------------
# آستانه‌ها (تجربی؛ هر کدام در docstring تست توجیه شده است)
# ---------------------------------------------------------------------------

# η برای دستگاه‌های خوش‌رفتار با κ کوچک. ماشین نوعی float64 در حد ~1e-16 تا ~1e-15 است؛
# 1e-12 حاشیه‌ای حدود 1e3 تا 1e4 برابر می‌دهد.
ETA_TOL_WELL = Fraction(1, 10 ** 12)

# η برای H5 (κ بزرگ‌تر). حد سست‌تر چون κ بزرگ است؛ فقط برای رد خطای فاحش.
ETA_TOL_ILL = Fraction(1, 10 ** 8)

# خطای جلو برای ماتریس‌های خوش‌رفتار با جواب مرجع دقیق. κ·u کوچک است.
FWD_TOL_WELL = Fraction(1, 10 ** 10)


# ---------------------------------------------------------------------------
# حساب دقیق مستقل از solve_dense
# ---------------------------------------------------------------------------

def _to_frac_matrix(A):
    return [[Fraction(v) for v in row] for row in A]


def _to_frac_vector(v):
    return [Fraction(x) for x in v]


def _vec_norm_inf(v):
    return max((abs(x) for x in v), default=Fraction(0))


def _mat_norm_inf(A):
    return max((sum((abs(a) for a in row), Fraction(0)) for row in A), default=Fraction(0))


def _mat_vec(A, x):
    return [sum((a * xi for a, xi in zip(row, x)), Fraction(0)) for row in A]


def _vec_sub(a, b):
    return [x - y for x, y in zip(a, b)]


def _exact_solve(A, b):
    """حل دقیق A x = b با حذف گاوسی و پیوت جزئی روی Fraction (بدون solve_dense)."""
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
        s = M[r][n] - sum((M[r][c] * x[c] for c in range(r + 1, n)), Fraction(0))
        x[r] = s / M[r][r]
    return x


def _exact_inverse(A):
    n = len(A)
    cols = [_exact_solve(A, [Fraction(int(i == j)) for i in range(n)]) for j in range(n)]
    return [[cols[j][i] for j in range(n)] for i in range(n)]


def _det_exact(A):
    """دترمینان دقیق با حذف گاوسی روی Fraction و جابه‌جایی سطر."""
    n = len(A)
    M = _to_frac_matrix(A)
    det = Fraction(1)
    for k in range(n):
        p = next((r for r in range(k, n) if M[r][k] != 0), None)
        if p is None:
            return Fraction(0)
        if p != k:
            M[k], M[p] = M[p], M[k]
            det = -det
        det *= M[k][k]
        for r in range(k + 1, n):
            f = M[r][k] / M[k][k]
            for c in range(k, n):
                M[r][c] -= f * M[k][c]
    return det


def _kappa_inf_exact(A):
    """κ∞(A) = ‖A‖∞ · ‖A⁻¹‖∞ با Fraction، از همان ورودی A داده‌شده."""
    Af = _to_frac_matrix(A)
    return _mat_norm_inf(Af) * _mat_norm_inf(_exact_inverse(Af))


def _eta_exact(A, x, b):
    """η = ‖b − A x‖∞ / (‖A‖∞ ‖x‖∞ + ‖b‖∞) با Fraction.

    مخرج صفر: مقدار مطلق ‖r‖∞ با نوع 'absolute' برگردانده می‌شود.
    """
    Af = _to_frac_matrix(A)
    X = _to_frac_vector(x)
    bf = _to_frac_vector(b)
    r = _vec_sub(bf, _mat_vec(Af, X))
    r_norm = _vec_norm_inf(r)
    denom = _mat_norm_inf(Af) * _vec_norm_inf(X) + _vec_norm_inf(bf)
    if denom == 0:
        return r_norm, "absolute"
    return r_norm / denom, "ratio"


def _fwd_error_exact(x_float, x_ref):
    """‖x − x_ref‖∞ / ‖x_ref‖∞ با Fraction؛ x_ref باید ناصفر باشد."""
    diff = _vec_sub(_to_frac_vector(x_float), _to_frac_vector(x_ref))
    return _vec_norm_inf(diff) / _vec_norm_inf(_to_frac_vector(x_ref))


def _assert_finite_list(tc, x, n, label):
    tc.assertIsInstance(x, list, msg=f"{label}: خروجی باید list باشد")
    tc.assertEqual(len(x), n, msg=f"{label}: طول {len(x)} به‌جای {n}")
    for i, v in enumerate(x):
        tc.assertTrue(math.isfinite(v), msg=f"{label}: مؤلفهٔ {i} غیرمتناهی است")


def _hilbert_frac(n):
    return [[Fraction(1, i + j + 1) for j in range(n)] for i in range(n)]


def _to_float_matrix(M):
    return [[float(v) for v in row] for row in M]


def _to_float_vector(v):
    return [float(x) for x in v]


# ---------------------------------------------------------------------------
# گروه R: باقیمانده و خطای عقب‌گرد (۳ تست)
# ---------------------------------------------------------------------------

class ResidualBackwardErrorTest(unittest.TestCase):
    """η روی دستگاه‌های با جواب معلوم و ورودی‌های دقیقاً قابل نمایش.

    هم‌پوشانی: R1 و R2 همان ماتریس‌های B1 و B2 در test_linalg_robustness.py هستند.
    معیار η در آن فایل وجود ندارد؛ این تست آن را صریحاً اضافه می‌کند.
    """

    def test_R1_two_by_two_backward_error(self):
        """R1: A = [[2,1],[1,3]] (ورودی صحیح)، x* = [4/5, 7/5]، b = A x* = [3, 5].

        ورودی‌ها صحیح‌اند، پس Fraction(float) دقیق است.
        det = 5، κ∞ = (4)·(4/5) = 16/5 (محاسبه در کد).
        انتظار: η ≤ ETA_TOL_WELL؛ خطای جلو نسبت به x* ≤ FWD_TOL_WELL.
        """
        A = [[2.0, 1.0], [1.0, 3.0]]
        x_exact = [Fraction(4, 5), Fraction(7, 5)]
        b = _to_float_vector(_mat_vec(_to_frac_matrix(A), x_exact))
        self.assertEqual(b, [3.0, 5.0])
        self.assertEqual(_det_exact(A), Fraction(5))
        self.assertEqual(_kappa_inf_exact(A), Fraction(16, 5))

        x = solve_dense(A, b)
        _assert_finite_list(self, x, 2, "R1")
        eta, _ = _eta_exact(A, x, b)
        self.assertLessEqual(eta, ETA_TOL_WELL, msg=f"R1 η={float(eta):.3e}")
        self.assertLessEqual(_fwd_error_exact(x, x_exact), FWD_TOL_WELL)

    def test_R2_spd_three_by_three_backward_error(self):
        """R2: A = [[4,−2,1],[−2,4,−2],[1,−2,4]] (ورودی صحیح)، x* = [1,−2,3].

        محاسبات (بررسی شده):
            det(A) = 36
            adj(A) = [[12,6,0],[6,15,6],[0,6,12]]، A⁻¹ = adj/36
            ‖A‖∞ = 8، ‖A⁻¹‖∞ = 27/36 = 3/4، κ∞ = 6
        """
        A = [[4.0, -2.0, 1.0], [-2.0, 4.0, -2.0], [1.0, -2.0, 4.0]]
        A_frac = _to_frac_matrix(A)
        x_exact = [Fraction(1), Fraction(-2), Fraction(3)]

        self.assertEqual(_det_exact(A), Fraction(36))
        adj = [
            [Fraction(12), Fraction(6), Fraction(0)],
            [Fraction(6), Fraction(15), Fraction(6)],
            [Fraction(0), Fraction(6), Fraction(12)],
        ]
        self.assertEqual(_exact_inverse(A_frac), [[v / 36 for v in row] for row in adj])
        self.assertEqual(_mat_norm_inf(A_frac), Fraction(8))
        self.assertEqual(_mat_norm_inf(_exact_inverse(A_frac)), Fraction(3, 4))
        self.assertEqual(_kappa_inf_exact(A), Fraction(6))

        b = _to_float_vector(_mat_vec(A_frac, x_exact))
        self.assertEqual(b, [11.0, -16.0, 17.0])

        x = solve_dense(A, b)
        _assert_finite_list(self, x, 3, "R2")
        eta, _ = _eta_exact(A, x, b)
        self.assertLessEqual(eta, ETA_TOL_WELL, msg=f"R2 η={float(eta):.3e}")
        self.assertLessEqual(_fwd_error_exact(x, x_exact), FWD_TOL_WELL)

    def test_R3_nonuniform_magnitude_backward_error(self):
        """R3: A = [[1e6, 2e6], [3e-6, 4e-6]]، x* = [1, 1].

        ورودی‌های 1e6 و 2e6 دقیق‌اند؛ 3e-6 و 4e-6 دقیق نیستند. b از همان
        ورودی float محاسبه می‌شود تا مرجع با ورودی سازگار باشد.
        det(A_float) در Fraction از همان ورودی float محاسبه و فقط ناصفر بودن ادعا می‌شود.
        این تست فقط η را می‌سنجد؛ خطای جلو ادعا نمی‌شود چون κ بزرگ است.
        """
        A = [[1e6, 2e6], [3e-6, 4e-6]]
        det = _det_exact(A)
        self.assertNotEqual(det, 0)
        b = _to_float_vector(_mat_vec(_to_frac_matrix(A), [Fraction(1), Fraction(1)]))
        x = solve_dense(A, b)
        _assert_finite_list(self, x, 2, "R3")
        eta, _ = _eta_exact(A, x, b)
        self.assertLessEqual(eta, ETA_TOL_WELL, msg=f"R3 η={float(eta):.3e}")


# ---------------------------------------------------------------------------
# گروه F: ثبت خطای جلو نسبت به R_fl (بدون کران نظری)
# ---------------------------------------------------------------------------

class ForwardErrorRecordTest(unittest.TestCase):
    """خطای جلو نسبت به R_fl ثبت می‌شود؛ R_fl جواب دقیق Fraction دستگاه float ورودی است.

    هیچ کران κη/(1−κη) استفاده نمی‌شود. فقط η و متناهی بودن ادعا می‌شوند.
    مقدار خطای جلو برای مطالعه چاپ می‌شود.
    """

    def _run(self, n, label):
        H = _hilbert_frac(n)
        A_fl = _to_float_matrix(H)
        b_fl = _to_float_vector(_mat_vec(H, [Fraction(1)] * n))
        R_fl = _exact_solve(_to_frac_matrix(A_fl), _to_frac_vector(b_fl))
        x = solve_dense(A_fl, b_fl)
        _assert_finite_list(self, x, n, label)
        eta, _ = _eta_exact(A_fl, x, b_fl)
        fwd = _fwd_error_exact(x, R_fl)
        self.assertLessEqual(eta, ETA_TOL_WELL, msg=f"{label} η={float(eta):.3e}")
        print(f"[{label}] η={float(eta):.3e}  خطای جلو نسبت به R_fl={float(fwd):.3e}")

    def test_F1_hilbert3_float_forward_recorded(self):
        """F1: H3 با ورودی float. κ∞ تأییدشده در گفتگو (748)."""
        self._run(3, "F1-H3")

    def test_F2_hilbert4_float_forward_recorded(self):
        """F2: H4 با ورودی float. κ∞ تأییدشده در گفتگو (28375)."""
        self._run(4, "F2-H4")


# ---------------------------------------------------------------------------
# گروه C: H5 و تفکیک رد عددی از تکینگی (۲ تست)
# ---------------------------------------------------------------------------

class HilbertFiveAndRejectionTest(unittest.TestCase):

    def test_C1_hilbert5_nonsingular_and_outcome(self):
        """C1: H5 ناتکین است؛ κ∞ از ورودی float با Fraction محاسبه و چاپ می‌شود.

        عدد κ∞(H5) در این تست hard-coded نیست. ادعای مقدار عددی تأییدشده نیست؛
        فقط ناتکین بودن و پذیرش یا رد عددی بررسی می‌شود.
        انتظار: یا جواب متناهی با η ≤ ETA_TOL_ILL، یا SingularSystemError (رد عددی).
        """
        H5 = _to_float_matrix(_hilbert_frac(5))
        self.assertNotEqual(_det_exact(H5), 0)
        kappa = _kappa_inf_exact(H5)
        print(f"[C1] κ∞(H5) از ورودی float با Fraction = {kappa} ≈ {float(kappa):.6e}")

        b = _to_float_vector(_mat_vec(_to_frac_matrix(H5), [Fraction(1)] * 5))
        try:
            x = solve_dense(H5, b)
        except SingularSystemError:
            return  # رد عددی؛ تکینگی ریاضی ادعا نمی‌شود
        _assert_finite_list(self, x, 5, "C1")
        eta, _ = _eta_exact(H5, x, b)
        self.assertLessEqual(eta, ETA_TOL_ILL, msg=f"C1 η={float(eta):.3e}")

    def test_C2_nearly_singular_nonsingular_rejected_by_threshold(self):
        """C2: A = [[1,1],[1,1+2^{-40}]]، b = [2, 2+2^{-40}].

        ورودی‌ها دقیقاً قابل نمایش‌اند (توان دو).
        det = 2^{-40} ≠ 0 (ناتکین ریاضی).
        پیوت دوم در حذف گاوسی = 2^{-40} ≈ 9.1e-13 ≤ rel_tol = 1e-9.
        انتظار: SingularSystemError به‌عنوان رد عددی تحت آستانه (نه اثبات تکینگی).
        """
        d = 2.0 ** -40
        A = [[1.0, 1.0], [1.0, 1.0 + d]]
        self.assertNotEqual(_det_exact(A), 0)
        b = [2.0, 2.0 + d]
        with self.assertRaises(SingularSystemError):
            solve_dense(A, b)


# ---------------------------------------------------------------------------
# گروه D: ماتریس‌های خوش‌رفتار با مقیاس نامتوازن (۲ تست)
# ---------------------------------------------------------------------------

class WellConditionedNonuniformTest(unittest.TestCase):

    def test_D1_nonuniform_magnitudes_backward_error(self):
        """D1: A = [[3, 1e-3], [2e3, 5]]، x* = [1, −2].

        اصلاح ایراد قبلی: det از ورودی float با Fraction محاسبه می‌شود و فقط
        ناصفر بودن ادعا می‌شود. مقدار 13 (ایده‌آل) ادعا نمی‌شود، چون
        fl(1e-3) دقیقاً 1/1000 نیست.
        κ∞ از همین ورودی float محاسبه و چاپ می‌شود.
        انتظار: η ≤ ETA_TOL_WELL.
        """
        A = [[3.0, 1e-3], [2e3, 5.0]]
        A_frac = _to_frac_matrix(A)
        det = _det_exact(A)
        self.assertNotEqual(det, 0)
        kappa = _kappa_inf_exact(A)
        print(f"[D1] det(ورودی float)={float(det):.17g}  κ∞={kappa} ≈ {float(kappa):.6e}")

        b = _to_float_vector(_mat_vec(A_frac, [Fraction(1), Fraction(-2)]))
        x = solve_dense(A, b)
        _assert_finite_list(self, x, 2, "D1")
        eta, _ = _eta_exact(A, x, b)
        self.assertLessEqual(eta, ETA_TOL_WELL, msg=f"D1 η={float(eta):.3e}")

    def test_D2_tridiagonal_known_kappa(self):
        """D2: A = [[4,1,0],[1,4,1],[0,1,4]] (ورودی صحیح)، x* = [1,2,3]، b = [6,12,14].

        det = 56، ‖A‖∞ = 6، ‖A⁻¹‖∞ = 24/56 = 3/7، κ∞ = 18/7 (کد بازتأیید می‌کند).
        انتظار: η ≤ ETA_TOL_WELL، خطای جلو ≤ FWD_TOL_WELL.
        """
        A = [[4.0, 1.0, 0.0], [1.0, 4.0, 1.0], [0.0, 1.0, 4.0]]
        x_exact = [Fraction(1), Fraction(2), Fraction(3)]
        self.assertEqual(_det_exact(A), Fraction(56))
        self.assertEqual(_kappa_inf_exact(A), Fraction(18, 7))
        b = _to_float_vector(_mat_vec(_to_frac_matrix(A), x_exact))
        self.assertEqual(b, [6.0, 12.0, 14.0])
        x = solve_dense(A, b)
        _assert_finite_list(self, x, 3, "D2")
        eta, _ = _eta_exact(A, x, b)
        self.assertLessEqual(eta, ETA_TOL_WELL, msg=f"D2 η={float(eta):.3e}")
        self.assertLessEqual(_fwd_error_exact(x, x_exact), FWD_TOL_WELL)


# ---------------------------------------------------------------------------
# گروه G: ماتریس‌های تصادفی قطعی با قطر غالب (۲ تست)
# ---------------------------------------------------------------------------

class DeterministicDominantTest(unittest.TestCase):
    """قطر غالب اکید سطری ⇒ ناتکین (قضیه Levy–Desplanques، قطعی).

    κ هر ماتریس به‌صورت مستقل محاسبه و چاپ می‌شود. هیچ کران κ از قطر غالب گرفته نمی‌شود.
    """

    def _build(self, n, seed):
        rng = random.Random(seed)
        A = [[0.0] * n for _ in range(n)]
        for i in range(n):
            off = 0.0
            for j in range(n):
                if i != j:
                    v = rng.randint(-2, 2) / 4.0
                    A[i][j] = v
                    off += abs(v)
            A[i][i] = off + 1.0 + rng.randint(0, 2) / 4.0
        x = [Fraction(rng.randint(-3, 3)) for _ in range(n)]
        return A, x

    def _check(self, n, seed, label):
        A, x_exact = self._build(n, seed)
        self.assertNotEqual(_det_exact(A), 0, msg=f"{label}: قطر غالب باید ناتکین بودن را تضمین کند")
        kappa = _kappa_inf_exact(A)
        print(f"[{label}] κ∞ = {kappa} ≈ {float(kappa):.6e}")
        b = _to_float_vector(_mat_vec(_to_frac_matrix(A), x_exact))
        x = solve_dense(A, b)
        _assert_finite_list(self, x, n, label)
        eta, _ = _eta_exact(A, x, b)
        self.assertLessEqual(eta, ETA_TOL_WELL, msg=f"{label} η={float(eta):.3e}")

    def test_G1_dominant_three(self):
        """G1: n = 3، seed = 12345."""
        self._check(3, 12345, "G1")

    def test_G2_dominant_eight(self):
        """G2: n = 8، seed = 2024."""
        self._check(8, 2024, "G2")


if __name__ == "__main__":
    unittest.main()
