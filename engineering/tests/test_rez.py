"""Tests for the .rez parser (rezeng.rez / rezeng.units / rezeng.eng).

Run from the repository root:  python3 -m unittest discover -s engineering/tests -v
Only the standard library is used.
"""

import copy
import glob
import json
import os
import tempfile
import unittest

import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                ".."))

from rezeng import (load_rez, save_rez, check_overridable, param_unit,
                    to_si, from_si, UnitError, load_eng, save_eng,
                    new_eng, eng_path)

REPO = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", ".."))
EXAMPLES = sorted(glob.glob(os.path.join(REPO, "bin", "examples", "*.rez")))
USER_CAVITY = os.path.join(os.path.expanduser("~"), "workspace", "user",
                           "files", "upload.rez")


class TestUnits(unittest.TestCase):
    def test_length(self):
        self.assertAlmostEqual(to_si(500, "mm"), 0.5)
        self.assertAlmostEqual(to_si(1, "cm"), 0.01)
        self.assertAlmostEqual(to_si(2, "m"), 2.0)
        self.assertAlmostEqual(to_si(1064, "nm"), 1064e-9)
        self.assertAlmostEqual(to_si(200, "mkm"), 200e-6)
        self.assertAlmostEqual(to_si(200, "µm"), 200e-6)
        self.assertAlmostEqual(from_si(0.5, "mm"), 500.0)
        self.assertAlmostEqual(from_si(200e-6, "mkm"), 200.0)

    def test_angle(self):
        self.assertAlmostEqual(to_si(180, "deg"), 3.141592653589793)
        self.assertAlmostEqual(to_si(1, "rad"), 1.0)
        self.assertAlmostEqual(to_si(5, "mrad"), 0.005)
        self.assertAlmostEqual(from_si(3.141592653589793, "deg"), 180.0)

    def test_dimensionless(self):
        self.assertAlmostEqual(to_si(2.16, "none"), 2.16)
        self.assertAlmostEqual(to_si(1e5, "inv_m2"), 1e5)

    def test_unknown_unit(self):
        with self.assertRaises(UnitError):
            to_si(1, "furlong")
        with self.assertRaises(UnitError):
            from_si(1, "furlong")


class TestRoundTrip(unittest.TestCase):
    def test_all_examples_round_trip(self):
        """Every example .rez survives load+save with identical content
        (ignoring JSON whitespace)."""
        self.assertTrue(EXAMPLES, "no example files found")
        for path in EXAMPLES:
            with self.subTest(path=os.path.basename(path)):
                original = load_rez(path)
                with tempfile.NamedTemporaryFile(
                        "w", suffix=".rez", delete=False) as tmp:
                    tmp_path = tmp.name
                try:
                    save_rez(tmp_path, original)
                    reloaded = load_rez(tmp_path)
                    self.assertEqual(reloaded, original)
                finally:
                    os.unlink(tmp_path)

    def test_user_cavity_round_trip(self):
        original = load_rez(USER_CAVITY)
        self.assertEqual(original["trip_type"], "SW")
        with tempfile.NamedTemporaryFile("w", suffix=".rez",
                                         delete=False) as tmp:
            tmp_path = tmp.name
        try:
            save_rez(tmp_path, original)
            self.assertEqual(load_rez(tmp_path), original)
        finally:
            os.unlink(tmp_path)

    def test_schema_version_preserved(self):
        for path in EXAMPLES:
            data = load_rez(path)
            self.assertIn("schema_version", data)
            version = data["schema_version"]
            with tempfile.NamedTemporaryFile("w", suffix=".rez",
                                             delete=False) as tmp:
                tmp_path = tmp.name
            try:
                save_rez(tmp_path, data)
                self.assertEqual(load_rez(tmp_path)["schema_version"], version)
            finally:
                os.unlink(tmp_path)

    def test_unknown_keys_preserved(self):
        data = load_rez(EXAMPLES[0])
        data["engineering_ext"] = {"note": "future data"}
        data["elements"][0]["unknown_field"] = [1, 2, 3]
        data["totally_new_top_key"] = {"a": 1}
        with tempfile.NamedTemporaryFile("w", suffix=".rez",
                                         delete=False) as tmp:
            tmp_path = tmp.name
        try:
            save_rez(tmp_path, data)
            reloaded = load_rez(tmp_path)
            self.assertEqual(reloaded["engineering_ext"], {"note": "future data"})
            self.assertEqual(reloaded["elements"][0]["unknown_field"], [1, 2, 3])
            self.assertEqual(reloaded["totally_new_top_key"], {"a": 1})
        finally:
            os.unlink(tmp_path)

    def test_param_units_preserved(self):
        # The user cavity mixes mm lengths; one example uses cm for L.
        data = load_rez(USER_CAVITY)
        self.assertEqual(param_unit(data, "M2", "R"), "mm")
        self.assertEqual(param_unit(data, "M2", "Alpha"), "deg")
        self.assertEqual(param_unit(data, "TL1", "n"), "none")
        cm_files = [p for p in EXAMPLES
                    if any(e.get("params", {}).get("L", {}).get("unit") == "cm"
                           for e in load_rez(p).get("elements", []))]
        self.assertTrue(cm_files, "expected at least one example with cm")
        for path in cm_files:
            d = load_rez(path)
            with tempfile.NamedTemporaryFile("w", suffix=".rez",
                                             delete=False) as tmp:
                tmp_path = tmp.name
            try:
                save_rez(tmp_path, d)
                self.assertEqual(load_rez(tmp_path), d)
            finally:
                os.unlink(tmp_path)


class TestCheckOverridable(unittest.TestCase):
    def test_free_param(self):
        data = load_rez(USER_CAVITY)
        self.assertIsNone(check_overridable(data, "M2", "R"))
        self.assertIsNone(check_overridable(data, "d1", "L"))

    def test_unknown(self):
        data = load_rez(USER_CAVITY)
        self.assertIsNotNone(check_overridable(data, "Nope", "R"))
        self.assertIsNotNone(check_overridable(data, "M2", "Nope"))

    def test_link_conflict(self):
        # global_params.rez links L0 -> elements 0 and 4 (L), F0 -> 1, 3 (F).
        path = os.path.join(REPO, "bin", "examples", "global_params.rez")
        data = load_rez(path)
        labels = [e["label"] for e in data["elements"]]
        self.assertIsNotNone(check_overridable(data, labels[0], "L"))
        self.assertIsNotNone(check_overridable(data, labels[4], "L"))
        # Parameters that are not linked stay free (n on d1, Alpha on F1).
        self.assertIsNone(check_overridable(data, labels[0], "n"))
        self.assertIsNone(check_overridable(data, labels[1], "Alpha"))

    def test_formula_drives_global_only(self):
        # spherical_symm_ex.rez has a formula driving global R0, which is
        # linked to M1/M3 R: the element params are caught by the link check.
        path = os.path.join(REPO, "bin", "examples", "spherical_symm_ex.rez")
        data = load_rez(path)
        self.assertTrue(data.get("formulas"))
        labels = [e["label"] for e in data["elements"]]
        self.assertIsNotNone(check_overridable(data, labels[0], "R"))
        self.assertIsNotNone(check_overridable(data, labels[2], "R"))


class TestEngSideCar(unittest.TestCase):
    def test_path(self):
        self.assertEqual(eng_path("/a/b/cavity.rez"),
                         "/a/b/cavity.rez.eng.json")

    def test_round_trip_and_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "x.rez.eng.json")
            self.assertEqual(load_eng(path), {})
            doc = new_eng()
            doc["lidt"] = {"M2": 500.0}
            save_eng(path, doc)
            self.assertEqual(load_eng(path), doc)

    def test_invalid(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json",
                                         delete=False) as tmp:
            tmp.write("[1, 2]")
            tmp_path = tmp.name
        try:
            with self.assertRaises(ValueError):
                load_eng(tmp_path)
        finally:
            os.unlink(tmp_path)


if __name__ == "__main__":
    unittest.main()
