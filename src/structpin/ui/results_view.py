"""نمایش نتایج تحلیل قاب دوبعدی STRUCTPIN (tkinter و ttk استاندارد).

این ماژول فقط نمایش‌دهنده است:
    - گزارش AnalysisReport را از services.analysis_service دریافت می‌کند.
    - هیچ محاسبهٔ مهندسی، تحلیل، اصلاح یا گرد کردن ذخیره‌شده انجام نمی‌دهد.
    - داده‌های گزارش را تغییر نمی‌دهد و فقط برای نمایش به متن تبدیل می‌کند.
    - هیچ فایل موتور FEM را import نمی‌کند.

قاعدهٔ جریان show_report:
    1. اعتبارسنجی نوع گزارش و ساختار همهٔ بخش‌ها (شامل n_points و warnings).
    2. تبدیل کامل داده‌ها به ردیف‌های نمایشی (بدون تغییر رابط).
    3. فقط پس از آماده‌شدن کامل داده‌ها، پاک‌سازی و پرکردن ویجت‌ها.
    4. اگر در مرحلهٔ 3 خطایی رخ دهد، رابط به حالت پاک‌شده برمی‌گردد و خطا دوباره پرتاب می‌شود.
"""

from __future__ import annotations

import math
import tkinter as tk
from collections.abc import Iterable, Mapping, Sequence
from tkinter import font as tkfont
from tkinter import ttk
from typing import Any, NamedTuple

from structpin.services.analysis_service import AnalysisReport

__all__ = ["ResultsView"]


_COLOR_BG = "#141B2D"
_COLOR_PANEL = "#1F2A44"
_COLOR_FIELD = "#252F45"
_COLOR_TEXT = "#E6E9EF"
_COLOR_MUTED = "#9AA4B8"
_COLOR_ACCENT = "#2F6DB5"
_COLOR_GOLD = "#C9A227"

_FONT_CANDIDATES = ("Tahoma", "Segoe UI")
_NO_WARNINGS_TEXT = "هشداری ثبت نشده است."
_EMPTY_TEXT = "—"

_TAB_SUMMARY = "خلاصه تحلیل"
_TAB_DISPLACEMENTS = "تغییرمکان گره‌ها"
_TAB_REACTIONS = "واکنش تکیه‌گاهی"
_TAB_END_ACTIONS = "نیروهای انتهایی اعضا"
_TAB_INTERNAL = "داده‌های N/V/M"
_TAB_WARNINGS = "هشدارها"

_DISPLACEMENT_COLUMNS = (("node", "شناسه گره"), ("ux", "Ux"), ("uy", "Uy"), ("rz", "Rz"))
_REACTION_COLUMNS = (("node", "شناسه گره"), ("Rx", "Rx"), ("Ry", "Ry"), ("Mz", "Mz"))
_END_ACTION_COLUMNS = (
    ("member", "شناسه عضو"),
    ("Ni", "Ni"),
    ("Vi", "Vi"),
    ("Mi", "Mi"),
    ("Nj", "Nj"),
    ("Vj", "Vj"),
    ("Mj", "Mj"),
)
_INTERNAL_COLUMNS = (("member", "شناسه عضو"), ("x", "x"), ("N", "N"), ("V", "V"), ("M", "M"))
_INTERNAL_KEYS = ("x", "N", "V", "M")

Row = tuple[str, ...]


class _Rows(NamedTuple):
    """همهٔ ردیف‌های نمایشی آمادهٔ درج، به‌همراه فهرست هشدارهای متنی."""

    displacements: list[Row]
    reactions: list[Row]
    end_actions: list[Row]
    internal: list[Row]
    warnings: list[str]


def _pick_font_family(root: tk.Misc) -> str:
    """اولین فونت موجود از میان گزینه‌ها؛ در غیر این صورت فونت پیش‌فرض Tk."""
    try:
        available = set(tkfont.families(root))
    except tk.TclError:
        return "TkDefaultFont"
    for name in _FONT_CANDIDATES:
        if name in available:
            return name
    return "TkDefaultFont"


def _format_number(value: Any) -> str:
    """نمایش امن عدد بدون تغییر مقدار ذخیره‌شده.

    مقادیر غیرعددی و غیرمتناهی به‌صورت متن نمایش داده می‌شوند و خطا ایجاد نمی‌کنند.
    """
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return f"{value:d}"
    if isinstance(value, float):
        if math.isnan(value):
            return "NaN"
        if math.isinf(value):
            return "∞" if value > 0 else "-∞"
        return f"{value:.6g}"
    return str(value)


def _as_sequence(value: Any, label: str) -> tuple[Any, ...]:
    """تبدیل توالی مرتب و قابل تکرار (tuple یا list) به تاپل.

    مجموعه‌های بدون ترتیب، iteratorهای یک‌بارمصرف، رشته، bytes و bytearray پذیرفته نمی‌شوند.
    """
    if isinstance(value, (str, bytes, bytearray)):
        raise ValueError(f"«{label}» نباید رشته یا bytes باشد")
    if not isinstance(value, (tuple, list)):
        raise ValueError(
            f"«{label}» باید tuple یا list باشد، نه {type(value).__name__}"
        )
    return tuple(value)


def _require_mapping(value: Any, label: str) -> Mapping[Any, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"«{label}» باید دیکشنری (Mapping) باشد، نه {type(value).__name__}")
    return value


def _validate_n_points(value: Any) -> int:
    """n_points باید int مثبت و غیر bool باشد."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(
            f"«n_points» باید عدد صحیح باشد، نه {type(value).__name__}"
        )
    if value < 1:
        raise ValueError(f"«n_points» باید حداقل ۱ باشد؛ مقدار داده‌شده: {value}")
    return value


def _validate_warnings(value: Any) -> list[str]:
    """warnings باید توالی مرتب باشد و هر عضو آن دقیقاً str باشد؛ تبدیل خودکار انجام نمی‌شود."""
    items = _as_sequence(value, "هشدارها")
    for position, item in enumerate(items, start=1):
        if not isinstance(item, str):
            raise ValueError(
                f"هشدار ردیف {position} باید متن (str) باشد، نه {type(item).__name__}"
            )
    return list(items)


def _rows_triplets(data: Mapping[Any, Any], label: str) -> list[Row]:
    """ردیف‌های سه‌تایی برای جدول‌های تغییرمکان و واکنش."""
    rows: list[Row] = []
    for node_id, triple in data.items():
        values = _as_sequence(triple, f"{label} گره {node_id}")
        if len(values) != 3:
            raise ValueError(f"{label} گره {node_id} باید دقیقاً سه مقدار داشته باشد")
        rows.append((_format_number(node_id), *(_format_number(v) for v in values)))
    return rows


def _rows_end_actions(data: Mapping[Any, Any]) -> list[Row]:
    """ردیف‌های نیروهای انتهایی؛ هر عضو باید دو انتها و هر انتها سه مقدار داشته باشد."""
    rows: list[Row] = []
    for member_id, pair in data.items():
        ends = _as_sequence(pair, f"نیروهای انتهایی عضو {member_id}")
        if len(ends) != 2:
            raise ValueError(f"نیروهای انتهایی عضو {member_id} باید دو انتها داشته باشد")
        end_i = _as_sequence(ends[0], f"انتهای i عضو {member_id}")
        end_j = _as_sequence(ends[1], f"انتهای j عضو {member_id}")
        if len(end_i) != 3 or len(end_j) != 3:
            raise ValueError(f"هر انتها در عضو {member_id} باید سه مقدار (N، V، M) داشته باشد")
        rows.append((
            _format_number(member_id),
            *(_format_number(v) for v in end_i),
            *(_format_number(v) for v in end_j),
        ))
    return rows


def _rows_internal(data: Mapping[Any, Any]) -> list[Row]:
    """ردیف‌های داده‌های داخلی؛ طول x، N، V، M باید برای هر عضو یکسان باشد."""
    rows: list[Row] = []
    for member_id, series in data.items():
        series_map = _require_mapping(series, f"داده‌های داخلی عضو {member_id}")
        arrays: dict[str, tuple[Any, ...]] = {}
        for key in _INTERNAL_KEYS:
            if key not in series_map:
                raise ValueError(f"داده‌های داخلی عضو {member_id} فاقد کلید «{key}» است")
            arrays[key] = _as_sequence(series_map[key], f"{key} عضو {member_id}")
        lengths = {key: len(arr) for key, arr in arrays.items()}
        if len(set(lengths.values())) != 1:
            raise ValueError(f"طول آرایه‌های عضو {member_id} یکسان نیست: {lengths}")
        member_label = _format_number(member_id)
        for index in range(lengths["x"]):
            rows.append((
                member_label,
                *(_format_number(arrays[key][index]) for key in _INTERNAL_KEYS),
            ))
    return rows


def _prepare_rows(report: AnalysisReport) -> _Rows:
    """اعتبارسنجی و تبدیل کامل گزارش به ردیف‌های نمایشی؛ هیچ ویجتی تغییر نمی‌کند."""
    displacements = _require_mapping(report.displacements, "تغییرمکان‌ها")
    reactions = _require_mapping(report.reactions, "واکنش‌ها")
    end_actions = _require_mapping(report.member_end_actions, "نیروهای انتهایی")
    internal = _require_mapping(report.internal_forces, "داده‌های داخلی")
    _validate_n_points(report.n_points)
    warnings = _validate_warnings(report.warnings)

    return _Rows(
        displacements=_rows_triplets(displacements, "تغییرمکان"),
        reactions=_rows_triplets(reactions, "واکنش"),
        end_actions=_rows_end_actions(end_actions),
        internal=_rows_internal(internal),
        warnings=warnings,
    )


class ResultsView(ttk.Frame):
    """نمایش گزارش تحلیل در چند تب جدولی.

    show_report(report) ابتدا همهٔ داده‌ها را اعتبارسنجی و آماده می‌کند؛ فقط در صورت
    موفقیت، محتوای رابط جایگزین می‌شود. clear() همهٔ جدول‌ها و خلاصه را پاک می‌کند.
    """

    def __init__(self, parent: tk.Misc, **kwargs: Any) -> None:
        super().__init__(parent, **kwargs)
        self._font_family = _pick_font_family(self)
        self._configure_styles()

        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self._notebook = ttk.Notebook(self, style="Results.TNotebook")
        self._notebook.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)

        self._summary_vars: dict[str, tk.StringVar] = {}
        self._summary_tab = self._build_summary_tab()
        self._notebook.add(self._summary_tab, text=_TAB_SUMMARY)

        self._displacement_tree = self._build_table_tab(_TAB_DISPLACEMENTS, _DISPLACEMENT_COLUMNS)
        self._reaction_tree = self._build_table_tab(_TAB_REACTIONS, _REACTION_COLUMNS)
        self._end_action_tree = self._build_table_tab(_TAB_END_ACTIONS, _END_ACTION_COLUMNS)
        self._internal_tree = self._build_table_tab(_TAB_INTERNAL, _INTERNAL_COLUMNS)
        self._warnings_text = self._build_warnings_tab()

        self.clear()

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
        style.configure("Results.TFrame", background=_COLOR_BG)
        style.configure("Results.TLabel", background=_COLOR_BG, foreground=_COLOR_TEXT, font=font)
        style.configure("ResultsValue.TLabel", background=_COLOR_BG,
                        foreground=_COLOR_ACCENT, font=(self._font_family, 10, "bold"))
        style.configure("Results.TNotebook", background=_COLOR_BG, borderwidth=0)
        style.configure("Results.TNotebook.Tab", background=_COLOR_PANEL,
                        foreground=_COLOR_TEXT, padding=(12, 5), font=font)
        style.map("Results.TNotebook.Tab",
                  background=[("selected", _COLOR_ACCENT)],
                  foreground=[("selected", "#FFFFFF")])
        style.configure("Results.Treeview", background=_COLOR_FIELD,
                        fieldbackground=_COLOR_FIELD, foreground=_COLOR_TEXT,
                        rowheight=22, font=font)
        style.configure("Results.Treeview.Heading", background=_COLOR_PANEL,
                        foreground=_COLOR_GOLD, font=(self._font_family, 10, "bold"),
                        relief="flat")
        style.map("Results.Treeview",
                  background=[("selected", _COLOR_ACCENT)],
                  foreground=[("selected", "#FFFFFF")])
        style.configure("Results.Vertical.TScrollbar", background=_COLOR_PANEL,
                        troughcolor=_COLOR_BG, arrowcolor=_COLOR_GOLD)
        style.configure("Results.Horizontal.TScrollbar", background=_COLOR_PANEL,
                        troughcolor=_COLOR_BG, arrowcolor=_COLOR_GOLD)

    def _build_summary_tab(self) -> ttk.Frame:
        tab = ttk.Frame(self._notebook, style="Results.TFrame", padding=16)
        tab.columnconfigure(1, weight=1)
        items = (
            ("nodes_displacement", "تعداد گره‌های دارای نتیجه تغییرمکان"),
            ("nodes_reaction", "تعداد گره‌های دارای واکنش"),
            ("members", "تعداد اعضای دارای نتایج"),
            ("n_points", "تعداد نقاط نمونه‌برداری"),
            ("warnings", "تعداد هشدارها"),
        )
        for row, (key, label) in enumerate(items):
            ttk.Label(tab, text=label, style="Results.TLabel").grid(
                row=row, column=0, sticky="e", padx=(0, 12), pady=6
            )
            var = tk.StringVar(master=self, value=_EMPTY_TEXT)
            self._summary_vars[key] = var
            ttk.Label(tab, textvariable=var, style="ResultsValue.TLabel").grid(
                row=row, column=1, sticky="w", pady=6
            )
        return tab

    def _build_table_tab(self, title: str, columns: Sequence[tuple[str, str]]) -> ttk.Treeview:
        tab = ttk.Frame(self._notebook, style="Results.TFrame", padding=8)
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(0, weight=1)
        tree = ttk.Treeview(
            tab,
            columns=tuple(key for key, _ in columns),
            show="headings",
            style="Results.Treeview",
            selectmode="browse",
        )
        for key, heading in columns:
            tree.heading(key, text=heading, anchor="center")
            tree.column(key, width=120, minwidth=70, stretch=True, anchor="center")
        vsb = ttk.Scrollbar(tab, orient="vertical", command=tree.yview,
                            style="Results.Vertical.TScrollbar")
        hsb = ttk.Scrollbar(tab, orient="horizontal", command=tree.xview,
                            style="Results.Horizontal.TScrollbar")
        tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        self._notebook.add(tab, text=title)
        return tree

    def _build_warnings_tab(self) -> tk.Text:
        tab = ttk.Frame(self._notebook, style="Results.TFrame", padding=8)
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(0, weight=1)
        text = tk.Text(
            tab,
            wrap="word",
            background=_COLOR_FIELD,
            foreground=_COLOR_TEXT,
            insertbackground=_COLOR_TEXT,
            relief="flat",
            font=(self._font_family, 10),
            state="disabled",
        )
        vsb = ttk.Scrollbar(tab, orient="vertical", command=text.yview,
                            style="Results.Vertical.TScrollbar")
        text.configure(yscrollcommand=vsb.set)
        text.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        self._notebook.add(tab, text=_TAB_WARNINGS)
        return text

    # ------------------------------------------------------------------
    # API عمومی
    # ------------------------------------------------------------------

    def show_report(self, report: AnalysisReport) -> None:
        """نمایش گزارش تحلیل.

        ابتدا همهٔ داده‌ها (شامل n_points و warnings) اعتبارسنجی و آماده می‌شوند؛ تا
        آن زمان محتوای رابط تغییر نمی‌کند. اگر در مرحلهٔ درج خطایی رخ دهد، رابط پاک
        می‌شود و خطا دوباره پرتاب می‌شود.

        Raises:
            ValueError: گزارش یا هر بخش آن ساختار معتبر ندارد.
        """
        if not isinstance(report, AnalysisReport):
            raise ValueError("ورودی نمایش نتایج باید نمونه‌ای از AnalysisReport باشد")

        rows = _prepare_rows(report)

        try:
            self.clear()
            self._fill_tree(self._displacement_tree, rows.displacements)
            self._fill_tree(self._reaction_tree, rows.reactions)
            self._fill_tree(self._end_action_tree, rows.end_actions)
            self._fill_tree(self._internal_tree, rows.internal)
            self._fill_warnings(rows.warnings)
            self._fill_summary(report, len(rows.warnings))
        except Exception:
            self.clear()
            raise

    def clear(self) -> None:
        """پاک‌کردن همهٔ جدول‌ها، هشدارها و خلاصه."""
        for tree in (
            self._displacement_tree,
            self._reaction_tree,
            self._end_action_tree,
            self._internal_tree,
        ):
            tree.delete(*tree.get_children())
        self._set_warnings_text(_NO_WARNINGS_TEXT)
        for var in self._summary_vars.values():
            var.set(_EMPTY_TEXT)

    # ------------------------------------------------------------------
    # پرکردن ویجت‌ها (فقط نمایش)
    # ------------------------------------------------------------------

    @staticmethod
    def _fill_tree(tree: ttk.Treeview, rows: Iterable[Row]) -> None:
        tree.delete(*tree.get_children())
        for row in rows:
            tree.insert("", tk.END, values=row)

    def _set_warnings_text(self, text: str) -> None:
        self._warnings_text.configure(state="normal")
        self._warnings_text.delete("1.0", tk.END)
        self._warnings_text.insert("1.0", text)
        self._warnings_text.configure(state="disabled")

    def _fill_warnings(self, warnings: Sequence[str]) -> None:
        if warnings:
            self._set_warnings_text("\n".join(f"• {w}" for w in warnings))
        else:
            self._set_warnings_text(_NO_WARNINGS_TEXT)

    def _fill_summary(self, report: AnalysisReport, warning_count: int) -> None:
        self._summary_vars["nodes_displacement"].set(str(len(report.displacements)))
        self._summary_vars["nodes_reaction"].set(str(len(report.reactions)))
        self._summary_vars["members"].set(str(len(report.member_end_actions)))
        self._summary_vars["n_points"].set(str(report.n_points))
        self._summary_vars["warnings"].set(str(warning_count))
