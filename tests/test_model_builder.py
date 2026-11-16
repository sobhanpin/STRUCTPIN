"""تست‌های D3-۱ (اصلاح‌شده): تبدیل داده‌های فرم به StructuralModel.

اجرا (ریشهٔ مخزن):
    PYTHONPATH=src python -m unittest discover -s tests -p "test_model_builder.py" -v

این فایل به tkinter وابسته نیست. در این گفتگو اجرا نشده است؛ نتیجه فقط از GitHub Actions معتبر است.
"""

import unittest
from decimal import Decimal
from fractions import Fraction

from structpin.model.structural_model import StructuralModel
from structpin.services.model_builder import ModelBuildError, build_model


def _valid_frame():
    return {
        "name": "قاب نمونه",
        "materials": [{"name": "فولاد", "E": 200.0}],
        "sections": [{"name": "IPE", "A": 0.01, "I": 2e-4}],
        "nodes": [
            {"id": 1, "x": 0.0, "y": 0.0},
            {"id": 2, "x": 0.0, "y": 3.0},
            {"id": 3, "x": 4.0, "y": 3.0},
        ],
        "members": [
            {"id": 1, "node_i": 1, "node_j": 2, "material": "فولاد", "section": "IPE"},
            {"id": 2, "node_i": 2, "node_j": 3, "material": "فولاد", "section": "IPE"},
        ],
        "restraints": [{"node": 1, "ux": True, "uy": True, "rz": True}],
        "nodal_loads": [{"node": 2, "fx": 10.0, "fy": -5.0, "mz": 0.0}],
        "member_udls": [{"member": 2, "qy": -3.0}],
    }


class ValidBuildTest(unittest.TestCase):
    def test_builds_structural_model_instance(self):
        self.assertIsInstance(build_model(_valid_frame()), StructuralModel)

    def test_project_name_is_kept(self):
        self.assertEqual(build_model(_valid_frame()).name, "قاب نمونه")

    def test_all_entities_are_created(self):
        model = build_model(_valid_frame())
        self.assertEqual(len(model.materials), 1)
        self.assertEqual(len(model.sections), 1)
        self.assertEqual(len(model.nodes), 3)
        self.assertEqual(len(model.members), 2)
        self.assertEqual(len(model.restraints), 1)
        self.assertEqual(len(model.nodal_loads), 1)
        self.assertEqual(len(model.member_udls), 1)

    def test_values_are_converted_to_float(self):
        model = build_model(_valid_frame())
        self.assertIsInstance(model.materials["فولاد"].E, float)
        self.assertEqual(model.nodes[3].x, 4.0)
        self.assertEqual(model.nodal_loads[0].fy, -5.0)

    def test_built_model_passes_structural_validation(self):
        self.assertEqual(build_model(_valid_frame()).validate(), [])

    def test_missing_optional_sections_are_allowed(self):
        data = {
            "materials": [{"name": "فولاد", "E": 200.0}],
            "sections": [{"name": "IPE", "A": 0.01, "I": 2e-4}],
            "nodes": [{"id": 1, "x": 0.0, "y": 0.0}, {"id": 2, "x": 1.0, "y": 0.0}],
            "members": [{"id": 1, "node_i": 1, "node_j": 2, "material": "فولاد", "section": "IPE"}],
        }
        model = build_model(data)
        self.assertEqual(len(model.restraints), 0)
        self.assertEqual(len(model.nodal_loads), 0)
        self.assertEqual(len(model.member_udls), 0)

    def test_default_name_when_absent(self):
        data = _valid_frame()
        del data["name"]
        self.assertEqual(build_model(data).name, "بدون نام")

    def test_blank_name_becomes_default(self):
        data = _valid_frame()
        data["name"] = "   "
        self.assertEqual(build_model(data).name, "بدون نام")

    def test_none_for_optional_list_is_empty(self):
        data = _valid_frame()
        data["restraints"] = None
        self.assertEqual(len(build_model(data).restraints), 0)

    def test_repeated_restraint_on_same_node_is_allowed(self):
        data = _valid_frame()
        data["restraints"].append({"node": 1, "ux": False, "uy": True, "rz": False})
        self.assertEqual(len(build_model(data).restraints), 2)

    def test_repeated_nodal_load_on_same_node_is_allowed(self):
        data = _valid_frame()
        data["nodal_loads"].append({"node": 2, "fx": 1.0, "fy": 0.0, "mz": 0.0})
        self.assertEqual(len(build_model(data).nodal_loads), 2)


class StringNumericInputTest(unittest.TestCase):
    """ورودی‌های عددی متنی معتبر باید پذیرفته و تبدیل شوند."""

    def test_string_node_id_converted_to_int(self):
        data = _valid_frame()
        data["nodes"][0]["id"] = "1"
        model = build_model(data)
        self.assertIn(1, model.nodes)
        self.assertIsInstance(list(model.nodes.keys())[0], int)

    def test_string_id_with_spaces_converted(self):
        """شناسهٔ " 1 " و ارجاع "1" باید به گره صحیح ۱ با نوع int تبدیل شوند."""
        data = _valid_frame()
        data["nodes"][0]["id"] = " 1 "
        data["members"][0]["node_i"] = "1"
        model = build_model(data)
        self.assertIn(1, model.nodes)
        self.assertIsInstance(model.nodes[1].id, int)
        self.assertEqual(model.nodes[1].id, 1)
        self.assertEqual(model.members[1].node_i, 1)
        self.assertEqual(model.restraints[0].node, 1)

    def test_string_coordinate_converted_to_float(self):
        data = _valid_frame()
        data["nodes"][0]["x"] = "0.0"
        model = build_model(data)
        self.assertEqual(model.nodes[1].x, 0.0)
        self.assertIsInstance(model.nodes[1].x, float)

    def test_string_negative_load_converted(self):
        data = _valid_frame()
        data["member_udls"][0]["qy"] = "-3.5"
        self.assertEqual(build_model(data).member_udls[0].qy, -3.5)

    def test_string_scientific_notation_converted(self):
        data = _valid_frame()
        data["materials"][0]["E"] = "2e5"
        self.assertEqual(build_model(data).materials["فولاد"].E, 2e5)

    def test_string_section_properties_converted(self):
        data = _valid_frame()
        data["sections"][0]["A"] = "0.01"
        data["sections"][0]["I"] = " 2e-4 "
        model = build_model(data)
        self.assertEqual(model.sections["IPE"].A, 0.01)
        self.assertEqual(model.sections["IPE"].I, 2e-4)

    def test_string_member_ids_converted(self):
        data = _valid_frame()
        data["members"][0]["id"] = "1"
        data["members"][0]["node_i"] = "1"
        data["members"][0]["node_j"] = "2"
        data["member_udls"][0]["member"] = "2"
        model = build_model(data)
        self.assertIn(1, model.members)
        self.assertEqual(model.member_udls[0].member, 2)

    def test_string_restraint_node_converted(self):
        data = _valid_frame()
        data["restraints"][0]["node"] = "1"
        self.assertEqual(build_model(data).restraints[0].node, 1)

    def test_string_nodal_load_values_converted(self):
        data = _valid_frame()
        data["nodal_loads"][0]["fx"] = "10"
        data["nodal_loads"][0]["fy"] = "-5.0"
        data["nodal_loads"][0]["mz"] = "0"
        ld = build_model(data).nodal_loads[0]
        self.assertEqual(ld.fx, 10.0)
        self.assertEqual(ld.fy, -5.0)
        self.assertEqual(ld.mz, 0.0)


class InputShapeErrorTest(unittest.TestCase):
    def test_root_not_dict_rejected(self):
        with self.assertRaises(ModelBuildError) as ctx:
            build_model([1, 2, 3])
        self.assertIn("دیکشنری", str(ctx.exception))

    def test_section_not_list_rejected(self):
        data = _valid_frame()
        data["nodes"] = "not a list"
        with self.assertRaises(ModelBuildError) as ctx:
            build_model(data)
        self.assertIn("گره‌ها", str(ctx.exception))
        self.assertIn("فهرست", str(ctx.exception))

    def test_row_not_dict_rejected_with_row_number(self):
        data = _valid_frame()
        data["nodes"][1] = [1, 2, 3]
        with self.assertRaises(ModelBuildError) as ctx:
            build_model(data)
        self.assertIn("ردیف 2", str(ctx.exception))

    def test_name_not_string_rejected(self):
        data = _valid_frame()
        data["name"] = 123
        with self.assertRaises(ModelBuildError) as ctx:
            build_model(data)
        self.assertIn("نام پروژه", str(ctx.exception))


class MissingFieldTest(unittest.TestCase):
    def test_missing_material_E(self):
        data = _valid_frame()
        del data["materials"][0]["E"]
        with self.assertRaises(ModelBuildError) as ctx:
            build_model(data)
        self.assertIn("ردیف 1", str(ctx.exception))
        self.assertIn("«E»", str(ctx.exception))

    def test_missing_node_x(self):
        data = _valid_frame()
        del data["nodes"][0]["x"]
        with self.assertRaises(ModelBuildError) as ctx:
            build_model(data)
        self.assertIn("«x»", str(ctx.exception))

    def test_missing_restraint_flag(self):
        data = _valid_frame()
        del data["restraints"][0]["rz"]
        with self.assertRaises(ModelBuildError) as ctx:
            build_model(data)
        self.assertIn("«rz»", str(ctx.exception))


class NumericValidationTest(unittest.TestCase):
    def test_non_numeric_text_rejected(self):
        data = _valid_frame()
        data["nodes"][0]["x"] = "صفر"
        with self.assertRaises(ModelBuildError) as ctx:
            build_model(data)
        self.assertIn("«x»", str(ctx.exception))
        self.assertIn("عدد", str(ctx.exception))

    def test_empty_string_number_rejected(self):
        data = _valid_frame()
        data["nodes"][0]["y"] = ""
        with self.assertRaises(ModelBuildError) as ctx:
            build_model(data)
        self.assertIn("خالی", str(ctx.exception))

    def test_whitespace_only_string_number_rejected(self):
        data = _valid_frame()
        data["nodes"][0]["y"] = "   "
        with self.assertRaises(ModelBuildError):
            build_model(data)

    def test_bool_as_number_rejected(self):
        data = _valid_frame()
        data["materials"][0]["E"] = True
        with self.assertRaises(ModelBuildError):
            build_model(data)

    def test_bool_as_coordinate_rejected(self):
        data = _valid_frame()
        data["nodes"][0]["x"] = False
        with self.assertRaises(ModelBuildError):
            build_model(data)

    def test_nan_float_rejected(self):
        data = _valid_frame()
        data["nodes"][0]["y"] = float("nan")
        with self.assertRaises(ModelBuildError) as ctx:
            build_model(data)
        self.assertIn("متناهی", str(ctx.exception))

    def test_nan_string_rejected(self):
        data = _valid_frame()
        data["nodes"][0]["y"] = "nan"
        with self.assertRaises(ModelBuildError) as ctx:
            build_model(data)
        self.assertIn("متناهی", str(ctx.exception))

    def test_positive_infinity_float_rejected(self):
        data = _valid_frame()
        data["nodal_loads"][0]["fy"] = float("inf")
        with self.assertRaises(ModelBuildError):
            build_model(data)

    def test_infinity_string_rejected(self):
        data = _valid_frame()
        data["nodal_loads"][0]["fy"] = "inf"
        with self.assertRaises(ModelBuildError) as ctx:
            build_model(data)
        self.assertIn("متناهی", str(ctx.exception))

    def test_negative_infinity_string_rejected(self):
        data = _valid_frame()
        data["member_udls"][0]["qy"] = "-Infinity"
        with self.assertRaises(ModelBuildError):
            build_model(data)

    def test_negative_infinity_float_rejected(self):
        data = _valid_frame()
        data["member_udls"][0]["qy"] = float("-inf")
        with self.assertRaises(ModelBuildError):
            build_model(data)

    def test_overflow_text_number_reports_row(self):
        """رشته‌ای که به بی‌نهایت یا سرریز می‌رسد باید با پیام فارسی و ردیف گزارش شود."""
        data = _valid_frame()
        data["materials"][0]["E"] = "1" + "0" * 400
        with self.assertRaises(ModelBuildError) as ctx:
            build_model(data)
        self.assertIn("مصالح، ردیف 1", str(ctx.exception))

    def test_zero_modulus_rejected(self):
        data = _valid_frame()
        data["materials"][0]["E"] = 0.0
        with self.assertRaises(ModelBuildError) as ctx:
            build_model(data)
        self.assertIn("مثبت", str(ctx.exception))

    def test_negative_area_rejected(self):
        data = _valid_frame()
        data["sections"][0]["A"] = -1.0
        with self.assertRaises(ModelBuildError) as ctx:
            build_model(data)
        self.assertIn("«A»", str(ctx.exception))

    def test_zero_inertia_rejected(self):
        data = _valid_frame()
        data["sections"][0]["I"] = 0.0
        with self.assertRaises(ModelBuildError):
            build_model(data)

    def test_zero_load_is_allowed(self):
        data = _valid_frame()
        data["nodal_loads"][0]["fy"] = 0.0
        self.assertEqual(build_model(data).nodal_loads[0].fy, 0.0)

    def test_negative_load_is_allowed(self):
        data = _valid_frame()
        data["member_udls"][0]["qy"] = -100.0
        self.assertEqual(build_model(data).member_udls[0].qy, -100.0)

    def test_decimal_rejected_with_persian_message(self):
        """Decimal پشتیبانی نمی‌شود و باید با پیام فارسی رد شود."""
        data = _valid_frame()
        data["nodes"][0]["x"] = Decimal("1.5")
        with self.assertRaises(ModelBuildError) as ctx:
            build_model(data)
        self.assertIn("«x»", str(ctx.exception))

    def test_fraction_rejected_with_persian_message(self):
        data = _valid_frame()
        data["nodes"][0]["x"] = Fraction(1, 2)
        with self.assertRaises(ModelBuildError):
            build_model(data)


class IntegerValidationTest(unittest.TestCase):
    def test_float_node_id_rejected(self):
        data = _valid_frame()
        data["nodes"][0]["id"] = 1.0
        with self.assertRaises(ModelBuildError) as ctx:
            build_model(data)
        self.assertIn("عدد صحیح", str(ctx.exception))

    def test_bool_node_id_rejected(self):
        data = _valid_frame()
        data["nodes"][0]["id"] = True
        with self.assertRaises(ModelBuildError):
            build_model(data)

    def test_decimal_like_string_id_rejected(self):
        data = _valid_frame()
        data["nodes"][0]["id"] = "1.5"
        with self.assertRaises(ModelBuildError) as ctx:
            build_model(data)
        self.assertIn("عدد صحیح", str(ctx.exception))

    def test_float_text_id_rejected(self):
        data = _valid_frame()
        data["nodes"][0]["id"] = "1.0"
        with self.assertRaises(ModelBuildError):
            build_model(data)

    def test_empty_string_id_rejected(self):
        data = _valid_frame()
        data["members"][0]["id"] = ""
        with self.assertRaises(ModelBuildError):
            build_model(data)

    def test_non_numeric_string_id_rejected(self):
        data = _valid_frame()
        data["members"][0]["node_i"] = "abc"
        with self.assertRaises(ModelBuildError) as ctx:
            build_model(data)
        self.assertIn("node_i", str(ctx.exception))

    def test_bool_member_reference_rejected(self):
        data = _valid_frame()
        data["member_udls"][0]["member"] = True
        with self.assertRaises(ModelBuildError):
            build_model(data)

    def test_integer_id_error_reports_row(self):
        data = _valid_frame()
        data["nodes"].append({"id": "x", "x": 0.0, "y": 0.0})
        with self.assertRaises(ModelBuildError) as ctx:
            build_model(data)
        self.assertIn("گره‌ها، ردیف 4", str(ctx.exception))


class BooleanValidationTest(unittest.TestCase):
    def test_integer_flag_rejected(self):
        data = _valid_frame()
        data["restraints"][0]["ux"] = 1
        with self.assertRaises(ModelBuildError) as ctx:
            build_model(data)
        self.assertIn("بله/خیر", str(ctx.exception))

    def test_string_flag_rejected(self):
        data = _valid_frame()
        data["restraints"][0]["uy"] = "true"
        with self.assertRaises(ModelBuildError):
            build_model(data)


class TextValidationTest(unittest.TestCase):
    def test_empty_material_name_rejected(self):
        data = _valid_frame()
        data["materials"][0]["name"] = "   "
        with self.assertRaises(ModelBuildError) as ctx:
            build_model(data)
        self.assertIn("خالی", str(ctx.exception))

    def test_non_string_section_name_rejected(self):
        data = _valid_frame()
        data["sections"][0]["name"] = 7
        with self.assertRaises(ModelBuildError):
            build_model(data)

    def test_member_material_name_is_stripped_for_lookup(self):
        data = _valid_frame()
        data["members"][0]["material"] = "  فولاد  "
        self.assertIn(1, build_model(data).members)


class DuplicateIdTest(unittest.TestCase):
    def test_duplicate_material(self):
        data = _valid_frame()
        data["materials"].append({"name": "فولاد", "E": 210.0})
        with self.assertRaises(ModelBuildError) as ctx:
            build_model(data)
        self.assertIn("ردیف 2", str(ctx.exception))
        self.assertIn("تکراری", str(ctx.exception))

    def test_duplicate_section(self):
        data = _valid_frame()
        data["sections"].append({"name": "IPE", "A": 0.02, "I": 3e-4})
        with self.assertRaises(ModelBuildError) as ctx:
            build_model(data)
        self.assertIn("مقاطع", str(ctx.exception))

    def test_duplicate_node(self):
        data = _valid_frame()
        data["nodes"].append({"id": 1, "x": 9.0, "y": 9.0})
        with self.assertRaises(ModelBuildError) as ctx:
            build_model(data)
        self.assertIn("ردیف 4", str(ctx.exception))

    def test_duplicate_member(self):
        data = _valid_frame()
        data["members"].append({"id": 1, "node_i": 1, "node_j": 3, "material": "فولاد", "section": "IPE"})
        with self.assertRaises(ModelBuildError):
            build_model(data)

    def test_duplicate_node_id_as_string_detected(self):
        """شناسهٔ "1" و 1 باید تکراری تشخیص داده شوند."""
        data = _valid_frame()
        data["nodes"].append({"id": "1", "x": 9.0, "y": 9.0})
        with self.assertRaises(ModelBuildError):
            build_model(data)


class ReferenceErrorTest(unittest.TestCase):
    def test_member_references_missing_node_i(self):
        data = _valid_frame()
        data["members"][0]["node_i"] = 99
        with self.assertRaises(ModelBuildError) as ctx:
            build_model(data)
        self.assertIn("ابتدا", str(ctx.exception))
        self.assertIn("99", str(ctx.exception))

    def test_member_references_missing_node_j(self):
        data = _valid_frame()
        data["members"][0]["node_j"] = 42
        with self.assertRaises(ModelBuildError) as ctx:
            build_model(data)
        self.assertIn("انتهای", str(ctx.exception))

    def test_member_references_unknown_material(self):
        data = _valid_frame()
        data["members"][0]["material"] = "بتن"
        with self.assertRaises(ModelBuildError) as ctx:
            build_model(data)
        self.assertIn("بتن", str(ctx.exception))
        self.assertIn("تعریف نشده", str(ctx.exception))

    def test_member_references_unknown_section(self):
        data = _valid_frame()
        data["members"][1]["section"] = "UNKNOWN"
        with self.assertRaises(ModelBuildError):
            build_model(data)

    def test_restraint_references_missing_node(self):
        data = _valid_frame()
        data["restraints"][0]["node"] = 77
        with self.assertRaises(ModelBuildError) as ctx:
            build_model(data)
        self.assertIn("77", str(ctx.exception))

    def test_nodal_load_references_missing_node(self):
        data = _valid_frame()
        data["nodal_loads"][0]["node"] = 55
        with self.assertRaises(ModelBuildError):
            build_model(data)

    def test_member_udl_references_missing_member(self):
        data = _valid_frame()
        data["member_udls"][0]["member"] = 8
        with self.assertRaises(ModelBuildError) as ctx:
            build_model(data)
        self.assertIn("عضو «8»", str(ctx.exception))

    def test_string_reference_matches_integer_node(self):
        data = _valid_frame()
        data["members"][0]["node_i"] = "1"
        self.assertIn(1, build_model(data).members)


class ErrorMessageLocationTest(unittest.TestCase):
    def test_row_number_is_one_based(self):
        data = _valid_frame()
        data["nodes"].append({"id": 4, "x": "x", "y": 0.0})
        with self.assertRaises(ModelBuildError) as ctx:
            build_model(data)
        self.assertIn("گره‌ها، ردیف 4", str(ctx.exception))

    def test_error_is_value_error_subclass(self):
        self.assertTrue(issubclass(ModelBuildError, ValueError))


if __name__ == "__main__":
    unittest.main()
