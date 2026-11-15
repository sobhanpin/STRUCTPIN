"""نیروهای داخلی در طول اعضای قاب دوبعدی (N، V، M).

این ماژول تابعی خالص است: فقط StructuralModel و FrameResults را می‌خواند.
هیچ فایل موتور تحلیل را تغییر نمی‌دهد.

قرارداد علامت (تعریف‌شده در این ماژول):
    x: از گره i (x=0) تا گره j (x=L)، در امتداد محلی عضو.
    N(x): کشش مثبت.
    V(x): نیروی عرضی (جهت محلی y) که قسمت راست عضو بر قسمت چپ در مقطع x اعمال می‌کند.
    M(x): لنگر خمشی؛ مثبت وقتی تار پایینی (y منفی) کشیده شود.

ارتباط با member_end_actions:
    member_end_actions[id] = (q_i, q_j) از solve_frame؛ q نیرویی است که گره‌ها بر عضو وارد
    می‌کنند، در دستگاه محلی.
    با تعادل قطعهٔ [0, x] داریم:
        N(0) = −q_i[0]
        V(0) = q_i[1]
        M(0) = −q_i[2]
    و برای انتهای j (x=L) با تعادل قطعهٔ [x, L] از سمت راست:
        N(L) = q_j[0]
        V(L) = −q_j[1]
        M(L) = q_j[2]
    (علامت‌ها با تست‌های تیر ساده، طره و محوری در tests/test_internal_forces.py کنترل می‌شوند.)

روابط داخل عضو با بار گسترده یکنواخت qy (در جهت محلی y):
    N(x) = N(0)
    V(x) = V(0) + qy·x
    M(x) = M(0) + V(0)·x + qy·x²/2

فرضیات:
    - عضو مستقیم و بین دو گره (طول L>0).
    - بار گسترده یکنواخت در جهت محلی y؛ بار محوری گسترده و بار نقطه‌ای داخل عضو پشتیبانی نمی‌شوند.
    - خروجی برای عضوی است که در results.member_end_actions وجود دارد.
    - اثر مرتبهٔ دوم و تغییر شکل عضو لحاظ نشده است.

ورودی‌ها:
    model: StructuralModel
    results: FrameResults
    n_points: عدد صحیح مثبت (پیش‌فرض ۲۰)؛ تعداد تقسیمات، نه تعداد نقاط.
        خروجی هر عضو n_points + 1 نقطه دارد.

خروجی:
    dict[member_id] -> {'x': [...], 'N': [...], 'V': [...], 'M': [...]}
"""

import math


def _validate_n_points(n_points):
    """فقط عدد صحیح مثبت (نه bool، نه float، نه رشته) پذیرفته است."""
    if isinstance(n_points, bool) or not isinstance(n_points, int):
        raise ValueError(f"n_points باید عدد صحیح باشد، مقدار داده‌شده: {n_points!r}")
    if n_points < 1:
        raise ValueError(f"n_points باید حداقل ۱ باشد، مقدار داده‌شده: {n_points}")
    return n_points


def _member_length(model, member_id):
    m = model.members[member_id]
    ni = model.nodes[m.node_i]
    nj = model.nodes[m.node_j]
    length = math.hypot(nj.x - ni.x, nj.y - ni.y)
    if length <= 0.0:
        raise ValueError(f"طول عضو {member_id} صفر است")
    return length


def _member_qy(model, member_id):
    """مجموع بار گسترده یکنواخت محلی روی عضو."""
    return sum(u.qy for u in model.member_udls if u.member == member_id)


def member_internal_forces(model, results, n_points=20):
    """محاسبهٔ N، V، M و x در n_points+1 نقطهٔ یکنواخت هر عضو.

    Raises:
        ValueError: n_points نامعتبر، یا عضو در results نیست، یا طول صفر.
    """
    n_points = _validate_n_points(n_points)

    out = {}
    for member_id in model.members:
        if member_id not in results.member_end_actions:
            raise ValueError(f"عضو {member_id} در نتایج تحلیل وجود ندارد")

        qi, _qj = results.member_end_actions[member_id]
        L = _member_length(model, member_id)
        qy = _member_qy(model, member_id)

        N0 = -qi[0]
        V0 = qi[1]
        M0 = -qi[2]

        xs, Ns, Vs, Ms = [], [], [], []
        for k in range(n_points + 1):
            x = L * k / n_points
            xs.append(x)
            Ns.append(N0)
            Vs.append(V0 + qy * x)
            Ms.append(M0 + V0 * x + qy * x * x / 2.0)

        out[member_id] = {"x": xs, "N": Ns, "V": Vs, "M": Ms}
    return out
