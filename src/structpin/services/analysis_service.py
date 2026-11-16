"""سرویس تحلیل قاب دوبعدی: اجرای تحلیل و ساخت گزارش ایمن.

این ماژول لایهٔ کاربردی است. هیچ فایل موتور تغییر نمی‌کند.

مسیر اعتبارسنجی مدل:
    فقط solve_frame مسئول اعتبارسنجی است. این سرویس model.validate() را صدا نمی‌زند.
    ModelError از solve_frame به AnalysisInputError تبدیل و علت اصلی حفظ می‌شود.

خطاها (بدون پنهان‌سازی):
    AnalysisInputError          ModelError از solve_frame (مدل نامعتبر)
    SingularSystemError         تکینگی/ناپایداری از موتور (پیام اصلی حفظ می‌شود)
    NumericalOverflowError      از موتور
    NumericalUnderflowError     از موتور
    ValueError                  n_points نامعتبر (در run_frame_analysis و در سازندهٔ AnalysisReport)

قرارداد immutability (AnalysisReport):
    در __post_init__ همهٔ فیلدها اعتبارسنجی و به ساختارهای غیرقابل‌تغییر تبدیل می‌شوند:
        - displacements، reactions، member_end_actions، internal_forces: MappingProxyType
          (با مقادیر tuple یا MappingProxyType تودرتو)
        - n_points: int مثبت و غیر bool (با _validate_n_points)
        - warnings: tuple از str (هر عنصر با str(...) تبدیل می‌شود)
    بنابراین گزارش، چه از run_frame_analysis و چه با سازندهٔ مستقیم، پس از ساخت
    قابل تغییر نیست و به ساختار قابل‌تغییر ورودی ارجاع ندارد.
"""

from dataclasses import dataclass, field
from types import MappingProxyType

from structpin.fem.frame2d import solve_frame
from structpin.fem.internal_forces import member_internal_forces
from structpin.model.structural_model import ModelError


class AnalysisError(Exception):
    """ریشهٔ خطاهای سرویس تحلیل (برای خطاهای سرویس، نه موتور)."""


class AnalysisInputError(AnalysisError):
    """مدل ورودی نامعتبر است. علت اصلی (ModelError) در __cause__ حفظ می‌شود."""


def _validate_n_points(n_points):
    """همان قاعدهٔ internal_forces._validate_n_points: فقط int غیر-bool و ≥ ۱."""
    if isinstance(n_points, bool) or not isinstance(n_points, int):
        raise ValueError(f"n_points باید عدد صحیح باشد، مقدار داده‌شده: {n_points!r}")
    if n_points < 1:
        raise ValueError(f"n_points باید حداقل ۱ باشد، مقدار داده‌شده: {n_points}")
    return n_points


def _freeze_triplet(values):
    return tuple(float(v) for v in values)


def _freeze_mapping_of_triplets(src):
    return MappingProxyType({k: _freeze_triplet(v) for k, v in dict(src).items()})


def _freeze_end_actions(src):
    out = {}
    for mid, pair in dict(src).items():
        out[mid] = (_freeze_triplet(pair[0]), _freeze_triplet(pair[1]))
    return MappingProxyType(out)


def _freeze_internal_forces(src):
    out = {}
    for mid, data in dict(src).items():
        out[mid] = MappingProxyType(
            {
                "x": tuple(float(v) for v in data["x"]),
                "N": tuple(float(v) for v in data["N"]),
                "V": tuple(float(v) for v in data["V"]),
                "M": tuple(float(v) for v in data["M"]),
            }
        )
    return MappingProxyType(out)


def _freeze_warnings(src):
    return tuple(str(w) for w in src)


@dataclass(frozen=True)
class AnalysisReport:
    """گزارش تحلیل غیرقابل‌تغییر و کاملاً مستقل از موتور.

    displacements:      node_id -> (ux, uy, rz)
    reactions:          node_id -> (Rx, Ry, Mz)
    member_end_actions: member_id -> ((N_i, V_i, M_i), (N_j, V_j, M_j))
    internal_forces:    member_id -> {'x': (...), 'N': (...), 'V': (...), 'M': (...)}
    n_points:           int مثبت و غیر bool (تعداد تقسیمات تحلیل داخلی)
    warnings:           tuple از رشته‌ها (فعلاً خالی)
    """

    displacements: MappingProxyType
    reactions: MappingProxyType
    member_end_actions: MappingProxyType
    internal_forces: MappingProxyType
    n_points: int
    warnings: tuple = field(default_factory=tuple)

    def __post_init__(self):
        object.__setattr__(self, "displacements", _freeze_mapping_of_triplets(self.displacements))
        object.__setattr__(self, "reactions", _freeze_mapping_of_triplets(self.reactions))
        object.__setattr__(self, "member_end_actions", _freeze_end_actions(self.member_end_actions))
        object.__setattr__(self, "internal_forces", _freeze_internal_forces(self.internal_forces))
        object.__setattr__(self, "n_points", _validate_n_points(self.n_points))
        object.__setattr__(self, "warnings", _freeze_warnings(self.warnings))


def run_frame_analysis(model, n_points=20):
    """تحلیل قاب دوبعدی و بازگرداندن AnalysisReport.

    Args:
        model: StructuralModel.
        n_points: عدد صحیح مثبت؛ تعداد تقسیمات نیروهای داخلی (پیش‌فرض ۲۰).

    Raises:
        ValueError: n_points نامعتبر.
        AnalysisInputError: مدل نامعتبر (علت اصلی در __cause__).
        SingularSystemError, NumericalOverflowError, NumericalUnderflowError: از موتور بدون تغییر.
    """
    n_points = _validate_n_points(n_points)

    try:
        results = solve_frame(model)
    except ModelError as exc:
        raise AnalysisInputError(f"مدل نامعتبر است: {exc}") from exc

    forces = member_internal_forces(model, results, n_points=n_points)
    return AnalysisReport(
        displacements=results.displacements,
        reactions=results.reactions,
        member_end_actions=results.member_end_actions,
        internal_forces=forces,
        n_points=n_points,
        warnings=(),
  )
