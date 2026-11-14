"""ممیزی عددی solve_dense — فایل تست مرحلهٔ چهارم STRUCTPIN.

ساختار:
    A (5)  اعتبارسنجی ابزارهای ممیزی                  همیشه فعال
    B (5)  رفتار حل‌گر در دستگاه‌های گویا               همیشه فعال
    S (4)  حساسیت جواب به اغتشاش                        همیشه فعال
    E (4)  تست‌های ساختاری حفظ‌شده                      همیشه فعال
    C (7)  ثبت رفتار قبل از پیاده‌سازی                  فقط وقتی پرچم مربوط False است
    D (7)  رفتار هدف پس از پیاده‌سازی                   فقط وقتی پرچم مربوط True است
    N (13) تست‌های جدید: مقیاس‌بندی، جایگشت، صفر، زیرنرمال،
           سرریز، تکینگی، اعتبارسنجی ورودی                همیشه فعال

قواعد:
    - بررسی‌های قطعی فقط بر پایهٔ جواب دقیق گویا، متناهی بودن، ابعاد، هویت‌های
      ریاضی روی ماتریس، و کران‌های مقدماتی اثبات‌شده در همان docstring هستند.
    - K_bw و K_fwd تشخیصی‌اند و فقط با warnings.warn هشدار می‌دهند.
    - A1 گزارشی است و آستانهٔ قبولی ندارد.
    - هیچ expectedFailure استفاده نشده است.
    - این فایل هیچ تستی را اجراشده یا موفق اعلام نمی‌کند.

اجرا (روی ماشین شما یا GitHub Actions):
    set PYTHONPATH=src
    python -m unittest tests.test_linalg_robustness -v
"""

import math
import sys
import unittest
import warnings
from fractions import Fraction

from structpin.fem.linalg import (
    solve_dense,
    SingularSystemError,
    NumericalOverflowError,
    NumericalUnderflowError,
)


# ---------------------------------------------------------------------------
# پرچم‌های وضعیت (پس از پیاده‌سازی مرحلهٔ چهارم برابر True)
# ---------------------------------------------------------------------------

SCALE_AWARE_PIVOT_IMPLEMENTED = True
FINITE_INPUT_GUARD_IMPLEMENTED = True


# ---------------------------------------------------------------------------
# ثابت‌های دقیق
# ---------------------------------------------------------------------------

U = Fraction(1, 2 ** 53)
DELTA = Fraction(1, 2 ** 20)
PRACTICAL_REL_TOL = Fraction(1, 10 ** 10)


# ---------------------------------------------------------------------------
# حساب دقیق با fractions.Fraction
# ---------------------------------------------------------------------------

def _frac_matrix(A):
    return [[Fraction(v) for v in row] for row in A]


def _frac_vector(v):
    return [Fraction(x) for x in v]


def _norm_inf_vec(v):
    return max(abs(x) for x in v)


def _norm_inf_mat(A):
    return max(sum(abs(a) for a in row) for row in A)


def _mat_vec(A, x):
    return [sum(a * xi for a, xi in zip(row, x)) for row in A]


def _mat_sub(A, B):
    return [[a - b for a, b in zip(ra, rb)] for ra, rb in zip(A, B)]


def _vec_sub(a, b):
    return [x - y for x, y in zip(a, b)]


def _exact_solve(A, b):
    """حل دقیق A x = b با حذف گاوسی و پیوت جزئی روی Fraction."""
    M = [row + [b_i] for row, b_i in zip(_frac_matrix(A), _frac_vector(b))]
    n = len(b)
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
    cols = [_exact_solve(A, [Fraction(int(i == j)) for i in range(n)]) for j in range(n)]
    return [[cols[j][i] for j in range(n)] for i in range(n)]


def _kappa_inf(A):
    Af = _frac_matrix(A)
    return _norm_inf_mat(Af) * _norm_inf_mat(_exact_inverse(Af))


def _growth_factor(A):
    """ρ = max_k max_ij |a_ij^(k)| / max_ij |a_ij^(0)| با پیوت جزئی روی Fraction."""
    M = _frac_matrix(A)
    n = len(M)
    a0 = max(abs(v) for row in M for v in row)
    peak = a0
    for k in range(n - 1):
        p = max(range(k, n), key=lambda r: abs(M[r][k]))
        M[k], M[p] = M[p], M[k]
        for r in range(k + 1, n):
            f = M[r][k] / M[k][k]
            for c in range(k + 1, n):
                M[r][c] -= f * M[k][c]
            M[r][k] = Fraction(0)
        peak = max(peak, max(abs(v) for row in M for v in row))
    return peak / a0


def _eta_exact(A, x, b):
    """باقیماندهٔ نرمال‌شدهٔ دقیق با Fraction؛ فقط روی خروجی متناهی."""
    Af = _frac_matrix(A)
    X = _frac_vector(x)
    bf = _frac_vector(b)
    r = _vec_sub(_mat_vec(Af, X), bf)
    denom = _norm_inf_mat(Af) * _norm_inf_vec(X) + _norm_inf_vec(bf)
    if denom == 0:
        return _norm_inf_vec(r), "absolute"
    return _norm_inf_vec(r) / denom, "ratio"


def _rel_err(x, ref):
    """‖x − ref‖∞ / ‖ref‖∞ با حساب دقیق؛ x باید متناهی باشد."""
    ref_f = _frac_vector(ref)
    diff = _vec_sub(_frac_vector(x), ref_f)
    return _norm_inf_vec(diff) / _norm_inf_vec(ref_f)


# ---------------------------------------------------------------------------
# کران‌های تشخیصی (تضمین‌شده نیستند؛ فقط هشدار صادر می‌کنند)
# ---------------------------------------------------------------------------

def _gamma(m):
    mu = m * U
    return mu / (1 - mu)


def _k_bw(n, rho):
    """K_bw = n·γ_{3n}·ρ. تشخیصی."""
    return n * _gamma(3 * n) * rho


def _k_fwd(kappa, kbw):
    if kappa * kbw >= 1:
        return None
    return kappa * kbw / (1 - kappa * kbw)


def _a5_bound(kappa, eps_A, eps_b):
    if kappa * eps_A >= 1:
        return None
    return kappa * (eps_A + eps_b) / (1 - kappa * eps_A)


def _diagnose(label, value, threshold):
    """هشدار تشخیصی. هرگز تست را شکست نمی‌دهد."""
    if threshold is None:
        warnings.warn(
            f"[تشخیصی] {label}: حد تشخیصی تعریف نشده است.",
            UserWarning,
            stacklevel=3,
        )
        return
    if value > threshold:
        warnings.warn(
            f"[تشخیصی] {label}: مقدار {float(value):.3e} از حد تشخیصی "
            f"{float(threshold):.3e} بیشتر است.",
            UserWarning,
            stacklevel=3,
        )


def _report_diagnostics(label, A, b, x, x_ref, n):
    kappa = _kappa_inf(A)
    rho = _growth_factor(A)
    kbw = _k_bw(n, rho)
    kfwd = _k_fwd(kappa, kbw)
    _diagnose(f"{label}: خطای جلو نسبت به جواب دقیق", _rel_err(x, x_ref), kfwd)
    eta, _ = _eta_exact(A, x, b)
    _diagnose(f"{label}: باقیماندهٔ نرمال‌شده", eta, kbw)


# ---------------------------------------------------------------------------
# بررسی‌های قطعی مشترک
# ---------------------------------------------------------------------------

def _check_exact_solution(tc, x, x_ref, label):
    tc.assertEqual(len(x), len(x_ref), msg=f"{label}: طول خروجی نادرست است")
    for i, v in enumerate(x):
        tc.assertTrue(math.isfinite(v), msg=f"{label}: مؤلفهٔ {i} غیرمتناهی است")
    err = _rel_err(x, x_ref)
    tc.assertLessEqual(
        err, PRACTICAL_REL_TOL,
        msg=f"{label}: خطای نسبی {float(err):.3e} از حد عملی بیشتر است",
    )


def _check_matrix_identities(tc, A, kappa_expected, rho_expected, label):
    tc.assertEqual(_kappa_inf(A), kappa_expected, msg=f"{label}: κ∞ نادرست")
    tc.assertEqual(_growth_factor(A), rho_expected, msg=f"{label}: ρ نادرست")


def _outcome(A, b):
    """طبقه‌بندی رفتار: singular، value_error، یا returned با مقدار x."""
    try:
        x = solve_dense(A, b)
    except SingularSystemError as exc:
        return "singular", str(exc)
    except ValueError as exc:
        return "value_error", str(exc)
    return "returned", x


def _normalized_residual_float(A, x, b):
    r = [sum(a * xi for a, xi in zip(row, x)) - bi for row, bi in zip(A, b)]
    r_norm = max((abs(v) for v in r), default=0.0)
    A_norm = max((sum(abs(a) for a in row) for row in A), default=0.0)
    x_norm = max((abs(v) for v in x), default=0.0)
    b_norm = max((abs(v) for v in b), default=0.0)
    denom = A_norm * x_norm + b_norm
    if denom == 0.0:
        return r_norm, "absolute"
    return r_norm / denom, "ratio"


# ---------------------------------------------------------------------------
# داده‌های ثابت
# ---------------------------------------------------------------------------

A_2 = [[2.0, 1.0], [1.0, 3.0]]
B_2 = [3.0, 5.0]
X_2 = [Fraction(4, 5), Fraction(7, 5)]

A_B2 = [[4.0, -2.0, 1.0], [-2.0, 4.0, -2.0], [1.0, -2.0, 4.0]]
B_B2 = [11.0, -16.0, 17.0]
X_B2 = [Fraction(1), Fraction(-2), Fraction(3)]

W_NEW = [[1.0, 0.0, 1.0], [-1.0, 1.0, 1.0], [-1.0, -1.0, 1.0]]
B_W = [2.0, 1.0, -1.0]
X_W = [Fraction(1), Fraction(1), Fraction(1)]

W_OLD = [[1.0, -1.0, -1.0], [1.0, 1.0, -1.0], [1.0, -1.0, 1.0]]

H3 = [[Fraction(1, i + j + 1) for j in range(3)] for i in range(3)]
X_H3_TRUE = [Fraction(1), Fraction(1), Fraction(1)]
B_H3 = _mat_vec(H3, X_H3_TRUE)
R1_H3 = _exact_solve(H3, B_H3)

A_FL_H3 = [[float(v) for v in row] for row in H3]
B_FL_H3 = [float(v) for v in B_H3]
A_FL_EXACT = _frac_matrix(A_FL_H3)
B_FL_EXACT = _frac_vector(B_FL_H3)
R_FL_H3 = _exact_solve(A_FL_EXACT, B_FL_EXACT)

C4_A = [[1.0, 0.0], [0.0, 1e-8]]
C4_B = [1.0, 1e301]


# ---------------------------------------------------------------------------
# گروه A: اعتبارسنجی ابزارهای ممیزی (۵ تست، همیشه فعال)
# ---------------------------------------------------------------------------

class ToolValidationTest(unittest.TestCase):

    def test_A1_residual_difference_informational(self):
        """A1 (گزارشی): اختلاف η_float و η_exact چاپ می‌شود، بدون آستانهٔ قبولی."""
        x_hat = [0.8, 1.4]
        eta_f, _ = _normalized_residual_float(A_2, x_hat, B_2)
        eta_e, _ = _eta_exact(A_2, x_hat, B_2)
        diff = float(eta_e) - eta_f
        print(
            f"[A1 گزارشی] eta_float={eta_f!r}  eta_exact≈{float(eta_e):.17g}  "
            f"اختلاف={diff:.3e}",
            file=sys.stderr,
        )

    def test_A2_zero_denominator_absolute_mode(self):
        value, kind = _normalized_residual_float(
            [[0.0, 0.0], [0.0, 0.0]], [0.0, 0.0], [0.0, 0.0]
        )
        self.assertEqual(kind, "absolute")
        self.assertEqual(value, 0.0)

    def test_A3_condition_numbers_exact(self):
        self.assertEqual(_kappa_inf(A_2), Fraction(16, 5))
        self.assertEqual(_kappa_inf(A_B2), Fraction(6))
        self.assertEqual(_kappa_inf(W_NEW), Fraction(3))

    def test_A4_growth_factor_exact(self):
        self.assertEqual(_growth_factor(W_NEW), Fraction(4))
        self.assertEqual(_growth_factor(W_OLD), Fraction(2))
        self.assertEqual(_growth_factor(A_2), Fraction(1))

    def test_A5_hilbert3_exact_chain(self):
        """A5: زنجیرهٔ مرجع H3 با حساب دقیق. ε_A ≤ u و ε_b ≤ u قطعی‌اند (گرد کردن IEEE)."""
        self.assertEqual(B_H3, [Fraction(11, 6), Fraction(13, 12), Fraction(47, 60)])
        self.assertEqual(R1_H3, X_H3_TRUE)
        kappa = _kappa_inf(H3)
        self.assertEqual(kappa, Fraction(748))

        eps_A = _norm_inf_mat(_mat_sub(A_FL_EXACT, _frac_matrix(H3))) / _norm_inf_mat(H3)
        eps_b = _norm_inf_vec(_vec_sub(B_FL_EXACT, B_H3)) / _norm_inf_vec(B_H3)
        self.assertLessEqual(eps_A, U)
        self.assertLessEqual(eps_b, U)
        self.assertLess(kappa * eps_A, 1)

        _diagnose(
            "A5: خطای نسبی R_fl نسبت به R1",
            _rel_err(R_FL_H3, R1_H3),
            _a5_bound(kappa, eps_A, eps_b),
        )


# ---------------------------------------------------------------------------
# گروه B: رفتار حل‌گر در دستگاه‌های گویا (۵ تست، همیشه فعال)
# ---------------------------------------------------------------------------

class GoldenSystemBehaviourTest(unittest.TestCase):

    def test_B1_two_by_two(self):
        x = solve_dense(A_2, B_2)
        _check_exact_solution(self, x, X_2, "B1")
        _check_matrix_identities(self, A_2, Fraction(16, 5), Fraction(1), "B1")
        _report_diagnostics("B1", A_2, B_2, x, X_2, n=2)

    def test_B2_three_by_three(self):
        x = solve_dense(A_B2, B_B2)
        _check_exact_solution(self, x, X_B2, "B2")
        _check_matrix_identities(self, A_B2, Fraction(6), Fraction(1), "B2")
        _report_diagnostics("B2", A_B2, B_B2, x, X_B2, n=3)

    def test_B3_wilkinson_growth(self):
        x = solve_dense(W_NEW, B_W)
        _check_exact_solution(self, x, X_W, "B3")
        _check_matrix_identities(self, W_NEW, Fraction(3), Fraction(4), "B3")
        _report_diagnostics("B3", W_NEW, B_W, x, X_W, n=3)

    def test_B4_uniform_tiny_scale(self):
        """B4: 2⁻⁹⁹⁰·I. مقادیر توانی دو دقیق‌اند، پس جواب دقیقاً [1, 1] است."""
        t = 2.0 ** -990
        A = [[t, 0.0], [0.0, t]]
        b = [t, t]
        x = solve_dense(A, b)
        _check_exact_solution(self, x, [Fraction(1), Fraction(1)], "B4")
        self.assertEqual(x, [1.0, 1.0])
        _check_matrix_identities(self, A, Fraction(1), Fraction(1), "B4")
        _report_diagnostics("B4", A, b, x, [Fraction(1), Fraction(1)], n=2)

    def test_B5_hilbert3_float_solve(self):
        """B5: قطعی — طول ۳ و متناهی بودن. تشخیصی — خطای جلو نسبت به R_fl."""
        x = solve_dense(A_FL_H3, B_FL_H3)
        self.assertEqual(len(x), 3)
        for v in x:
            self.assertTrue(math.isfinite(v))
        _report_diagnostics("B5", A_FL_H3, B_FL_H3, x, R_FL_H3, n=3)


# ---------------------------------------------------------------------------
# گروه S: حساسیت به اغتشاش (۴ تست، همیشه فعال)
# ---------------------------------------------------------------------------

class PerturbationSensitivityTest(unittest.TestCase):

    def test_S1_b_perturbation_sensitivity_exact(self):
        """S1 (ریاضی): ‖x̃−x‖/‖x‖ ≤ κ·ε_b با ε_b = δ/5؛ مقدار واقعی 3δ/7."""
        b = [Fraction(3), Fraction(5)]
        b_p = [Fraction(3) + DELTA, Fraction(5)]
        x = _exact_solve(A_2, b)
        self.assertEqual(x, X_2)
        x_t = _exact_solve(A_2, b_p)
        eps_b = _norm_inf_vec(_vec_sub(b_p, b)) / _norm_inf_vec(b)
        self.assertEqual(eps_b, DELTA / 5)
        kappa = _kappa_inf(A_2)
        self.assertEqual(kappa * eps_b, 16 * DELTA / 25)
        rel = _rel_err(x_t, x)
        self.assertEqual(rel, 3 * DELTA / 7)
        self.assertLessEqual(rel, kappa * eps_b)

    def test_S2_solver_on_b_perturbation(self):
        b_pert = [3.0 + 2.0 ** -20, 5.0]
        self.assertEqual(_frac_vector(b_pert), [Fraction(3) + DELTA, Fraction(5)])
        x = solve_dense(A_2, b_pert)
        x_ref = _exact_solve(A_2, b_pert)
        _check_exact_solution(self, x, x_ref, "S2")
        _check_matrix_identities(self, A_2, Fraction(16, 5), Fraction(1), "S2")
        _report_diagnostics("S2", A_2, b_pert, x, x_ref, n=2)

    def test_S3_matrix_perturbation_sensitivity_exact(self):
        """S3 (ریاضی): ‖x̃−x‖/‖x‖ ≤ κε_A/(1−κε_A)؛ مقدار واقعی 3δ/(5−δ)."""
        A_p = [[Fraction(2), 1 + DELTA], [Fraction(1), Fraction(3)]]
        b = [Fraction(3), Fraction(5)]
        x_t = _exact_solve(A_p, b)
        self.assertEqual(x_t, [(4 - 5 * DELTA) / (5 - DELTA), Fraction(7) / (5 - DELTA)])
        delta_A = _mat_sub(A_p, _frac_matrix(A_2))
        eps_A = _norm_inf_mat(delta_A) / _norm_inf_mat(_frac_matrix(A_2))
        self.assertEqual(eps_A, DELTA / 4)
        kappa = _kappa_inf(A_2)
        self.assertEqual(kappa * eps_A, 4 * DELTA / 5)
        bound = kappa * eps_A / (1 - kappa * eps_A)
        self.assertEqual(bound, 4 * DELTA / (5 - 4 * DELTA))
        rel = _rel_err(x_t, X_2)
        self.assertEqual(rel, 3 * DELTA / (5 - DELTA))
        self.assertLessEqual(rel, bound)

    def test_S4_solver_on_matrix_perturbation(self):
        A_p = [[2.0, 1.0 + 2.0 ** -20], [1.0, 3.0]]
        self.assertEqual(
            _frac_matrix(A_p), [[Fraction(2), 1 + DELTA], [Fraction(1), Fraction(3)]]
        )
        x = solve_dense(A_p, B_2)
        x_ref = _exact_solve(A_p, B_2)
        _check_exact_solution(self, x, x_ref, "S4")
        _check_matrix_identities(self, A_p, 4 * (4 + DELTA) / (5 - DELTA), Fraction(1), "S4")
        _report_diagnostics("S4", A_p, B_2, x, x_ref, n=2)


# ---------------------------------------------------------------------------
# گروه E: تست‌های ساختاری حفظ‌شده (۴ تست، همیشه فعال)
# ---------------------------------------------------------------------------

class StructuralContractTest(unittest.TestCase):

    def test_E1_singular_matrix_raises_singular_error(self):
        """E1: [[1,2],[2,4]] پس از مقیاس‌بندی، پیوت دوم دقیقاً صفر است."""
        with self.assertRaises(SingularSystemError):
            solve_dense([[1.0, 2.0], [2.0, 4.0]], [1.0, 2.0])

    def test_E2_zero_matrix_raises_singular_error(self):
        """E2: ماتریس صفر یعنی سطر صفر، SingularSystemError."""
        with self.assertRaises(SingularSystemError):
            solve_dense([[0.0, 0.0], [0.0, 0.0]], [1.0, 1.0])

    def test_E3_rhs_length_mismatch_raises_value_error(self):
        with self.assertRaises(ValueError):
            solve_dense([[1.0, 0.0], [0.0, 1.0]], [1.0, 2.0, 3.0])

    def test_E4_non_square_matrix_raises_value_error(self):
        with self.assertRaises(ValueError):
            solve_dense([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]], [1.0, 2.0])


# ---------------------------------------------------------------------------
# گروه C: ثبت رفتار قبل از پیاده‌سازی (۷ تست، فقط وقتی پرچم False است)
# ---------------------------------------------------------------------------

@unittest.skipIf(
    SCALE_AWARE_PIVOT_IMPLEMENTED,
    "پرچم SCALE_AWARE_PIVOT_IMPLEMENTED فعال است؛ رفتار هدف در گروه D تست می‌شود.",
)
class ScaleCurrentBehaviorTest(unittest.TestCase):

    def _assert_global_threshold_error(self, A, b):
        kind, detail = _outcome(A, b)
        self.assertEqual(kind, "singular", msg=f"خروجی: {kind}")
        self.assertIn("pivot", detail)

    def test_C1_diag_1e8_1e_minus_8(self):
        self._assert_global_threshold_error([[1e8, 0.0], [0.0, 1e-8]], [1e8, 1e-8])

    def test_C2_diag_1e10_1e_minus_10(self):
        self._assert_global_threshold_error([[1e10, 0.0], [0.0, 1e-10]], [1e10, 1e-10])

    def test_C3_diag_1e300_1e_minus_300(self):
        self._assert_global_threshold_error([[1e300, 0.0], [0.0, 1e-300]], [1e300, 1e-300])


@unittest.skipIf(
    FINITE_INPUT_GUARD_IMPLEMENTED,
    "پرچم FINITE_INPUT_GUARD_IMPLEMENTED فعال است؛ رفتار هدف در گروه D تست می‌شود.",
)
class GuardCurrentBehaviorTest(unittest.TestCase):

    def test_C4_overflow_in_back_substitution(self):
        kind, x = _outcome(C4_A, C4_B)
        self.assertEqual(kind, "returned")
        self.assertTrue(math.isnan(x[0]))
        self.assertEqual(x[1], math.inf)

    def test_C5_nan_in_matrix(self):
        nan = float("nan")
        kind, x = _outcome([[nan, 1.0], [1.0, 2.0]], [1.0, 1.0])
        self.assertEqual(kind, "returned")
        self.assertTrue(all(math.isnan(v) for v in x))

    def test_C6_inf_in_matrix(self):
        kind, detail = _outcome([[math.inf, 0.0], [0.0, 1.0]], [1.0, 1.0])
        self.assertEqual(kind, "singular")
        self.assertIn("pivot", detail)

    def test_C7_nan_in_rhs(self):
        nan = float("nan")
        kind, x = _outcome([[2.0, 0.0], [0.0, 2.0]], [nan, 1.0])
        self.assertEqual(kind, "returned")
        self.assertTrue(math.isnan(x[0]))
        self.assertEqual(x[1], 0.5)


# ---------------------------------------------------------------------------
# گروه D: رفتار هدف پس از پیاده‌سازی (۷ تست، فقط وقتی پرچم True است)
# ---------------------------------------------------------------------------

@unittest.skipUnless(
    SCALE_AWARE_PIVOT_IMPLEMENTED,
    "نیازمند پیاده‌سازی مقیاس‌بندی توانی دو.",
)
class ScaleTargetTest(unittest.TestCase):
    """ماتریس قطری: b_i = a_ii، پس پس از مقیاس‌بندی همه‌چیز توانی دو است و جواب دقیقاً 1."""

    def test_D1_diag_1e8_1e_minus_8(self):
        self.assertEqual(solve_dense([[1e8, 0.0], [0.0, 1e-8]], [1e8, 1e-8]), [1.0, 1.0])

    def test_D2_diag_1e10_1e_minus_10(self):
        self.assertEqual(solve_dense([[1e10, 0.0], [0.0, 1e-10]], [1e10, 1e-10]), [1.0, 1.0])

    def test_D3_diag_1e300_1e_minus_300(self):
        self.assertEqual(solve_dense([[1e300, 0.0], [0.0, 1e-300]], [1e300, 1e-300]), [1.0, 1.0])


@unittest.skipUnless(
    FINITE_INPUT_GUARD_IMPLEMENTED,
    "نیازمند پیاده‌سازی کنترل ورودی و خروجی غیرمتناهی.",
)
class GuardTargetTest(unittest.TestCase):

    def test_D4_nan_in_matrix_raises_value_error(self):
        with self.assertRaises(ValueError):
            solve_dense([[float("nan"), 1.0], [1.0, 2.0]], [1.0, 1.0])

    def test_D5_inf_in_matrix_raises_value_error(self):
        with self.assertRaises(ValueError):
            solve_dense([[math.inf, 0.0], [0.0, 1.0]], [1.0, 1.0])

    def test_D6_nan_in_rhs_raises_value_error(self):
        with self.assertRaises(ValueError):
            solve_dense([[2.0, 0.0], [0.0, 2.0]], [float("nan"), 1.0])

    def test_D7_unrepresentable_solution_raises_overflow(self):
        """D7: جواب واقعی 1e309 است و در float قابل نمایش نیست؛ خطای سرریز صریح لازم است."""
        with self.assertRaises(NumericalOverflowError):
            solve_dense(C4_A, C4_B)


# ---------------------------------------------------------------------------
# گروه N: تست‌های جدید مرحلهٔ چهارم (۱۳ تست، همیشه فعال)
# ---------------------------------------------------------------------------

class PolicyAndScalingTest(unittest.TestCase):
    """تست‌های سیاست: ناوردایی، جایگشت، صفر، زیرنرمال، سرریز، تکینگی و ورودی."""

    def test_N1_power_of_two_scaling_invariance(self):
        """N1: A' = D1·A·D2، b' = D1·b  ⇒  y = D2⁻¹·x.

        D1 = diag(4, 1/2)، D2 = diag(1/8, 2)، x = [4/5, 7/5].
        A' = [[1, 8], [1/16, 3]]، b' = [12, 5/2]، y = [32/5, 7/10].
        بررسی: 1·32/5 + 8·7/10 = 12؛ (1/16)·32/5 + 3·7/10 = 5/2.
        """
        D1 = [4.0, 0.5]
        D2 = [0.125, 2.0]
        A_p = [[D1[i] * A_2[i][j] * D2[j] for j in range(2)] for i in range(2)]
        b_p = [D1[i] * B_2[i] for i in range(2)]
        y = solve_dense(A_p, b_p)
        _check_exact_solution(self, y, [Fraction(32, 5), Fraction(7, 10)], "N1")

    def test_N2_row_permutation_invariance(self):
        """N2: جابه‌جایی سطرها و b یکسان، جواب تغییر نمی‌کند."""
        x = solve_dense([[1.0, 3.0], [2.0, 1.0]], [5.0, 3.0])
        _check_exact_solution(self, x, X_2, "N2")

    def test_N3_column_permutation_permutes_solution(self):
        """N3: جابه‌جایی ستون‌ها ⇒ x جابه‌جا می‌شود. [[1,2],[3,1]] x = [3,5] ⇒ x = [7/5, 4/5]."""
        x = solve_dense([[1.0, 2.0], [3.0, 1.0]], [3.0, 5.0])
        _check_exact_solution(self, x, [Fraction(7, 5), Fraction(4, 5)], "N3")

    def test_N4_zero_diagonal_exact(self):
        """N4: [[0,1],[1,0]] x = [2,3] ⇒ x = [3,2] دقیقاً."""
        self.assertEqual(solve_dense([[0.0, 1.0], [1.0, 0.0]], [2.0, 3.0]), [3.0, 2.0])

    def test_N5_zero_row_raises_singular(self):
        with self.assertRaises(SingularSystemError):
            solve_dense([[0.0, 0.0], [1.0, 2.0]], [1.0, 1.0])

    def test_N6_zero_column_raises_singular(self):
        with self.assertRaises(SingularSystemError):
            solve_dense([[1.0, 0.0], [2.0, 0.0]], [1.0, 1.0])

    def test_N7_subnormal_exact_scaling(self):
        """N7: diag(2⁻¹⁰⁷⁴)·x = 2⁻¹⁰⁷⁴ ⇒ x = [1]. مقیاس‌بندی زیرنرمال دقیق است و خطا ندارد."""
        t = 2.0 ** -1074
        self.assertEqual(solve_dense([[t, 0.0], [0.0, t]], [t, t]), [1.0, 1.0])

    def test_N8_inexact_subnormal_scaling_raises_underflow(self):
        """N8: ستون دوم کوچک‌ترین مقدار 3·2⁻¹⁰⁷⁴ دارد. ضرب در 2⁻¹ بیت از دست می‌دهد.

        پس سیاست سخت‌گیرانه NumericalUnderflowError می‌دهد.
        """
        with self.assertRaises(NumericalUnderflowError):
            solve_dense([[1.0, 3.0 * 2.0 ** -1074], [0.0, 1.0]], [1.0, 1.0])

    def test_N9_scaled_rhs_overflow_raises(self):
        """N9: b_1 = 1e300 با ردیفی به بیشینهٔ 1e-300؛ مقیاس‌بندی سرریز می‌کند."""
        with self.assertRaises(NumericalOverflowError):
            solve_dense([[1e-300, 0.0], [0.0, 1.0]], [1e300, 1.0])

    def test_N10_near_dependent_rows_numerically_singular(self):
        """N10: [[1,1],[1,1+1e-12]] پس از مقیاس‌بندی پیوت دوم حدود 5e-13 است؛ زیر rel_tol.

        این تکینگی عددی تحت آستانه است، نه اثبات تکینگی دقیق.
        """
        with self.assertRaises(SingularSystemError):
            solve_dense([[1.0, 1.0], [1.0, 1.0 + 1e-12]], [2.0, 2.0 + 1e-12])

    def test_N11_moderately_near_dependent_accepted(self):
        """N11: [[1,1],[1,1+1e-8]] پیوت حدود 5e-9 دارد و بالای rel_tol است.

        این تست فقط بررسی می‌کند که جواب متناهی و با طول درست بازگردانده شود.
        دقت آن با κ≈4e8 تضمین نشده و هشدار شرط بد در این مرحله پیاده‌سازی نشده است.
        """
        x = solve_dense([[1.0, 1.0], [1.0, 1.0 + 1e-8]], [2.0, 2.0 + 1e-8])
        self.assertEqual(len(x), 2)
        for v in x:
            self.assertTrue(math.isfinite(v))

    def test_N12_singular_integer_matrix_raises(self):
        """N12: [[1,2,3],[4,5,6],[7,8,9]] در حساب دقیق تکین است.

        در float پیوت نهایی حدود خطای گرد کردن (≈1e-15) است و زیر rel_tol می‌افتد.
        این انتظار مبتنی بر تحلیل اندازهٔ خطای گرد کردن است، نه تضمین ریاضی.
        """
        with self.assertRaises(SingularSystemError):
            solve_dense([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0], [7.0, 8.0, 9.0]], [1.0, 1.0, 1.0])

    def test_N13_input_validation(self):
        """N13: رشته، rel_tol غیرمثبت، سطر ناهم‌طول و دستگاه تهی باید ValueError بدهند."""
        with self.assertRaises(ValueError):
            solve_dense([["1", 0.0], [0.0, 1.0]], [1.0, 1.0])
        with self.assertRaises(ValueError):
            solve_dense([[1.0, 0.0], [0.0, 1.0]], [1.0, 1.0], rel_tol=0)
        with self.assertRaises(ValueError):
            solve_dense([[1.0, 0.0], [0.0]], [1.0, 1.0])
        with self.assertRaises(ValueError):
            solve_dense([], [])


if __name__ == "__main__":
    unittest.main()
