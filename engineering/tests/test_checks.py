"""Tests for the engineering checks (rezeng.checks / rezeng.eng).

Run from the repository root:  python3 -m unittest discover -s engineering/tests -v
Pure-formula tests need no CLI; the integration test at the end uses the
locally built binary (rezonator2/bin/rezonator) on the user cavity with
the SAMPLE side-car in tests/data/ (values invented for demonstration).
"""

import json
import math
import os
import tempfile
import unittest
from unittest import mock

import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                ".."))

from rezeng.checks import (
    aperture_loss_fraction, check_aperture, check_board, check_lidt,
    classify_lidt, combined_loss, grid_offset, lidt_fluence_J_per_cm2,
    mount_rect, rect_overlap_area, rect_overhang, rects_overlap,
    run_checks)
from rezeng.eng import validate_eng

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
EXAMPLE_ENG = os.path.join(TESTS_DIR, "data", "example.eng.json")
USER_CAVITY = os.path.join(os.path.expanduser("~"), "workspace", "user",
                           "files", "upload.rez")


class TestLidtFormula(unittest.TestCase):
    def test_hand_checkable_value(self):
        # Task's worked example: w = 0.2 mm = 0.02 cm, E = 1 mJ.
        # F = 2e-3 / (pi * 0.02^2) = 1.5915... J/cm^2.
        f = lidt_fluence_J_per_cm2(1e-3, 0.2, 0.2)
        self.assertAlmostEqual(f, 2e-3 / (math.pi * 0.02 ** 2), places=12)
        self.assertAlmostEqual(f, 1.5915494309189535, places=9)

    def test_elliptical(self):
        # w_T = 0.1 mm, w_S = 0.2 mm: F = 2e-3 / (pi * 0.01 * 0.02).
        f = lidt_fluence_J_per_cm2(1e-3, 0.1, 0.2)
        self.assertAlmostEqual(f, 2e-3 / (math.pi * 0.01 * 0.02), places=9)

    def test_invalid_inputs(self):
        with self.assertRaises(ValueError):
            lidt_fluence_J_per_cm2(1e-3, 0.0, 0.2)
        with self.assertRaises(ValueError):
            lidt_fluence_J_per_cm2(1e-3, 0.2, -0.1)
        with self.assertRaises(ValueError):
            lidt_fluence_J_per_cm2(-1e-3, 0.2, 0.2)


class TestLidtClassify(unittest.TestCase):
    def test_boundaries(self):
        self.assertEqual(classify_lidt(0.5), "ok")
        self.assertEqual(classify_lidt(0.8), "ok")      # > 0.8 warns
        self.assertEqual(classify_lidt(0.8001), "warn")
        self.assertEqual(classify_lidt(1.0), "warn")    # > 1.0 fails
        self.assertEqual(classify_lidt(1.0001), "fail")
        self.assertEqual(classify_lidt(2.0), "fail")


class TestApertureFormula(unittest.TestCase):
    def test_aperture_equals_waist(self):
        # a = w -> exp(-2) = 13.53%.
        self.assertAlmostEqual(aperture_loss_fraction(2.0, 1.0),
                               math.exp(-2.0), places=12)

    def test_blocked(self):
        # a = 0 -> everything clipped.
        self.assertAlmostEqual(aperture_loss_fraction(0.0, 1.0), 1.0)

    def test_large_aperture(self):
        # a = 1 mm, w = 0.2 mm -> exp(-50), essentially zero.
        self.assertLess(aperture_loss_fraction(2.0, 0.2), 1e-20)

    def test_invalid(self):
        with self.assertRaises(ValueError):
            aperture_loss_fraction(1.0, 0.0)
        with self.assertRaises(ValueError):
            aperture_loss_fraction(-1.0, 1.0)

    def test_combined_loss(self):
        self.assertAlmostEqual(combined_loss([]), 0.0)
        self.assertAlmostEqual(combined_loss([0.1]), 0.1)
        # 1 - (0.9 * 0.8) = 0.28.
        self.assertAlmostEqual(combined_loss([0.1, 0.2]), 0.28, places=12)


class TestBoardGeometry(unittest.TestCase):
    def test_overlap(self):
        a = (0.0, 0.0, 10.0, 10.0)
        self.assertTrue(rects_overlap(a, (5.0, 5.0, 15.0, 15.0)))
        self.assertAlmostEqual(rect_overlap_area(a, (5.0, 5.0, 15.0, 15.0)),
                               25.0)
        # Contained rectangle overlaps fully.
        self.assertTrue(rects_overlap(a, (2.0, 2.0, 4.0, 4.0)))
        self.assertAlmostEqual(rect_overlap_area(a, (2.0, 2.0, 4.0, 4.0)),
                               4.0)

    def test_no_overlap_and_edge_touch(self):
        a = (0.0, 0.0, 10.0, 10.0)
        self.assertFalse(rects_overlap(a, (20.0, 0.0, 30.0, 10.0)))
        self.assertEqual(rect_overlap_area(a, (20.0, 0.0, 30.0, 10.0)), 0.0)
        # Sharing an edge is zero-area contact, not a collision.
        self.assertFalse(rects_overlap(a, (10.0, 0.0, 20.0, 10.0)))
        self.assertEqual(rect_overlap_area(a, (10.0, 0.0, 20.0, 10.0)), 0.0)

    def test_overhang(self):
        self.assertEqual(rect_overhang((10.0, 10.0, 20.0, 20.0), (100, 100)),
                         0.0)
        # Exactly on the board edge is inside.
        self.assertEqual(rect_overhang((0.0, 0.0, 100.0, 100.0), (100, 100)),
                         0.0)
        self.assertAlmostEqual(
            rect_overhang((90.0, 10.0, 115.0, 20.0), (100, 100)), 15.0)
        self.assertAlmostEqual(
            rect_overhang((-5.0, -3.0, 10.0, 10.0), (100, 100)), 5.0)

    def test_grid_offset(self):
        self.assertAlmostEqual(grid_offset(100.0, 25.0), 0.0)
        self.assertAlmostEqual(grid_offset(137.0, 25.0), 12.0)
        self.assertAlmostEqual(grid_offset(12.5, 25.0), 12.5)

    def test_mount_rect(self):
        rect = mount_rect({"footprint_mm": [50, 40],
                           "board_x_mm": 100, "board_y_mm": 100})
        self.assertEqual(rect, (75.0, 80.0, 125.0, 120.0))
        self.assertIsNone(mount_rect({"footprint_mm": [50, 40]}))
        self.assertIsNone(mount_rect({"footprint_mm": [50],
                                      "board_x_mm": 1, "board_y_mm": 1}))
        self.assertIsNone(mount_rect(None))


def _fake_cli_result(beam):
    return {"version": 1, "trip_type": "SW", "warnings": [],
            "results": [{"id": 0, "ok": True, "g_T": 0.0, "g_S": 0.0,
                         "stable": True, "total_length_mm": 100.0,
                         "beam": beam, "waist": None}]}


def _beam(label, w_T, w_S):
    return {"label": label, "w_T_mm": w_T, "w_S_mm": w_S,
            "R_T_mm": None, "R_S_mm": None}


class TestCheckBuilders(unittest.TestCase):
    def test_lidt_statuses_and_nodata(self):
        eng = {"laser": {"pulse_energy_J": 1e-3},
               "elements": {
                   "M1": {"lidt_J_per_cm2": 1.0},   # F=1.59 -> fail
                   "M2": {"lidt_J_per_cm2": 2.0},   # ratio 0.80 -> ok
                   "M3": {"lidt_J_per_cm2": 1.8},   # ratio 0.88 -> warn
                   "M4": {},                        # no LIDT -> nodata
               }}
        beam = {b["label"]: b for b in [_beam("M1", 0.2, 0.2),
                                        _beam("M2", 0.2, 0.2),
                                        _beam("M3", 0.2, 0.2)]}
        out = {c["element"]: c for c in
               check_lidt(["M1", "M2", "M3", "M4", "M5"], beam, eng)}
        self.assertEqual(out["M1"]["status"], "fail")
        self.assertAlmostEqual(out["M1"]["value"], 1.5915494309189535,
                               places=9)
        self.assertEqual(out["M2"]["status"], "ok")
        self.assertEqual(out["M3"]["status"], "warn")
        self.assertEqual(out["M4"]["status"], "nodata")
        # M5 has no beam entry (and no data) -> nodata, not a crash.
        self.assertEqual(out["M5"]["status"], "nodata")

    def test_lidt_no_energy_is_nodata(self):
        eng = {"laser": {}, "elements": {"M1": {"lidt_J_per_cm2": 1.0}}}
        out = check_lidt(["M1"], {"M1": _beam("M1", 0.2, 0.2)}, eng)
        self.assertEqual(out[0]["status"], "nodata")
        self.assertIn("pulse_energy_J", out[0]["message"])

    def test_aperture_statuses_and_total(self):
        eng = {"elements": {
            "M1": {"aperture_diameter_mm": 2.0},  # a=w=1 -> 13.5% warn
            "M2": {"aperture_diameter_mm": 10.0},  # ~0 -> ok
            "M3": {},                              # nodata
        }}
        beam = {b["label"]: b for b in [_beam("M1", 1.0, 1.0),
                                        _beam("M2", 1.0, 1.0)]}
        out = check_aperture(["M1", "M2", "M3"], beam, eng)
        by_id = {c["id"]: c for c in out}
        self.assertEqual(by_id["aperture:M1"]["status"], "warn")
        self.assertAlmostEqual(by_id["aperture:M1"]["value"],
                               math.exp(-2.0), places=12)
        self.assertEqual(by_id["aperture:M2"]["status"], "ok")
        self.assertEqual(by_id["aperture:M3"]["status"], "nodata")
        total = by_id["aperture_total"]
        self.assertEqual(total["status"], "warn")  # 13.5% > 2%
        self.assertAlmostEqual(total["value"], math.exp(-2.0), places=12)

    def test_aperture_total_nodata_without_data(self):
        out = check_aperture(["M1"], {}, {"elements": {}})
        total = [c for c in out if c["id"] == "aperture_total"][0]
        self.assertEqual(total["status"], "nodata")

    def test_aperture_uses_max_radius(self):
        # Elliptical beam: w = max(0.2, 0.5) = 0.5, a = 0.5 -> exp(-2).
        eng = {"elements": {"M1": {"aperture_diameter_mm": 1.0}}}
        beam = {"M1": _beam("M1", 0.2, 0.5)}
        out = check_aperture(["M1"], beam, eng)
        self.assertAlmostEqual(out[0]["value"], math.exp(-2.0), places=12)

    def test_board_overlap_and_bounds(self):
        eng = {"board": {"board_mm": [600, 600], "hole_pitch_mm": 25},
               "elements": {
                   "M1": {"mount": {"footprint_mm": [50, 50],
                                    "board_x_mm": 100, "board_y_mm": 100}},
                   "M2": {"mount": {"footprint_mm": [50, 50],
                                    "board_x_mm": 200, "board_y_mm": 100}},
                   # Overlaps M2 (y 112-162 vs 75-125) and off-grid in y.
                   "M3": {"mount": {"footprint_mm": [50, 50],
                                    "board_x_mm": 200, "board_y_mm": 137}},
                   # Sticks out 15 mm past the board edge, off-grid in x.
                   "M4": {"mount": {"footprint_mm": [50, 50],
                                    "board_x_mm": 590, "board_y_mm": 300}},
                   "M5": {},
               }}
        out = check_board(["M1", "M2", "M3", "M4", "M5"], eng)
        by_id = {c["id"]: c for c in out}
        self.assertEqual(by_id["board_bounds:M1"]["status"], "ok")
        self.assertEqual(by_id["board_bounds:M4"]["status"], "fail")
        self.assertAlmostEqual(by_id["board_bounds:M4"]["value"], 15.0)
        self.assertEqual(by_id["board_grid:M1"]["status"], "ok")
        self.assertEqual(by_id["board_grid:M3"]["status"], "warn")
        self.assertAlmostEqual(by_id["board_grid:M3"]["value"], 12.0)
        self.assertEqual(by_id["board_grid:M4"]["status"], "warn")
        self.assertEqual(by_id["board_overlap:M2/M3"]["status"], "fail")
        self.assertAlmostEqual(by_id["board_overlap:M2/M3"]["value"], 650.0)
        self.assertEqual(by_id["board_overlap:M1/M2"]["status"], "ok")
        self.assertEqual(by_id["board_bounds:M5"]["status"], "nodata")
        self.assertEqual(by_id["board_grid:M5"]["status"], "nodata")

    def test_board_without_board_size_or_pitch(self):
        eng = {"board": {},
               "elements": {"M1": {"mount": {"footprint_mm": [50, 50],
                                             "board_x_mm": 100,
                                             "board_y_mm": 100}},
                            "M2": {"mount": {"footprint_mm": [50, 50],
                                             "board_x_mm": 200,
                                             "board_y_mm": 100}}}}
        out = check_board(["M1", "M2"], eng)
        by_id = {c["id"]: c for c in out}
        self.assertEqual(by_id["board_bounds:M1"]["status"], "nodata")
        self.assertEqual(by_id["board_grid:M1"]["status"], "nodata")
        # Overlap needs no board size: still computed.
        self.assertEqual(by_id["board_overlap:M1/M2"]["status"], "ok")


class TestValidateEng(unittest.TestCase):
    def test_valid_and_empty(self):
        self.assertEqual(validate_eng({}), [])
        self.assertEqual(validate_eng(json.load(open(EXAMPLE_ENG))), [])

    def test_problems(self):
        problems = validate_eng({
            "format_version": 99,
            "laser": {"pulse_energy_J": -1},
            "board": {"board_mm": [600], "hole_pitch_mm": 0},
            "elements": {"M1": {"lidt_J_per_cm2": "high",
                                "mount": {"footprint_mm": [50, -1]}}},
            "surprise": True,
        })
        self.assertTrue(any("format_version" in p for p in problems))
        self.assertTrue(any("pulse_energy_J" in p for p in problems))
        self.assertTrue(any("board_mm" in p for p in problems))
        self.assertTrue(any("hole_pitch_mm" in p for p in problems))
        self.assertTrue(any("lidt_J_per_cm2" in p for p in problems))
        self.assertTrue(any("footprint_mm" in p for p in problems))
        self.assertTrue(any("surprise" in p for p in problems))


class TestRunChecksSynthetic(unittest.TestCase):
    def test_full_report_with_stubbed_cli(self):
        beam = [_beam("M1", 0.2, 0.2), _beam("M2", 1.0, 1.0)]
        eng = {"laser": {"pulse_energy_J": 1e-3},
               "board": {"board_mm": [600, 600], "hole_pitch_mm": 25},
               "elements": {
                   "M1": {"lidt_J_per_cm2": 1.0,
                          "aperture_diameter_mm": 0.3,  # a=0.15 on a 0.2 mm
                          "mount": {"footprint_mm": [50, 50],  # beam: ~32% clipped
                                    "board_x_mm": 100, "board_y_mm": 100}},
                   "M2": {"lidt_J_per_cm2": 10.0,
                          "aperture_diameter_mm": 10.0,
                          "mount": {"footprint_mm": [50, 50],
                                    "board_x_mm": 200, "board_y_mm": 100}},
                   "Ghost": {"lidt_J_per_cm2": 1.0},
               }}
        with tempfile.TemporaryDirectory() as tmp:
            rez_path = os.path.join(tmp, "c.rez")
            eng_path = os.path.join(tmp, "c.rez.eng.json")
            with open(rez_path, "w") as f:
                json.dump({"schema_version": "2.1", "elements": [
                    {"label": "M1", "type": "ElemFlatMirror", "params": {}},
                    {"label": "M2", "type": "ElemCurveMirror", "params": {}},
                ]}, f)
            with open(eng_path, "w") as f:
                json.dump(eng, f)
            with mock.patch("rezeng.checks.run_headless_file",
                           return_value=_fake_cli_result(beam)):
                report = run_checks(rez_path, eng_path)
        self.assertEqual(report["version"], 1)
        by_id = {c["id"]: c for c in report["checks"]}
        self.assertEqual(by_id["lidt:M1"]["status"], "fail")
        self.assertEqual(by_id["lidt:M2"]["status"], "ok")
        self.assertEqual(by_id["aperture:M1"]["status"], "warn")
        self.assertEqual(by_id["aperture_total"]["status"], "warn")
        self.assertEqual(by_id["board_overlap:M1/M2"]["status"], "ok")
        self.assertTrue(any("Ghost" in w for w in report["warnings"]))
        summary = report["summary"]
        self.assertEqual(summary["total"], len(report["checks"]))
        self.assertEqual(summary["fail"], 1)
        self.assertEqual(summary["ok"] + summary["warn"] + summary["fail"]
                         + summary["nodata"], summary["total"])

    def test_unstable_cavity_reports_nodata(self):
        beam_none = {"version": 1, "trip_type": "SW", "warnings": [],
                     "results": [{"id": 0, "ok": True, "g_T": 1.2,
                                  "g_S": 1.1, "stable": False,
                                  "total_length_mm": 100.0,
                                  "beam": None, "waist": None}]}
        with tempfile.TemporaryDirectory() as tmp:
            rez_path = os.path.join(tmp, "c.rez")
            eng_path = os.path.join(tmp, "c.rez.eng.json")
            with open(rez_path, "w") as f:
                json.dump({"schema_version": "2.1", "elements": [
                    {"label": "M1", "type": "ElemFlatMirror", "params": {}},
                ]}, f)
            with open(eng_path, "w") as f:
                json.dump({"laser": {"pulse_energy_J": 1e-3},
                           "elements": {"M1": {"lidt_J_per_cm2": 1.0}}}, f)
            with mock.patch("rezeng.checks.run_headless_file",
                           return_value=beam_none):
                report = run_checks(rez_path, eng_path)
        by_id = {c["id"]: c for c in report["checks"]}
        self.assertEqual(by_id["lidt:M1"]["status"], "nodata")
        self.assertEqual(by_id["aperture:M1"]["status"], "nodata")
        self.assertTrue(any("unstable" in w or "no beam" in w
                            for w in report["warnings"]))


class TestRunChecksRealCavity(unittest.TestCase):
    def test_user_cavity_with_sample_sidecar(self):
        report = run_checks(USER_CAVITY, EXAMPLE_ENG)
        self.assertEqual(report["version"], 1)
        by_id = {c["id"]: c for c in report["checks"]}
        # Sample data was chosen to exercise every status:
        # M1 fluence ~6.18 J/cm^2 vs LIDT 5.0 -> fail;
        # M4 fluence ~1.47 vs 1.8 (ratio ~0.81) -> warn;
        # M2 fluence ~0.041 vs 0.05 (ratio ~0.82) -> warn.
        self.assertEqual(by_id["lidt:M1"]["status"], "fail")
        self.assertAlmostEqual(by_id["lidt:M1"]["value"], 6.1755, places=3)
        self.assertEqual(by_id["lidt:M4"]["status"], "warn")
        self.assertEqual(by_id["lidt:M2"]["status"], "warn")
        self.assertEqual(by_id["lidt:M3"]["status"], "ok")
        self.assertEqual(by_id["lidt:d1"]["status"], "nodata")
        # M1 aperture 0.3 mm on a 0.103 mm beam clips ~1.45% -> warn.
        self.assertEqual(by_id["aperture:M1"]["status"], "warn")
        self.assertEqual(by_id["aperture_total"]["status"], "warn")
        # M2/M3 mounts overlap; M4 sticks out past the board edge.
        self.assertEqual(by_id["board_overlap:M2/M3"]["status"], "fail")
        self.assertEqual(by_id["board_bounds:M4"]["status"], "fail")
        self.assertEqual(by_id["board_grid:M3"]["status"], "warn")
        self.assertEqual(by_id["board_grid:M1"]["status"], "ok")
        # Unknown side-car label is a warning, not a crash.
        self.assertTrue(any("Ghost" in w for w in report["warnings"]))
        summary = report["summary"]
        self.assertEqual(summary["total"], len(report["checks"]))
        self.assertGreaterEqual(summary["fail"], 3)
        self.assertGreater(summary["nodata"], 0)


if __name__ == "__main__":
    unittest.main()
