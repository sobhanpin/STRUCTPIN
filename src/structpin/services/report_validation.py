"""اعتبارسنجی عددی مشترک گزارش تحلیل برای ResultsView و PlotCanvas.

این ماژول:
    - هیچ محاسبه‌ای انجام نمی‌دهد.
    - هیچ import از structpin ندارد (headless و مستقل).
    - فقط مقادیر عددی گزارش را بررسی می‌کند؛ ساختار هر بخش در ResultsView
      و PlotCanvas جداگانه اعتبارسنجی می‌شود.

قاعده عددی (هم‌راستا با PlotCanvas):
    - bool پذیرفته نیست.
    - رشته، bytes و bytearray پذیرفته نیستند.
    - NaN، Infinity و عددی که قابل تبدیل به float نیست رد می‌شود.
"""

from __future__ import annotations

import math
from collections.abc import Mapping

__all__ = ["validate_report_numbers"]

_REPORT_SECTIONS = (
    "displacements",
    "reactions",
    "member_end_actions",
    "internal_forces",
)


def _check_number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(
            f"«{label}» باید عدد باشد، نه {type(value).__name__}"
        )

    try:
        number = float(value)
    except OverflowError as exc:
        raise ValueError(
            f"«{label}» خارج از محدودهٔ قابل نمایش عددی است"
        ) from exc

    if not math.isfinite(number):
        raise ValueError(
            f"«{label}» باید متناهی باشد؛ مقدار داده‌شده: {value}"
        )


def _walk(value, label):
    if isinstance(value, (str, bytes, bytearray)):
        raise ValueError(f"«{label}» نباید رشته یا bytes باشد")

    if isinstance(value, (tuple, list)):
        for position, item in enumerate(value):
            _walk(item, f"{label}[{position}]")
        return

    if isinstance(value, Mapping):
        for key, item in value.items():
            _walk(item, f"{label}[{key!r}]")
        return

    _check_number(value, label)


def validate_report_numbers(report):
    """بررسی همهٔ مقادیر عددی گزارش؛ در صورت خطا ValueError فارسی پرتاب می‌شود.

    بخش‌های گزارش و n_points بررسی می‌شوند. ساختار دقیق بخش‌ها (مثلاً طول
    سه‌تایی بودن) بر عهدهٔ ویوها است؛ این تابع فقط عدد بودن و متناهی بودن را
    تضمین می‌کند.

    Raises:
        ValueError: گزارش ناقص است یا مقدار عددی نامعتبر دارد.
    """
    for section in _REPORT_SECTIONS:
        if not hasattr(report, section):
            raise ValueError(f"گزارش فاقد بخش «{section}» است")
        _walk(getattr(report, section), section)

    if not hasattr(report, "n_points"):
        raise ValueError("گزارش فاقد «n_points» است")
    _check_number(report.n_points, "n_points")
