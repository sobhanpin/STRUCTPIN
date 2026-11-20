
"""نمودار نیروهای داخلی N، V و M برای قاب دوبعدی STRUCTPIN.

این ماژول فقط نمایش‌دهنده است:
    - داده‌ها را از report.internal_forces می‌خواند و پیش از نمایش اعتبارسنجی می‌کند.
    - هیچ محاسبهٔ تحلیل یا مهندسی انجام نمی‌دهد.
    - هیچ import از FEM، مدل سازه یا موتور تحلیل ندارد.

پایداری عددی:
    - نگاشت‌ها در فضای نرمال‌شده با frexp و ldexp انجام می‌شوند.
    - بازه‌های نمایشی با حاشیهٔ متناسب با مقیاس داده ساخته می‌شوند.
    - نسبت نقاط، tickها و خط صفر در مرحلهٔ آماده‌سازی محاسبه می‌شوند.
    - مختصات Canvas پیش از شروع رسم ساخته و اعتبارسنجی می‌شوند.
    - رسم جدید ابتدا به‌صورت موقت ساخته می‌شود تا شکست در ساخت آن
      نمودار قبلی را از بین نبرد.

قرارداد API:
    show_report(report) -> None
    clear() -> None
"""

from __future__ import annotations

import math
import sys
import tkinter as tk
from collections.abc import Mapping
from tkinter import font as tkfont
from tkinter import ttk
from typing import Any, NamedTuple

from structpin.services.analysis_service import AnalysisReport

__all__ = ["PlotCanvas"]


_COLOR_BG = "#141B2D"
_COLOR_PANEL = "#1F2A44"
_COLOR_SURFACE = "#252F45"
_COLOR_TEXT = "#E6E9EF"
_COLOR_MUTED = "#9AA4B8"
_COLOR_GOLD = "#C9A227"
_COLOR_GRID = "#34405E"
_COLOR_ZERO = "#9AA4B8"
_COLOR_CURVE = "#2F6DB5"
_COLOR_POINT = "#C9A227"

_FONT_CANDIDATES = ("Tahoma", "Segoe UI")
_QUANTITY_KEYS = ("N", "V", "M")
_QUANTITY_LABELS = {
    "N": "نیروی محوری N",
    "V": "نیروی برشی V",
    "M": "لنگر خمشی M",
}
_SERIES_KEYS = ("x", "N", "V", "M")

_PADDING_LEFT = 70
_PADDING_RIGHT = 20
_PADDING_TOP = 40
_PADDING_BOTTOM = 50
_GRID_DIVISIONS = 5
_POINT_RADIUS = 4
_RANGE_MARGIN_RATIO = 0.16
_CONSTANT_MARGIN_RATIO = 0.1
_MAX_FLOAT = sys.float_info.max
_MIN_SUBNORMAL = 5e-324
_RESIZE_DELAY_MS = 60

_EMPTY_MESSAGE = "گزارشی برای نمایش وجود ندارد."
_NO_MEMBER_MESSAGE = "عضوی برای نمایش انتخاب نشده است."

_DRAW_TAG = "structpin_plot"
_STAGE_TAG = "structpin_plot_stage"
_ERROR_TAG = "structpin_plot_error"

_Op = tuple[str, tuple[float, ...], dict[str, Any]]


class _Series(NamedTuple):
    """داده معتبر و مستقل یک عضو."""

    x: tuple[float, ...]
    N: tuple[float, ...]
    V: tuple[float, ...]
    M: tuple[float, ...]

    def values(self, quantity: str) -> tuple[float, ...]:
        return getattr(self, quantity)


class _Range(NamedTuple):
    """بازه نمایشی معتبر."""

    lo: float
    hi: float


class _Tick(NamedTuple):
    """مقدار و موقعیت نسبی یک tick."""

    value: float
    t: float


class _MemberPlot(NamedTuple):
    """داده‌های آماده‌شده برای رسم یک عضو."""

    x_ticks: tuple[_Tick, ...]
    x_points: tuple[float, ...]
    y_ticks: dict[str, tuple[_Tick, ...]]
    y_points: dict[str, tuple[float, ...]]
    zero_t: dict[str, float | None]


class _Prepared(NamedTuple):
    """داده‌های آماده‌شده گزارش."""

    plots: dict[Any, _MemberPlot]
    label_map: dict[str, Any]


# ----------------------------------------------------------------------
# ابزارهای نرمال‌سازی عددی
# ----------------------------------------------------------------------


def _exponent(lo: float, hi: float) -> int:
    scale = max(abs(lo), abs(hi))
    if scale == 0.0:
        return 0
    return math.frexp(scale)[1]


def _to_norm(value: float, exp: int) -> float:
    return math.ldexp(value, -exp)


def _from_norm(value_n: float, exp: int) -> float:
    try:
        return math.ldexp(value_n, exp)
    except OverflowError:
        return math.copysign(math.inf, value_n)


def _span_norm(lo: float, hi: float) -> float:
    exp = _exponent(lo, hi)
    return _to_norm(hi, exp) - _to_norm(lo, exp)


def _has_positive_width(lo: float, hi: float) -> bool:
    if not (math.isfinite(lo) and math.isfinite(hi) and lo < hi):
        return False
    span = _span_norm(lo, hi)
    return math.isfinite(span) and span > 0.0


def _lerp(rng: _Range, t: float) -> float:
    if t <= 0.0:
        return rng.lo
    if t >= 1.0:
        return rng.hi

    exp = _exponent(rng.lo, rng.hi)
    lo_n = _to_norm(rng.lo, exp)
    hi_n = _to_norm(rng.hi, exp)
    mixed = lo_n * (1.0 - t) + hi_n * t
    result = _from_norm(mixed, exp)

    if not math.isfinite(result):
        raise ValueError("مقدار میان‌یابی نمودار متناهی نیست")

    return min(max(result, rng.lo), rng.hi)


def _scaled_fraction(value: float, rng: _Range) -> float:
    exp = _exponent(rng.lo, rng.hi)
    lo_n = _to_norm(rng.lo, exp)
    hi_n = _to_norm(rng.hi, exp)
    value_n = _to_norm(value, exp)

    width_n = hi_n - lo_n
    if not (math.isfinite(width_n) and width_n > 0.0):
        raise ValueError("عرض نرمال‌شدهٔ بازه نمودار معتبر نیست")

    t = (value_n - lo_n) / width_n
    if not math.isfinite(t):
        raise ValueError("نسبت نمایش نمودار متناهی نیست")

    return min(max(t, 0.0), 1.0)


def _safe_range(values: tuple[float, ...], label: str) -> _Range:
    """ساخت بازه نمایشی امن برای مقادیر متناهی."""

    if not values:
        raise ValueError(f"مقادیر بازه {label} خالی هستند")

    lo = min(values)
    hi = max(values)

    if lo == hi:
        if lo == 0.0:
            return _Range(-1.0, 1.0)

        margin = max(
            abs(lo) * _CONSTANT_MARGIN_RATIO,
            _MIN_SUBNORMAL,
        )
        new_lo = lo - margin
        new_hi = hi + margin

    else:
        exp = _exponent(lo, hi)
        lo_n = _to_norm(lo, exp)
        hi_n = _to_norm(hi, exp)

        span_n = hi_n - lo_n
        if not (math.isfinite(span_n) and span_n > 0.0):
            raise ValueError(
                f"بازه {label} برای نمایش قابل محاسبه نیست"
            )

        margin_n = span_n * _RANGE_MARGIN_RATIO

        new_lo = _from_norm(lo_n - margin_n, exp)
        new_hi = _from_norm(hi_n + margin_n, exp)

    if math.isinf(new_lo):
        new_lo = -_MAX_FLOAT
    if math.isinf(new_hi):
        new_hi = _MAX_FLOAT

    if new_lo >= lo:
        new_lo = math.nextafter(lo, -math.inf)
    if new_hi <= hi:
        new_hi = math.nextafter(hi, math.inf)

    if math.isinf(new_lo):
        new_lo = -_MAX_FLOAT
    if math.isinf(new_hi):
        new_hi = _MAX_FLOAT

    if not (math.isfinite(new_lo) and math.isfinite(new_hi)):
        raise ValueError(
            f"بازه {label} برای نمایش قابل محاسبه نیست (سرریز عددی)"
        )

    if not _has_positive_width(new_lo, new_hi):
        raise ValueError(
            f"بازه {label} عرض مثبت و قابل نمایش ندارد"
        )

    return _Range(new_lo, new_hi)


def _make_ticks(rng: _Range, label: str) -> tuple[_Tick, ...]:
    ticks = []

    for i in range(_GRID_DIVISIONS + 1):
        t = i / _GRID_DIVISIONS
        value = _lerp(rng, t)

        if not (
            math.isfinite(value)
            and rng.lo <= value <= rng.hi
        ):
            raise ValueError(
                f"مقدار tick بیرون از بازه {label} است"
            )

        ticks.append(_Tick(value, t))

    return tuple(ticks)


# ----------------------------------------------------------------------
# اعتبارسنجی داده
# ----------------------------------------------------------------------


def _pick_font_family(root: tk.Misc) -> str:
    try:
        available = set(tkfont.families(root))
    except tk.TclError:
        return "TkDefaultFont"

    for name in _FONT_CANDIDATES:
        if name in available:
            return name

    return "TkDefaultFont"


def _as_sequence(value: Any, label: str) -> tuple[Any, ...]:
    if isinstance(value, (str, bytes, bytearray)):
        raise ValueError(
            f"«{label}» نباید رشته یا bytes باشد"
        )

    if not isinstance(value, (tuple, list)):
        raise ValueError(
            f"«{label}» باید tuple یا list باشد، "
            f"نه {type(value).__name__}"
        )

    return tuple(value)


def _as_plot_number(value: Any, label: str) -> float:
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

    return number


def _validate_series(member_id: Any, data: Any) -> _Series:
    label = f"داده‌های عضو {member_id}"

    if not isinstance(data, Mapping):
        raise ValueError(
            f"{label} باید دیکشنری (Mapping) باشد"
        )

    for key in _SERIES_KEYS:
        if key not in data:
            raise ValueError(
                f"{label} فاقد کلید «{key}» است"
            )

    arrays = {
        key: _as_sequence(data[key], f"{key} {label}")
        for key in _SERIES_KEYS
    }

    lengths = {
        key: len(arr)
        for key, arr in arrays.items()
    }

    if len(set(lengths.values())) != 1:
        raise ValueError(
            f"طول آرایه‌های {label} یکسان نیست: {lengths}"
        )

    if lengths["x"] == 0:
        raise ValueError(
            f"آرایه‌های {label} خالی هستند و نمودار قابل رسم نیست"
        )

    converted = {
        key: tuple(
            _as_plot_number(v, f"{key} {label}")
            for v in arrays[key]
        )
        for key in _SERIES_KEYS
    }

    xs = converted["x"]

    for index in range(1, len(xs)):
        if not xs[index] > xs[index - 1]:
            raise ValueError(
                f"آرایه x {label} باید اکیداً صعودی باشد؛ "
                f"مقدار ردیف {index + 1} بزرگ‌تر از ردیف قبلی نیست"
            )

    return _Series(**converted)


def _validate_report(report: Any) -> dict[Any, _Series]:
    if not isinstance(report, AnalysisReport):
        raise ValueError(
            "ورودی نمودار باید نمونه‌ای از AnalysisReport باشد"
        )

    forces = report.internal_forces

    if not isinstance(forces, Mapping):
        raise ValueError(
            "«internal_forces» باید دیکشنری (Mapping) باشد"
        )

    return {
        member_id: _validate_series(member_id, data)
        for member_id, data in forces.items()
    }


def _prepare(report: Any) -> _Prepared:
    """آماده‌سازی کامل داده‌ها پیش از تغییر وضعیت رابط."""

    series = _validate_report(report)
    label_map = PlotCanvas._build_label_map(list(series.keys()))

    plots: dict[Any, _MemberPlot] = {}

    for member_id, data in series.items():
        x_label = f"x عضو {member_id}"
        x_range = _safe_range(data.x, x_label)

        x_points = tuple(
            _scaled_fraction(x, x_range)
            for x in data.x
        )
        x_ticks = _make_ticks(x_range, x_label)

        y_ticks: dict[str, tuple[_Tick, ...]] = {}
        y_points: dict[str, tuple[float, ...]] = {}
        zero_t: dict[str, float | None] = {}

        for quantity in _QUANTITY_KEYS:
            values = data.values(quantity)
            y_label = f"{quantity} عضو {member_id}"
            y_range = _safe_range(values, y_label)

            y_ticks[quantity] = _make_ticks(
                y_range,
                y_label,
            )

            y_points[quantity] = tuple(
                _scaled_fraction(y, y_range)
                for y in values
            )

            if y_range.lo <= 0.0 <= y_range.hi:
                zero_t[quantity] = _scaled_fraction(
                    0.0,
                    y_range,
                )
            else:
                zero_t[quantity] = None

        plots[member_id] = _MemberPlot(
            x_ticks=x_ticks,
            x_points=x_points,
            y_ticks=y_ticks,
            y_points=y_points,
            zero_t=zero_t,
        )

    return _Prepared(
        plots=plots,
        label_map=label_map,
    )


# ----------------------------------------------------------------------
# ساخت عملیات رسم بدون تماس با Canvas
# ----------------------------------------------------------------------


def _line(
    coords: tuple[float, ...],
    **options: Any,
) -> _Op:
    return ("line", coords, options)


def _oval(
    cx: float,
    cy: float,
    radius: float,
    fill: str,
) -> _Op:
    return (
        "oval",
        (
            cx - radius,
            cy - radius,
            cx + radius,
            cy + radius,
        ),
        {
            "fill": fill,
            "outline": "",
        },
    )


def _rect(
    coords: tuple[float, ...],
    outline: str,
) -> _Op:
    return (
        "rect",
        coords,
        {"outline": outline},
    )


def _text(
    x: float,
    y: float,
    text: str,
    **options: Any,
) -> _Op:
    return (
        "text",
        (x, y),
        {
            "text": text,
            **options,
        },
    )


def _check_op_finite(op: _Op) -> None:
    _, coords, _ = op

    if not all(math.isfinite(c) for c in coords):
        raise ValueError(
            "مختصات نمودار متناهی نیست و رسم انجام نمی‌شود"
        )


def _message_ops(
    text: str,
    width: float,
    height: float,
    font_family: str,
) -> list[_Op]:
    ops = [
        _text(
            width / 2,
            height / 2,
            text,
            fill=_COLOR_MUTED,
            font=(font_family, 11),
            justify="center",
        )
    ]

    for op in ops:
        _check_op_finite(op)

    return ops


def _build_plan(
    plot: _MemberPlot,
    quantity: str,
    title: str,
    width: float,
    height: float,
    font_family: str,
) -> list[_Op]:
    """ساخت کامل مختصات پیکسلی و عملیات رسم."""

    left = _PADDING_LEFT
    right = width - _PADDING_RIGHT
    top = _PADDING_TOP
    bottom = height - _PADDING_BOTTOM

    if right <= left or bottom <= top:
        return _message_ops(
            _EMPTY_MESSAGE,
            width,
            height,
            font_family,
        )

    span_x = right - left
    span_y = bottom - top
    ops: list[_Op] = []

    for tick in plot.x_ticks:
        px = left + tick.t * span_x

        ops.append(
            _line(
                (px, top, px, bottom),
                fill=_COLOR_GRID,
            )
        )

        ops.append(
            _text(
                px,
                bottom + 14,
                f"{tick.value:.4g}",
                fill=_COLOR_MUTED,
                font=(font_family, 9),
            )
        )

    for tick in plot.y_ticks[quantity]:
        py = bottom - tick.t * span_y

        ops.append(
            _line(
                (left, py, right, py),
                fill=_COLOR_GRID,
            )
        )

        ops.append(
            _text(
                left - 8,
                py,
                f"{tick.value:.4g}",
                fill=_COLOR_MUTED,
                font=(font_family, 9),
                anchor="e",
            )
        )

    ops.append(
        _rect(
            (left, top, right, bottom),
            outline=_COLOR_MUTED,
        )
    )

    zero = plot.zero_t[quantity]

    if zero is not None:
        zy = bottom - zero * span_y

        ops.append(
            _line(
                (left, zy, right, zy),
                fill=_COLOR_ZERO,
                dash=(4, 3),
                width=1,
            )
        )

    pixels = [
        (
            left + tx * span_x,
            bottom - ty * span_y,
        )
        for tx, ty in zip(
            plot.x_points,
            plot.y_points[quantity],
        )
    ]

    if len(pixels) == 1:
        px, py = pixels[0]
        ops.append(
            _oval(
                px,
                py,
                _POINT_RADIUS,
                _COLOR_POINT,
            )
        )
    else:
        flat = tuple(
            coordinate
            for point in pixels
            for coordinate in point
        )

        ops.append(
            _line(
                flat,
                fill=_COLOR_CURVE,
                width=2,
                smooth=False,
            )
        )

        for px, py in (pixels[0], pixels[-1]):
            ops.append(
                _oval(
                    px,
                    py,
                    _POINT_RADIUS,
                    _COLOR_POINT,
                )
            )

    ops.append(
        _text(
            width / 2,
            _PADDING_TOP / 2,
            title,
            fill=_COLOR_GOLD,
            font=(font_family, 11, "bold"),
        )
    )

    ops.append(
        _text(
            (left + right) / 2,
            bottom + 32,
            "x (طول عضو)",
            fill=_COLOR_TEXT,
            font=(font_family, 10),
        )
    )

    for op in ops:
        _check_op_finite(op)

    return ops


_CREATE_METHODS = {
    "line": "create_line",
    "oval": "create_oval",
    "rect": "create_rectangle",
    "text": "create_text",
}


# ----------------------------------------------------------------------
# رابط نمودار
# ----------------------------------------------------------------------


class PlotCanvas(ttk.Frame):
    """نمودار N، V یا M برای عضو انتخاب‌شده."""

    def __init__(
        self,
        parent: tk.Misc,
        **kwargs: Any,
    ) -> None:
        super().__init__(parent, **kwargs)

        self._font_family = _pick_font_family(self)
        self._prepared: _Prepared | None = None

        self._quantity_var = tk.StringVar(
            master=self,
            value=_QUANTITY_LABELS["M"],
        )
        self._member_var = tk.StringVar(
            master=self,
            value="",
        )

        self._resize_job: str | None = None
        self._last_draw_ops: tuple[_Op, ...] = ()
        self._last_redraw_error: str | None = None

        self._configure_styles()

        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        self._build_controls()
        self._build_canvas()
        self._bind_events()

        self._show_message(_EMPTY_MESSAGE)

    # ------------------------------------------------------------------
    # ساخت رابط
    # ------------------------------------------------------------------

    def _configure_styles(self) -> None:
        style = ttk.Style(self)

        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        font = (self._font_family, 10)

        style.configure(
            "Plot.TFrame",
            background=_COLOR_BG,
        )

        style.configure(
            "Plot.TLabel",
            background=_COLOR_BG,
            foreground=_COLOR_TEXT,
            font=font,
        )

        style.configure(
            "Plot.TCombobox",
            fieldbackground=_COLOR_SURFACE,
            background=_COLOR_PANEL,
            foreground=_COLOR_TEXT,
            font=font,
        )

    def _build_controls(self) -> None:
        bar = ttk.Frame(
            self,
            style="Plot.TFrame",
            padding=(8, 8),
        )
        bar.grid(
            row=0,
            column=0,
            sticky="ew",
        )

        ttk.Label(
            bar,
            text="عضو:",
            style="Plot.TLabel",
        ).pack(
            side=tk.RIGHT,
            padx=(6, 0),
        )

        self._member_box = ttk.Combobox(
            bar,
            textvariable=self._member_var,
            state="readonly",
            width=12,
            justify="right",
        )
        self._member_box.pack(
            side=tk.RIGHT,
            padx=(0, 16),
        )

        ttk.Label(
            bar,
            text="کمیت:",
            style="Plot.TLabel",
        ).pack(
            side=tk.RIGHT,
            padx=(6, 0),
        )

        self._quantity_box = ttk.Combobox(
            bar,
            textvariable=self._quantity_var,
            state="readonly",
            width=18,
            values=[
                _QUANTITY_LABELS[key]
                for key in _QUANTITY_KEYS
            ],
            justify="right",
        )
        self._quantity_box.pack(
            side=tk.RIGHT,
        )

    def _build_canvas(self) -> None:
        self._canvas = tk.Canvas(
            self,
            background=_COLOR_SURFACE,
            highlightthickness=0,
            borderwidth=0,
        )

        self._canvas.grid(
            row=1,
            column=0,
            sticky="nsew",
            padx=8,
            pady=(0, 8),
        )

    def _bind_events(self) -> None:
        self._canvas.bind(
            "<Configure>",
            self._on_canvas_configure,
        )

        self._member_box.bind(
            "<<ComboboxSelected>>",
            self._on_selection_changed,
        )

        self._quantity_box.bind(
            "<<ComboboxSelected>>",
            self._on_selection_changed,
        )

    # ------------------------------------------------------------------
    # API عمومی
    # ------------------------------------------------------------------

    
    def show_report(
        self,
        report: AnalysisReport,
    ) -> None:
        """اعتبارسنجی و نمایش گزارش."""

        prepared = _prepare(report)
        labels = list(prepared.label_map.keys())

        old_prepared = self._prepared
        old_labels = (
            list(old_prepared.label_map.keys())
            if old_prepared is not None
            else []
        )
        old_member = self._member_var.get()
        old_ops = self._last_draw_ops

        def restore_previous() -> None:
            """بازسازی وضعیت قبلی بدون پوشاندن خطای اصلی."""

            self._prepared = old_prepared

            restored = False

            if old_ops:
                try:
                    self._draw(list(old_ops))
                    restored = True
                except Exception:
                    restored = False

            if not restored:
                if old_prepared is None:
                    fallback_ops = _message_ops(
                        _EMPTY_MESSAGE,
                        *self._canvas_size(),
                        self._font_family,
                    )
                else:
                    member_id = old_prepared.label_map.get(
                        old_member
                    )

                    if member_id is None and old_labels:
                        member_id = old_prepared.label_map[
                            old_labels[0]
                        ]

                    if member_id is None:
                        fallback_ops = _message_ops(
                            _EMPTY_MESSAGE,
                            *self._canvas_size(),
                            self._font_family,
                        )
                    else:
                        quantity = self._selected_quantity()
                        width, height = self._canvas_size()

                        fallback_ops = _build_plan(
                            old_prepared.plots[member_id],
                            quantity,
                            self._plot_title(
                                member_id,
                                quantity,
                            ),
                            width,
                            height,
                            self._font_family,
                        )

                try:
                    self._draw(fallback_ops)
                    restored = True
                except Exception:
                    restored = False

            try:
                self._member_box.configure(
                    values=old_labels,
                )
                self._member_var.set(old_member)
            except Exception:
                pass

            if not restored:
                self._last_draw_ops = ()

        if not labels:
            ops = _message_ops(
                _EMPTY_MESSAGE,
                *self._canvas_size(),
                self._font_family,
            )

            self._draw(ops)

            try:
                self._member_box.configure(values=[])
                self._member_var.set("")
            except Exception:
                restore_previous()
                raise

            self._prepared = prepared
            return

        member_id = prepared.label_map[labels[0]]
        quantity = self._selected_quantity()
        width, height = self._canvas_size()

        ops = _build_plan(
            prepared.plots[member_id],
            quantity,
            self._plot_title(member_id, quantity),
            width,
            height,
            self._font_family,
        )

        self._draw(ops)

        try:
            self._member_box.configure(values=labels)
            self._member_var.set(labels[0])
        except Exception:
            restore_previous()
            raise

        self._prepared = prepared


    
    def clear(self) -> None:
        """پاک‌کردن داده‌ها و نمودار به‌صورت امن."""

        old_prepared = self._prepared
        old_labels = (
            list(old_prepared.label_map.keys())
            if old_prepared is not None
            else []
        )
        old_member = self._member_var.get()
        old_ops = self._last_draw_ops

        ops = _message_ops(
            _EMPTY_MESSAGE,
            *self._canvas_size(),
            self._font_family,
        )

        self._draw(ops)

        try:
            self._member_box.configure(values=[])
            self._member_var.set("")
        except Exception:
            self._prepared = old_prepared
            restored = False

            if old_ops:
                try:
                    self._draw(list(old_ops))
                    restored = True
                except Exception:
                    restored = False

            if not restored:
                if old_prepared is None:
                    fallback_ops = _message_ops(
                        _EMPTY_MESSAGE,
                        *self._canvas_size(),
                        self._font_family,
                    )
                else:
                    member_id = old_prepared.label_map.get(
                        old_member
                    )

                    if member_id is None and old_labels:
                        member_id = old_prepared.label_map[
                            old_labels[0]
                        ]

                    if member_id is None:
                        fallback_ops = _message_ops(
                            _EMPTY_MESSAGE,
                            *self._canvas_size(),
                            self._font_family,
                        )
                    else:
                        quantity = self._selected_quantity()
                        width, height = self._canvas_size()

                        fallback_ops = _build_plan(
                            old_prepared.plots[member_id],
                            quantity,
                            self._plot_title(
                                member_id,
                                quantity,
                            ),
                            width,
                            height,
                            self._font_family,
                        )

                try:
                    self._draw(fallback_ops)
                    restored = True
                except Exception:
                    restored = False

            try:
                self._member_box.configure(
                    values=old_labels,
                )
                self._member_var.set(old_member)
            except Exception:
                pass

            if not restored:
                self._last_draw_ops = ()

            raise

        self._prepared = None


    # ------------------------------------------------------------------
    # نگاشت شناسه اعضا
    # ------------------------------------------------------------------

    @staticmethod
    def _build_label_map(
        member_ids: list[Any],
    ) -> dict[str, Any]:
        mapping: dict[str, Any] = {}

        for member_id in member_ids:
            label = (
                f"{member_id} "
                f"({type(member_id).__name__})"
            )

            if label in mapping:
                raise ValueError(
                    "شناسه‌های عضو مبهم هستند و نمی‌توان "
                    f"آن‌ها را تفکیک کرد: {label}"
                )

            mapping[label] = member_id

        return mapping

    # ------------------------------------------------------------------
    # رویدادها
    # ------------------------------------------------------------------

    def _on_selection_changed(
        self,
        _event: Any = None,
    ) -> None:
        self._redraw()

    def _on_canvas_configure(
        self,
        _event: Any = None,
    ) -> None:
        if self._resize_job is not None:
            self.after_cancel(self._resize_job)

        self._resize_job = self.after(
            _RESIZE_DELAY_MS,
            self._on_resize_done,
        )

    def _on_resize_done(self) -> None:
        self._resize_job = None
        self._redraw()

    # ------------------------------------------------------------------
    # انتخاب‌ها
    # ------------------------------------------------------------------

    def _selected_quantity(self) -> str:
        label = self._quantity_var.get()

        for key, text in _QUANTITY_LABELS.items():
            if text == label:
                return key

        return "M"

    def _selected_member(self) -> Any | None:
        if self._prepared is None:
            return None

        text = self._member_var.get()

        if text not in self._prepared.label_map:
            return None

        return self._prepared.label_map[text]

    @staticmethod
    def _plot_title(
        member_id: Any,
        quantity: str,
    ) -> str:
        return (
            f"عضو {member_id} — "
            f"{_QUANTITY_LABELS[quantity]}"
        )

    # ------------------------------------------------------------------
    # رسم
    # ------------------------------------------------------------------

    def _canvas_size(self) -> tuple[float, float]:
        return (
            float(max(self._canvas.winfo_width(), 1)),
            float(max(self._canvas.winfo_height(), 1)),
        )

    def _redraw(self) -> None:
        """بازترسیم با حفظ نمودار قبلی در صورت خطا."""

        if (
            self._prepared is None
            or not self._prepared.plots
        ):
            self._show_message(_EMPTY_MESSAGE)
            return

        member_id = self._selected_member()

        if member_id is None:
            self._show_message(_NO_MEMBER_MESSAGE)
            return

        quantity = self._selected_quantity()
        width, height = self._canvas_size()

        try:
            ops = _build_plan(
                self._prepared.plots[member_id],
                quantity,
                self._plot_title(
                    member_id,
                    quantity,
                ),
                width,
                height,
                self._font_family,
            )

            self._draw(ops)
            self._last_redraw_error = None

        except (
            ValueError,
            tk.TclError,
            RuntimeError,
        ) as exc:
            self._last_redraw_error = str(exc)
            self._show_redraw_error()

    def _show_message(self, text: str) -> None:
        width, height = self._canvas_size()

        ops = _message_ops(
            text,
            width,
            height,
            self._font_family,
        )

        self._draw(ops)

    def _show_redraw_error(self) -> None:
        """نمایش هشدار بدون پاک‌کردن نمودار قبلی."""

        try:
            self._canvas.delete(_ERROR_TAG)

            width, height = self._canvas_size()

            self._canvas.create_text(
                width / 2,
                14,
                text="بازترسیم نمودار ناموفق بود",
                fill="#E6A23C",
                font=(self._font_family, 9),
                tags=(_ERROR_TAG,),
            )

        except (
            tk.TclError,
            RuntimeError,
        ):
            # خطای اصلی در _last_redraw_error حفظ می‌شود.
            pass

    def _create_ops(
        self,
        ops: list[_Op],
        tag: str,
    ) -> None:
        """ساخت عملیات رسم با برچسب مشخص."""

        for kind, coords, options in ops:
            method_name = _CREATE_METHODS.get(kind)

            if method_name is None:
                raise ValueError(
                    f"نوع عملیات رسم ناشناخته است: {kind}"
                )

            _check_op_finite(
                (kind, coords, options)
            )

            draw_options = dict(options)
            draw_options["tags"] = (tag,)

            getattr(
                self._canvas,
                method_name,
            )(
                *coords,
                **draw_options,
            )

    def _restore_previous_draw(
        self,
        previous: tuple[_Op, ...],
    ) -> None:
        """بازیابی بهترین‌تلاش نمودار قبلی."""

        try:
            self._canvas.delete("all")

            if previous:
                self._create_ops(
                    list(previous),
                    _DRAW_TAG,
                )

            self._last_draw_ops = previous

        except Exception:
            # خطای بازیابی نباید خطای اصلی را پنهان کند.
            pass

    def _draw(
        self,
        ops: list[_Op],
    ) -> None:
        """ساخت موقت و سپس جایگزینی نمودار قبلی."""

        canvas = self._canvas
        previous = self._last_draw_ops

        # مرحله اول: ساخت نمودار جدید در لایه موقت.
        # نمودار قبلی در این مرحله دست‌نخورده باقی می‌ماند.
        try:
            canvas.delete(_STAGE_TAG)

            self._create_ops(
                ops,
                _STAGE_TAG,
            )

        except Exception:
            try:
                canvas.delete(_STAGE_TAG)
            except Exception:
                pass

            raise

        # مرحله دوم: جایگزینی نمودار قبلی.
        try:
            canvas.delete(_DRAW_TAG)

            canvas.addtag_withtag(
                _DRAW_TAG,
                _STAGE_TAG,
            )

            canvas.dtag(
                _STAGE_TAG,
                _STAGE_TAG,
            )

            canvas.delete(_ERROR_TAG)

        except Exception:
            try:
                canvas.delete(_STAGE_TAG)
            except Exception:
                pass

            self._restore_previous_draw(previous)
            raise

        self._last_draw_ops = tuple(ops)
        self._last_redraw_error = None
