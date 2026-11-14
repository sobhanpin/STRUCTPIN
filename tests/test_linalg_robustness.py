"""ممیزی عددی تابع solve_dense — فایل ۳۲ تستی مرحلهٔ دوم STRUCTPIN.

ساختار (بدون تغییر نسبت به طرح تأییدشده):
    A (5)  اعتبارسنجی ابزارهای ممیزی                  همیشه فعال
    B (5)  رفتار حل‌گر در دستگاه‌های گویا               همیشه فعال
    S (4)  حساسیت جواب به اغتشاش                        همیشه فعال
    E (4)  تست‌های ساختاری حفظ‌شده                      همیشه فعال
    C (7)  ثبت رفتار فعلی solve_dense                    فعال وقتی پرچم مربوط False است
    D (7)  رفتار هدف پس از اصلاح solve_dense             فعال وقتی پرچم مربوط True است

قواعد بررسی‌ها:
    - بررسی‌های قطعی (assert) فقط بر پایهٔ موارد زیر هستند:
        * جواب دقیق گویا (Fraction)، با حد عملی PRACTICAL_REL_TOL؛
        * متناهی بودن خروجی و درستی ابعاد؛
        * هویت‌های ریاضی دقیق روی خود ماتریس‌ها (κ∞ و ρ) که بدون solve_dense محاسبه می‌شوند؛
        * کران‌های مقدماتی که با نامساوی‌های اثبات‌شده در docstring همان تست به دست می‌آیند
          (S1 و S3)، و نامساوی‌های ناشی از گرد کردن IEEE 754 (ε_A ≤ u و ε_b ≤ u در A5).
    - کران‌های K_bw و K_fwd (بر پایهٔ شماره‌های Higham که هنوز تأیید نشده‌اند) هرگز assert
      نمی‌شوند. مقایسه با آن‌ها فقط با تابع _diagnose هشدار تشخیصی (warnings.warn) صادر می‌کند.
    - A1 کاملاً گزارشی است: اختلاف η_float و η_exact را چاپ می‌کند و هیچ آستانهٔ قبولی ندارد.
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

from structpin.fem.linalg import solve_dense, SingularSystemError


# ---------------------------------------------------------------------------
# پرچم‌های وضعیت (در ابتدا False)
# ---------------------------------------------------------------------------

SCALE_AWARE_PIVOT_IMPLEMENTED = False
FINITE_INPUT_GUARD_IMPLEMENTED = False


# ---------------------------------------------------------------------------
# ثابت‌های دقیق
# ---------------------------------------------------------------------------

U = Fraction(1, 2 ** 53)          # واحد گرد کردن float64 (گرد کردن به نزدیک‌ترین)
DELTA = Fraction(1, 2 ** 20)      # δ = 2⁻²⁰ (دقیقاً در float قابل نمایش است)

# حد عملی نسبی برای مقایسه با جواب دقیق در دستگاه‌های کوچک و خوش‌رفتار.
# این یک انتخاب مهندسی است و نه کران اثبات‌شده. خطای واقعی float64 برای این
# دستگاه‌ها در حد ۱۰⁻¹⁵ انتظار می‌رود و حد ۱۰⁻¹⁰ حاشیهٔ بزرگی می‌دهد.
PRACTICAL_REL_TOL = Fraction(1, 10 ** 10)


# ---------------------------------------------------------------------------
# حساب دقیق با fractions.Fraction
# ---------------------------------------------------------------------------

def _frac_matrix(A):
    """تبدیل ماتریس به Fraction. Fraction(float) مقدار دقیق float را نگه می‌دارد."""
    return [[Fraction(v) for v in row] for row in A]


def _frac_vector(v):
    return [Fraction(x) for x in v]


def _norm_inf_vec(v):
    """نرم بی‌نهایت بردار: بیشینهٔ قدرمطلق عناصر."""
    return max(abs(x) for x in v)


def _norm_inf_mat(A):
    """نرم بی‌نهایت ماتریس: بیشینهٔ مجموع قدرمطلق سطرها."""
    return max(sum(abs(a) for a in row) for row in A)


def _mat_vec(A, x):
    return [sum(a * xi for a, xi in zip(row, x)) for row in A]


def _mat_sub(A, B):
    return [[a - b for a, b in zip(ra, rb)] for ra, rb in zip(A, B)]


def _vec_sub(a, b):
    return [x - y for x, y in zip(a, b)]


def _exact_solve(A, b):
    """حل دقیق A x = b با حذف گاوسی و پیوت جزئی روی Fraction.

    قاعدهٔ تساوی: اولین سطر با بیشینهٔ قدرمطلق (همان قاعدهٔ max در پایتون).
    """
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
    """وارون دقیق با حل دستگاه برای ستون‌های واحد."""
    n = len(A)
    cols = [_exact_solve(A, [Fraction(int(i == j)) for i in range(n)]) for j in range(n)]
    return [[cols[j][i] for j in range(n)] for i in range(n)]


def _kappa_inf(A):
    """عدد وضعیت دقیق κ∞(A) = ‖A‖∞ · ‖A⁻¹‖∞."""
    Af = _frac_matrix(A)
    return _norm_inf_mat(Af) * _norm_inf_mat(_exact_inverse(Af))


def _growth_factor(A):
    """ضریب رشد پیوت ρ = max_k max_ij |a_ij^(k)| / max_ij |a_ij^(0)|.

    k = 0 تا n−1، یعنی A^(0) (ورودی) و ماتریس‌های پس از هر مرحلهٔ حذف.
    قاعدهٔ پیوت جزئی روی Fraction، با اولین بیشینه در تساوی.
    """
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
    """باقیماندهٔ نرمال‌شدهٔ دقیق: ‖Ax−b‖∞ / (‖A‖∞‖x‖∞ + ‖b‖∞).

    x و b با Fraction(·) دقیقاً تفسیر می‌شوند و هیچ عملیات float در آن رخ نمی‌دهد.
    این تابع باید فقط روی خروجی‌های متناهی فراخوانی شود.
    """
    Af = _frac_matrix(A)
    X = _frac_vector(x)
    bf = _frac_vector(b)
    r = _vec_sub(_mat_vec(Af, X), bf)
    denom = _norm_inf_mat(Af) * _norm_inf_vec(X) + _norm_inf_vec(bf)
    if denom == 0:
        return _norm_inf_vec(r), "absolute"
    return _norm_inf_vec(r) / denom, "ratio"


def _rel_err(x, ref):
    """خطای نسبی بی‌نهایت ‖x−ref‖∞ / ‖ref‖∞ با حساب دقیق.

    x می‌تواند خروجی float باشد؛ Fraction(x) دقیق است. قبل از فراخوانی باید
    متناهی بودن x بررسی شده باشد، زیرا Fraction(nan) استثنا می‌دهد.
    """
    ref_f = _frac_vector(ref)
    diff = _vec_sub(_frac_vector(x), ref_f)
    return _norm_inf_vec(diff) / _norm_inf_vec(ref_f)


# ---------------------------------------------------------------------------
# کران‌های تشخیصی (تضمین‌شده نیستند؛ فقط هشدار صادر می‌کنند)
# ---------------------------------------------------------------------------

def _gamma(m):
    """γ_m = m·u / (1 − m·u)."""
    mu = m * U
    return mu / (1 - mu)


def _k_bw(n, rho):
    """K_bw = n·γ_{3n}·ρ. تشخیصی؛ شماره‌ها و ثابت‌های Higham تأیید نشده‌اند."""
    return n * _gamma(3 * n) * rho


def _k_fwd(kappa, kbw):
    """K_fwd = κ·K_bw / (1 − κ·K_bw) فقط وقتی κ·K_bw < 1؛ در غیر این صورت None."""
    if kappa * kbw >= 1:
        return None
    return kappa * kbw / (1 - kappa * kbw)


def _a5_bound(kappa, eps_A, eps_b):
    """κ(ε_A+ε_b)/(1−κε_A) برای خطای نسبی نسبت به R1. تشخیصی."""
    if kappa * eps_A >= 1:
        return None
    return kappa * (eps_A + eps_b) / (1 - kappa * eps_A)


def _diagnose(label, value, threshold):
    """هشدار تشخیصی. این تابع هرگز تست را شکست نمی‌دهد."""
    if threshold is None:
        warnings.warn(
            f"[تشخیصی] {label}: حد تشخیصی تعریف نشده است (κ·K ≥ 1 یا مخرج صفر).",
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
    """هشدارهای تشخیصی برای خطای جلو و باقیماندهٔ نرمال‌شده.

    فرض: x قبلاً متناهی بودن و طولش بررسی شده است.
    κ و ρ از همان ماتریسی محاسبه می‌شوند که به solve_dense داده شده است.
    """
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
    """بررسی قطعی: طول، متناهی بودن، و نزدیکی به جواب دقیق با حد عملی."""
    tc.assertEqual(len(x), len(x_ref), msg=f"{label}: طول خروجی با ابعاد مسئله سازگار نیست")
    for i, v in enumerate(x):
        tc.assertTrue(math.isfinite(v), msg=f"{label}: مؤلفهٔ {i} غیرمتناهی است: {v!r}")
    err = _rel_err(x, x_ref)
    tc.assertLessEqual(
        err, PRACTICAL_REL_TOL,
        msg=f"{label}: خطای نسبی {float(err):.3e} از حد عملی بیشتر است",
    )


def _check_matrix_identities(tc, A, kappa_expected, rho_expected, label):
    """بررسی قطعی هویت‌های دقیق κ∞ و ρ روی ماتریس، بدون solve_dense."""
    tc.assertEqual(
        _kappa_inf(A), kappa_expected,
        msg=f"{label}: κ∞ دقیق با مقدار مورد انتظار همخوان نیست",
    )
    tc.assertEqual(
        _growth_factor(A), rho_expected,
        msg=f"{label}: ρ دقیق با مقدار مورد انتظار همخوان نیست",
    )


def _outcome(A, b):
    """طبقه‌بندی رفتار solve_dense. خطاهای دیگر پنهان نمی‌شوند."""
    try:
        x = solve_dense(A, b)
    except SingularSystemError as exc:
        return "singular", str(exc)
    except ValueError as exc:
        return "value_error", str(exc)
    return "returned", x


def _normalized_residual_float(A, x, b):
    """باقیمانده نرمال‌شده در float (فقط برای A1 و A2)."""
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
B_B2 = [11.0, -16.0, 17.0]            # = A_B2 · [1, −2, 3]
X_B2 = [Fraction(1), Fraction(-2), Fraction(3)]

W_NEW = [[1.0, 0.0, 1.0], [-1.0, 1.0, 1.0], [-1.0, -1.0, 1.0]]
B_W = [2.0, 1.0, -1.0]                # = W_NEW · [1, 1, 1]
X_W = [Fraction(1), Fraction(1), Fraction(1)]

W_OLD = [[1.0, -1.0, -1.0], [1.0, 1.0, -1.0], [1.0, -1.0, 1.0]]

# ماتریس Hilbert سه‌درسه با اندیس‌های صفرمبنا: H3[i][j] = 1/(i+j+1)
# معادل h_ij = 1/(i+j−1) با اندیس‌های یک‌مبنا.
H3 = [[Fraction(1, i + j + 1) for j in range(3)] for i in range(3)]
X_H3_TRUE = [Fraction(1), Fraction(1), Fraction(1)]
B_H3 = _mat_vec(H3, X_H3_TRUE)                    # = [11/6, 13/12, 47/60]
R1_H3 = _exact_solve(H3, B_H3)                    # جواب دقیق مسئلهٔ اصلی = [1, 1, 1]

A_FL_H3 = [[float(v) for v in row] for row in H3]  # ورودی float به solve_dense
B_FL_H3 = [float(v) for v in B_H3]                 # ورودی float به solve_dense
A_FL_EXACT = _frac_matrix(A_FL_H3)                 # مقدار دقیق ماتریس float
B_FL_EXACT = _frac_vector(B_FL_H3)                 # مقدار دقیق بردار float
R_FL_H3 = _exact_solve(A_FL_EXACT, B_FL_EXACT)     # جواب دقیق دستگاه float (R_fl)

C4_A = [[1.0, 0.0], [0.0, 1e-8]]
C4_B = [1.0, 1e301]


# ---------------------------------------------------------------------------
# گروه A: اعتبارسنجی ابزارهای ممیزی (۵ تست، همیشه فعال)
# solve_dense در این گروه فراخوانی نمی‌شود.
# ---------------------------------------------------------------------------

class ToolValidationTest(unittest.TestCase):
    """گروه A: درستی ابزارهای ممیزی (باقیمانده، κ، ρ و زنجیرهٔ مرجع H3)."""

    def test_A1_residual_difference_informational(self):
        """A1 (گزارشی): اختلاف η_float و η_exact را چاپ می‌کند.

        η_exact با Fraction و بدون گرد کردن محاسبه می‌شود (X = Fraction(x̂)).
        η_float با فرمول float محاسبه می‌شود. این تست هیچ آستانهٔ قبولی یا ردی
        ندارد و عمداً assert ندارد؛ کران γ_5 برای این اختلاف اثبات نشده و استفاده نمی‌شود.
        """
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
        """A2: وقتی A=0، x=0 و b=0 باشد، مخرج صفر است و حالت absolute برمی‌گردد."""
        value, kind = _normalized_residual_float(
            [[0.0, 0.0], [0.0, 0.0]], [0.0, 0.0], [0.0, 0.0]
        )
        self.assertEqual(kind, "absolute")
        self.assertEqual(value, 0.0)

    def test_A3_condition_numbers_exact(self):
        """A3: κ∞ دقیق سه ماتریس: 16/5 برای [[2,1],[1,3]]، 6 برای B2، 3 برای W_NEW."""
        self.assertEqual(_kappa_inf(A_2), Fraction(16, 5))
        self.assertEqual(_kappa_inf(A_B2), Fraction(6))
        self.assertEqual(_kappa_inf(W_NEW), Fraction(3))

    def test_A4_growth_factor_exact(self):
        """A4: ضریب رشد دقیق. W_NEW → 4، W_OLD → 2، [[2,1],[1,3]] → 1."""
        self.assertEqual(_growth_factor(W_NEW), Fraction(4))
        self.assertEqual(_growth_factor(W_OLD), Fraction(2))
        self.assertEqual(_growth_factor(A_2), Fraction(1))

    def test_A5_hilbert3_exact_chain(self):
        """A5: زنجیرهٔ مرجع Hilbert سه‌درسه با حساب دقیق.

        قطعی (هویت‌های دقیق و نامساوی‌های گرد کردن IEEE 754):
            - H3 · [1,1,1] = b دقیقاً؛ R1 = [1,1,1] دقیقاً؛ κ∞(H3) = 748 دقیقاً.
            - ε_A = ‖ΔA‖∞/‖H3‖∞ ≤ u و ε_b = ‖Δb‖∞/‖b‖∞ ≤ u (گرد کردن به نزدیک‌ترین)؛
              زیرا |fl(x)−x| ≤ u|x| برای اعداد نرمال و ‖ΔA‖∞ ≤ u‖H3‖∞.
            - κ·ε_A < 1 (شرط اعتبار کران تشخیصی).
        تشخیصی (فقط هشدار):
            - ‖R_fl − R1‖∞/‖R1‖∞ نسبت به κ(ε_A+ε_b)/(1−κε_A)، که شماره‌های قضیه تأیید نشده‌اند.
        """
        self.assertEqual(B_H3, [Fraction(11, 6), Fraction(13, 12), Fraction(47, 60)])
        self.assertEqual(R1_H3, X_H3_TRUE)
        kappa = _kappa_inf(H3)
        self.assertEqual(kappa, Fraction(748))

        eps_A = _norm_inf_mat(_mat_sub(A_FL_EXACT, _frac_matrix(H3))) / _norm_inf_mat(H3)
        eps_b = _norm_inf_vec(_vec_sub(B_FL_EXACT, B_H3)) / _norm_inf_vec(B_H3)
        self.assertLessEqual(eps_A, U)
        self.assertLessEqual(eps_b, U)
        self.assertLess(kappa * eps_A, 1)

        diff_R = _rel_err(R_FL_H3, R1_H3)
        bound = _a5_bound(kappa, eps_A, eps_b)
        _diagnose("A5: خطای نسبی R_fl نسبت به R1", diff_R, bound)


# ---------------------------------------------------------------------------
# گروه B: رفتار حل‌گر در دستگاه‌های گویا (۵ تست، همیشه فعال)
# ---------------------------------------------------------------------------

class GoldenSystemBehaviourTest(unittest.TestCase):
    """گروه B: دقت solve_dense روی دستگاه‌هایی با جواب دقیق معلوم.

    بررسی قطعی: جواب دقیق با حد عملی، متناهی بودن، ابعاد، و هویت‌های κ و ρ.
    بررسی تشخیصی: مقایسه با K_fwd و K_bw (فقط هشدار).
    """

    def test_B1_two_by_two(self):
        """B1: A = [[2,1],[1,3]]، b = [3,5]، x* = [4/5, 7/5]."""
        x = solve_dense(A_2, B_2)
        _check_exact_solution(self, x, X_2, "B1")
        _check_matrix_identities(self, A_2, Fraction(16, 5), Fraction(1), "B1")
        _report_diagnostics("B1", A_2, B_2, x, X_2, n=2)

    def test_B2_three_by_three(self):
        """B2: A = [[4,−2,1],[−2,4,−2],[1,−2,4]]، b = [11,−16,17]، x* = [1,−2,3].

        κ∞ = 6 (det = 36، ‖A‖∞ = 8، ‖A⁻¹‖∞ = 3/4) و ρ = 1 (بیشینهٔ همهٔ مراحل = 4).
        """
        x = solve_dense(A_B2, B_B2)
        _check_exact_solution(self, x, X_B2, "B2")
        _check_matrix_identities(self, A_B2, Fraction(6), Fraction(1), "B2")
        _report_diagnostics("B2", A_B2, B_B2, x, X_B2, n=3)

    def test_B3_wilkinson_growth(self):
        """B3: W_NEW، b = [2,1,−1]، x* = [1,1,1]. κ∞ = 3 و ρ = 4."""
        x = solve_dense(W_NEW, B_W)
        _check_exact_solution(self, x, X_W, "B3")
        _check_matrix_identities(self, W_NEW, Fraction(3), Fraction(4), "B3")
        _report_diagnostics("B3", W_NEW, B_W, x, X_W, n=3)

    def test_B4_uniform_tiny_scale(self):
        """B4: A = 2⁻⁹⁹⁰·I₂، b = 2⁻⁹⁹⁰·[1,1]، x* = [1,1].

        تقسیم‌های b_i/a_ii دقیقاً برابر ۱ هستند، زیرا مقادیر توانی از ۲ دقیقاً
        نمایش داده می‌شوند و در محدودهٔ نرمال float64 قرار دارند. بنابراین
        برابری دقیق با [1.0, 1.0] توجیه دارد. این تست بررسی می‌کند که آستانهٔ
        نسبی پیوت برای مقیاس یکنواخت خطای کاذب ندهد.
        """
        t = 2.0 ** -990
        A = [[t, 0.0], [0.0, t]]
        b = [t, t]
        x = solve_dense(A, b)
        _check_exact_solution(self, x, [Fraction(1), Fraction(1)], "B4")
        self.assertEqual(x, [1.0, 1.0])
        _check_matrix_identities(self, A, Fraction(1), Fraction(1), "B4")
        _report_diagnostics("B4", A, b, x, [Fraction(1), Fraction(1)], n=2)

    def test_B5_hilbert3_float_solve(self):
        """B5: حل دستگاه float از H3 (A_FL_H3، B_FL_H3).

        قطعی: خروجی طول ۳ دارد و کاملاً متناهی است.
        تشخیصی: خطای جلو نسبت به R_fl و باقیماندهٔ η با K_fwd و K_bw (فقط هشدار).
        """
        x = solve_dense(A_FL_H3, B_FL_H3)
        self.assertEqual(len(x), 3)
        for v in x:
            self.assertTrue(math.isfinite(v))
        _report_diagnostics("B5", A_FL_H3, B_FL_H3, x, R_FL_H3, n=3)


# ---------------------------------------------------------------------------
# گروه S: حساسیت به اغتشاش (۴ تست، همیشه فعال)
# ---------------------------------------------------------------------------

class PerturbationSensitivityTest(unittest.TestCase):
    """گروه S: کران حساسیت ریاضی و دقت solve_dense روی ورودی اغتشاش‌یافته.

    S1 و S3 فقط ریاضی‌اند و solve_dense را فراخوانی نمی‌کنند.
    S2 و S4 دقت solve_dense را می‌سنجند.
    """

    def test_S1_b_perturbation_sensitivity_exact(self):
        """S1 (ریاضی): حساسیت به اغتشاش بردار b.

        اثبات کران (مقدماتی): x̃ − x = A⁻¹Δb، پس ‖x̃−x‖ ≤ ‖A⁻¹‖‖Δb‖.
        همچنین ‖b‖ ≤ ‖A‖‖x‖ یعنی 1/‖x‖ ≤ ‖A‖/‖b‖. در نتیجه
        ‖x̃−x‖/‖x‖ ≤ κ·‖Δb‖/‖b‖ = κ·ε_b.
        مخرج کران ‖x‖ (جواب اولیه) است.

        مقادیر: ε_b = δ/5، κ·ε_b = 16δ/25، خطای واقعی 3δ/7.
        """
        b = [Fraction(3), Fraction(5)]
        b_p = [Fraction(3) + DELTA, Fraction(5)]
        x = _exact_solve(A_2, b)
        self.assertEqual(x, X_2)

        x_t = _exact_solve(A_2, b_p)
        eps_b = _norm_inf_vec(_vec_sub(b_p, b)) / _norm_inf_vec(b)
        self.assertEqual(eps_b, DELTA / 5)

        kappa = _kappa_inf(A_2)
        self.assertEqual(kappa, Fraction(16, 5))
        self.assertEqual(kappa * eps_b, 16 * DELTA / 25)

        rel = _rel_err(x_t, x)
        self.assertEqual(rel, 3 * DELTA / 7)
        self.assertLessEqual(rel, kappa * eps_b)

    def test_S2_solver_on_b_perturbation(self):
        """S2 (حل‌گر): solve_dense روی b' = [3+δ, 5].

        مرجع: x̃ = A⁻¹b' با حساب دقیق. κ و ρ از ماتریس ورودی A محاسبه می‌شوند،
        زیرا ماتریس به solve_dense بدون تغییر داده می‌شود.
        """
        b_pert = [3.0 + 2.0 ** -20, 5.0]
        self.assertEqual(_frac_vector(b_pert), [Fraction(3) + DELTA, Fraction(5)])

        x = solve_dense(A_2, b_pert)
        x_ref = _exact_solve(A_2, b_pert)
        _check_exact_solution(self, x, x_ref, "S2")
        _check_matrix_identities(self, A_2, Fraction(16, 5), Fraction(1), "S2")
        _report_diagnostics("S2", A_2, b_pert, x, x_ref, n=2)

    def test_S3_matrix_perturbation_sensitivity_exact(self):
        """S3 (ریاضی): حساسیت به اغتشاش ماتریس A.

        A' = [[2, 1+δ],[1,3]]، ΔA = [[0,δ],[0,0]]، ε_A = ‖ΔA‖∞/‖A‖∞ = δ/4.

        اثبات کران (مقدماتی): x̃ − x = −A⁻¹ΔA·x̃، پس ‖x̃−x‖ ≤ κε_A‖x̃‖.
        با ‖x̃‖ ≤ ‖x‖ + ‖x̃−x‖ داریم ‖x̃−x‖(1−κε_A) ≤ κε_A‖x‖، یعنی
        ‖x̃−x‖/‖x‖ ≤ κε_A/(1−κε_A) وقتی κε_A < 1. κ از ماتریس اولیه A است،
        زیرا کران به جواب اولیه x نسبت داده شده است.

        مقادیر: x̃ = ((4−5δ)/(5−δ), 7/(5−δ))، خطای واقعی 3δ/(5−δ)، کران 4δ/(5−4δ).
        """
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
        """S4 (حل‌گر): solve_dense روی A' = [[2, 1+δ],[1,3]] و b = [3,5].

        κ' و ρ' از همان ماتریس ورودی A' محاسبه می‌شوند:
            κ' = 4(4+δ)/(5−δ)،  ρ' = 1 (max(A') = 3 و بیشینهٔ همهٔ مراحل = 3).
        مرجع: x̃ = A'⁻¹b با حساب دقیق.
        """
        A_p = [[2.0, 1.0 + 2.0 ** -20], [1.0, 3.0]]
        self.assertEqual(
            _frac_matrix(A_p),
            [[Fraction(2), 1 + DELTA], [Fraction(1), Fraction(3)]],
        )

        x = solve_dense(A_p, B_2)
        x_ref = _exact_solve(A_p, B_2)
        _check_exact_solution(self, x, x_ref, "S4")
        _check_matrix_identities(
            self, A_p, 4 * (4 + DELTA) / (5 - DELTA), Fraction(1), "S4"
        )
        _report_diagnostics("S4", A_p, B_2, x, x_ref, n=2)


# ---------------------------------------------------------------------------
# گروه E: تست‌های ساختاری حفظ‌شده (۴ تست، همیشه فعال)
# ---------------------------------------------------------------------------

class StructuralContractTest(unittest.TestCase):
    """گروه E: رفتارهای ساختاری حفظ‌شده از نسخهٔ قبلی."""

    def test_E1_singular_matrix_raises_singular_error(self):
        """E1: A = [[1,2],[2,4]] تکین است. پس از جابه‌جایی و حذف، پیوت دوم صفر می‌شود."""
        with self.assertRaises(SingularSystemError):
            solve_dense([[1.0, 2.0], [2.0, 4.0]], [1.0, 2.0])

    def test_E2_zero_matrix_raises_singular_error(self):
        """E2: ماتریس صفر. شاخهٔ scale == 0 در solve_dense، SingularSystemError."""
        with self.assertRaises(SingularSystemError):
            solve_dense([[0.0, 0.0], [0.0, 0.0]], [1.0, 1.0])

    def test_E3_rhs_length_mismatch_raises_value_error(self):
        """E3: ماتریس ۲×۲ و بردار طول ۳. بررسی ابعاد، ValueError."""
        with self.assertRaises(ValueError):
            solve_dense([[1.0, 0.0], [0.0, 1.0]], [1.0, 2.0, 3.0])

    def test_E4_non_square_matrix_raises_value_error(self):
        """E4: ماتریس ۲×۳ و بردار طول ۲. طول سطرها با n مطابقت ندارد، ValueError."""
        with self.assertRaises(ValueError):
            solve_dense([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]], [1.0, 2.0])


# ---------------------------------------------------------------------------
# گروه C: ثبت رفتار فعلی solve_dense (۷ تست)
# این تست‌ها رفتار فعلی را ثبت می‌کنند و درستی آن را تأیید نمی‌کنند.
# ---------------------------------------------------------------------------

@unittest.skipIf(
    SCALE_AWARE_PIVOT_IMPLEMENTED,
    "SCALE_AWARE_PIVOT_IMPLEMENTED فعال است؛ تست‌های هدف مقیاس (D1–D3) جایگزین هستند.",
)
class ScaleCurrentBehaviorTest(unittest.TestCase):
    """C1 تا C3: آستانهٔ سراسری پیوت، پیوت کوچک را تکین اعلام می‌کند.

    وابستگی به پیاده‌سازی: پیام خطا باید واژهٔ 'pivot' را داشته باشد.
    اگر متن پیام در linalg.py تغییر کند، این تست‌ها باید بازبینی شوند.
    """

    def _assert_global_threshold_error(self, A, b):
        kind, detail = _outcome(A, b)
        self.assertEqual(kind, "singular", msg=f"رفتار فعلی با پیش‌بینی نمی‌خواند؛ خروجی: {kind}")
        self.assertIn("pivot", detail)

    def test_C1_diag_1e8_1e_minus_8(self):
        """C1: diag(1e8, 1e-8). scale=1e8، آستانه ≈ 0.1، پیوت 1e-8 کوچک‌تر است."""
        self._assert_global_threshold_error([[1e8, 0.0], [0.0, 1e-8]], [1e8, 1e-8])

    def test_C2_diag_1e10_1e_minus_10(self):
        """C2: diag(1e10, 1e-10). scale=1e10، آستانه ≈ 10، پیوت 1e-10 کوچک‌تر است."""
        self._assert_global_threshold_error([[1e10, 0.0], [0.0, 1e-10]], [1e10, 1e-10])

    def test_C3_diag_1e300_1e_minus_300(self):
        """C3: diag(1e300, 1e-300). scale=1e300، آستانه ≈ 1e291، پیوت 1e-300 کوچک‌تر است."""
        self._assert_global_threshold_error([[1e300, 0.0], [0.0, 1e-300]], [1e300, 1e-300])


@unittest.skipIf(
    FINITE_INPUT_GUARD_IMPLEMENTED,
    "FINITE_INPUT_GUARD_IMPLEMENTED فعال است؛ تست‌های هدف NaN/Inf (D4–D7) جایگزین هستند.",
)
class GuardCurrentBehaviorTest(unittest.TestCase):
    """C4 تا C7: نبود math.isfinite؛ ورودی غیرمتناهی بی‌صدا منتشر می‌شود.

    وابستگی‌های جزئیات Python (این پیش‌بینی‌ها اجرا نشده‌اند):
        - تقسیم float در Python با سرریز استثنا پرتاب نمی‌کند و inf برمی‌گرداند.
        - 0.0 * inf برابر nan است.
        - max() با مقایسهٔ > کار می‌کند؛ مقایسه با nan همیشه False است.
        - abs(inf) <= inf برابر True است.
    """

    def test_C4_overflow_in_back_substitution(self):
        """C4: A = diag(1, 1e-8)، b = [1, 1e301].

        پیوت دوم 1e-8 از آستانهٔ 1e-9 بزرگ‌تر است، پس خطای تکینگی نیست.
        x2 = 1e301/1e-8 سرریز و inf می‌شود؛ x1 = (1 − 0·inf)/1 = nan.
        """
        kind, x = _outcome(C4_A, C4_B)
        self.assertEqual(kind, "returned", msg=f"خروجی غیرمنتظر: {kind}")
        self.assertTrue(math.isnan(x[0]), msg="x1 باید nan باشد")
        self.assertEqual(x[1], math.inf, msg="x2 باید inf باشد")

    def test_C5_nan_in_matrix(self):
        """C5: A = [[nan,1],[1,2]]، b = [1,1].

        max با nan اولین عنصر، scale = nan می‌ماند. پیوت اول nan است و مقایسه با
        آستانهٔ nan همیشه False است، پس خطا رخ نمی‌دهد و جواب nan است.
        """
        nan = float("nan")
        kind, x = _outcome([[nan, 1.0], [1.0, 2.0]], [1.0, 1.0])
        self.assertEqual(kind, "returned", msg=f"خروجی غیرمنتظر: {kind}")
        self.assertTrue(all(math.isnan(v) for v in x))

    def test_C6_inf_in_matrix(self):
        """C6: A = [[inf,0],[0,1]]، b = [1,1].

        scale = inf، آستانه = inf، و abs(inf) <= inf برابر True است.
        خطای ورودی به خطای تکینگی با واژهٔ 'pivot' تبدیل می‌شود.
        """
        kind, detail = _outcome([[math.inf, 0.0], [0.0, 1.0]], [1.0, 1.0])
        self.assertEqual(kind, "singular", msg=f"خروجی غیرمنتظر: {kind}")
        self.assertIn("pivot", detail)

    def test_C7_nan_in_rhs(self):
        """C7: A = 2·I، b = [nan, 1].

        پیوت‌ها سالم‌اند؛ x1 = (nan − 0)/2 = nan و x2 = 1/2 = 0.5.
        """
        nan = float("nan")
        kind, x = _outcome([[2.0, 0.0], [0.0, 2.0]], [nan, 1.0])
        self.assertEqual(kind, "returned", msg=f"خروجی غیرمنتظر: {kind}")
        self.assertTrue(math.isnan(x[0]))
        self.assertEqual(x[1], 0.5)


# ---------------------------------------------------------------------------
# گروه D: رفتار هدف پس از اصلاحات آینده (۷ تست)
# این تست‌ها رفتار مطلوب را بیان می‌کنند و تا فعال‌شدن پرچم skip می‌شوند.
# ---------------------------------------------------------------------------

@unittest.skipUnless(
    SCALE_AWARE_PIVOT_IMPLEMENTED,
    "نیازمند اصلاح حل‌گر: آستانهٔ پیوت هنوز سراسری است.",
)
class ScaleTargetTest(unittest.TestCase):
    """D1 تا D3: پس از اصلاح پیوت، حل باید جواب [1, 1] را دقیقاً بدهد.

    توجیه برابری دقیق: ماتریس قطری است و b_i = a_ii، پس b_i / a_ii = 1.0
    دقیقاً در float.
    """

    def test_D1_diag_1e8_1e_minus_8(self):
        self.assertEqual(solve_dense([[1e8, 0.0], [0.0, 1e-8]], [1e8, 1e-8]), [1.0, 1.0])

    def test_D2_diag_1e10_1e_minus_10(self):
        self.assertEqual(solve_dense([[1e10, 0.0], [0.0, 1e-10]], [1e10, 1e-10]), [1.0, 1.0])

    def test_D3_diag_1e300_1e_minus_300(self):
        self.assertEqual(solve_dense([[1e300, 0.0], [0.0, 1e-300]], [1e300, 1e-300]), [1.0, 1.0])


@unittest.skipUnless(
    FINITE_INPUT_GUARD_IMPLEMENTED,
    "نیازمند اصلاح حل‌گر: کنترل ورودی غیرمتناهی هنوز وجود ندارد.",
)
class GuardTargetTest(unittest.TestCase):
    """D4 تا D7: ورودی یا خروجی غیرمتناهی نباید بی‌صدا پذیرفته شود."""

    def test_D4_nan_in_matrix_raises_value_error(self):
        with self.assertRaises(ValueError):
            solve_dense([[float("nan"), 1.0], [1.0, 2.0]], [1.0, 1.0])

    def test_D5_inf_in_matrix_raises_value_error(self):
        with self.assertRaises(ValueError):
            solve_dense([[math.inf, 0.0], [0.0, 1.0]], [1.0, 1.0])

    def test_D6_nan_in_rhs_raises_value_error(self):
        with self.assertRaises(ValueError):
            solve_dense([[2.0, 0.0], [0.0, 2.0]], [float("nan"), 1.0])

    def test_D7_overflow_case_must_raise_explicitly(self):
        """D7: ورودی C4. جواب واقعی در float قابل نمایش نیست، پس خطای صریح لازم است.

        پذیرفته: ValueError یا SingularSystemError.
        ممنوع: بازگرداندن هر جوابی (متناهی یا غیرمتناهی).
        """
        kind, _ = _outcome(C4_A, C4_B)
        self.assertIn(kind, ("value_error", "singular"), msg=f"خروجی غیرمجاز: {kind}")


if __name__ == "__main__":
    unittest.main()
