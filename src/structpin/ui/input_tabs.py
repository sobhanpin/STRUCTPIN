
"""رابط ورود اطلاعات مدل قاب دوبعدی STRUCTPIN (tkinter و ttk استاندارد).

این ماژول فقط لایه ورود داده است.
اعتبارسنجی و تبدیل نهایی داده‌ها توسط model_builder انجام می‌شود.
"""

import contextlib
import tkinter as tk
from collections import namedtuple
from tkinter import ttk

from structpin.services.model_builder import ModelBuildError
from structpin.services.model_builder import build_model as build_structural_model

__all__ = ["InputTabs", "ModelBuildError"]


_FONT_FAMILY = "Tahoma"
_COLOR_BG = "#141B2D"
_COLOR_PANEL = "#1F2A44"
_COLOR_FIELD = "#252F45"
_COLOR_TEXT = "#E6E9EF"
_COLOR_MUTED = "#9AA4B8"
_COLOR_ACCENT = "#2F6DB5"
_COLOR_GOLD = "#C9A227"

_KIND_TEXT = "text"
_KIND_BOOL = "bool"

_Column = namedtuple("_Column", ("key", "heading", "width", "kind"))

_MATERIAL_COLUMNS = (
    _Column("name", "نام مصالح", 200, _KIND_TEXT),
    _Column("E", "E (مدول الاستیسیته)", 180, _KIND_TEXT),
)
_SECTION_COLUMNS = (
    _Column("name", "نام مقطع", 180, _KIND_TEXT),
    _Column("A", "A (مساحت)", 150, _KIND_TEXT),
    _Column("I", "I (ممان اینرسی)", 150, _KIND_TEXT),
)
_NODE_COLUMNS = (
    _Column("id", "ID", 120, _KIND_TEXT),
    _Column("x", "X", 150, _KIND_TEXT),
    _Column("y", "Y", 150, _KIND_TEXT),
)
_MEMBER_COLUMNS = (
    _Column("id", "ID", 100, _KIND_TEXT),
    _Column("node_i", "node_i", 120, _KIND_TEXT),
    _Column("node_j", "node_j", 120, _KIND_TEXT),
    _Column("material", "material", 160, _KIND_TEXT),
    _Column("section", "section", 160, _KIND_TEXT),
)
_RESTRAINT_COLUMNS = (
    _Column("node", "node", 120, _KIND_TEXT),
    _Column("ux", "ux", 100, _KIND_BOOL),
    _Column("uy", "uy", 100, _KIND_BOOL),
    _Column("rz", "rz", 100, _KIND_BOOL),
)
_NODAL_LOAD_COLUMNS = (
    _Column("node", "node", 120, _KIND_TEXT),
    _Column("fx", "fx", 130, _KIND_TEXT),
    _Column("fy", "fy", 130, _KIND_TEXT),
    _Column("mz", "mz", 130, _KIND_TEXT),
)
_MEMBER_UDL_COLUMNS = (
    _Column("member", "member", 120, _KIND_TEXT),
    _Column("qy", "qy", 150, _KIND_TEXT),
)

_TABLE_SPECS = (
    ("materials", "مصالح", _MATERIAL_COLUMNS,
     "مقادیر عددی را با نقطه اعشار وارد کنید (مثلاً 200.0). برای ویرایش، روی سلول دوبار کلیک کنید."),
    ("sections", "مقاطع", _SECTION_COLUMNS,
     "مقادیر A و I باید مثبت باشند. برای ویرایش، روی سلول دوبار کلیک کنید."),
    ("nodes", "گره‌ها", _NODE_COLUMNS,
     "شناسه گره عدد صحیح است. برای ویرایش، روی سلول دوبار کلیک کنید."),
    ("members", "اعضا", _MEMBER_COLUMNS,
     "node_i و node_j شناسه گره، و material و section نام مصالح و مقطع هستند."),
    ("restraints", "تکیه‌گاه‌ها", _RESTRAINT_COLUMNS,
     "برای تغییر بله/خیر هر پرچم، روی همان سلول دوبار کلیک کنید."),
    ("nodal_loads", "بارهای گره‌ای", _NODAL_LOAD_COLUMNS,
     "بار گره‌ای با مقدار صفر مجاز است. برای ویرایش، روی سلول دوبار کلیک کنید."),
    ("member_udls", "بارهای گسترده اعضا", _MEMBER_UDL_COLUMNS,
     "qy بار گسترده یکنواخت در جهت محلی y عضو است."),
)

_TABLE_KEYS = tuple(spec[0] for spec in _TABLE_SPECS)


def _configure_styles(master):
    """تنظیم سبک ظاهری ttk."""
    style = ttk.Style(master)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    style.configure("TFrame", background=_COLOR_BG)
    style.configure("TLabel", background=_COLOR_BG, foreground=_COLOR_TEXT,
                    font=(_FONT_FAMILY, 10))
    style.configure("Hint.TLabel", background=_COLOR_BG, foreground=_COLOR_MUTED,
                    font=(_FONT_FAMILY, 9))
    style.configure("TNotebook", background=_COLOR_BG, borderwidth=0)
    style.configure("TNotebook.Tab", background=_COLOR_PANEL, foreground=_COLOR_TEXT,
                    padding=(14, 6), font=(_FONT_FAMILY, 10))
    style.map("TNotebook.Tab",
              background=[("selected", _COLOR_ACCENT)],
              foreground=[("selected", "#FFFFFF")])
    style.configure("TButton", background=_COLOR_PANEL, foreground=_COLOR_TEXT,
                    padding=(10, 4), font=(_FONT_FAMILY, 10))
    style.map("TButton",
              background=[("active", _COLOR_ACCENT)],
              foreground=[("active", "#FFFFFF")])
    style.configure("TEntry", fieldbackground=_COLOR_FIELD, foreground=_COLOR_TEXT,
                    insertcolor=_COLOR_TEXT, padding=4)
    style.configure("Treeview", background=_COLOR_FIELD, fieldbackground=_COLOR_FIELD,
                    foreground=_COLOR_TEXT, rowheight=24, font=(_FONT_FAMILY, 10))
    style.configure("Treeview.Heading", background=_COLOR_PANEL, foreground=_COLOR_GOLD,
                    font=(_FONT_FAMILY, 10, "bold"), relief="flat")
    style.map("Treeview",
              background=[("selected", _COLOR_ACCENT)],
              foreground=[("selected", "#FFFFFF")])
    style.map("Treeview.Heading", background=[("active", _COLOR_ACCENT)])
    style.configure("Vertical.TScrollbar", background=_COLOR_PANEL,
                    troughcolor=_COLOR_BG, arrowcolor=_COLOR_GOLD)


class _RowTable(ttk.Frame):
    """جدول ورود داده با امکان اطلاع‌رسانی تغییرات واقعی کاربر."""

    def __init__(self, master, columns, hint, on_change=None):
        super().__init__(master, padding=(8, 8))
        self._columns = tuple(columns)
        self._keys = tuple(c.key for c in self._columns)
        self._rows = []
        self._editor = None
        self._edit_index = None
        self._edit_key = None
        self._on_change = on_change

        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        toolbar = ttk.Frame(self)
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        ttk.Label(toolbar, text=hint, style="Hint.TLabel").pack(side="left")
        ttk.Button(
            toolbar, text="حذف ردیف‌های انتخاب‌شده",
            command=self.delete_selected
        ).pack(side="right", padx=(6, 0))
        ttk.Button(
            toolbar, text="افزودن ردیف",
            command=self.add_row
        ).pack(side="right", padx=(6, 0))

        body = ttk.Frame(self)
        body.grid(row=1, column=0, sticky="nsew")
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)

        self._tree = ttk.Treeview(
            body,
            columns=("row_no",) + self._keys,
            show="headings",
            selectmode="extended",
        )
        vsb = ttk.Scrollbar(body, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        self._tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")

        self._tree.heading("row_no", text="ردیف", anchor="center")
        self._tree.column("row_no", width=60, minwidth=50,
                          stretch=False, anchor="center")

        for col in self._columns:
            self._tree.heading(col.key, text=col.heading, anchor="center")
            self._tree.column(col.key, width=col.width, minwidth=60,
                              stretch=True, anchor="center")

        self._tree.bind("<Double-1>", self._on_double_click)
        self._tree.bind("<Delete>", self._on_delete_key)
        self._tree.bind("<MouseWheel>", self._on_wheel)
        self._tree.bind("<Button-4>", self._on_wheel_up_linux)
        self._tree.bind("<Button-5>", self._on_wheel_down_linux)

    def _notify(self):
        if self._on_change is not None:
            self._on_change()

    def selected_indices(self):
        return [int(iid) for iid in self._tree.selection()]

    def _flush_edit_silently(self):
        """ثبت ویرایش باز بدون ارسال callback."""
        editor = self._editor
        if editor is None:
            return False

        value = editor.get()
        index = self._edit_index
        key = self._edit_key
        self._close_editor()

        if index is None or key is None or not (0 <= index < len(self._rows)):
            self._refresh()
            return False

        changed = self._rows[index][key] != value
        if changed:
            self._rows[index][key] = value
        self._refresh()
        return changed

    def add_row(self):
        self._flush_edit_silently()

        row = {}
        for col in self._columns:
            if col.kind == _KIND_BOOL:
                row[col.key] = tk.BooleanVar(master=self, value=False)
            else:
                row[col.key] = ""

        self._rows.append(row)
        new_index = len(self._rows) - 1
        self._refresh(select=[new_index])
        self._tree.see(str(new_index))
        self._notify()

    def delete_selected(self):
        edited = self._flush_edit_silently()
        indices = sorted(set(self.selected_indices()), reverse=True)

        deleted = False
        for index in indices:
            if 0 <= index < len(self._rows):
                del self._rows[index]
                deleted = True

        if deleted:
            self._refresh(select=[])
        if deleted or edited:
            self._notify()

    def clear(self):
        self._close_editor()
        self._rows = []
        self._refresh(select=[])

    def has_data(self):
        return bool(self._rows or self._editor is not None)

    def get_rows(self):
        """دریافت داده بدون ایجاد callback ناخواسته."""
        self._flush_edit_silently()
        result = []

        for row in self._rows:
            item = {}
            for col in self._columns:
                value = row[col.key]
                item[col.key] = (
                    bool(value.get()) if col.kind == _KIND_BOOL else value
                )
            result.append(item)

        return result

    def set_rows(self, items):
        """جایگزینی برنامه‌ای ردیف‌ها بدون callback."""
        self._close_editor()
        new_rows = []

        for position, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                raise ValueError(f"ردیف {position}: هر ردیف باید دیکشنری باشد")

            row = {}
            for col in self._columns:
                raw = item.get(col.key)

                if col.kind == _KIND_BOOL:
                    if raw is None:
                        raw = False
                    if not isinstance(raw, bool):
                        raise ValueError(
                            f"ردیف {position}، «{col.heading}»: "
                            "مقدار باید بله/خیر (bool) باشد"
                        )
                    row[col.key] = tk.BooleanVar(master=self, value=raw)
                else:
                    row[col.key] = "" if raw is None else str(raw)

            new_rows.append(row)

        self._rows = new_rows
        self._refresh(select=[])

    def _refresh(self, select=None):
        """بازسازی نمایش؛ بدون ثبت ویرایش باز."""
        if select is None:
            select = self.selected_indices()

        self._tree.delete(*self._tree.get_children())

        for index, row in enumerate(self._rows):
            values = [str(index + 1)]
            for col in self._columns:
                value = row[col.key]
                if col.kind == _KIND_BOOL:
                    values.append("بله" if value.get() else "خیر")
                else:
                    values.append(value)

            self._tree.insert("", "end", iid=str(index), values=values)

        valid = [str(i) for i in select if 0 <= i < len(self._rows)]
        if valid:
            self._tree.selection_set(valid)

    def _on_double_click(self, event):
        if self._tree.identify_region(event.x, event.y) != "cell":
            return "break"

        row_id = self._tree.identify_row(event.y)
        col_id = self._tree.identify_column(event.x)
        if not row_id or not col_id:
            return "break"

        col_pos = int(col_id.lstrip("#")) - 2
        if not 0 <= col_pos < len(self._columns):
            return "break"

        index = int(row_id)
        if index >= len(self._rows):
            return "break"

        column = self._columns[col_pos]

        if column.kind == _KIND_BOOL:
            self._flush_edit_silently()
            flag = self._rows[index][column.key]
            flag.set(not flag.get())
            self._refresh()
            self._notify()
            return "break"

        self._open_editor(index, column, row_id, col_id)
        return "break"

    def _open_editor(self, index, column, row_id, col_id):
        edited = self._flush_edit_silently()
        if edited:
            self._notify()

        bbox = self._tree.bbox(row_id, col_id)
        if not bbox:
            return

        x, y, width, height = bbox
        editor = ttk.Entry(self._tree, justify="right")
        editor.insert(0, self._rows[index][column.key])
        editor.place(x=x, y=y, width=width, height=height)
        editor.bind("<Return>", self._commit_edit)
        editor.bind("<KP_Enter>", self._commit_edit)
        editor.bind("<FocusOut>", self._commit_edit)
        editor.bind("<Escape>", self._cancel_edit)

        self._editor = editor
        self._edit_index = index
        self._edit_key = column.key

        editor.focus_set()
        editor.select_range(0, "end")

    def _commit_edit(self, _event=None):
        """ثبت ویرایش و اعلام تغییر فقط در صورت تغییر واقعی مقدار."""
        changed = self._flush_edit_silently()
        if changed:
            self._notify()
        return "break"

    def _cancel_edit(self, _event=None):
        self._close_editor()
        self._refresh()
        return "break"

    def _close_editor(self):
        editor = self._editor
        if editor is None:
            return

        self._editor = None
        self._edit_index = None
        self._edit_key = None
        editor.destroy()

    def _on_delete_key(self, _event=None):
        self.delete_selected()
        return "break"

    def _on_wheel(self, event):
        step = -1 if event.delta > 0 else 1
        self._tree.yview_scroll(step, "units")
        return "break"

    def _on_wheel_up_linux(self, _event=None):
        self._tree.yview_scroll(-1, "units")
        return "break"

    def _on_wheel_down_linux(self, _event=None):
        self._tree.yview_scroll(1, "units")
        return "break"


class InputTabs(ttk.Frame):
    """فرم ورود اطلاعات قاب دوبعدی."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        _configure_styles(self)

        self._project_name = tk.StringVar(master=self, value="")
        self._on_change_callback = None
        self._quiet_depth = 0
        self._last_name = ""

        self._project_name.trace_add("write", self._on_name_var_write)

        self._tables = {}

        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self._notebook = ttk.Notebook(self)
        self._notebook.grid(row=0, column=0, sticky="nsew",
                            padx=8, pady=(8, 4))

        self._build_project_tab()

        for key, title, columns, hint in _TABLE_SPECS:
            table = _RowTable(
                self._notebook,
                columns,
                hint,
                on_change=self._notify_user_change,
            )
            self._notebook.add(table, text=title)
            self._tables[key] = table

        footer = ttk.Frame(self)
        footer.grid(row=1, column=0, sticky="ew", padx=8, pady=(4, 8))
        ttk.Button(
            footer,
            text="پاک‌کردن فرم",
            command=self._on_clear_button,
        ).pack(side="left")

    def _build_project_tab(self):
        frame = ttk.Frame(self._notebook, padding=16)
        frame.columnconfigure(1, weight=1)

        ttk.Label(
            frame, text="نام پروژه:"
        ).grid(row=0, column=0, sticky="e", padx=(0, 10), pady=6)

        entry = ttk.Entry(
            frame,
            textvariable=self._project_name,
            justify="right",
        )
        entry.grid(row=0, column=1, sticky="ew", pady=6)

        self._notebook.add(frame, text="اطلاعات پروژه")

    # ------------------------------------------------------------------
    # سیستم اعلان تغییرات
    # ------------------------------------------------------------------

    def set_on_change(self, callback):
        """تنظیم callback تغییرات واقعی کاربر."""
        if callback is not None and not callable(callback):
            raise TypeError("callback باید قابل فراخوانی باشد")
        self._on_change_callback = callback

    @contextlib.contextmanager
    def _quiet(self):
        """جلوگیری از اعلان هنگام تغییرات برنامه‌ای فرم."""
        self._quiet_depth += 1
        try:
            yield
        finally:
            self._quiet_depth -= 1

    def _notify_user_change(self):
        if self._quiet_depth > 0:
            return

        callback = self._on_change_callback
        if callback is not None:
            callback()

    def _on_name_var_write(self, *_args):
        name = self._project_name.get()
        if name == self._last_name:
            return

        self._last_name = name
        self._notify_user_change()

    def _has_any_data(self):
        if self._project_name.get():
            return True
        return any(table.has_data() for table in self._tables.values())

    def _on_clear_button(self):
        if not self._has_any_data():
            return

        self.clear_form()
        self._notify_user_change()

    # ------------------------------------------------------------------
    # API عمومی
    # ------------------------------------------------------------------

    def get_form_data(self):
        """دریافت داده‌های فرم بدون اعلان تغییر ناخواسته."""
        data = {"name": self._project_name.get()}

        for key in _TABLE_KEYS:
            data[key] = self._tables[key].get_rows()

        return data

    def set_form_data(self, data):
        """بارگذاری برنامه‌ای فرم بدون ایجاد callback تغییر کاربر."""
        if not isinstance(data, dict):
            raise ValueError("داده‌های فرم باید دیکشنری باشند")

        name = data.get("name", "")
        if name is None:
            name = ""
        if not isinstance(name, str):
            raise ValueError("نام پروژه باید متن باشد")

        sections = {}
        for key, title, _columns, _hint in _TABLE_SPECS:
            value = data.get(key)
            if value is None:
                value = []
            if not isinstance(value, list):
                raise ValueError(f"بخش «{title}» باید فهرست باشد")
            sections[key] = value

        with self._quiet():
            self.clear_form()
            try:
                self._project_name.set(name)
                self._last_name = name

                for key in _TABLE_KEYS:
                    self._tables[key].set_rows(sections[key])

            except ValueError:
                self.clear_form()
                raise

    def build_model(self):
        """ساخت StructuralModel با استفاده از سرویس model_builder."""
        return build_structural_model(self.get_form_data())

    def clear_form(self):
        """پاک‌سازی برنامه‌ای فرم بدون اعلان تغییر کاربر."""
        with self._quiet():
            self._project_name.set("")
            self._last_name = ""

            for key in _TABLE_KEYS:
                self._tables[key].clear()
