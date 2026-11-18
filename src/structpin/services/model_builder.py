"""تبدیل داده‌های فرم (ورودی کاربر) به StructuralModel.

این ماژول کاملاً مستقل از tkinter است و هیچ محاسبهٔ مهندسی انجام نمی‌دهد.

ورودی:
    دیکشنری با کلیدهای زیر (هر کدام لیست؛ کلیدهای اختیاری پیش‌فرض خالی دارند):
        name:          نام پروژه (متن؛ خالی یا فاصله‌دار → 'بدون نام')
        materials:     [{'name': متن, 'E': عدد}]
        sections:      [{'name': متن, 'A': عدد, 'I': عدد}]
        nodes:         [{'id': عدد صحیح, 'x': عدد, 'y': عدد}]
        members:       [{'id': عدد صحیح, 'node_i': عدد صحیح, 'node_j': عدد صحیح,
                         'material': متن, 'section': متن}]
        restraints:    [{'node': عدد صحیح, 'ux': bool, 'uy': bool, 'rz': bool}]
        nodal_loads:   [{'node': عدد صحیح, 'fx': عدد, 'fy': عدد, 'mz': عدد}]
        member_udls:   [{'member': عدد صحیح, 'qy': عدد}]

قواعد تبدیل مقادیر:
    عدد صحیح (شناسه‌ها):
        int غیر-bool، یا رشتهٔ معتبر برای int (پس از strip). مثال‌های معتبر: 1، "1"، " 12 ".
        رد: "1.5"، "1.0"، "", "abc"، True، 1.0 (float).
    عدد اعشاری (مختصات، بار، خواص مقطع و مصالح):
        int/float غیر-bool، یا رشتهٔ معتبر برای float (پس از strip).
        مثال‌های معتبر: 0.0، "0.0"، "-3.5"، "2e5".
        رد: "", "abc"، NaN و Infinity (عدد یا رشته)، True، Decimal و سایر انواع.
    پرچم تکیه‌گاه:
        فقط bool واقعی.
    متن (نام‌ها):
        فقط str غیرخالی پس از strip.

قواعد تکرار:
    تکیه‌گاه:
        - تکرار با مقدار یکسان روی (node, dof): پذیرفته؛ فقط یک بار به مدل افزوده می‌شود.
        - تکرار با مقدار متناقض روی (node, dof): رد با ModelBuildError.
        - ترتیب افزودن: ترتیب اولین حضور هر گره در ورودی.
        - گره‌ای که در ورودی آمده ولی هر سه پرچم آن False است، به مدل افزوده می‌شود.
    بار گره‌ای و بار گسترده:
        - تکرار مجاز است و موتور آن‌ها را جمع می‌کند (معنای فیزیکی: بارهای هم‌راستا).
    بار گسترده:
        - همیشه روی تمام طول عضو اعمال می‌شود. بار جزئی (روی بخشی از عضو) پشتیبانی نمی‌شود.
          (ثبت در KNOWN_LIMITATIONS.md)

خروجی:
    StructuralModel (بدون اعتبارسنجی هندسی کامل؛ آن بر عهدهٔ solve_frame است)

خطا:
    ModelBuildError با پیام فارسی که بخش و شماره ردیف (از ۱) را مشخص می‌کند.

قرارداد API مبنا (از structural_model.py):
    add_material(name, E)، add_section(name, A, I)، add_node(node_id, x, y)،
    add_member(member_id, node_i, node_j, material, section)،
    add_restraint(node, ux=False, uy=False, rz=False)،
    add_nodal_load(node, fx=0.0, fy=0.0, mz=0.0)، add_member_udl(member, qy)
    ModelError برای شناسهٔ تکراری در مصالح، مقاطع، گره‌ها و اعضا.
"""

import math

from structpin.model.structural_model import ModelError, StructuralModel


class ModelBuildError(ValueError):
    """داده‌های فرم برای ساخت مدل معتبر نیستند. پیام فارسی و قابل نمایش به کاربر است."""


_SECTION_NAMES = (
    "materials",
    "sections",
    "nodes",
    "members",
    "restraints",
    "nodal_loads",
    "member_udls",
)

_SECTION_LABELS = {
    "materials": "مصالح",
    "sections": "مقاطع",
    "nodes": "گره‌ها",
    "members": "اعضا",
    "restraints": "تکیه‌گاه‌ها",
    "nodal_loads": "بارهای گرهی",
    "member_udls": "بارهای گسترده",
}

_DOF_LABELS = {"ux": "ux", "uy": "uy", "rz": "rz"}


def _fail(section, row, message):
    """ساخت ModelBuildError با محل خطا (row از ۱؛ None یعنی سطح بخش)."""
    label = _SECTION_LABELS.get(section, section)
    if row is None:
        raise ModelBuildError(f"{label}: {message}")
    raise ModelBuildError(f"{label}، ردیف {row}: {message}")


def _require_mapping(item, section, row):
    if not isinstance(item, dict):
        _fail(section, row, "هر ردیف باید یک دیکشنری (شیء) باشد")


def _get(item, key, section, row):
    if key not in item:
        _fail(section, row, f"فیلد «{key}» وجود ندارد")
    return item[key]


def _as_text(value, key, section, row):
    if not isinstance(value, str):
        _fail(section, row, f"«{key}» باید متن باشد")
    text = value.strip()
    if not text:
        _fail(section, row, f"«{key}» نمی‌تواند خالی باشد")
    return text


def _as_int(value, key, section, row):
    """عدد صحیح: int غیر-bool یا رشتهٔ معتبر برای int. اعشار و خالی رد می‌شوند."""
    if isinstance(value, bool):
        _fail(section, row, f"«{key}» باید عدد صحیح باشد")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        text = value.strip()
        try:
            return int(text)
        except ValueError:
            _fail(section, row, f"«{key}» باید عدد صحیح باشد؛ مقدار داده‌شده: «{value}»")
    _fail(section, row, f"«{key}» باید عدد صحیح باشد")


def _as_bool(value, key, section, row):
    if not isinstance(value, bool):
        _fail(section, row, f"«{key}» باید بله/خیر (درست/نادرست) باشد")
    return value


def _as_finite_number(value, key, section, row):
    """عدد اعشاری متناهی از int، float یا رشتهٔ عددی. bool، NaN، Infinity، رشتهٔ خالی و متن رد می‌شوند."""
    if isinstance(value, bool):
        _fail(section, row, f"«{key}» باید عدد باشد، نه بله/خیر")
    if isinstance(value, (int, float)):
        raw = value
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            _fail(section, row, f"«{key}» نمی‌تواند خالی باشد")
        raw = text
    else:
        _fail(section, row, f"«{key}» باید عدد باشد")

    try:
        x = float(raw)
    except OverflowError:
        _fail(section, row, f"«{key}» خارج از محدودهٔ عددی است")
    except ValueError:
        _fail(section, row, f"«{key}» باید عدد باشد؛ مقدار داده‌شده: «{value}»")

    if not math.isfinite(x):
        _fail(section, row, f"«{key}» باید عدد متناهی باشد (نه بی‌نهایت یا NaN)")
    return x


def _positive(value, key, section, row):
    if value <= 0.0:
        _fail(section, row, f"«{key}» باید مثبت باشد")
    return value


def _section_list(data, name):
    value = data.get(name, [])
    if value is None:
        return []
    if not isinstance(value, list):
        label = _SECTION_LABELS.get(name, name)
        raise ModelBuildError(f"{label}: باید فهرست باشد")
    return value


def _build_name(data):
    value = data.get("name", "بدون نام")
    if not isinstance(value, str):
        raise ModelBuildError("نام پروژه باید متن باشد")
    text = value.strip()
    return text if text else "بدون نام"


def _wrap_model_error(section, row, exc):
    """تبدیل ModelError از add_* به ModelBuildError فارسی با محل خطا."""
    _fail(section, row, f"داده نامعتبر یا تکراری: {exc}")


def _add_restraints(model, items, node_ids):
    """افزودن تکیه‌گاه‌ها با سیاست تکرار.

    هر (node, dof) فقط یک مقدار دارد. تکرار با مقدار یکسان بی‌صدا پذیرفته و
    نادیده گرفته می‌شود؛ تکرار با مقدار متناقض رد می‌شود.

    ترتیب افزودن به مدل، ترتیب اولین حضور هر گره در ورودی است (بدون مرتب‌سازی).
    گره‌ای که در ورودی آمده باشد حتی اگر هر سه پرچم آن False باشد به مدل افزوده می‌شود.
    """
    seen = {}
    node_order = {}

    for idx, item in enumerate(items, start=1):
        _require_mapping(item, "restraints", idx)
        node = _as_int(_get(item, "node", "restraints", idx), "node", "restraints", idx)
        if node not in node_ids:
            _fail("restraints", idx, f"گره «{node}» در بخش گره‌ها تعریف نشده است")

        if node not in node_order:
            node_order[node] = len(node_order)

        flags = {
            "ux": _as_bool(_get(item, "ux", "restraints", idx), "ux", "restraints", idx),
            "uy": _as_bool(_get(item, "uy", "restraints", idx), "uy", "restraints", idx),
            "rz": _as_bool(_get(item, "rz", "restraints", idx), "rz", "restraints", idx),
        }

        for dof, value in flags.items():
            key = (node, dof)
            if key in seen:
                if seen[key] != value:
                    _fail(
                        "restraints",
                        idx,
                        f"تکیه‌گاه متناقض روی گره «{node}» و درجه آزادی «{_DOF_LABELS[dof]}»: "
                        f"قبلاً «{'بله' if seen[key] else 'خیر'}» و اکنون "
                        f"«{'بله' if value else 'خیر'}» تعریف شده است",
                    )
            seen[key] = value

    restrained_nodes = {}
    for (node, dof), value in seen.items():
        restrained_nodes.setdefault(node, {"ux": False, "uy": False, "rz": False})
        restrained_nodes[node][dof] = value

    for node in node_order:
        flags = restrained_nodes[node]
        model.add_restraint(node, ux=flags["ux"], uy=flags["uy"], rz=flags["rz"])


def build_model(data):
    """ساخت StructuralModel از دیکشنری فرم.

    Raises:
        ModelBuildError: داده‌های ورودی نامعتبر، ناقص، با نوع نادرست، ارجاع ناموجود،
            یا تکیه‌گاه متناقض.
    """
    if not isinstance(data, dict):
        raise ModelBuildError("ورودی باید یک دیکشنری (شیء) باشد")

    for name in _SECTION_NAMES:
        if name in data and data[name] is not None and not isinstance(data[name], list):
            label = _SECTION_LABELS[name]
            raise ModelBuildError(f"{label}: باید فهرست باشد")

    model = StructuralModel(_build_name(data))

    # ---- مصالح ----
    material_names = set()
    for idx, item in enumerate(_section_list(data, "materials"), start=1):
        _require_mapping(item, "materials", idx)
        name = _as_text(_get(item, "name", "materials", idx), "name", "materials", idx)
        E = _positive(_as_finite_number(_get(item, "E", "materials", idx), "E", "materials", idx), "E", "materials", idx)
        try:
            model.add_material(name, E)
        except ModelError as exc:
            _wrap_model_error("materials", idx, exc)
        material_names.add(name)

    # ---- مقاطع ----
    section_names = set()
    for idx, item in enumerate(_section_list(data, "sections"), start=1):
        _require_mapping(item, "sections", idx)
        name = _as_text(_get(item, "name", "sections", idx), "name", "sections", idx)
        A = _positive(_as_finite_number(_get(item, "A", "sections", idx), "A", "sections", idx), "A", "sections", idx)
        I = _positive(_as_finite_number(_get(item, "I", "sections", idx), "I", "sections", idx), "I", "sections", idx)
        try:
            model.add_section(name, A, I)
        except ModelError as exc:
            _wrap_model_error("sections", idx, exc)
        section_names.add(name)

    # ---- گره‌ها ----
    node_ids = set()
    for idx, item in enumerate(_section_list(data, "nodes"), start=1):
        _require_mapping(item, "nodes", idx)
        node_id = _as_int(_get(item, "id", "nodes", idx), "id", "nodes", idx)
        x = _as_finite_number(_get(item, "x", "nodes", idx), "x", "nodes", idx)
        y = _as_finite_number(_get(item, "y", "nodes", idx), "y", "nodes", idx)
        try:
            model.add_node(node_id, x, y)
        except ModelError as exc:
            _wrap_model_error("nodes", idx, exc)
        node_ids.add(node_id)

    # ---- اعضا ----
    member_ids = set()
    for idx, item in enumerate(_section_list(data, "members"), start=1):
        _require_mapping(item, "members", idx)
        member_id = _as_int(_get(item, "id", "members", idx), "id", "members", idx)
        node_i = _as_int(_get(item, "node_i", "members", idx), "node_i", "members", idx)
        node_j = _as_int(_get(item, "node_j", "members", idx), "node_j", "members", idx)
        mat = _as_text(_get(item, "material", "members", idx), "material", "members", idx)
        sec = _as_text(_get(item, "section", "members", idx), "section", "members", idx)
        if node_i not in node_ids:
            _fail("members", idx, f"گره ابتدای «{node_i}» در بخش گره‌ها تعریف نشده است")
        if node_j not in node_ids:
            _fail("members", idx, f"گره انتهای «{node_j}» در بخش گره‌ها تعریف نشده است")
        if mat not in material_names:
            _fail("members", idx, f"مصالح «{mat}» تعریف نشده است")
        if sec not in section_names:
            _fail("members", idx, f"مقطع «{sec}» تعریف نشده است")
        try:
            model.add_member(member_id, node_i, node_j, mat, sec)
        except ModelError as exc:
            _wrap_model_error("members", idx, exc)
        member_ids.add(member_id)

    # ---- تکیه‌گاه‌ها (با سیاست تکرار) ----
    _add_restraints(model, _section_list(data, "restraints"), node_ids)

    # ---- بارهای گرهی (تکرار مجاز؛ موتور جمع می‌کند) ----
    for idx, item in enumerate(_section_list(data, "nodal_loads"), start=1):
        _require_mapping(item, "nodal_loads", idx)
        node = _as_int(_get(item, "node", "nodal_loads", idx), "node", "nodal_loads", idx)
        if node not in node_ids:
            _fail("nodal_loads", idx, f"گره «{node}» در بخش گره‌ها تعریف نشده است")
        fx = _as_finite_number(_get(item, "fx", "nodal_loads", idx), "fx", "nodal_loads", idx)
        fy = _as_finite_number(_get(item, "fy", "nodal_loads", idx), "fy", "nodal_loads", idx)
        mz = _as_finite_number(_get(item, "mz", "nodal_loads", idx), "mz", "nodal_loads", idx)
        model.add_nodal_load(node, fx=fx, fy=fy, mz=mz)

    # ---- بارهای گسترده (تکرار مجاز؛ همیشه روی تمام طول عضو) ----
    for idx, item in enumerate(_section_list(data, "member_udls"), start=1):
        _require_mapping(item, "member_udls", idx)
        member = _as_int(_get(item, "member", "member_udls", idx), "member", "member_udls", idx)
        if member not in member_ids:
            _fail("member_udls", idx, f"عضو «{member}» در بخش اعضا تعریف نشده است")
        qy = _as_finite_number(_get(item, "qy", "member_udls", idx), "qy", "member_udls", idx)
        model.add_member_udl(member, qy)

    return model
