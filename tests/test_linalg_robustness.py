"""ممیزی عددی تابع solve_dense (Numerical robustness audit).

پرچم‌های وضعیت (Status flags):
    SCALE_AWARE_PIVOT_IMPLEMENTED:
        False یعنی آستانهٔ پیوت هنوز سراسری است (نقص F-L1).
        فقط کلاس‌های مربوط به مقیاس را کنترل می‌کند.
    FINITE_INPUT_GUARD_IMPLEMENTED:
        False یعنی solve_dense کنترل ورودی غیرمتناهی ندارد (نقص F-L3).
        فقط کلاس‌های مربوط به NaN/Inf را کنترل می‌کند.

چهار کلاس مستقل:
    ScaleDisparityCurrentBehaviorTest  : کنترل فقط با SCALE_AWARE_PIVOT_IMPLEMENTED
    ScaleDisparityTargetTest           : کنترل فقط با SCALE_AWARE_PIVOT_IMPLEMENTED
    NonFiniteCurrentBehaviorTest       : کنترل فقط با FINITE_INPUT_GUARD_IMPLEMENTED
    NonFiniteTargetTest                : کنترل فقط با FINITE_INPUT_GUARD_IMPLEMENTED

شمارش:
    الف) ExpectedBehaviorTest: ۷ تست، همیشه فعال.
    ب) ثبت رفتار فعلی: ۲ تست مقیاس + ۳ تست NaN/Inf = ۵ تست.
    ج) رفتار هدف: ۲ تست مقیاس + ۳ تست NaN/Inf = ۵ تست.
    مجموع: ۱۷ تست.

هیچ expectedFailure استفاده نشده است.
این فایل هیچ ادعای اجرای تست نمی‌کند.
"""

import unittest

from structpin.fem.linalg import solve_dense, SingularSystemError


# ---------------------------------------------------------------------------
# پرچم‌های وضعیت
# ---------------------------------------------------------------------------

SCALE_AWARE_PIVOT_IMPLEMENTED = False
FINITE_INPUT_GUARD_IMPLEMENTED = False


# ---------------------------------------------------------------------------
# توابع کمکی مستقل از solve_dense
# ---------------------------------------------------------------------------

def _vec_inf_norm(v):
    """نرم بی‌نهایت بردار: بیشینهٔ قدرمطلق عناصر."""
    return max((abs(x) for x in v), default=0.0)


def _mat_inf_norm(A):
    """نرم بی‌نهایت ماتریس: بیشینهٔ مجموع قدرمطلق هر سطر."""
    return max((sum(abs(a) for a in row) for row in A), default=0.0)


def _mat_vec(A, x):
    """ضرب ماتریس در بردار."""
    return [sum(a * xi for a, xi in zip(row, x)) for row in A]


def normalized_residual(A, x, b):
    """خطای باقیمانده نرمال‌شده: ‖Ax−b‖∞ / (‖A‖∞‖x‖∞ + ‖b‖∞).

    فقط برای سنجش کیفیت جواب‌هایی به کار می‌رود که solve_dense بازگردانده است.
    اگر مخرج صفر باشد، مقدار مطلق باقیمانده با نوع 'absolute' گزارش می‌شود.
    """
    r = [ax - bi for ax, bi in zip(_mat_vec(A, x), b)]
    r_norm = _vec_inf_norm(r)
    denom = _mat_inf_norm(A) * _vec_inf_norm(x) + _vec_inf_norm(b)
    if denom == 0.0:
        return r_norm, "absolute"
    return r_norm / denom, "ratio"


def relative_error(x, x_ref):
    """خطای نسبی بی‌نهایت: ‖x−x*‖∞ / ‖x*‖∞."""
    diff = [xi - xr for xi, xr in zip(x, x_ref)]
    denom = _vec_inf_norm(x_ref)
    if denom == 0.0:
        return _vec_inf_norm(diff), "absolute"
    return _vec_inf_norm(diff) / denom, "ratio"


def _classify_solver_output(A, b):
    """طبقه‌بندی خروجی solve_dense بدون فرض نوع خطا.

    خروجی‌های ممکن:
        'singular_error'      : SingularSystemError
        'value_error'         : ValueError
        'returned_nonfinite'  : جواب بازگشته و شامل nan یا inf است
        'returned_finite'     : جواب بازگشته و همه عناصر متناهی‌اند
    هر خطای دیگری پنهان نمی‌شود و مستقیم منتشر می‌شود.
    """
    try:
        x = solve_dense(A, b)
    except SingularSystemError:
        return "singular_error"
    except ValueError:
        return "value_error"
    has_nonfinite = any(v != v or abs(v) == float("inf") for v in x)
    return "returned_nonfinite" if has_nonfinite else "returned_finite"


# ---------------------------------------------------------------------------
# الف) رفتار مورد انتظار (۷ تست، همیشه فعال)
# ---------------------------------------------------------------------------

class ExpectedBehaviorTest(unittest.TestCase):
    """تست‌های عادی. این موارد با کد فعلی باید موفق شوند."""

    TOL = 1e-12

    def test_two_by_two_exact_solution(self):
        """A = [[2,1],[1,3]]، b = [3,5]، جواب دقیق x* = [0.8, 1.4].

        اشتقاق: det(A) = 2·3 − 1·1 = 5.
        x = (3·3 − 1·5)/5 = 0.8 و y = (2·5 − 1·3)/5 = 1.4.
        """
        A = [[2.0, 1.0], [1.0, 3.0]]
        b = [3.0, 5.0]
        x = solve_dense(A, b)
        eta, _ = normalized_residual(A, x, b)
        err, _ = relative_error(x, [0.8, 1.4])
        self.assertLessEqual(eta, self.TOL)
        self.assertLessEqual(err, self.TOL)

    def test_three_by_three_exact_solution(self):
        """A = [[4,−2,1],[−2,4,−2],[1,−2,4]]، x* = [1, −2, 3].

        b = A·x* = [11, −16, 17]. ماتریس متقارن معین است.
        """
        A = [[4.0, -2.0, 1.0], [-2.0, 4.0, -2.0], [1.0, -2.0, 4.0]]
        x_ref = [1.0, -2.0, 3.0]
        b = _mat_vec(A, x_ref)
        x = solve_dense(A, b)
        eta, _ = normalized_residual(A, x, b)
        err, _ = relative_error(x, x_ref)
        self.assertLessEqual(eta, self.TOL)
        self.assertLessEqual(err, self.TOL)

    def test_singular_matrix_raises_singular_error(self):
        """A = [[1,2],[2,4]] تکین است و باید SingularSystemError بدهد."""
        with self.assertRaises(SingularSystemError):
            solve_dense([[1.0, 2.0], [2.0, 4.0]], [1.0, 2.0])

    def test_zero_matrix_raises_singular_error(self):
        """ماتریس صفر: شاخهٔ scale == 0 در کد، SingularSystemError می‌دهد."""
        with self.assertRaises(SingularSystemError):
            solve_dense([[0.0, 0.0], [0.0, 0.0]], [1.0, 1.0])

    def test_dimension_mismatch_raises_value_error(self):
        """ماتریس ۲×۲ و بردار طول ۳: ValueError از بررسی ابعاد."""
        with self.assertRaises(ValueError):
            solve_dense([[1.0, 0.0], [0.0, 1.0]], [1.0, 2.0, 3.0])

    def test_non_square_matrix_raises_value_error(self):
        """ماتریس ۲×۳: ValueError از بررسی طول سطرها."""
        with self.assertRaises(ValueError):
            solve_dense([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]], [1.0, 2.0])

    def test_residual_helper_zero_denominator(self):
        """ابزار ممیزی: وقتی A، x و b صفرند، حالت 'absolute' برمی‌گردد.

        این تست درستی ابزار را می‌سنجد، نه solve_dense را.
        """
        value, kind = normalized_residual(
            [[0.0, 0.0], [0.0, 0.0]], [0.0, 0.0], [0.0, 0.0]
        )
        self.assertEqual(kind, "absolute")
        self.assertEqual(value, 0.0)


# ---------------------------------------------------------------------------
# ب) ثبت رفتار فعلی مقیاس (۲ تست، فقط با SCALE_AWARE_PIVOT_IMPLEMENTED = False)
# ---------------------------------------------------------------------------

@unittest.skipIf(
    SCALE_AWARE_PIVOT_IMPLEMENTED,
    "پرچم SCALE_AWARE_PIVOT_IMPLEMENTED فعال است؛ تست‌های هدف مقیاس جایگزین هستند.",
)
class ScaleDisparityCurrentBehaviorTest(unittest.TestCase):
    """ثبت رفتار فعلی حل‌گر در برابر اختلاف مقیاس (نقص F-L1).

    این تست‌ها **آزمون ثبت رفتار فعلی** هستند، نه آزمون موفقیت حل.
    ماتریس‌ها ناتکین‌اند و جواب یکتای [1, 1] دارند، اما کد فعلی آستانهٔ
    پیوت را سراسری و برابر rel_tol × max|A_ij| می‌گیرد؛ پس پیوت کوچک‌تر را
    تکین اعلام می‌کند و SingularSystemError می‌دهد.

    اگر خطا با پیام شامل 'pivot' بیاید، رفتار فعلی ثبت می‌شود.
    اگر solve_dense جواب بدهد، تست FAIL می‌شود، چون رفتار با پیش‌بینی
    نسخهٔ فعلی نمی‌خواند و باید بررسی شود.
    """

    def _assert_current_pivot_threshold_error(self, A, b):
        try:
            x = solve_dense(A, b)
        except SingularSystemError as exc:
            self.assertIn(
                "pivot", str(exc),
                msg="خطا رخ داد اما پیام آن به آستانهٔ پیوت اشاره ندارد",
            )
            return
        self.fail(
            "رفتار فعلی با پیش‌بینی نمی‌خواند: solve_dense جواب داد "
            f"{x} به‌جای SingularSystemError. لطفاً linalg.py را بررسی کنید."
        )

    def test_diag_1e8_1e_minus_8_records_global_threshold_error(self):
        """diag(1e8, 1e-8): آستانه = 1e−9 × 1e8 = 0.1 و پیوت 1e−8 < 0.1."""
        self._assert_current_pivot_threshold_error(
            [[1e8, 0.0], [0.0, 1e-8]], [1e8, 1e-8]
        )

    def test_diag_1e10_1e_minus_10_records_global_threshold_error(self):
        """diag(1e10, 1e-10): آستانه = 1e−9 × 1e10 = 10 و پیوت 1e−10 < 10."""
        self._assert_current_pivot_threshold_error(
            [[1e10, 0.0], [0.0, 1e-10]], [1e10, 1e-10]
        )


# ---------------------------------------------------------------------------
# ب) ثبت رفتار فعلی NaN/Inf (۳ تست، فقط با FINITE_INPUT_GUARD_IMPLEMENTED = False)
# ---------------------------------------------------------------------------

@unittest.skipIf(
    FINITE_INPUT_GUARD_IMPLEMENTED,
    "پرچم FINITE_INPUT_GUARD_IMPLEMENTED فعال است؛ تست‌های هدف NaN/Inf جایگزین هستند.",
)
class NonFiniteCurrentBehaviorTest(unittest.TestCase):
    """ثبت رفتار فعلی solve_dense برای ورودی غیرمتناهی (نقص F-L3).

    کد فعلی math.isfinite ندارد. این تست‌ها پیش‌بینی تحلیلی رفتار را ثبت
    می‌کنند و تأیید رفتار مهندسی نیستند.
    """

    def test_nan_in_matrix_recorded_as_returned_nonfinite(self):
        """nan در A: پیش‌بینی 'returned_nonfinite' (نقص F-L3).

        جواب غیرمتناهی بی‌صدا یک نقص است، نه رفتار قابل قبول.
        """
        kind = _classify_solver_output(
            [[float("nan"), 1.0], [1.0, 2.0]], [1.0, 1.0]
        )
        self.assertEqual(
            kind, "returned_nonfinite",
            msg="نقص ثبت‌شده: nan در A بی‌صدا به جواب غیرمتناهی تبدیل شد. "
                f"خروجی واقعی: {kind}",
        )

    def test_inf_in_matrix_recorded_as_misleading_singular_error(self):
        """inf در A: پیش‌بینی 'singular_error' (نوع خطای گمراه‌کننده، نقص F-L3)."""
        kind = _classify_solver_output(
            [[float("inf"), 0.0], [0.0, 1.0]], [1.0, 1.0]
        )
        self.assertEqual(
            kind, "singular_error",
            msg="نقص ثبت‌شده: inf در A به‌جای خطای ورودی، به خطای تکینگی "
                f"تبدیل شد. خروجی واقعی: {kind}",
        )

    def test_nan_in_rhs_recorded_as_returned_nonfinite(self):
        """nan در b: پیش‌بینی 'returned_nonfinite' (نقص F-L3)."""
        kind = _classify_solver_output(
            [[2.0, 0.0], [0.0, 2.0]], [float("nan"), 1.0]
        )
        self.assertEqual(
            kind, "returned_nonfinite",
            msg="نقص ثبت‌شده: nan در b بی‌صدا به جواب منتقل شد. "
                f"خروجی واقعی: {kind}",
        )


# ---------------------------------------------------------------------------
# ج) رفتار هدف مقیاس (۲ تست، فقط با SCALE_AWARE_PIVOT_IMPLEMENTED = True)
# ---------------------------------------------------------------------------

@unittest.skipUnless(
    SCALE_AWARE_PIVOT_IMPLEMENTED,
    "نیازمند اصلاح حل‌گر: آستانهٔ پیوت هنوز سراسری است.",
)
class ScaleDisparityTargetTest(unittest.TestCase):
    """رفتار هدف: پس از اصلاح پیوت، حل باید با جواب [1, 1] موفق باشد.

    توجیه تلورانس 1e−12: ماتریس قطری است و جواب هر مؤلفه برابر b_i/a_ii است.
    چون a_ii = b_i در هر دو مؤلفه، تقسیم دقیقاً 1.0 می‌دهد و خطای گرد کردن
    صفر است؛ 1e−12 فقط حاشیهٔ احتیاط است.
    """

    TOL = 1e-12

    def test_diag_1e8_1e_minus_8_solves_to_ones(self):
        x = solve_dense([[1e8, 0.0], [0.0, 1e-8]], [1e8, 1e-8])
        err, _ = relative_error(x, [1.0, 1.0])
        self.assertLessEqual(err, self.TOL)

    def test_diag_1e10_1e_minus_10_solves_to_ones(self):
        x = solve_dense([[1e10, 0.0], [0.0, 1e-10]], [1e10, 1e-10])
        err, _ = relative_error(x, [1.0, 1.0])
        self.assertLessEqual(err, self.TOL)


# ---------------------------------------------------------------------------
# ج) رفتار هدف NaN/Inf (۳ تست، فقط با FINITE_INPUT_GUARD_IMPLEMENTED = True)
# ---------------------------------------------------------------------------

@unittest.skipUnless(
    FINITE_INPUT_GUARD_IMPLEMENTED,
    "نیازمند اصلاح حل‌گر: کنترل ورودی غیرمتناهی هنوز وجود ندارد.",
)
class NonFiniteTargetTest(unittest.TestCase):
    """رفتار هدف: ورودی غیرمتناهی باید با ValueError رد شود.

    این رفتار مطلوب مهندسی است و از کد فعلی قابل اثبات نیست.
    """

    def test_nan_in_matrix_raises_value_error(self):
        with self.assertRaises(ValueError):
            solve_dense([[float("nan"), 1.0], [1.0, 2.0]], [1.0, 1.0])

    def test_inf_in_matrix_raises_value_error(self):
        with self.assertRaises(ValueError):
            solve_dense([[float("inf"), 0.0], [0.0, 1.0]], [1.0, 1.0])

    def test_nan_in_rhs_raises_value_error(self):
        with self.assertRaises(ValueError):
            solve_dense([[2.0, 0.0], [0.0, 2.0]], [float("nan"), 1.0])


if __name__ == "__main__":
    unittest.main()
