"""Tests for Phase 3 block 1: merit function, two-stage optimizer,
Snap catalogue, dual stability-zone scan.

Run: ``python3 -m unittest discover -s tests`` (from engineering/).
"""

import csv
import math
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rezeng import (BatchEvaluator, CatalogError, OptimizerError,
                    dioptric_distance, load_rez, optimize,
                    optimize_with_discrete, run_headless_file,
                    scan_zones, snap_and_reoptimize, snap_radius)
from rezeng.merit import (PENALTY_BASE, PENALTY_SLOPE, PENALTY_UNSTABLE,
                          evaluate_result)

HERE = os.path.dirname(os.path.abspath(__file__))
USER_REZ = "/home/hatch/workspace/user/files/upload.rez"
SYMM_FREE = os.path.join(HERE, "data", "spherical_symm_free.rez")
SYMM_LINKED = os.path.join(os.path.dirname(HERE), "..", "bin", "examples",
                           "spherical_symm.rez")


def _fake_result(g_T=0.5, g_S=-0.3, w_T=0.20, w_S=0.21,
                 R_T=-500.0, R_S=-500.0, ok=True):
    return {"ok": ok, "error": None if ok else "rejected",
            "g_T": g_T, "g_S": g_S, "stable": abs(g_T) < 1 and abs(g_S) < 1,
            "total_length_mm": 1000.0,
            "beam": [{"label": "M1", "w_T_mm": w_T, "w_S_mm": w_S,
                      "R_T_mm": R_T, "R_S_mm": R_S}],
            "waist": {"w0_T_mm": 0.1, "w0_S_mm": 0.1,
                      "z_T_mm": 0.0, "z_S_mm": 0.0}}


class TestMerit(unittest.TestCase):
    def test_beam_target(self):
        # C++: term = W * ((w - T) / T)^2.
        m, br = evaluate_result(
            _fake_result(w_T=0.22), [{"kind": "beam_T", "element": "M1",
                                      "target_mm": 0.20, "weight": 2.0}])
        self.assertAlmostEqual(m, 2.0 * (0.02 / 0.20) ** 2)
        self.assertAlmostEqual(br[0]["value"], 0.22)

    def test_astigmatism(self):
        # C++: d = |wT - wS|, ref = max(max(wT, wS), 1e-12).
        m, _br = evaluate_result(
            _fake_result(w_T=0.20, w_S=0.21),
            [{"kind": "astigmatism", "element": "M1", "weight": 10.0}])
        self.assertAlmostEqual(m, 10.0 * (0.01 / 0.21) ** 2)

    def test_stability_center(self):
        # C++: term = W * (gT^2 + gS^2).
        m, _br = evaluate_result(
            _fake_result(g_T=0.5, g_S=-0.3),
            [{"kind": "stability_center", "weight": 3.0}])
        self.assertAlmostEqual(m, 3.0 * (0.25 + 0.09))

    def test_unstable_penalty(self):
        # Gemini form: 1e6 + 1e4 * max(0, max(|g|) - 1)^2.
        m, br = evaluate_result(
            _fake_result(g_T=1.3, g_S=0.5),
            [{"kind": "stability_center", "weight": 1.0}])
        self.assertAlmostEqual(m, PENALTY_BASE + PENALTY_SLOPE * 0.3 ** 2)
        self.assertEqual(br[0]["kind"], "penalty")

    def test_failed_and_nonfinite(self):
        m, _ = evaluate_result(
            _fake_result(ok=False),
            [{"kind": "stability_center", "weight": 1.0}])
        self.assertEqual(m, PENALTY_UNSTABLE)
        m, _ = evaluate_result(
            _fake_result(g_T=float("nan")),
            [{"kind": "stability_center", "weight": 1.0}])
        self.assertEqual(m, PENALTY_UNSTABLE)

    def test_merit_matches_real_cli(self):
        # Cross-check against the real binary on the symmetric cavity.
        out = run_headless_file(SYMM_FREE)
        result = out["results"][0]
        m, br = evaluate_result(result, [
            {"kind": "beam_T", "element": "M1", "target_mm": 0.25,
             "weight": 1.0},
            {"kind": "stability_center", "weight": 2.0}])
        w = result["beam"][0]["w_T_mm"]
        g = result["g_T"]
        expect = ((w - 0.25) / 0.25) ** 2 + 2.0 * (g * g + g * g)
        self.assertAlmostEqual(m, expect, places=12)
        self.assertEqual(len(br), 2)

    def test_waist_target_real_cli(self):
        # User cavity: M1 segment waist w0_T = 0.1000 mm at the start.
        out = run_headless_file(USER_REZ)
        result = out["results"][0]
        data = load_rez(USER_REZ)
        m, br = evaluate_result(
            result, [{"kind": "waist", "element": "M1",
                      "target_mm": 0.12, "weight": 1.0}], data=data)
        self.assertAlmostEqual(br[0]["value"], 0.1000, places=4)
        self.assertAlmostEqual(m, ((0.1 - 0.12) / 0.12) ** 2, places=4)


class TestOptimizerBatching(unittest.TestCase):
    def test_de_vectorized_is_one_batch_per_generation(self):
        # Mock the CLI: g is a parabola in the L override (mm).
        import rezeng.optimizer as opt_mod
        calls = []

        def fake_run_headless(request, binary=None, timeout=None):
            mutations = request["mutations"]
            calls.append(len(mutations))
            results = []
            for mut in mutations:
                L_mm = mut["overrides"]["L"]["L"]
                g = (L_mm - 90.0) / 100.0
                results.append({"id": mut["id"], "ok": True,
                                "error": None, "g_T": g, "g_S": g,
                                "stable": abs(g) < 1, "beam": None,
                                "waist": None,
                                "total_length_mm": L_mm})
            return {"version": 1, "results": results}

        real = opt_mod.run_headless
        opt_mod.run_headless = fake_run_headless
        try:
            data = load_rez(SYMM_FREE)
            res = optimize(
                data, [{"label": "L", "alias": "L",
                        "min_si": 0.0, "max_si": 0.2}],
                [{"kind": "stability_center", "weight": 1.0}],
                de_maxiter=4, de_popsize=5, de_seed=0, nm_maxfev=50)
        finally:
            opt_mod.run_headless = real
        # One CLI call per DE generation (initial + 4), each carrying
        # the whole population of 5 -- batching, not point-by-point.
        # (The start evaluation is one extra 1-mutation call; NM and
        # the tie-break refinement add single-point calls after.)
        self.assertEqual(calls[:6], [1, 5, 5, 5, 5, 5])
        self.assertLess(len(calls), res["evaluations"])
        self.assertEqual(sum(calls), res["evaluations"])
        best_L_mm = res["best_values_si"][("L", "L")] * 1e3
        self.assertAlmostEqual(best_L_mm, 90.0, delta=2.0)

    def test_linked_variable_fails_fast(self):
        # M1.R / M2.R in the shipped example are driven by the R0
        # link; the CLI would reject every override, so setup must
        # fail instead of returning 1e9 for every point.
        data = load_rez(SYMM_LINKED)
        with self.assertRaises(OptimizerError):
            BatchEvaluator(
                data, [{"label": "M1", "alias": "R",
                        "min_si": 0.001, "max_si": 0.1}],
                [{"kind": "stability_center", "weight": 1.0}])


class TestOptimizerReproducesPrototype(unittest.TestCase):
    def test_max_margin(self):
        # Phase 0 prototype (grid search): margin 0.72 -> 1.00 at
        # (L=90, R1=45, R2=60) mm. The continuous optimizer must reach
        # margin ~1.00 on the same problem (unlinked fixture: the
        # shipped example links R1 = R2 = R0, so it cannot vary them
        # independently through the CLI).
        data = load_rez(SYMM_FREE)
        res = optimize(
            data, [{"label": "L", "alias": "L",
                    "min_si": 0.0, "max_si": 0.2},
                   {"label": "M1", "alias": "R",
                    "min_si": 0.001, "max_si": 0.1},
                   {"label": "M2", "alias": "R",
                    "min_si": 0.001, "max_si": 0.1}],
            [{"kind": "stability_center", "weight": 1.0}],
            de_maxiter=40, de_popsize=10, de_seed=0, nm_maxfev=300)
        vals = res["best_values_si"]
        L = vals[("L", "L")] * 1e3
        R1 = vals[("M1", "R")] * 1e3
        R2 = vals[("M2", "R")] * 1e3
        g = res["breakdown"][0]["value"]
        self.assertLess(abs(g), 1e-4)  # margin >= 0.9999
        # The tie-break refinement finds the *closest* surface point
        # (~84, ~49, ~49), nearer to the start than the prototype's
        # grid-limited (90, 45, 60) -- same margin 1.00.
        self.assertLess(res["tie_break"]["distance"], 0.06)
        self.assertAlmostEqual(L, 83.95, delta=3.0)
        self.assertAlmostEqual(R1, 49.17, delta=3.0)
        self.assertAlmostEqual(R2, 49.17, delta=3.0)

    def test_waist_target_reproduces_phase1_solve(self):
        # Phase 1 Brent solve: w0(M1) = 0.12 mm -> d1 = 365.4487 mm.
        data = load_rez(USER_REZ)
        res = optimize(
            data, [{"label": "d1", "alias": "L",
                    "min_si": 0.30, "max_si": 0.45}],
            [{"kind": "waist", "element": "M1", "target_mm": 0.12,
             "weight": 1.0}],
            de_maxiter=25, de_popsize=10, de_seed=0, nm_maxfev=200)
        d1 = res["best_values_si"][("d1", "L")] * 1e3
        self.assertAlmostEqual(d1, 365.4487, delta=0.5)
        self.assertAlmostEqual(res["breakdown"][0]["value"], 0.12,
                               delta=1e-3)

    def test_discrete_outer_loop(self):
        data = load_rez(SYMM_FREE)
        res = optimize_with_discrete(
            data, [{"label": "L", "alias": "L",
                    "min_si": 0.0, "max_si": 0.2},
                   {"label": "M1", "alias": "R",
                    "candidates_si": [0.045, 0.050, 0.060]},
                   {"label": "M2", "alias": "R",
                    "min_si": 0.001, "max_si": 0.1}],
            [{"kind": "stability_center", "weight": 1.0}],
            de_maxiter=5, de_popsize=5, de_seed=0, nm_maxfev=50)
        self.assertIsNotNone(res["discrete_combo"])
        self.assertIn(res["discrete_combo"][0], (0.045, 0.050, 0.060))
        self.assertLess(res["best_merit"], 1e-3)

    def test_fixed_total_constraint(self):
        # d1 + d2 fixed at the current total: d2 is derived, never a
        # free variable, and the constraint holds exactly.
        data = load_rez(USER_REZ)
        total = 0.37207096207130354 + 0.4696766836102186
        ev = BatchEvaluator(
            data, [{"label": "d1", "alias": "L",
                    "min_si": 0.30, "max_si": 0.45}],
            [{"kind": "waist", "element": "M1", "target_mm": 0.12,
             "weight": 1.0}],
            constraints=[{"kind": "fixed_total",
                          "members": [("d1", "L"), ("d2", "L")],
                          "total_si": total}])
        ov, ok = ev._overrides_for_point({("d1", "L"): 0.35})
        self.assertTrue(ok)
        self.assertAlmostEqual(ov["d1"]["L"] + ov["d2"]["L"],
                               total * 1e3, places=6)
        _ov, ok = ev._overrides_for_point({("d1", "L"): 0.90})
        self.assertFalse(ok)  # derived d2 would be negative
        res = optimize(
            data, [{"label": "d1", "alias": "L",
                    "min_si": 0.30, "max_si": 0.45}],
            [{"kind": "waist", "element": "M1", "target_mm": 0.12,
             "weight": 1.0}],
            constraints=[{"kind": "fixed_total",
                          "members": [("d1", "L"), ("d2", "L")],
                          "total_si": total}],
            de_maxiter=5, de_popsize=5, de_seed=0, nm_maxfev=50)
        got = res["best_values_si"]
        self.assertAlmostEqual(got[("d1", "L")] + got[("d2", "L")],
                               total, places=9)


class TestSnap(unittest.TestCase):
    def test_dioptric_distances(self):
        # Flat vs R=10000 mm: almost identical (d = 1e-4 /mm).
        # R=50 vs R=60: 20% of the 60 mm dioptric power.
        self.assertAlmostEqual(dioptric_distance(None, 10000), 1e-4)
        d = dioptric_distance(50, 60)
        self.assertAlmostEqual(d / (1.0 / 60.0), 0.20)
        self.assertLess(dioptric_distance(None, 10000),
                        dioptric_distance(50, 60) / 30.0)

    def test_sign_preserved(self):
        part, _d = snap_radius(-450.0)
        self.assertLess(part["R_mm"], 0)
        part, _d = snap_radius(450.0)
        self.assertGreater(part["R_mm"], 0)
        part, _d = snap_radius(None)
        self.assertIsNone(part["R_mm"])
        # Concave radius with a convex-only catalogue: no snap.
        convex_only = [{"vendor": "V", "part_number": "P",
                        "R_mm": 500, "diameter_mm": 25.4,
                        "coating": "HR"}]
        with self.assertRaises(CatalogError):
            snap_radius(-450.0, catalog=convex_only)

    def test_csv_import_and_filter(self):
        with tempfile.NamedTemporaryFile("w", suffix=".csv",
                                         delete=False) as f:
            f.write("vendor,part_number,R_mm,diameter_mm,coating\n")
            f.write("ACME,AC-500,500,25.4,1064nm HR\n")
            f.write("ACME,AC-FLAT,inf,50.8,1064nm HR\n")
            path = f.name
        try:
            from rezeng.catalog import load_catalog_csv
            parts = load_catalog_csv(path)
            self.assertEqual(len(parts), 2)
            self.assertIsNone(parts[1]["R_mm"])
            part, _d = snap_radius(-450.0, catalog=parts,
                                   min_diameter_mm=50.0)
            self.assertIsNone(part["R_mm"])  # only the flat is big enough
        finally:
            os.unlink(path)

    def test_snap_and_reoptimize(self):
        data = load_rez(USER_REZ)
        res = snap_and_reoptimize(
            data, [{"label": "M3", "alias": "R"}],
            [{"label": "M3", "alias": "R",
              "min_si": -0.55, "max_si": -0.35},
             {"label": "d2", "alias": "L",
              "min_si": 0.40, "max_si": 0.55},
             {"label": "d3", "alias": "L",
              "min_si": 0.015, "max_si": 0.04}],
            [{"kind": "astigmatism", "element": "M4", "weight": 10.0},
             {"kind": "stability_center", "weight": 1.0}],
            [("d2", "L"), ("d3", "L")], nm_maxfev=150)
        self.assertEqual(res["snapped"][0]["old_R_mm"], -450.0)
        self.assertEqual(res["snapped"][0]["new_R_mm"], -500)
        self.assertEqual(res["after"]["values_si"][("M3", "R")], -0.5)
        # Re-optimised lengths must not make the merit worse than the
        # pre-snap cavity.
        self.assertLess(res["after"]["merit"], res["before"]["merit"])
        self.assertIn("M4", res["comparison"]["delta_w"])
        self.assertIsNotNone(res["comparison"]["delta_g_T"])


class TestZones(unittest.TestCase):
    def test_boundaries_and_common_zone(self):
        data = load_rez(USER_REZ)
        z = scan_zones(data, lens=("TL1", "F"), d_min=0.0, d_max=12.0,
                       n_points=80, sesam_label="M1",
                       crystal_label="TL1", working_f_mm=230.0)
        # Every refined boundary must satisfy |g| = 1 to 1e-6 in D:
        # g(D_crit - 1e-6) and g(D_crit + 1e-6) straddle the level
        # (the |g| residual itself is slope-amplified: near the far
        # edge of Zone II, dg/dD is ~2e3 per 1/m, so a 1e-9 D error
        # already shows up as ~2e-6 in |g|).
        for b in z["boundaries"]:
            self.assertTrue(b["bracket"][0] <= b["D_th"]
                            <= b["bracket"][1])
            level = float(b["g"])
            axis = b["axis"]
            vals = []
            for d in (b["D_th"] - 1e-6, b["D_th"] + 1e-6):
                out = run_headless_file(
                    USER_REZ, [{"id": 0, "overrides":
                                {"TL1": {"F": 1000.0 / d}}}])
                r = out["results"][0]
                g = r["g_T"] if axis == "T" else r["g_S"]
                vals.append(g - level)
            self.assertLessEqual(vals[0] * vals[1], 0.0)
        # Working point F=230 mm (D=4.348) sits in Zone I; F=115 mm
        # (D=8.696) sits in Zone II -- cross-checks the Phase 2
        # non-monotonic g(F) demo.
        self.assertEqual(z["working_point"]["zone"], "Zone_I")
        common = z["zones_common"]
        self.assertEqual(len(common), 2)
        self.assertEqual(common[0]["id"], "Zone_I")
        self.assertEqual(common[1]["id"], "Zone_II")
        lo, hi = common[1]["D_range"]
        self.assertTrue(lo < 8.696 < hi)
        # Zone_Common is the strict intersection of Zone_T and Zone_S.
        t_lo, t_hi = z["zones_T"][0]["D_range"]
        s_lo, s_hi = z["zones_S"][0]["D_range"]
        c_lo, c_hi = common[0]["D_range"]
        self.assertAlmostEqual(c_lo, max(t_lo, s_lo), places=6)
        self.assertAlmostEqual(c_hi, min(t_hi, s_hi), places=6)
        self.assertLess(c_hi - c_lo, t_hi - t_lo)
        self.assertLess(c_hi - c_lo, s_hi - s_lo)


if __name__ == "__main__":
    unittest.main()
