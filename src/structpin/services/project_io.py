
"""ذخیره و بارگذاری پروژهٔ STRUCTPIN به‌صورت JSON."""

import json
import math
from pathlib import Path

from structpin.model.structural_model import ModelError, StructuralModel

SCHEMA_VERSION = 1


class ProjectFileError(Exception):
    """خطای فایل پروژه."""


def model_to_dict(model):
    """تبدیل مدل به دیکشنری JSON."""
    return {
        "schema_version": SCHEMA_VERSION,
        "name": model.name,
        "materials": [
            {"name": m.name, "E": m.E} for m in model.materials.values()
        ],
        "sections": [
            {"name": s.name, "A": s.A, "I": s.I}
            for s in model.sections.values()
        ],
        "nodes": [
            {"id": n.id, "x": n.x, "y": n.y}
            for n in model.nodes.values()
        ],
        "members": [
            {
                "id": m.id,
                "node_i": m.node_i,
                "node_j": m.node_j,
                "material": m.material,
                "section": m.section,
            }
            for m in model.members.values()
        ],
        "restraints": [
            {"node": r.node, "ux": r.ux, "uy": r.uy, "rz": r.rz}
            for r in model.restraints
        ],
        "nodal_loads": [
            {"node": ld.node, "fx": ld.fx, "fy": ld.fy, "mz": ld.mz}
            for ld in model.nodal_loads
        ],
        "member_udls": [
            {"member": u.member, "qy": u.qy}
            for u in model.member_udls
        ],
    }


def _require(obj, key, expected_types, where):
    if not isinstance(obj, dict):
        raise ProjectFileError(f"{where}: باید یک شیء JSON باشد")

    if key not in obj:
        raise ProjectFileError(
            f"{where}: کلید ضروری {key!r} وجود ندارد"
        )

    value = obj[key]

    if isinstance(value, bool) and bool not in expected_types:
        raise ProjectFileError(
            f"{where}.{key}: نوع bool پذیرفته نیست"
        )

    if not isinstance(value, expected_types):
        raise ProjectFileError(
            f"{where}.{key}: نوع نادرست؛ مقدار {value!r}"
        )

    return value


def _require_list(obj, key, where):
    return _require(obj, key, (list,), where)


def _require_number(obj, key, where):
    value = _require(obj, key, (int, float), where)

    try:
        as_float = float(value)
    except (OverflowError, ValueError) as exc:
        raise ProjectFileError(
            f"{where}.{key}: عدد قابل تبدیل نیست"
        ) from exc

    if not math.isfinite(as_float):
        raise ProjectFileError(
            f"{where}.{key}: مقدار عددی غیرمتناهی پذیرفته نیست"
        )

    return value


def dict_to_model(data):
    """ساخت مدل از داده JSON."""
    if not isinstance(data, dict):
        raise ProjectFileError(
            "ریشهٔ فایل باید یک شیء JSON باشد"
        )

    if "schema_version" not in data:
        raise ProjectFileError(
            "کلید schema_version در فایل وجود ندارد"
        )

    version = data["schema_version"]

    if isinstance(version, bool) or not isinstance(version, int):
        raise ProjectFileError(
            "schema_version باید عدد صحیح باشد"
        )

    if version != SCHEMA_VERSION:
        raise ProjectFileError(
            f"نسخهٔ فایل {version} پشتیبانی نمی‌شود؛ "
            f"نسخهٔ پشتیبانی‌شده {SCHEMA_VERSION}"
        )

    name = _require(data, "name", (str,), "root")
    model = StructuralModel(name)

    try:
        for i, item in enumerate(
            _require_list(data, "materials", "root")
        ):
            where = f"materials[{i}]"
            model.add_material(
                _require(item, "name", (str,), where),
                _require_number(item, "E", where),
            )

        for i, item in enumerate(
            _require_list(data, "sections", "root")
        ):
            where = f"sections[{i}]"
            model.add_section(
                _require(item, "name", (str,), where),
                _require_number(item, "A", where),
                _require_number(item, "I", where),
            )

        for i, item in enumerate(
            _require_list(data, "nodes", "root")
        ):
            where = f"nodes[{i}]"
            model.add_node(
                _require(item, "id", (int,), where),
                _require_number(item, "x", where),
                _require_number(item, "y", where),
            )

        for i, item in enumerate(
            _require_list(data, "members", "root")
        ):
            where = f"members[{i}]"
            model.add_member(
                _require(item, "id", (int,), where),
                _require(item, "node_i", (int,), where),
                _require(item, "node_j", (int,), where),
                _require(item, "material", (str,), where),
                _require(item, "section", (str,), where),
            )

        for i, item in enumerate(
            _require_list(data, "restraints", "root")
        ):
            where = f"restraints[{i}]"
            model.add_restraint(
                _require(item, "node", (int,), where),
                ux=_require(item, "ux", (bool,), where),
                uy=_require(item, "uy", (bool,), where),
                rz=_require(item, "rz", (bool,), where),
            )

        for i, item in enumerate(
            _require_list(data, "nodal_loads", "root")
        ):
            where = f"nodal_loads[{i}]"
            model.add_nodal_load(
                _require(item, "node", (int,), where),
                fx=_require_number(item, "fx", where),
                fy=_require_number(item, "fy", where),
                mz=_require_number(item, "mz", where),
            )

        for i, item in enumerate(
            _require_list(data, "member_udls", "root")
        ):
            where = f"member_udls[{i}]"
            model.add_member_udl(
                _require(item, "member", (int,), where),
                _require_number(item, "qy", where),
            )

    except ModelError as exc:
        raise ProjectFileError(
            f"داده‌های پروژه نامعتبر: {exc}"
        ) from exc

    return model


def save_project(model, path):
    """ذخیره پروژه با UTF-8."""
    path = Path(path)
    payload = model_to_dict(model)

    try:
        text = json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        )
    except (ValueError, OverflowError) as exc:
        raise ProjectFileError(
            f"مدل شامل مقدار عددی نامعتبر است: {exc}"
        ) from exc

    try:
        path.write_text(text, encoding="utf-8")
    except OSError as exc:
        raise ProjectFileError(
            f"ذخیرهٔ فایل ناموفق بود: {exc}"
        ) from exc


def load_project(path):
    """بارگذاری پروژه از فایل JSON."""
    path = Path(path)

    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ProjectFileError(
            f"فایل پروژه پیدا نشد: {path}"
        ) from exc
    except (OSError, UnicodeDecodeError) as exc:
        raise ProjectFileError(
            f"خواندن فایل پروژه ناموفق بود: {exc}"
        ) from exc

    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError) as exc:
        raise ProjectFileError(
            f"فایل JSON خراب است: {exc}"
        ) from exc

    return dict_to_model(data)
