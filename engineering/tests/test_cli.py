"""Tests for the headless CLI wrapper (rezeng.cli) and the CLI protocol.

Run from the repository root:  python3 -m unittest discover -s engineering/tests -v
Requires the locally built binary (rezonator2/bin/rezonator).
"""

import json
import math
import os
import unittest

import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                ".."))

from rezeng import load_rez, run_headless, run_headless_file, HeadlessError
from rezeng.units import to_si

REPO = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", ".."))
EXAMPLES = os.path.join(REPO, "bin", "examples")
USER_CAVITY = os.path.join(os.path.expanduser("~"), "workspace", "user",
                           "files", "upload.rez")

# Verified reference values for the user cavity, full precision, from the
# verified Python prototype (~/workspace/user_cavity_astig.py, analyze()):
# the 4-decimal figures in the task (g_T 0.9288, g_S 0.9212, M4 w 0.2057/0.2113,
# M1 w 0.1000/0.1031) are those values rounded, so a 1e-6 check must use
# the full precision. CLI output matches the prototype bit-for-bit here.
REF = {
    "g_T": 0.928759881642, "g_S": 0.921218437061,
    "M4": (0.205657252, 0.211257375), "M1": (0.100000009, 0.103087306),
    "total_length_mm": 1171.32,
}


def rel(a, b):
    return abs(a - b) / max(abs(b), 1e-12)


class TestHeadlessUserCavity(unittest.TestCase):
    def test_matches_verified_reference(self):
        out = run_headless_file(USER_CAVITY)
        self.assertEqual(out["version"], 1)
        self.assertEqual(out["trip_type"], "SW")
        self.assertEqual(out["warnings"], [])
        r = out["results"][0]
        self.assertTrue(r["ok"], r.get("error"))
        self.assertTrue(r["stable"])
        self.assertLess(rel(r["g_T"], REF["g_T"]), 1e-6)
        self.assertLess(rel(r["g_S"], REF["g_S"]), 1e-6)
        # Total length: the .rez stores non-round L values (d1 372.07096...,
        # d2 469.67668..., d3 25.67200..., d4 276.89818...); the nominal
        # 1171.32 mm in the notes is their rounded sum. Expect the exact
        # sum of the stored values.
        data = load_rez(USER_CAVITY)
        expected_total = sum(
            to_si(e["params"]["L"]["value"], e["params"]["L"]["unit"])
            for e in data["elements"] if "L" in e.get("params", {})) * 1e3
        self.assertLess(rel(r["total_length_mm"], expected_total), 1e-9)
        beam = {b["label"]: b for b in r["beam"]}
        for label, (wT, wS) in (("M4", REF["M4"]), ("M1", REF["M1"])):
            self.assertLess(rel(beam[label]["w_T_mm"], wT), 1e-6)
            self.assertLess(rel(beam[label]["w_S_mm"], wS), 1e-6)
        # Waist is at the flat end mirror M1: w0 == w, z == 0 there.
        waist = r["waist"]
        self.assertLess(rel(waist["w0_T_mm"], REF["M1"][0]), 1e-6)
        self.assertLess(rel(waist["w0_S_mm"], REF["M1"][1]), 1e-6)
        self.assertLess(abs(waist["z_T_mm"]), 1e-6)
        self.assertLess(abs(waist["z_S_mm"]), 1e-6)

    def test_waist_consistent_within_segments(self):
        """w0 derived from (w, R) is constant within a beam segment.

        Gaussian-beam physics: free-space propagation leaves w0 (and z_R)
        unchanged, but a focusing element (mirror/lens) changes them. So
        w0 must agree inside each segment of this cavity and differ
        between segments:
          [M1, d1] -> 0.1000 (the real waist, at the flat SESAM mirror)
          [M2, d2] -> 0.1985, [M3, d3] -> 0.3644, [TL1, d4, M4] -> 0.2057
        (w0 from an element's (w, R) via 1/q = 1/R - i*lam/(pi*w^2).)
        """
        out = run_headless_file(USER_CAVITY)
        r = out["results"][0]
        lam = to_si(1064, "nm")
        w0 = {}
        for b in r["beam"]:
            for plane in ("T", "S"):
                w = b["w_%s_mm" % plane] * 1e-3
                R = b["R_%s_mm" % plane]
                if R is None or w <= 0:
                    continue
                R *= 1e-3
                inv_q = complex(1.0 / R, -lam / (math.pi * w * w))
                q = 1.0 / inv_q
                w0[(b["label"], plane)] = math.sqrt(lam * q.imag / math.pi) * 1e3
        for plane in ("T", "S"):
            self.assertAlmostEqual(w0[("d1", plane)],
                                   r["waist"]["w0_%s_mm" % plane], delta=1e-9)
            self.assertAlmostEqual(w0[("M2", plane)], w0[("d2", plane)],
                                   delta=1e-9)
            self.assertAlmostEqual(w0[("M3", plane)], w0[("d3", plane)],
                                   delta=1e-9)
            self.assertAlmostEqual(w0[("TL1", plane)], w0[("d4", plane)],
                                   delta=1e-9)
            self.assertAlmostEqual(w0[("d4", plane)], w0[("M4", plane)],
                                   delta=1e-9)
            seg = [w0[("d1", plane)], w0[("M2", plane)],
                   w0[("M3", plane)], w0[("TL1", plane)]]
            for a, b in zip(seg, seg[1:]):
                self.assertGreater(abs(a - b) / max(a, b), 1e-3)


class TestHeadlessExamples(unittest.TestCase):
    def test_sw_example(self):
        out = run_headless_file(os.path.join(EXAMPLES, "spherical_symm.rez"))
        self.assertEqual(out["trip_type"], "SW")
        r = out["results"][0]
        self.assertTrue(r["ok"], r.get("error"))
        self.assertIsNotNone(r["g_T"])
        self.assertIsNotNone(r["stable"])
        self.assertTrue(all(b["w_T_mm"] > 0 and b["w_S_mm"] > 0
                            for b in r["beam"]))

    def test_sp_gaussian_pump(self):
        # gauss_aperture.rez uses a Waist (Gaussian) pump: real beam radii.
        out = run_headless_file(os.path.join(EXAMPLES, "gauss_aperture.rez"))
        self.assertEqual(out["trip_type"], "SP")
        r = out["results"][0]
        self.assertTrue(r["ok"], r.get("error"))
        self.assertIsNone(r["g_T"])
        self.assertIsNone(r["g_S"])
        self.assertIsNone(r["stable"])
        self.assertIsNotNone(r["beam"])
        self.assertTrue(all(b["w_T_mm"] > 0 and b["w_S_mm"] > 0
                            for b in r["beam"]))

    def test_sp_ray_pump_has_no_beam(self):
        # axicon_lens.rez uses a RayVector pump: a ray height is not a
        # beam radius, so beam/waist are null (with a warning), not wrong.
        out = run_headless_file(os.path.join(EXAMPLES, "axicon_lens.rez"))
        self.assertEqual(out["trip_type"], "SP")
        r = out["results"][0]
        self.assertTrue(r["ok"], r.get("error"))
        self.assertIsNone(r["beam"])
        self.assertIsNone(r["waist"])
        self.assertTrue(any("ray-vector" in w for w in out["warnings"]))


class TestHeadlessBatch(unittest.TestCase):
    def test_batch_matches_singles(self):
        data = load_rez(USER_CAVITY)
        mutations = [
            {"id": i, "overrides": {"M2": {"R": 500.0 + 10 * i}}}
            for i in range(6)
        ]
        batch = run_headless({"base_schema": data, "mutations": mutations})
        self.assertEqual(len(batch["results"]), 6)
        for i, mut in enumerate(mutations):
            single = run_headless({"base_schema": data, "mutations": [mut]})
            b, s = batch["results"][i], single["results"][0]
            self.assertEqual(b["id"], s["id"])
            self.assertEqual(b["ok"], s["ok"])
            self.assertAlmostEqual(b["g_T"], s["g_T"], places=12)
            self.assertAlmostEqual(b["g_S"], s["g_S"], places=12)
            for bb, ss in zip(b["beam"], s["beam"]):
                self.assertAlmostEqual(bb["w_T_mm"], ss["w_T_mm"], places=12)
                self.assertAlmostEqual(bb["w_S_mm"], ss["w_S_mm"], places=12)

    def test_mutation_failure_is_per_group(self):
        data = load_rez(USER_CAVITY)
        mutations = [
            {"id": "bad-elem", "overrides": {"Nope": {"R": 100}}},
            {"id": "bad-param", "overrides": {"M2": {"Nope": 100}}},
            {"id": "bad-value", "overrides": {"M2": {"R": 0}}},
            {"id": "good", "overrides": {"M2": {"R": 500}}},
        ]
        out = run_headless({"base_schema": data, "mutations": mutations})
        self.assertFalse(out["results"][0]["ok"])
        self.assertFalse(out["results"][1]["ok"])
        self.assertFalse(out["results"][2]["ok"])
        self.assertTrue(out["results"][3]["ok"])
        self.assertIn("Nope", out["results"][0]["error"])

    def test_driven_param_conflict(self):
        # global_params.rez: d1.L is driven by a link from L0.
        data = load_rez(os.path.join(EXAMPLES, "global_params.rez"))
        label0 = data["elements"][0]["label"]
        out = run_headless({"base_schema": data, "mutations": [
            {"id": 0, "overrides": {label0: {"L": 10}}},
            {"id": 1, "overrides": {label0: {"n": 1.5}}},
        ]})
        self.assertFalse(out["results"][0]["ok"])
        self.assertIn("link", out["results"][0]["error"])
        self.assertTrue(out["results"][1]["ok"])

    def test_unstable_is_not_an_error(self):
        data = load_rez(USER_CAVITY)
        out = run_headless({"base_schema": data, "mutations": [
            {"id": 0, "overrides": {"d1": {"L": 2000}}},
        ]})
        r = out["results"][0]
        self.assertTrue(r["ok"])
        self.assertFalse(r["stable"])
        self.assertIsNotNone(r["g_T"])
        self.assertIsNone(r["beam"])
        self.assertIsNone(r["waist"])
        self.assertIsNotNone(r["total_length_mm"])

    def test_bad_base_schema_raises(self):
        with self.assertRaises(HeadlessError):
            run_headless({"base_schema": {"schema_version": "9.9",
                                          "elements": []}})


if __name__ == "__main__":
    unittest.main()
