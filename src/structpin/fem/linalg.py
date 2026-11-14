"""حل‌گر دستگاه معادلات خطی متراکم STRUCTPIN (مرحلهٔ چهارم).

قرارداد عمومی:
    solve_dense(A, b, rel_tol=1e-9) -> list[float]

روش:
    1. اعتبارسنجی ورودی: ابعاد، نوع، متناهی بودن، مثبت بودن rel_tol.
    2. مقیاس‌بندی توانی دو:
           A_s = R A C,   b_s = R b,   R = diag(2^(-e_i)),   C = diag(2^(-f_j))
       ضرایب صحیح‌اند و با math.frexp به دست می‌آیند. هر درایهٔ ناصفر پس از
       مقیاس‌بندی با حساب دقیق (fractions.Fraction) بررسی می‌شود. اگر بیتی از
       دست برود، NumericalUnderflowError پرتاب می‌شود.
    3. حذف گاوسی با پیوت جزئی روی A_s. پیوتی که قدر مطلقش از rel_tol کوچک‌تر
       یا مساوی باشد، تکینگی (دقیق یا عددی تحت آستانه) تلقی و SingularSystemError
       پرتاب می‌شود.
    4. پسروی روی y، سپس x = C y با بررسی سرریز و صفرشدن مؤلفهٔ ناصفر.

استثناها:
    ValueError               ورودی نامعتبر (ابعاد، nan/inf، رشته، rel_tol نامعتبر)
    SingularSystemError      سطر صفر، ستون صفر، پیوت صفر یا پیوت زیر rel_tol
    NumericalUnderflowError  از دست رفتن بیت یک درایهٔ ناصفر، یا صفرشدن جواب ناصفر
    NumericalOverflowError   سرریز میانی، یا جوابی که در float قابل نمایش نیست

نکات سازگاری:
    - امضای solve_dense و نوع بازگشتی (list) حفظ شده‌اند.
    - SingularSystemError همچنان از ArithmeticError ارث می‌برد.
    - rel_tol اکنون آستانهٔ مطلق روی پیوت‌های مقیاس‌شده است، نه نسبت به بیشینهٔ
      کل ماتریس. چون ردیف‌های A_s بیشینه‌ای در بازهٔ [0.5, 1) دارند، این آستانه
      عملاً نسبی به اندازهٔ سطر است.
    - Hager/Higham و IllConditionedWarning در این نسخه پیاده‌سازی نشده‌اند.
"""

import math
from fractions import Fraction


class SingularSystemError(ArithmeticError):
    """تکینگی دقیق (پیوت یا سطر/ستون صفر) یا تکینگی عددی تحت آستانهٔ rel_tol."""


class NumericalOverflowError(ArithmeticError):
    """سرریز میانی، یا جواب نهایی که در محدودهٔ float64 قابل نمایش نیست."""


class NumericalUnderflowError(ArithmeticError):
    """از دست رفتن بیت یک درایهٔ ناصفر در مقیاس‌بندی، یا صفرشدن جواب ناصفر."""


def _pow2(k):
    """2**k به‌صورت Fraction دقیق (k عدد صحیح، مثبت یا منفی)."""
    return Fraction(2) ** k


def _to_float(value, where):
    """تبدیل یک عدد ورودی به float متناهی. رشته و نوع‌های ناسازگار ValueError می‌دهند."""
    if isinstance(value, (str, bytes)):
        raise ValueError(f"{where}: رشته به‌عنوان عدد پذیرفته نیست: {value!r}")
    try:
        x = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{where}: قابل تبدیل به float نیست: {value!r}") from exc
    if not math.isfinite(x):
        raise ValueError(f"{where}: مقدار غیرمتناهی است: {value!r}")
    return x


def _validate(A, b, rel_tol):
    """اعتبارسنجی کامل ورودی و تبدیل آن به فهرست‌های float."""
    try:
        rows = [list(row) for row in A]
    except TypeError as exc:
        raise ValueError("A باید دنباله‌ای از سطرها باشد") from exc

    n = len(rows)
    if n == 0:
        raise ValueError("دستگاه باید حداقل یک معادله داشته باشد")
    for i, row in enumerate(rows):
        if len(row) != n:
            raise ValueError(
                f"A باید مربعی باشد: سطر {i} طول {len(row)} دارد و باید {n} باشد"
            )

    try:
        rhs = list(b)
    except TypeError as exc:
        raise ValueError("b باید دنباله‌ای از اعداد باشد") from exc
    if len(rhs) != n:
        raise ValueError(f"طول b ({len(rhs)}) با ابعاد A ({n}) سازگار نیست")

    A_f = [[_to_float(v, f"A[{i}][{j}]") for j, v in enumerate(row)]
           for i, row in enumerate(rows)]
    b_f = [_to_float(v, f"b[{i}]") for i, v in enumerate(rhs)]

    tol = _to_float(rel_tol, "rel_tol")
    if tol <= 0.0:
        raise ValueError(f"rel_tol باید مثبت باشد، مقدار داده‌شده: {rel_tol!r}")
    return A_f, b_f, tol


def _row_exponents(A_f):
    """توان دو سطری e_i: max_j |a_ij| = m_i * 2**e_i با m_i در [0.5, 1).

    سطر صفر تکینگی دقیق است و SingularSystemError می‌دهد.
    """
    exps = []
    for i, row in enumerate(A_f):
        m = max(abs(v) for v in row)
        if m == 0.0:
            raise SingularSystemError(f"سطر صفر در اندیس {i}: دستگاه تکین است")
        exps.append(math.frexp(m)[1])
    return exps


def _column_exponents(A_f, row_exp):
    """توان دو ستونی f_j برای ماتریس R A.

    مقدار |a_ij| 2**(-e_i) = m * 2**q با q = p_ij - e_i، که p_ij توان frexp
    مقدار |a_ij| است. بیشینهٔ ستون در بازهٔ [2**(f_j-1), 2**f_j) قرار دارد،
    پس ضرب در 2**(-f_j) بیشینهٔ ستون را در [0.5, 1) می‌برد.
    ستون صفر تکینگی دقیق است و SingularSystemError می‌دهد.
    """
    n = len(A_f)
    exps = []
    for j in range(n):
        best = None
        for i in range(n):
            a = A_f[i][j]
            if a != 0.0:
                p = math.frexp(abs(a))[1]
                q = p - row_exp[i]
                if best is None or q > best:
                    best = q
        if best is None:
            raise SingularSystemError(f"ستون صفر در اندیس {j}: دستگاه تکین است")
        exps.append(best)
    return exps


def _scale_exact(x, k, where):
    """محاسبهٔ x * 2**k به‌صورت تضمین‌شده بدون از دست رفتن بیت.

    - سرریز یا غیرمتناهی شدن: NumericalOverflowError.
    - صفرشدن مقدار ناصفر: NumericalUnderflowError.
    - گرد شدن (معمولاً در محدودهٔ زیرنرمال): NumericalUnderflowError.
    - نتیجهٔ دقیق (حتی اگر زیرنرمال باشد): بدون خطا برگردانده می‌شود.

    بررسی دقت با Fraction انجام می‌شود، نه با بررسی توان یا ضرب دوباره در float.
    """
    if x == 0.0:
        return 0.0
    try:
        y = math.ldexp(x, k)
    except OverflowError as exc:
        raise NumericalOverflowError(
            f"{where}: ضرب در 2**{k} باعث سرریز float64 می‌شود"
        ) from exc
    if not math.isfinite(y):
        raise NumericalOverflowError(f"{where}: نتیجهٔ مقیاس‌بندی غیرمتناهی است")
    if y == 0.0:
        raise NumericalUnderflowError(f"{where}: مقدار ناصفر به صفر تبدیل شد")
    if Fraction(y) != Fraction(x) * _pow2(k):
        raise NumericalUnderflowError(
            f"{where}: در محدودهٔ زیرنرمال بیت‌هایی از دست رفته‌اند"
        )
    return y


def _equilibrate(A_f, b_f, row_exp, col_exp):
    """ساختن A_s = R A C و b_s = R b با بررسی دقت هر درایه.

    درایه‌های صفر دست‌نخورده می‌مانند. ماتریس میانی R A ساخته نمی‌شود؛
    هر درایهٔ A با توان ترکیبی -(e_i + f_j) یک‌بار مقیاس می‌شود.
    """
    n = len(A_f)
    A_s = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            a = A_f[i][j]
            if a != 0.0:
                A_s[i][j] = _scale_exact(
                    a, -(row_exp[i] + col_exp[j]), f"A[{i}][{j}]"
                )
    b_s = [
        _scale_exact(v, -row_exp[i], f"b[{i}]") if v != 0.0 else 0.0
        for i, v in enumerate(b_f)
    ]
    return A_s, b_s


def _check_finite(value, where):
    if not math.isfinite(value):
        raise NumericalOverflowError(f"مقدار میانی غیرمتناهی در {where}")
    return value


def _lu_solve(A_s, b_s, rel_tol):
    """حذف گاوسی با پیوت جزئی و پسروی روی ماتریس مقیاس‌شده.

    پیوت ها با قدر مطلق کامل مقایسه می‌شوند؛ در تساوی، اولین سطر انتخاب می‌شود.
    """
    n = len(b_s)
    M = [row[:] for row in A_s]
    y = b_s[:]

    for k in range(n):
        p = k
        best = abs(M[k][k])
        for r in range(k + 1, n):
            v = abs(M[r][k])
            if v > best:
                best = v
                p = r

        if best == 0.0:
            raise SingularSystemError(
                f"تکینگی دقیق: پیوت صفر در مرحلهٔ {k} (pivot = 0)"
            )
        if best <= rel_tol:
            raise SingularSystemError(
                f"تکینگی عددی تحت rel_tol={rel_tol!r}: اندازهٔ پیوت {best!r} "
                f"در مرحلهٔ {k} (pivot)"
            )

        if p != k:
            M[k], M[p] = M[p], M[k]
            y[k], y[p] = y[p], y[k]

        pivot_row = M[k]
        pk = pivot_row[k]
        for r in range(k + 1, n):
            row = M[r]
            f = row[k] / pk
            if f != 0.0:
                for c in range(k, n):
                    row[c] -= f * pivot_row[c]
                row[k] = 0.0
                y[r] -= f * y[k]
                _check_finite(y[r], f"سطر {r} در مرحلهٔ {k}")
                for c in range(k + 1, n):
                    _check_finite(row[c], f"سطر {r} ستون {c} در مرحلهٔ {k}")

    x = [0.0] * n
    for r in range(n - 1, -1, -1):
        s = y[r]
        row = M[r]
        for c in range(r + 1, n):
            s -= row[c] * x[c]
        x[r] = _check_finite(s / row[r], f"پسروی سطر {r}")
    return x


def _unscale_solution(y_j, col_exp_j, j):
    """محاسبهٔ مؤلفهٔ x_j = 2**(-f_j) * y_j با بررسی سرریز و صفرشدن.

    گرد شدن جواب به نزدیک‌ترین مقدار قابل نمایش (شامل زیرنرمال) پذیرفته است.
    صفرشدن مؤلفهٔ ناصفر یک خطای صریح است.
    """
    if y_j == 0.0:
        return 0.0
    try:
        x_j = math.ldexp(y_j, -col_exp_j)
    except OverflowError as exc:
        raise NumericalOverflowError(
            f"مؤلفهٔ {j} جواب در float64 قابل نمایش نیست"
        ) from exc
    if not math.isfinite(x_j):
        raise NumericalOverflowError(f"مؤلفهٔ {j} جواب غیرمتناهی است")
    if x_j == 0.0:
        raise NumericalUnderflowError(f"مؤلفهٔ {j} جواب ناصفر به صفر تبدیل شد")
    return x_j


def solve_dense(A, b, rel_tol=1e-9):
    """حل دستگاه A x = b با مقیاس‌بندی توانی دو و حذف گاوسی با پیوت جزئی.

    Args:
        A: ماتریس مربعی (فهرست سطرها) با درایه‌های عددی متناهی.
        b: بردار سمت راست با همان طول.
        rel_tol: آستانهٔ مطلق برای قدر مطلق پیوت‌های ماتریس مقیاس‌شده.

    Returns:
        list[float]: جواب x.

    Raises:
        ValueError: ورودی نامعتبر.
        SingularSystemError: تکینگی دقیق یا عددی تحت rel_tol.
        NumericalUnderflowError: از دست رفتن بیت یا صفرشدن مقدار ناصفر.
        NumericalOverflowError: سرریز میانی یا جواب غیرقابل‌نمایش.
    """
    A_f, b_f, tol = _validate(A, b, rel_tol)
    row_exp = _row_exponents(A_f)
    col_exp = _column_exponents(A_f, row_exp)
    A_s, b_s = _equilibrate(A_f, b_f, row_exp, col_exp)
    y = _lu_solve(A_s, b_s, tol)
    return [_unscale_solution(y[j], col_exp[j], j) for j in range(len(y))]
