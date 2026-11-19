"""Tests for the Solves (rezeng.solves): Pickup and waist Solves.

Run from the repository root:  python3 -m unittest discover -s engineering/tests -v
Requires the locally built binary (rezonator2/bin/rezonator).

The waist solves are verified against the user cavity
(~/workspace/user/files/upload.rez) with independent CLI re-evaluation:
a solve is only trusted when a fresh ``--headless`` run at the solved
value reproduces the target to < 1e-6 relative error.
"""

import copy
import math
import os
import unittest

import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                ".."))

from rezeng import (load_rez, save_rez, run_headless, to_si, from_si)
from rezeng.solves import (
    PickupError, SolveError, apply_pickup, find_pickup, verify_pickup,
    solve_waist_size, solve_waist_position, apply_solution,
    waist_from_wr, element_plane_position_mm, total_length_mm)

REPO = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", ".."))
EXAMPLES = os.path.join(REPO, "bin", "examples")
USER_CAVITY = os.path.join(os.path.expanduser("~"), "workspace", "user",
                           "files", "upload.rez")
LAM_NM = 1064.0

# d1.L in the user cavity (mm); the stable window for d1 is roughly
# 240-380 mm (see the scans in the development notes).
D1_MM = 372.07096207130354
D4_MM = 276.89818345838876


def rel(a, b):
    return abs(a - b) / max(abs(b), 1e-12)


def _beam(out, label):
    r = out["results"][0]
    assert r["ok"], r.get("error")
    assert r["stable"], "cavity is unstable"
    for entry in r["beam"]:
        if entry["label"] == label:
            return entry
    raise AssertionError("no beam entry for %r" % label)


def _w0_from_entry(entry, plane="T"):
    w = entry["w_%s_mm" % plane]
    R = entry["R_%s_mm" % plane]
    return waist_from_wr(w, R, LAM_NM)


def _plane_positions(data, overrides_si=None):
    """Element plane positions (mm), computed inline (independent of
    the module under test): cumulative L of preceding elements plus
    the element's own L. ``overrides_si`` is {label: {alias: si}}."""
    positions = {}
    s = 0.0
    for elem in data["elements"]:
        label = elem["label"]
        params = elem.get("params", {})
        length = None
        if "L" in params:
            if overrides_si and label in overrides_si \
                    and "L" in overrides_si[label]:
                length = overrides_si[label]["L"] * 1e3
            else:
                length = to_si(params["L"]["value"],
                               params["L"]["unit"]) * 1e3
        if length is not None:
            s += length
        positions[label] = s
    return positions


def _consistent_b(data, driven, source, k):
    """Offset ``b`` (in the driven parameter's unit) that keeps the
    current values: driven = k*source + b."""
    from rezeng.rez import param_value_si, param_unit
    src_si = param_value_si(data, source[0], source[1])
    drv_si = param_value_si(data, driven[0], driven[1])
    return from_si(drv_si - k * src_si, param_unit(data, driven[0],
                                                   driven[1]))


class TestWaistMath(unittest.TestCase):
    def test_waist_from_wr_flat(self):
        w0, z = waist_from_wr(0.1, None, LAM_NM)
        self.assertEqual(w0, 0.1)
        self.assertEqual(z, 0.0)

    def test_waist_from_wr_user_cavity_m4(self):
        # Hand-computed: w=0.205657 mm, R=-100000 mm, lam=1064 nm ->
        # w0 ~= 0.205657 mm, z ~= -0.156 mm (waist 0.156 mm downstream
        # of M4's plane; the M4 segment waist is virtual).
        w0, z = waist_from_wr(0.205657252, -100000.0, LAM_NM)
        self.assertAlmostEqual(w0, 0.205657, places=5)
        self.assertAlmostEqual(z, -0.156, places=3)

    def test_waist_from_wr_bad_inputs(self):
        with self.assertRaises(ValueError):
            waist_from_wr(0.0, None, LAM_NM)
        with self.assertRaises(ValueError):
            waist_from_wr(-1.0, None, LAM_NM)
        with self.assertRaises(ValueError):
            waist_from_wr(0.1, 0.0, LAM_NM)

    def test_plane_positions_user_cavity(self):
        data = load_rez(USER_CAVITY)
        pos = _plane_positions(data)
        self.assertAlmostEqual(pos["M1"], 0.0, places=9)
        self.assertAlmostEqual(pos["M2"], D1_MM, places=6)
        self.assertAlmostEqual(pos["M4"], 1171.317834448, places=6)
        self.assertAlmostEqual(total_length_mm(data), 1171.317834448,
                               places=6)
        # The module's own position function agrees with the inline one.
        for label in ("M1", "d1", "M2", "d2", "M3", "d3", "TL1", "d4",
                      "M4"):
            self.assertAlmostEqual(
                element_plane_position_mm(data, label), pos[label],
                places=9)
        # An override upstream moves the planes downstream.
        over = {"d1": {"L": to_si(400.0, "mm")}}
        self.assertAlmostEqual(
            element_plane_position_mm(data, "M4", over),
            400.0 + 469.6766836102186 + 25.672005308024055 + 27.0
            + 276.89818345838876, places=6)
        with self.assertRaises(SolveError):
            element_plane_position_mm(data, "Nope")


class TestPickup(unittest.TestCase):
    def test_apply_writes_native_structure(self):
        data = load_rez(USER_CAVITY)
        data["zz_unknown_key"] = {"note": "must survive"}
        k = 0.5
        b_mm = _consistent_b(data, ("d4", "L"), ("d1", "L"), k)
        info = apply_pickup(data, ("d4", "L"), ("d1", "L"), k, b_mm)
        self.assertEqual(info["source_global"], "PK_E1_L")
        self.assertEqual(info["driven_global"], "PK_E7_L")
        self.assertEqual(info["formula"], "0.5 * PK_E1_L + %r"
                         % (to_si(b_mm, "mm"),))
        self.assertEqual(info["created_globals"], ["PK_E1_L", "PK_E7_L"])
        self.assertEqual(data["schema_version"], "2.1")
        self.assertEqual(data["zz_unknown_key"], {"note": "must survive"})
        # Structure: two globals, one formula, two links.
        self.assertIn("PK_E1_L", data["custom_params"])
        self.assertIn("PK_E7_L", data["custom_params"])
        self.assertEqual(data["custom_params"]["PK_E1_L"]["dim"], "linear")
        self.assertEqual(data["custom_params"]["PK_E1_L"]["unit"], "mm")
        self.assertEqual(data["custom_params"]["PK_E1_L"]["value"], D1_MM)
        self.assertEqual(data["formulas"], [{
            "code": info["formula"], "param_deps": ["PK_E1_L"],
            "target_param": "PK_E7_L"}])
        self.assertEqual(data["param_links"], [
            {"source_param": "PK_E1_L", "target_elem": 1,
             "target_param": "L"},
            {"source_param": "PK_E7_L", "target_elem": 7,
             "target_param": "L"}])
        self.assertEqual(verify_pickup(data, ("d4", "L"), ("d1", "L"),
                                       k, b_mm), [])
        found = find_pickup(data, ("d4", "L"))
        self.assertEqual(found["source"], ("d1", "L"))
        self.assertEqual(found["source_global"], "PK_E1_L")
        self.assertEqual(found["driven_global"], "PK_E7_L")

    def test_pickup_cli_load_unchanged(self):
        """A consistent Pickup loads through the real C++ code with
        byte-identical optics (links + formula apply on load)."""
        data = load_rez(USER_CAVITY)
        k = 0.5
        b_mm = _consistent_b(data, ("d4", "L"), ("d1", "L"), k)
        apply_pickup(data, ("d4", "L"), ("d1", "L"), k, b_mm)
        base = run_headless({"base_schema": load_rez(USER_CAVITY)})
        picked = run_headless({"base_schema": data})
        rb, rp = base["results"][0], picked["results"][0]
        self.assertTrue(rp["ok"], rp.get("error"))
        self.assertAlmostEqual(rp["g_T"], rb["g_T"], places=12)
        self.assertAlmostEqual(rp["g_S"], rb["g_S"], places=12)
        # Beam/waist values agree to ~1e-12 relative (a unit round-trip
        # through the global parameter can cost 1 ulp).
        for eb, ep in zip(rb["beam"], rp["beam"]):
            self.assertEqual(eb["label"], ep["label"])
            for key in ("w_T_mm", "w_S_mm"):
                self.assertLess(rel(ep[key], eb[key]), 1e-12)
        for key in ("w0_T_mm", "w0_S_mm"):
            self.assertLess(rel(rp["waist"][key], rb["waist"][key]), 1e-12)

    def test_pickup_follow_through_cli(self):
        """Changing the source global (with a consistently updated
        driven value) follows exactly like direct overrides.

        d1 = 340 mm stays stable; the direct-override run is the
        independent prediction.
        """
        data = load_rez(USER_CAVITY)
        k = 0.5
        b_mm = _consistent_b(data, ("d4", "L"), ("d1", "L"), k)
        apply_pickup(data, ("d4", "L"), ("d1", "L"), k, b_mm)
        changed = copy.deepcopy(data)
        changed["custom_params"]["PK_E1_L"]["value"] = 340.0
        changed["custom_params"]["PK_E7_L"]["value"] = 0.5 * 340.0 + b_mm
        followed = run_headless({"base_schema": changed})["results"][0]
        direct = run_headless({
            "base_schema": load_rez(USER_CAVITY),
            "mutations": [{"id": 0, "overrides": {
                "d1": {"L": 340.0},
                "d4": {"L": 0.5 * 340.0 + b_mm}}}]})["results"][0]
        self.assertTrue(followed["ok"], followed.get("error"))
        self.assertTrue(direct["ok"], direct.get("error"))
        self.assertAlmostEqual(followed["g_T"], direct["g_T"], places=9)
        self.assertAlmostEqual(followed["g_S"], direct["g_S"], places=9)
        for fb, db in zip(followed["beam"], direct["beam"]):
            self.assertEqual(fb["label"], db["label"])
            self.assertAlmostEqual(fb["w_T_mm"], db["w_T_mm"], places=9)
            self.assertAlmostEqual(fb["w_S_mm"], db["w_S_mm"], places=9)

    def test_pickup_reuses_existing_source_link(self):
        """spherical_symm.rez: M1.R is already linked to R0, so the
        Pickup reuses R0 as the formula source (no new source link)."""
        data = load_rez(os.path.join(EXAMPLES, "spherical_symm.rez"))
        k = 1.0
        b_mm = _consistent_b(data, ("L", "L"), ("M1", "R"), k)
        info = apply_pickup(data, ("L", "L"), ("M1", "R"), k, b_mm)
        self.assertEqual(info["source_global"], "R0")
        self.assertEqual(info["created_globals"], ["PK_E1_L"])
        self.assertEqual(info["links_added"], [
            {"source_param": "PK_E1_L", "target_elem": 1,
             "target_param": "L"}])
        self.assertEqual(verify_pickup(data, ("L", "L"), ("M1", "R"),
                                       k, b_mm), [])

    def test_pickup_conflicts(self):
        data = load_rez(USER_CAVITY)
        k = 0.5
        b_mm = _consistent_b(data, ("d4", "L"), ("d1", "L"), k)
        apply_pickup(data, ("d4", "L"), ("d1", "L"), k, b_mm)
        # Driven parameter is now link-driven: a second Pickup fails.
        with self.assertRaises(PickupError):
            apply_pickup(data, ("d4", "L"), ("d2", "L"), 1.0, 0.0)
        # A chain is allowed: a pickup-driven value can be a source.
        info = apply_pickup(data, ("d2", "L"), ("d4", "L"), 1.0,
                            _consistent_b(data, ("d2", "L"), ("d4", "L"),
                                          1.0))
        self.assertEqual(info["source_global"], "PK_E7_L")
        # Same parameter, unknown parameter, dimension mismatch.
        with self.assertRaises(PickupError):
            apply_pickup(data, ("d2", "L"), ("d2", "L"), 1.0, 0.0)
        with self.assertRaises(PickupError):
            apply_pickup(data, ("Nope", "L"), ("d1", "L"), 1.0, 0.0)
        with self.assertRaises(PickupError):
            apply_pickup(data, ("d3", "L"), ("M2", "Alpha"), 1.0, 0.0)
        with self.assertRaises(PickupError):
            apply_pickup(data, ("d3", "L"), ("d1", "L"), float("inf"), 0.0)
        # A driven value violating the CLI guards is refused.
        with self.assertRaises(PickupError):
            apply_pickup(data, ("d3", "L"), ("d1", "L"), -1.0, 0.0)

    def test_verify_pickup_reports_problems(self):
        data = load_rez(USER_CAVITY)
        k = 0.5
        b_mm = _consistent_b(data, ("d4", "L"), ("d1", "L"), k)
        problems = verify_pickup(data, ("d4", "L"), ("d1", "L"), k, b_mm)
        self.assertTrue(problems)  # no Pickup yet
        apply_pickup(data, ("d4", "L"), ("d1", "L"), k, b_mm)
        self.assertEqual(verify_pickup(data, ("d4", "L"), ("d1", "L"),
                                       k, b_mm), [])
        # Tamper with the stored driven value: verification complains.
        data["custom_params"]["PK_E7_L"]["value"] += 5.0
        self.assertTrue(verify_pickup(data, ("d4", "L"), ("d1", "L"),
                                      k, b_mm))
        # Wrong k also complains.
        data["custom_params"]["PK_E7_L"]["value"] -= 5.0
        self.assertTrue(verify_pickup(data, ("d4", "L"), ("d1", "L"),
                                      0.6, b_mm))

    def test_formulas_not_recalculated_on_load(self):
        """Lock-in of real application behaviour (verified against the
        binary): editing only the source global in a file does NOT
        re-derive the formula target on load -- ``Formula::calculate``
        only runs when a dependency changes interactively. So a Pickup
        file stores a *consistent snapshot*; external edits must update
        the driven value too (see ``apply_solution``).
        """
        data = load_rez(os.path.join(EXAMPLES, "global_params.rez"))
        base = run_headless({"base_schema": data})["results"][0]
        self.assertAlmostEqual(base["total_length_mm"], 250.0, places=9)
        data["custom_params"]["F0"]["value"] = 20.0  # formula: dL = F0/2
        changed = run_headless({"base_schema": data})["results"][0]
        self.assertAlmostEqual(changed["total_length_mm"], 250.0, places=9)


class TestWaistSolves(unittest.TestCase):
    def test_waist_at_m1_is_degenerate(self):
        """(a) The waist of the [M1, d1] segment is at the flat end
        mirror M1 for *any* d1 (R is infinite there), so the residual
        is identically 0: the solver returns the current value."""
        data = load_rez(USER_CAVITY)
        result = solve_waist_position(data, ("d1", "L"), "M1",
                                      ("ref", "M1", 0),
                                      bounds_si=(0.25, 0.42))
        self.assertTrue(result["converged"], result)
        self.assertAlmostEqual(result["solved_value"], D1_MM * 1e-3,
                               places=12)
        self.assertAlmostEqual(result["residual_mm"], 0.0, places=9)
        self.assertTrue(any("already satisfied" in w
                            for w in result["warnings"]))

    def test_waist_size_solves_and_rechecks(self):
        """(b) w0 at M1 = 0.12 mm with d1 as the variable; the solution
        is re-checked with a fresh, independent CLI run."""
        data = load_rez(USER_CAVITY)
        result = solve_waist_size(data, ("d1", "L"), "M1", 0.12,
                                  bounds_si=(0.33, 0.38))
        self.assertTrue(result["converged"], result)
        solved_mm = result["solved_value_display"]
        self.assertGreater(solved_mm, 360.0)
        self.assertLess(solved_mm, 372.071)
        # Independent re-check: fresh CLI run at the solved value.
        out = run_headless({
            "base_schema": data,
            "mutations": [{"id": 0,
                           "overrides": {"d1": {"L": solved_mm}}}]})
        entry = _beam(out, "M1")
        w0, z = _w0_from_entry(entry, "T")
        self.assertLess(rel(w0, 0.12), 1e-6)
        self.assertLess(result["residual_rel"], 1e-6)

    def test_waist_position_solves_and_rechecks(self):
        """(c) M4-segment waist at absolute s = 1100 mm with d1 as
        the variable; re-checked with a fresh CLI run."""
        data = load_rez(USER_CAVITY)
        result = solve_waist_position(data, ("d1", "L"), "M4", 1100.0,
                                      bounds_si=(0.25, 0.38))
        self.assertTrue(result["converged"], result)
        solved_mm = result["solved_value_display"]
        self.assertGreater(solved_mm, 290.0)
        self.assertLess(solved_mm, 300.0)
        out = run_headless({
            "base_schema": data,
            "mutations": [{"id": 0,
                           "overrides": {"d1": {"L": solved_mm}}}]})
        entry = _beam(out, "M4")
        w0, z = _w0_from_entry(entry, "T")
        positions = _plane_positions(
            data, {"d1": {"L": to_si(solved_mm, "mm")}})
        waist_s = positions["M4"] - z
        self.assertLess(rel(waist_s, 1100.0), 1e-6)

    def test_waist_position_no_solution(self):
        """The M4-segment waist never reaches M4's plane in the stable
        range (it approaches it at the stability edge): no solution,
        honestly reported with the best point found."""
        data = load_rez(USER_CAVITY)
        result = solve_waist_position(data, ("d1", "L"), "M4",
                                      ("ref", "M4", 0),
                                      bounds_si=(0.27, 0.38))
        self.assertFalse(result["converged"], result)
        self.assertIsNotNone(result["solved_value"])
        self.assertGreater(result["residual_mm"], 0.1)
        self.assertTrue(any("no sign change" in w
                            for w in result["warnings"]))

    def test_waist_size_multi_solution(self):
        """w0 at M1 = 0.15 mm has two solutions in d1 (rising and
        falling branch); the solver warns and solves the one closest
        to the current value."""
        data = load_rez(USER_CAVITY)
        result = solve_waist_size(data, ("d1", "L"), "M1", 0.15,
                                  bounds_si=(0.24, 0.38))
        self.assertTrue(result["converged"], result)
        self.assertEqual(len(result["brackets_si"]), 2)
        self.assertTrue(any("multiple" in w for w in result["warnings"]))
        solved_mm = result["solved_value_display"]
        self.assertGreater(solved_mm, 338.0)
        self.assertLess(solved_mm, 345.0)
        out = run_headless({
            "base_schema": data,
            "mutations": [{"id": 0,
                           "overrides": {"d1": {"L": solved_mm}}}]})
        w0, _ = _w0_from_entry(_beam(out, "M1"), "T")
        self.assertLess(rel(w0, 0.15), 1e-6)

    def test_waist_solve_all_unstable(self):
        data = load_rez(USER_CAVITY)
        result = solve_waist_size(data, ("d1", "L"), "M1", 0.12,
                                  bounds_si=(0.45, 0.60))
        self.assertFalse(result["converged"], result)
        self.assertIsNone(result["solved_value"])
        self.assertTrue(any("no feasible point" in w
                            for w in result["warnings"]))

    def test_waist_solve_refusals(self):
        data = load_rez(os.path.join(EXAMPLES, "global_params.rez"))
        # d1.L is link-driven: it cannot be a solve variable.
        with self.assertRaises(SolveError):
            solve_waist_size(data, ("d1", "L"), "d1", 0.1,
                             bounds_si=(0.05, 0.15))
        data = load_rez(USER_CAVITY)
        with self.assertRaises(SolveError):
            solve_waist_size(data, ("Nope", "L"), "M1", 0.1)
        with self.assertRaises(SolveError):
            solve_waist_size(data, ("d1", "L"), "M1", 0.12,
                             bounds_si=(0.38, 0.33))
        # Curvature interval crossing 0 is refused (CLI guard).
        with self.assertRaises(SolveError):
            solve_waist_size(data, ("M2", "R"), "M1", 0.12,
                             bounds_si=(-0.1, 0.6))
        with self.assertRaises(SolveError):
            solve_waist_size(data, ("d1", "L"), "M1", -0.1)
        with self.assertRaises(SolveError):
            solve_waist_size(data, ("d1", "L"), "Nope", 0.12)

    def test_apply_solution_roundtrip(self):
        """Solve, write back, reload: the file keeps the solution and
        its schema_version, and a fresh CLI run confirms the waist."""
        data = load_rez(USER_CAVITY)
        result = solve_waist_size(data, ("d1", "L"), "M1", 0.12,
                                  bounds_si=(0.33, 0.38))
        self.assertTrue(result["converged"], result)
        solved = copy.deepcopy(data)
        apply_solution(solved, ("d1", "L"), result["solved_value"])
        self.assertEqual(solved["schema_version"], "2.1")
        out = run_headless({"base_schema": solved})
        w0, _ = _w0_from_entry(_beam(out, "M1"), "T")
        self.assertLess(rel(w0, 0.12), 1e-6)
        # Write to disk and read back: the value survives in its unit.
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "data", "_test_solved.rez")
        try:
            save_rez(path, solved)
            reloaded = load_rez(path)
            self.assertAlmostEqual(
                reloaded["elements"][1]["params"]["L"]["value"],
                result["solved_value_display"], places=9)
            self.assertEqual(reloaded["elements"][1]["params"]["L"]["unit"],
                             "mm")
        finally:
            if os.path.exists(path):
                os.remove(path)
        # Refused on a driven parameter.
        driven = copy.deepcopy(data)
        apply_pickup(driven, ("d4", "L"), ("d1", "L"), 0.5,
                     _consistent_b(data, ("d4", "L"), ("d1", "L"), 0.5))
        with self.assertRaises(SolveError):
            apply_solution(driven, ("d4", "L"), 0.2)


if __name__ == "__main__":
    unittest.main()
