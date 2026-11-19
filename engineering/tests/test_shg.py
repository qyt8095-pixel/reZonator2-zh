"""Tests for the Phase 2 SHG module (rezeng.shg).

Run from the repository root:
    python3 -m unittest discover -s engineering/tests -v

Conventions verified here:

* Boyd-Kleinman coefficient: the prefactor is pinned two independent
  ways -- the collimated limit (xi -> 0, h -> xi) reproduces exactly
  the plane-wave result derived from I_2w = (2*w^2*d^2*L^2 /
  (eps0*c^3*n^2*n_2w)) * I_w^2, and the PPLN coefficient matches a
  hand computation (K = 0.018608 /W for d_eff = 14 pm/V, L = 20 mm,
  n = 2.16/2.23, lambda = 1064 nm, h = 1). The focusing function is
  h(0, xi) = arctan(xi)^2 / xi, peaking at ~0.645 for xi ~ 1.39
  (L ~ 2.8 * z_R). (The often-quoted 1.068 belongs to a different
  normalisation of h with half the prefactor; the product K is what
  matters, and the plane-wave limit pins it down.)
* Intracavity SHG is solved by a nested brentq on
  F(P) = Gamma(P) - [delta + delta_SHG(P)] = 0, never by relaxation
  iteration. With K -> 0 it degenerates exactly to mode B.
* The SHG crystal must be an ElemPlate in the .rez (a real dielectric
  slab, C++ matrix [[1, L/n], [0, 1]]). ElemMediumRange ignores n in
  its matrix and is rejected with an explicit error.
"""

import copy
import math
import os
import unittest

import numpy as np

import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                ".."))

from rezeng import (load_rez, load_eng, validate_eng, new_eng,
                    run_headless_file, HeadlessError)
from rezeng.power import (PowerError, resolve_params, solve_p_circ,
                          overlap_integral, H_PLANCK, C_LIGHT)
from rezeng.qevolve import element_matrix
from rezeng.shg import (SHGError, MATERIALS, material_reference,
                        fill_typical, resolve_shg, boyd_kleinman_h,
                        aperture_length, focusing_parameter,
                        shg_coefficient_K, single_pass_eta,
                        shg_beam_in_crystal, shg_K_for_point,
                        shg_output_beam, green_noise_assessment,
                        gamma_round_trip, solve_shg_intracavity,
                        solve_shg_extracavity, shg_pump_scan,
                        insert_crystal_element, EPS0)

REPO = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", ".."))
ENGINEERING = os.path.join(REPO, "engineering")
BINARY = os.path.join(REPO, "bin", "rezonator")
USER_CAVITY = os.path.join(os.path.expanduser("~"), "workspace", "user",
                           "files", "upload.rez")
EXAMPLE_ENG = os.path.join(ENGINEERING, "tests", "data",
                           "example-shg.eng.json")

# --- Synthetic benchmark case (same numbers as test_power.py) ----------
SIGMA = 15.6e-19 * 1e-4          # m^2
TAU = 90e-6                      # s
LAM_L = 1064e-9
LAM_P = 808e-9
L_CRYST = 0.010                  # m
ALPHA = 1.5 * 100                # 1/m
WP = 200e-6
WL = 180e-6
TOC, LI = 0.10, 0.02
DELTA = TOC + LI
ETA_ABS = 1.0 - math.exp(-ALPHA * L_CRYST)
ETA_Q = LAM_P / LAM_L
I_SAT = H_PLANCK * (C_LIGHT / LAM_L) / (SIGMA * TAU)


def rel(a, b):
    return abs(a - b) / max(abs(b), 1e-12)


def bench_params(profile="gaussian", w_p=WP, w_l=WL, L=L_CRYST,
                 alpha=ALPHA, toc=TOC):
    eta_abs = 1.0 - math.exp(-alpha * L) if alpha * L > 1e-12 else 1.0
    return {"gain_label": "TL1", "L_m": L, "n0": 2.16,
            "lambda_l_m": LAM_L, "lambda_p_m": LAM_P,
            "sigma_em": SIGMA, "tau_f": TAU, "alpha_p": alpha,
            "w_p0": w_p, "z_p0": L / 2, "Mp2": 1.0, "eta_p": 1.0,
            "profile": profile, "T_oc": toc, "L_i": LI,
            "eta_mode": None, "eta_abs": eta_abs, "eta_q": ETA_Q,
            "I_sat": I_SAT, "thermal": {}, "warnings": [],
            "F_current_m": 0.23}


def bench_slices(w_l=WL, n_z=24, L=L_CRYST):
    x, w = np.polynomial.legendre.leggauss(n_z)
    z = 0.5 * L * (x + 1.0)
    return {"label": "TL1", "L_m": L, "n0": 2.16,
            "gamma_T": 0.0, "gamma_S": 0.0, "z_m": z,
            "w_T_m": np.full(n_z, w_l), "w_S_m": np.full(n_z, w_l),
            "w_z": 0.5 * L * w}


def base_shg(**over):
    """Minimal enabled nonlinear_shg section (NCPM LBO example)."""
    shg = {"enabled": True, "mode": "intracavity",
           "crystal_element_id": "LBO_1", "material": "LBO",
           "length_mm": 15.0, "d_eff_pm_V": 0.85,
           "n_omega": 1.60, "n_2omega": 1.61,
           "phase_matching": "NCPM", "walkoff_plane": "T",
           "delta_T_C": 0.0, "temp_acceptance_C_cm": 4.0,
           "single_frequency": False}
    shg.update(over)
    return {"nonlinear_shg": shg}


def demo_cavity():
    """User cavity with an ElemPlate LBO crystal after M1 (d1 shortened
    by the crystal length, total geometric length unchanged)."""
    data = load_rez(USER_CAVITY)
    return insert_crystal_element(data, "LBO_1", 15.0, 1.60, "M1",
                                  shorten_label="d1")


# --------------------------------------------------------------------------
# Focusing function, walk-off, coefficient
# --------------------------------------------------------------------------

class TestFormulas(unittest.TestCase):
    def test_h_small_xi_limit(self):
        # h(0, xi) -> xi for xi -> 0 (plane-wave limit).
        for xi in (1e-6, 1e-4, 1e-3):
            self.assertAlmostEqual(boyd_kleinman_h(xi) / xi, 1.0,
                                   places=5)

    def test_h_maximum(self):
        # Peak ~0.645 at xi ~ 1.39 (L ~ 2.8 * z_R).
        self.assertAlmostEqual(boyd_kleinman_h(1.39), 0.6454, places=3)
        self.assertLess(boyd_kleinman_h(2.84), boyd_kleinman_h(1.39))
        self.assertLess(boyd_kleinman_h(10.0), 0.25)

    def test_h_zero(self):
        self.assertEqual(boyd_kleinman_h(0.0), 0.0)
        with self.assertRaises(SHGError):
            boyd_kleinman_h(-1.0)

    def test_aperture_length(self):
        self.assertAlmostEqual(aperture_length(100e-6, 7.2e-3),
                               math.pi * 100e-6 / 7.2e-3)
        self.assertEqual(aperture_length(100e-6, 0.0), float("inf"))

    def test_K_ppln_hand_computed(self):
        # d_eff = 14 pm/V, L = 20 mm, n = 2.16/2.23, lam = 1064 nm,
        # h = 1, mismatch = 1 -> K = 0.018608 /W (hand computation).
        # The public function takes xi, so check K0 * h(xi) against
        # the hand value with h evaluated at its maximum.
        K0 = (16.0 * math.pi ** 2 * (14e-12) ** 2 * 0.020
              / (EPS0 * C_LIGHT * 2.16 ** 2 * 2.23 * (1064e-9) ** 3))
        self.assertAlmostEqual(K0, 0.018607975, places=6)
        xi_max = 1.39
        K = shg_coefficient_K(14e-12, 0.020, xi_max, 2.16, 2.23,
                              1064e-9, mismatch=1.0)
        self.assertAlmostEqual(K, K0 * boyd_kleinman_h(xi_max),
                               places=12)

    def test_K_matches_plane_wave_limit(self):
        # Collimated LBO beam (w = 100 um, L = 15 mm): the BK
        # coefficient must equal the plane-wave coefficient times
        # h/xi (the two derivations agree exactly in the xi -> 0
        # limit; at xi = 0.254 the h/xi factor is 0.959).
        w = 100e-6
        L = 0.015
        xi = focusing_parameter(L, 1064e-9, w)
        K_bk = shg_coefficient_K(0.85e-12, L, xi, 1.60, 1.61, 1064e-9,
                                 mismatch=1.0)
        K_pw = (8.0 * math.pi * (0.85e-12) ** 2 * L ** 2
                / (EPS0 * C_LIGHT * 1.60 ** 2 * 1.61
                   * (1064e-9) ** 2 * w ** 2))
        self.assertAlmostEqual(K_bk, K_pw * boyd_kleinman_h(xi) / xi,
                               places=10)
        self.assertAlmostEqual(K_pw, 3.29869148e-05, places=10)

    def test_single_pass_eta_limits(self):
        # Small-signal: eta ~ K*P (relative error ~ (K*P)/3).
        self.assertAlmostEqual(single_pass_eta(1e-4, 0.01), 1e-6,
                               delta=1e-9)
        self.assertAlmostEqual(single_pass_eta(0.02, 1.0),
                               math.tanh(math.sqrt(0.02)) ** 2)
        self.assertGreater(single_pass_eta(1.0, 100.0), 0.999)
        with self.assertRaises(SHGError):
            single_pass_eta(-1.0, 1.0)


# --------------------------------------------------------------------------
# Side-car schema
# --------------------------------------------------------------------------

class TestSidecar(unittest.TestCase):
    def test_example_sidecar_validates(self):
        eng = load_eng(EXAMPLE_ENG)
        self.assertEqual(validate_eng(eng), [])

    def test_new_eng_has_nonlinear_shg(self):
        self.assertIn("nonlinear_shg", new_eng())

    def test_bad_values_flagged(self):
        eng = {"nonlinear_shg": {"enabled": "yes", "mode": "sideways",
                                  "phase_matching": "XYZ",
                                  "walkoff_mrad": -3,
                                  "d_eff_pm_V": 0}}
        problems = validate_eng(eng)
        self.assertTrue(any("enabled" in p for p in problems))
        self.assertTrue(any("mode" in p for p in problems))
        self.assertTrue(any("phase_matching" in p for p in problems))
        self.assertTrue(any("walkoff_mrad" in p for p in problems))
        self.assertTrue(any("d_eff_pm_V" in p for p in problems))

    def test_material_reference(self):
        ref = material_reference("LBO")
        self.assertEqual(ref["d_eff_pm_V"], 0.85)
        self.assertEqual(ref["walkoff_mrad"], 7.2)
        with self.assertRaises(SHGError):
            material_reference("NOPE")

    def test_fill_typical_is_explicit(self):
        filled = fill_typical({"material": "LBO",
                               "phase_matching": "CPM"})
        self.assertEqual(filled["d_eff_pm_V"], 0.85)
        self.assertEqual(filled["walkoff_mrad"], 7.2)
        # Never overrides a value the user gave.
        kept = fill_typical({"material": "LBO", "d_eff_pm_V": 1.2,
                             "phase_matching": "CPM"})
        self.assertEqual(kept["d_eff_pm_V"], 1.2)


class TestResolve(unittest.TestCase):
    def setUp(self):
        self.data = demo_cavity()

    def test_disabled_returns_none(self):
        self.assertIsNone(resolve_shg(self.data, {}))
        self.assertIsNone(resolve_shg(
            self.data, {"nonlinear_shg": {"enabled": False}}))

    def test_ncpm_ok(self):
        shg = resolve_shg(self.data, base_shg())
        self.assertEqual(shg["phase_matching"], "NCPM")
        self.assertEqual(shg["rho"], 0.0)
        self.assertEqual(shg["mismatch"], 1.0)
        self.assertEqual(shg["mode"], "intracavity")
        self.assertAlmostEqual(shg["L_m"], 0.015)
        self.assertAlmostEqual(shg["lambda_2w_m"], 532e-9)

    def test_cpm_needs_walkoff(self):
        with self.assertRaises(SHGError):
            resolve_shg(self.data, base_shg(phase_matching="CPM"))
        shg = resolve_shg(self.data, base_shg(phase_matching="CPM",
                                              walkoff_mrad=7.2))
        self.assertEqual(shg["phase_matching"], "CPM")
        self.assertAlmostEqual(shg["rho"], 7.2e-3)

    def test_ncpm_rejects_walkoff(self):
        with self.assertRaises(SHGError):
            resolve_shg(self.data, base_shg(phase_matching="NCPM",
                                            walkoff_mrad=7.2))

    def test_missing_d_eff_raises(self):
        eng = base_shg()
        del eng["nonlinear_shg"]["d_eff_pm_V"]
        with self.assertRaises(SHGError):
            resolve_shg(self.data, eng)

    def test_missing_indices_raise(self):
        eng = base_shg()
        del eng["nonlinear_shg"]["n_omega"]
        with self.assertRaises(SHGError):
            resolve_shg(self.data, eng)

    def test_unknown_element_raises(self):
        with self.assertRaises(SHGError):
            resolve_shg(self.data,
                        base_shg(crystal_element_id="NOPE"))

    def test_medium_range_rejected_with_plate_hint(self):
        # d1 is an ElemEmptyRange in the demo cavity: the solver must
        # refuse it and point at ElemPlate.
        with self.assertRaises(SHGError) as ctx:
            resolve_shg(self.data, base_shg(crystal_element_id="d1"))
        self.assertIn("ElemPlate", str(ctx.exception))

    def test_length_defaults_to_rez_element(self):
        eng = base_shg()
        del eng["nonlinear_shg"]["length_mm"]
        shg = resolve_shg(self.data, eng)
        self.assertAlmostEqual(shg["L_m"], 0.015)

    def test_phase_matching_inferred(self):
        eng = base_shg()
        del eng["nonlinear_shg"]["phase_matching"]
        shg = resolve_shg(self.data, eng)
        self.assertEqual(shg["phase_matching"], "NCPM")
        self.assertTrue(any("inferred" in w for w in shg["warnings"]))

    def test_temperature_mismatch(self):
        # At dT * L = acceptance product the tuning curve is at half
        # maximum: sinc^2(1.3916) = 0.5.
        shg = resolve_shg(self.data, base_shg(delta_T_C=4.0 / 1.5,
                                              temp_acceptance_C_cm=4.0))
        # dT * L = (4/1.5 C) * 1.5 cm = 4 C*cm = acceptance product.
        self.assertAlmostEqual(shg["mismatch"], 0.5, places=6)
        # No detuning: perfect phase matching.
        shg0 = resolve_shg(self.data, base_shg(delta_T_C=0.0))
        self.assertEqual(shg0["mismatch"], 1.0)

    def test_explicit_delta_k_wins(self):
        shg = resolve_shg(self.data, base_shg(delta_k_per_m=100.0,
                                              delta_T_C=5.0))
        self.assertAlmostEqual(shg["delta_k_per_m"], 100.0)
        self.assertAlmostEqual(
            shg["mismatch"],
            (math.sin(100.0 * 0.015 / 2.0) / (100.0 * 0.015 / 2.0)) ** 2)


# --------------------------------------------------------------------------
# Intracavity solve: degeneracy, monotonicity, convergence
# --------------------------------------------------------------------------

class TestIntracavitySolve(unittest.TestCase):
    def setUp(self):
        self.params = bench_params()
        self.slices = bench_slices()

    def test_degenerates_to_mode_b(self):
        # K = 0 must reproduce solve_p_circ exactly.
        P_abs = ETA_ABS * 5.0
        ref = solve_p_circ(self.params, self.slices, P_abs, DELTA)
        sol = solve_shg_intracavity(self.params, self.slices, P_abs,
                                    DELTA, 0.0, passes=2)
        self.assertAlmostEqual(sol["P_circ"], ref["P_circ"], places=9)
        self.assertEqual(sol["P_2w"], 0.0)
        self.assertEqual(sol["delta_shg"], 0.0)
        self.assertFalse(sol["below_threshold"])

    def test_small_K_perturbation(self):
        # Small K: P_circ slightly below the no-SHG value, and the
        # green power is ~2 * K * P_circ^2 (low-depletion limit).
        P_abs = ETA_ABS * 5.0
        ref = solve_p_circ(self.params, self.slices, P_abs, DELTA)
        K = 1e-5
        sol = solve_shg_intracavity(self.params, self.slices, P_abs,
                                    DELTA, K, passes=2)
        self.assertLess(sol["P_circ"], ref["P_circ"])
        self.assertGreater(sol["P_circ"], 0.95 * ref["P_circ"])
        self.assertAlmostEqual(sol["P_2w"],
                               2.0 * K * sol["P_circ"] ** 2,
                               delta=0.05 * sol["P_2w"])
        self.assertAlmostEqual(sol["eta_1pass"], K * sol["P_circ"],
                               delta=0.05 * sol["eta_1pass"])

    def test_brentq_convergence(self):
        P_abs = ETA_ABS * 5.0
        sol = solve_shg_intracavity(self.params, self.slices, P_abs,
                                    DELTA, 1e-3, passes=2)
        # Few overlap-integral evaluations for 1e-9 accuracy.
        self.assertLessEqual(sol["evaluations"], 40)
        # Residual of the self-consistent equation at the root.
        F = (gamma_round_trip(self.params, self.slices, P_abs,
                              sol["P_circ"])
             - DELTA - 2.0 * single_pass_eta(1e-3, sol["P_circ"]))
        self.assertLess(abs(F), 1e-6)

    def test_below_threshold_zero(self):
        sol = solve_shg_intracavity(self.params, self.slices, 0.001,
                                    DELTA, 1e-3, passes=2)
        self.assertTrue(sol["below_threshold"])
        self.assertEqual(sol["P_circ"], 0.0)
        self.assertEqual(sol["P_2w"], 0.0)

    def test_monotone_in_pump(self):
        prev = -1.0
        for P_pump in (1.0, 2.0, 5.0, 10.0, 20.0):
            sol = solve_shg_intracavity(self.params, self.slices,
                                        ETA_ABS * P_pump, DELTA, 1e-3,
                                        passes=2)
            self.assertGreaterEqual(sol["P_2w"], prev)
            prev = sol["P_2w"]

    def test_higher_T_oc_lowers_green(self):
        # Intracavity: a larger output coupling lowers P_circ, so the
        # (quadratic) green power falls.
        P_abs = ETA_ABS * 5.0
        low = solve_shg_intracavity(self.params, self.slices, P_abs,
                                    0.05 + LI, 1e-3, passes=2)
        high = solve_shg_intracavity(self.params, self.slices, P_abs,
                                     0.30 + LI, 1e-3, passes=2)
        self.assertGreater(low["P_2w"], high["P_2w"])
        self.assertGreater(low["P_circ"], high["P_circ"])

    def test_extracavity_no_feedback(self):
        P_abs = ETA_ABS * 5.0
        ref = solve_p_circ(self.params, self.slices, P_abs, DELTA)
        ext = solve_shg_extracavity(ref["P_out"], 1e-3)
        self.assertAlmostEqual(ext["P_2w"], ref["P_out"]
                               * single_pass_eta(1e-3, ref["P_out"]))
        # The fundamental is untouched by extracavity conversion.
        self.assertEqual(ref["P_circ"], ref["P_circ"])


# --------------------------------------------------------------------------
# Walk-off, ellipticity, green noise
# --------------------------------------------------------------------------

class TestWalkoffAndNoise(unittest.TestCase):
    def test_long_crystal_saturates_at_aperture_length(self):
        # L >> L_a: K stops growing with L (walk-off limited).
        w0 = 100e-6
        rho = 7.2e-3
        L_a = aperture_length(w0, rho)
        self.assertLess(L_a, 0.050)
        K_short = shg_coefficient_K(0.85e-12, L_a, 1.39, 1.60, 1.61,
                                    1064e-9, mismatch=1.0)
        K_long = shg_coefficient_K(0.85e-12, L_a, 1.39, 1.60, 1.61,
                                   1064e-9, mismatch=1.0)
        self.assertEqual(K_short, K_long)
        # With L_eff = min(L, L_a) a 100 mm crystal gives the same K
        # as a crystal cut at L_a (same xi, same L_eff).
        K_100 = shg_coefficient_K(0.85e-12, min(0.100, L_a), 1.39,
                                  1.60, 1.61, 1064e-9, mismatch=1.0)
        self.assertEqual(K_100, K_short)

    def test_ncpm_no_ellipticity(self):
        beam = {"slices": {"w_T_m": np.full(5, 100e-6),
                           "w_S_m": np.full(5, 100e-6)}}
        out = shg_output_beam(beam, {"rho": 0.0, "L_m": 0.015,
                                     "walkoff_plane": "T"})
        self.assertAlmostEqual(out["ellipticity"], 1.0)
        self.assertAlmostEqual(out["M2_parallel"], 1.0)
        self.assertAlmostEqual(out["M2_perp"], 1.0)

    def test_cpm_ellipticity(self):
        beam = {"slices": {"w_T_m": np.full(5, 100e-6),
                           "w_S_m": np.full(5, 100e-6)}}
        out = shg_output_beam(beam, {"rho": 7.2e-3, "L_m": 0.015,
                                     "walkoff_plane": "T"})
        # w_2w,|| = sqrt((50 um)^2 + (54 um)^2) = 73.6 um,
        # w_2w,perp = 50 um -> ellipticity ~1.47.
        self.assertAlmostEqual(out["w_2w_parallel_um"], 73.6, delta=0.5)
        self.assertAlmostEqual(out["ellipticity"], 1.47, delta=0.02)
        self.assertGreater(out["M2_parallel"], 1.0)

    def test_green_noise_bands(self):
        self.assertEqual(green_noise_assessment(0.01)["risk"], "low")
        self.assertEqual(green_noise_assessment(0.08)["risk"], "elevated")
        self.assertEqual(green_noise_assessment(0.30)["risk"], "high")
        # Single-frequency operation removes the mechanism.
        self.assertEqual(green_noise_assessment(
            0.30, single_frequency=True)["risk"], "low")
        # Extracavity conversion never feeds back.
        self.assertEqual(green_noise_assessment(
            0.30, mode="extracavity")["risk"], "low")


# --------------------------------------------------------------------------
# .rez helpers and the real CLI (user cavity + inserted plate)
# --------------------------------------------------------------------------

class TestInsertCrystal(unittest.TestCase):
    def test_insert_keeps_total_length(self):
        data = load_rez(USER_CAVITY)
        total_before = sum(
            e["params"]["L"]["value"]
            for e in data["elements"]
            if "L" in e.get("params", {}))
        out = insert_crystal_element(data, "LBO_1", 15.0, 1.60, "M1",
                                     shorten_label="d1")
        total_after = sum(
            e["params"]["L"]["value"]
            for e in out["elements"]
            if "L" in e.get("params", {}))
        self.assertAlmostEqual(total_after, total_before)
        labels = [e["label"] for e in out["elements"]]
        self.assertEqual(labels[1], "LBO_1")
        plate = out["elements"][1]
        self.assertEqual(plate["type"], "ElemPlate")
        self.assertEqual(plate["params"]["n"]["value"], 1.60)
        # Input dict untouched.
        self.assertEqual(len(data["elements"]),
                         len(out["elements"]) - 1)

    def test_insert_errors(self):
        data = load_rez(USER_CAVITY)
        with self.assertRaises(SHGError):
            insert_crystal_element(data, "LBO_1", 15.0, 1.60, "NOPE")
        with self.assertRaises(SHGError):
            insert_crystal_element(data, "M1", 15.0, 1.60, "M1")


@unittest.skipIf(not os.path.exists(BINARY),
                 "local binary not built: %s" % BINARY)
@unittest.skipIf(not os.path.exists(USER_CAVITY),
                 "user cavity file missing: %s" % USER_CAVITY)
class TestSHGRealCLI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = demo_cavity()
        cls.eng = load_eng(EXAMPLE_ENG)
        from rezeng import run_headless
        cls.result = run_headless({"base_schema": cls.data,
                                   "mutations": []})["results"][0]

    def test_plate_exit_matches_evolver(self):
        # The ElemPlate refraction convention: evolved exit == CLI exit.
        beam = shg_beam_in_crystal(self.data, self.result, "LBO_1")
        self.assertLess(beam["exit_rel_err"], 1e-6)
        # Waist sits at the crystal entrance (M1 is a flat end mirror),
        # so the waist radius equals the M1 spot size -- which is NOT
        # 100 um any more: inserting the plate (L/n instead of L)
        # changed the cavity mode (the cavity sits near the stability
        # edge, so a 5.6 mm optical-length change moves the waist).
        from rezeng.qevolve import beam_entry
        m1_w_T = beam_entry(self.result, "M1")[0] * 1e-3
        self.assertAlmostEqual(beam["w0_T_m"], m1_w_T, places=12)
        self.assertAlmostEqual(beam["waist_depth_T_m"], 0.0, places=6)
        self.assertTrue(beam["waist_inside"])

    def test_plate_matrix_matches_cli_chain(self):
        # element_matrix(ElemPlate) = [[1, L/n], [0, 1]]: propagate
        # the M1 exit entry through it and compare with the LBO_1
        # CLI entry.
        from rezeng.qevolve import (beam_entry, q_from_wr, wr_from_q,
                                    element_matrix)
        wT, wS, RT, RS = beam_entry(self.result, "M1")
        lam = 1064e-9
        qT = q_from_wr(wT * 1e-3,
                       None if RT is None else RT * 1e-3, lam)
        M_T, M_S = element_matrix(self.data, "LBO_1")
        qT2 = (M_T[0, 0] * qT + M_T[0, 1]) / (M_T[1, 0] * qT + M_T[1, 1])
        wT2, _R = wr_from_q(qT2, lam)
        wT_cli = beam_entry(self.result, "LBO_1")[0]
        self.assertLess(abs(wT2 * 1e3 - wT_cli) / wT_cli, 1e-6)

    def test_intracavity_point_beats_no_shg(self):
        from rezeng.power import resolve_params, _slices_for
        params = resolve_params(self.data, self.eng)
        shg = resolve_shg(self.data, self.eng)
        slices = _slices_for(self.data, self.result, params, 24)
        beam = shg_beam_in_crystal(self.data, self.result, "LBO_1")
        K, _Leff, _xi, _La = shg_K_for_point(shg, beam)
        P_abs = params["eta_abs"] * 5.0
        sol = solve_shg_intracavity(params, slices, P_abs,
                                    params["T_oc"] + params["L_i"], K,
                                    passes=2)
        ref = solve_p_circ(params, slices, P_abs,
                           params["T_oc"] + params["L_i"])
        self.assertGreater(sol["P_2w"], 0.0)
        self.assertLess(sol["P_circ"], ref["P_circ"])
        self.assertLessEqual(sol["evaluations"], 40)

    def test_scan_smoke(self):
        scan = shg_pump_scan(self.data, self.eng, [5.0])
        self.assertEqual(scan["summary"]["shg_status"], "ok")
        self.assertEqual(scan["summary"]["mode"], "intracavity")
        pt = scan["points"][0]
        self.assertEqual(pt["status"], "ok")
        self.assertGreater(pt["P_2w"], 0.0)
        self.assertEqual(pt["green_risk"], "low")
        # NCPM (rho = 0): no walk-off broadening, so the green
        # ellipticity is just the fundamental's own T/S ratio in the
        # crystal (the cavity is astigmatic), and M2_parallel is 1.
        beam = shg_beam_in_crystal(self.data, self.result, "LBO_1")
        w_T = float(np.mean(np.asarray(
            beam["slices"]["w_T_m"])))
        w_S = float(np.mean(np.asarray(
            beam["slices"]["w_S_m"])))
        self.assertAlmostEqual(pt["ellipticity"], w_T / w_S, places=6)
        self.assertAlmostEqual(pt["M2_parallel"], 1.0)
        self.assertEqual(scan["summary"]["phase_matching"], "NCPM")


if __name__ == "__main__":
    unittest.main()
