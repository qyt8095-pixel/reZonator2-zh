"""Tests for Phase 3 block 3: alignment Jacobian and screw-turn guide.

Run: ``python3 -m unittest discover -s tests`` (from engineering/).
"""

import math
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rezeng import (JacobianError, load_rez, run_headless, mirror_labels,
                    roundtrip_list, jacobian_analytic,
                    jacobian_finite_difference, compare_jacobians,
                    screw_turns, direction_table, tilt_to_screws,
                    recenter_guide, JACOBIAN_TOL)

USER_REZ = "/home/hatch/workspace/user/files/upload.rez"
SP_REZ = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      "data", "mopa_amp_sp.rez")


def _param(value, unit):
    return {"unit": unit, "value": value}


def _elem(label, etype, params):
    return {"label": label, "type": etype, "title": label,
            "is_disabled": False, "params": params}


def _flat_flat_cavity():
    """Two flat mirrors 500 mm apart: g = +1, singular axis solve."""
    elems = [_elem("M1", "ElemFlatMirror", {}),
             _elem("d1", "ElemEmptyRange",
                   {"L": _param(500, "mm"), "n": _param(1, "none")}),
             _elem("M2", "ElemFlatMirror", {})]
    return {"builtin_params": {"lambda": _param(1064, "nm")},
            "custom_params": {}, "elements": elems, "formulas": [],
            "param_links": [], "notes": "", "schema_version": "2.0",
            "title": "flat-flat", "trip_type": "SW", "pumps": [],
            "windows": []}


def _cli_axis(data, misalign, ref_label="M4"):
    """Axis entry (mm, mrad) at ``ref_label`` for one misalign dict."""
    resp = run_headless({"base_schema": data,
                         "mutations": [{"id": "m", "misalign": misalign}]})
    res = resp["results"][0]
    assert res["ok"], res.get("error")
    for entry in res["axis"]:
        if entry["label"] == ref_label:
            return np.array([entry["x_T_mm"], entry["th_T_mrad"],
                             entry["x_S_mm"], entry["th_S_mrad"]],
                            dtype=float)
    raise AssertionError("no axis entry for %r" % ref_label)


class TestAnalyticVsFiniteDifference(unittest.TestCase):
    def setUp(self):
        self.data = load_rez(USER_REZ)

    def test_at_output_m4(self):
        ja = jacobian_analytic(self.data, "M4")
        jf = jacobian_finite_difference(self.data, "M4")
        self.assertEqual(ja["columns"], jf["columns"])
        self.assertEqual(ja["rows"], jf["rows"])
        diff, ok = compare_jacobians(ja["jacobian"], jf["jacobian"])
        self.assertTrue(ok, "max diff %g exceeds %g" % (diff, JACOBIAN_TOL))
        # The Jacobian is not tiny: M2 dT moves the output spot by
        # 0.64 mm per mrad, and M4 dT changes the pointing by ~1 mrad/mrad.
        self.assertAlmostEqual(ja["jacobian"][0, 2], 0.6435, places=3)
        self.assertAlmostEqual(ja["jacobian"][1, 6], 1.0065, places=3)

    def test_at_sesam_m1(self):
        ja = jacobian_analytic(self.data, "M1")
        jf = jacobian_finite_difference(self.data, "M1")
        diff, ok = compare_jacobians(ja["jacobian"], jf["jacobian"])
        self.assertTrue(ok, "max diff %g exceeds %g" % (diff, JACOBIAN_TOL))

    def test_zero_tilt_zero_axis(self):
        jf = jacobian_finite_difference(self.data, "M4")
        np.testing.assert_allclose(jf["base_axis"], 0.0, atol=1e-12)

    def test_t_and_s_planes_decoupled(self):
        ja = jacobian_analytic(self.data, "M4")
        J = ja["jacobian"]
        # dT columns (even) touch only the T rows; dS columns (odd)
        # only the S rows.
        np.testing.assert_allclose(J[2:, 0::2], 0.0, atol=1e-15)
        np.testing.assert_allclose(J[:2, 1::2], 0.0, atol=1e-15)


class TestCliAxisLinearity(unittest.TestCase):
    def setUp(self):
        self.data = load_rez(USER_REZ)

    def test_single_mirror_scales_linearly(self):
        # Axis is exactly linear in the tilt: +1 mrad is 10x +0.1 mrad.
        a01 = _cli_axis(self.data, {"M2": {"dT_mrad": 0.1}})
        a1 = _cli_axis(self.data, {"M2": {"dT_mrad": 1.0}})
        np.testing.assert_allclose(a1, 10.0 * a01, rtol=1e-9, atol=1e-12)
        # And the +0.1 mrad value is the one the demo reports.
        self.assertAlmostEqual(a01[0], 0.0643, places=3)
        self.assertAlmostEqual(a01[1], -0.0006, places=3)

    def test_superposition_two_mirrors(self):
        # Tilting M2 and M3 together = sum of the individual tilts.
        a2 = _cli_axis(self.data, {"M2": {"dT_mrad": 0.1}})
        a3 = _cli_axis(self.data, {"M3": {"dS_mrad": -0.2}})
        ab = _cli_axis(self.data, {"M2": {"dT_mrad": 0.1},
                                   "M3": {"dS_mrad": -0.2}})
        np.testing.assert_allclose(ab, a2 + a3, rtol=1e-9, atol=1e-12)


class TestRoundtripList(unittest.TestCase):
    def test_sw_user_cavity_ref_m1(self):
        data = load_rez(USER_REZ)
        labels = [e["label"] for e in data["elements"]]
        lst = roundtrip_list(labels, "M1", "SW")
        self.assertEqual(lst, ["M1", "d1", "M2", "d2", "M3", "d3", "TL1",
                               "d4", "M4", "d4", "TL1", "d3", "M3", "d2",
                               "M2", "d1"])

    def test_rr_ring_order(self):
        lst = roundtrip_list(["A", "B", "C", "D"], "C", "RR")
        self.assertEqual(lst, ["C", "B", "A", "D"])

    def test_sp_raises(self):
        with self.assertRaises(JacobianError):
            roundtrip_list(["A", "B"], "A", "SP")


class TestSingularAndSp(unittest.TestCase):
    def test_flat_flat_singular(self):
        data = _flat_flat_cavity()
        with self.assertRaises(JacobianError):
            jacobian_analytic(data, "M1")

    def test_single_pass_raises(self):
        data = load_rez(SP_REZ)
        self.assertEqual(data.get("trip_type"), "SP")
        with self.assertRaises(JacobianError):
            jacobian_analytic(data, data["elements"][0]["label"])


class TestScrewTurns(unittest.TestCase):
    def test_hand_computed_100_tpi(self):
        # Hand check: theta = 1 mrad, arm = 50 mm, 100 TPI (p = 0.254 mm):
        # N = theta * L / p = 1e-3 * 50 / 0.254 = 0.19685 turns.
        self.assertAlmostEqual(screw_turns(1e-3, 50, 100),
                               0.05 / 0.254, places=12)
        self.assertAlmostEqual(screw_turns(1e-3, 50, 100),
                               0.1968503937007874, places=12)

    def test_hand_computed_80_tpi(self):
        # 80 TPI: p = 25.4/80 = 0.3175 mm -> N = 0.05/0.3175.
        self.assertAlmostEqual(screw_turns(1e-3, 50, 80),
                               0.05 / 0.3175, places=12)

    def test_one_turn_is_pitch_over_arm(self):
        # One full turn of a 100 TPI screw with a 50 mm arm tilts the
        # mirror by p/L = 0.254/50 = 5.08 mrad.
        self.assertAlmostEqual(0.254 / 50.0, 0.00508, places=12)
        # Inverse: that tilt needs exactly one turn.
        self.assertAlmostEqual(screw_turns(0.00508, 50, 100), 1.0,
                               places=12)

    def test_direction_table(self):
        table = direction_table()
        # Back view, right-hand thread, screw on the +T/+S side:
        # clockwise advances the screw and pushes that edge forward,
        # so the normal rotates the other way.
        self.assertEqual(table["dT+"], "CCW")
        self.assertEqual(table["dT-"], "CW")
        self.assertEqual(table["dS+"], "CCW")
        self.assertEqual(table["dS-"], "CW")

    def test_tilt_to_screws_zero_azimuth(self):
        out = tilt_to_screws(1e-3, 0.0, 100, 50, 50, azimuth_deg=0.0)
        self.assertAlmostEqual(out["screw_A"]["turns"], 0.05 / 0.254,
                               places=12)
        self.assertEqual(out["screw_A"]["direction"], "CCW")
        self.assertAlmostEqual(out["screw_B"]["turns"], 0.0, places=12)

    def test_tilt_to_screws_azimuth_90(self):
        # Mount rotated 90 deg: a pure dT tilt is produced by screw B
        # alone, with the opposite sign (R(-90) . (1, 0) = (0, -1)).
        out = tilt_to_screws(1e-3, 0.0, 100, 50, 50, azimuth_deg=90.0)
        self.assertAlmostEqual(out["screw_A"]["turns"], 0.0, places=9)
        self.assertAlmostEqual(out["screw_B"]["turns"], 0.05 / 0.254,
                               places=12)
        self.assertEqual(out["screw_B"]["direction"], "CW")

    def test_unsupported_tpi(self):
        with self.assertRaises(JacobianError):
            screw_turns(1e-3, 50, 64)


class TestRecenterGuide(unittest.TestCase):
    def test_m2_tilt_recentered_with_m2(self):
        # "Measured" output axis: M2 tilted +0.1 mrad (CLI, labelled
        # example values). Recentering with M2 must undo exactly that
        # tilt: dT = -0.1 mrad, dS = 0, position residual ~0.
        data = load_rez(USER_REZ)
        measured = _cli_axis(data, {"M2": {"dT_mrad": 0.1}})
        guide = recenter_guide(data, "M4", "M2", measured,
                               tpi=100, arm_T_mm=50, arm_S_mm=50,
                               azimuth_deg=0.0)
        self.assertAlmostEqual(guide["correction_mrad"]["dT"], -0.1,
                               places=6)
        self.assertAlmostEqual(guide["correction_mrad"]["dS"], 0.0,
                               places=9)
        # 0.1 mrad * 50 mm / 0.254 mm = 0.019685 turns, clockwise
        # (negative tilt -> CW, back view).
        self.assertAlmostEqual(guide["screws"]["screw_A"]["turns"],
                               0.1e-3 * 50 / 0.254, places=9)
        self.assertEqual(guide["screws"]["screw_A"]["direction"], "CW")
        self.assertAlmostEqual(guide["screws"]["screw_B"]["turns"], 0.0,
                               places=9)
        self.assertAlmostEqual(guide["residual_axis"]["x_T_mm"], 0.0,
                               places=9)
        self.assertAlmostEqual(guide["residual_axis"]["x_S_mm"], 0.0,
                               places=9)
        # Pointing is not corrected by a position-only guide; it stays
        # tiny (the M2 tilt barely changes the output pointing).
        self.assertLess(abs(guide["residual_axis"]["th_T_mrad"]), 1e-3)


if __name__ == "__main__":
    unittest.main()
