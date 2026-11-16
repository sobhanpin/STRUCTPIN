
"""تست‌های D1: ذخیره و بارگذاری پروژه."""

import json
import math
import tempfile
import unittest
from pathlib import Path

from structpin.model.structural_model import StructuralModel
from structpin.services.project_io import (
    SCHEMA_VERSION,
    ProjectFileError,
    dict_to_model,
    load_project,
    model_to_dict,
    save_project,
)


def _sample_model():
    m = StructuralModel("قاب نمونه")
    m.add_material("فولاد", 200.0)
    m.add_section("IPE", 0.01, 2e-4)
    m.add_node(1, 0.0, 0.0)
    m.add_node(2, 0.0, 3.0)
    m.add_node(3, 4.0, 3.0)
    m.add_member(1, 1, 2, "فولاد", "IPE")
    m.add_member(2, 2, 3, "فولاد", "IPE")
    m.add_restraint(1, ux=True, uy=True, rz=True)
    m.add_restraint(3, uy=True)
    m.add_nodal_load(2, fx=10.0, fy=-5.0, mz=0.0)
    m.add_member_udl(2, -3.0)
    return m


class RoundTripTest(unittest.TestCase):

    def test_round_trip_preserves_everything(self):
        original = _sample_model()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "frame.json"
            save_project(original, path)
            loaded = load_project(path)

        self.assertEqual(loaded.name, "قاب نمونه")
        self.assertEqual(model_to_dict(loaded), model_to_dict(original))

    def test_round_trip_entity_counts_and_values(self):
        original = _sample_model()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "frame.json"
            save_project(original, path)
            loaded = load_project(path)

        self.assertEqual(len(loaded.nodes), 3)
        self.assertEqual(len(loaded.members), 2)
        self.assertEqual(len(loaded.materials), 1)
        self.assertEqual(len(loaded.sections), 1)
        self.assertEqual(len(loaded.restraints), 2)
        self.assertEqual(len(loaded.nodal_loads), 1)
        self.assertEqual(len(loaded.member_udls), 1)
        self.assertEqual(loaded.nodes[2].x, 0.0)
        self.assertEqual(loaded.nodes[2].y, 3.0)
        self.assertEqual(loaded.members[2].node_i, 2)
        self.assertEqual(loaded.members[2].node_j, 3)
        self.assertEqual(loaded.materials["فولاد"].E, 200.0)
        self.assertEqual(loaded.sections["IPE"].I, 2e-4)
        self.assertTrue(loaded.restraints[0].rz)
        self.assertFalse(loaded.restraints[1].ux)
        self.assertEqual(loaded.nodal_loads[0].fx, 10.0)
        self.assertEqual(loaded.member_udls[0].qy, -3.0)

    def test_file_contains_schema_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "frame.json"
            save_project(_sample_model(), path)
            data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data["schema_version"], SCHEMA_VERSION)

    def test_utf8_persian_names_are_readable_in_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "frame.json"
            save_project(_sample_model(), path)
            text = path.read_text(encoding="utf-8")
        self.assertIn("قاب نمونه", text)
        self.assertIn("فولاد", text)

    def test_loaded_model_is_valid_for_analysis_checks(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "frame.json"
            save_project(_sample_model(), path)
            loaded = load_project(path)
        self.assertEqual(loaded.validate(), [])


class UnknownVersionTest(unittest.TestCase):

    def _data_with_version(self, version):
        d = model_to_dict(_sample_model())
        d["schema_version"] = version
        return d

    def test_unknown_version_rejected(self):
        with self.assertRaises(ProjectFileError) as ctx:
            dict_to_model(self._data_with_version(SCHEMA_VERSION + 1))
        self.assertIn("پشتیبانی نمی‌شود", str(ctx.exception))

    def test_version_zero_rejected(self):
        with self.assertRaises(ProjectFileError):
            dict_to_model(self._data_with_version(0))

    def test_version_as_string_rejected(self):
        with self.assertRaises(ProjectFileError):
            dict_to_model(self._data_with_version("1"))

    def test_version_as_bool_rejected(self):
        with self.assertRaises(ProjectFileError):
            dict_to_model(self._data_with_version(True))

    def test_missing_version_rejected(self):
        d = model_to_dict(_sample_model())
        del d["schema_version"]
        with self.assertRaises(ProjectFileError):
            dict_to_model(d)


class CorruptFileTest(unittest.TestCase):

    def test_invalid_json_raises_project_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.json"
            path.write_text("{ این JSON نیست", encoding="utf-8")
            with self.assertRaises(ProjectFileError) as ctx:
                load_project(path)
        self.assertIn("خراب", str(ctx.exception))

    def test_missing_file_raises_project_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ProjectFileError):
                load_project(Path(tmp) / "nope.json")

    def test_root_not_object_rejected(self):
        with self.assertRaises(ProjectFileError):
            dict_to_model([1, 2, 3])

    def test_missing_required_list_rejected(self):
        d = model_to_dict(_sample_model())
        del d["nodes"]
        with self.assertRaises(ProjectFileError):
            dict_to_model(d)

    def test_wrong_type_for_node_coordinate_rejected(self):
        d = model_to_dict(_sample_model())
        d["nodes"][0]["x"] = "صفر"
        with self.assertRaises(ProjectFileError):
            dict_to_model(d)

    def test_bool_for_numeric_field_rejected(self):
        d = model_to_dict(_sample_model())
        d["materials"][0]["E"] = True
        with self.assertRaises(ProjectFileError):
            dict_to_model(d)

    def test_duplicate_node_id_rejected_via_model(self):
        d = model_to_dict(_sample_model())
        d["nodes"].append({"id": 1, "x": 9.0, "y": 9.0})
        with self.assertRaises(ProjectFileError):
            dict_to_model(d)

    def test_missing_restraint_flag_rejected(self):
        d = model_to_dict(_sample_model())
        del d["restraints"][0]["rz"]
        with self.assertRaises(ProjectFileError):
            dict_to_model(d)


class NonFiniteLoadTest(unittest.TestCase):

    def test_nan_in_numeric_field_rejected_on_load(self):
        d = model_to_dict(_sample_model())
        d["nodes"][0]["x"] = float("nan")

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "nan.json"
            path.write_text(json.dumps(d), encoding="utf-8")
            with self.assertRaises(ProjectFileError):
                load_project(path)

    def test_infinity_in_numeric_field_rejected_on_load(self):
        d = model_to_dict(_sample_model())
        d["materials"][0]["E"] = float("inf")

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "inf.json"
            path.write_text(json.dumps(d), encoding="utf-8")
            with self.assertRaises(ProjectFileError):
                load_project(path)


class NonFiniteSaveTest(unittest.TestCase):

    def test_save_rejects_nan_and_writes_no_file(self):
        m = _sample_model()
        m.nodes[1] = m.nodes[1].__class__(1, float("nan"), 0.0)

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "out.json"
            with self.assertRaises(ProjectFileError):
                save_project(m, path)
            self.assertFalse(path.exists())

    def test_save_rejects_infinity(self):
        m = _sample_model()
        m.materials["فولاد"] = m.materials["فولاد"].__class__(
            "فولاد", math.inf
        )

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "out.json"
            with self.assertRaises(ProjectFileError):
                save_project(m, path)
            self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
