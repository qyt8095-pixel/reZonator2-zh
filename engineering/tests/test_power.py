"""Tests for the Phase 2 power solver (rezeng.qevolve + rezeng.power).

Run from the repository root:
    python3 -m unittest discover -s engineering/tests -v

Conventions verified here (against ``src/core/Elements.cpp`` and the
headless CLI on the user's real cavity):

* the ray vector is geometric ``(r, theta)``; element matrices are
  air-to-air; the CLI ``beam`` entry of an element is its ``(w, R)``
  at the element's *exit* plane, air side; a mirror entry is
  post-reflection;
* the GRIN submatrix is the C++ ``calcSubmatrices`` ``TS1_`` and the
  exit refraction ``R_out = [[1, 0], [0, n0]]`` maps the medium-side
  ``q`` back to air (``q_air = q_med / n0``).

Benchmark discrepancy (documented, not fudged): with the Gemini
review's own benchmark numbers (sigma_e = 15.6e-19 cm^2, tau_f = 90 us,
w_p = 200 um, w_c = 180 um, delta = 2% + T_oc = 10% = 0.12) the spec's
Rigrod formula gives P_th ~ 0.12 W absorbed (~0.15 W incident for a
10 mm crystal at alpha_p = 1.5/cm), NOT the 1.2-2.0 W quoted in the
review -- a ~10x decimal slip in the review. The tests assert the
formula-derived value and guard against anyone "fixing" the formula
to hit 1.2 W.
"""

import math
import os
import unittest

import numpy as np

import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                ".."))

from rezeng import (load_rez, load_eng, validate_eng, run_headless_file,
                    HeadlessError)
from rezeng.qevolve import (QevolveError, solve_n2, grin_gamma, calc_focus,
                            q_from_wr, wr_from_q, waist_from_q,
                            element_grin_params, find_gain_element,
                            beam_entry, entrance_entry, element_matrix,
                            evolve_element, crystal_slices)
from rezeng.power import (PowerError, resolve_params, param_F_current,
                          overlap_eta_mode, mean_mode_radius,
                          mode_a_threshold, mode_a_output, pump_radius,
                          overlap_integral, solve_p_circ, small_signal_gain,
                          analytic_overlap, higher_order_gains, two_mode_m2,
                          multimode_threshold, thermal_kappa,
                          thermal_focal_lengths, pump_scan, toc_scan,
                          H_PLANCK, C_LIGHT)

REPO = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", ".."))
ENGINEERING = os.path.join(REPO, "engineering")
BINARY = os.path.join(REPO, "bin", "rezonator")
USER_CAVITY = os.path.join(os.path.expanduser("~"), "workspace", "user",
                           "files", "upload.rez")
EXAMPLE_ENG = os.path.join(ENGINEERING, "tests", "data",
                           "example-power.eng.json")

# --- Benchmark (Nd:YVO4, 808 -> 1064 nm; Gemini review numbers) --------
SIGMA = 15.6e-19 * 1e-4          # m^2 (15.6e-19 cm^2)
TAU = 90e-6                      # s
LAM_L = 1064e-9
LAM_P = 808e-9
L_CRYST = 0.010                  # m (synthetic uniform crystal)
ALPHA = 1.5 * 100                # 1/m (1.5 /cm)
WP = 200e-6
WL = 180e-6
TOC, LI = 0.10, 0.02
DELTA = TOC + LI
ETA_ABS = 1.0 - math.exp(-ALPHA * L_CRYST)     # 0.7769
ETA_Q = LAM_P / LAM_L                          # 0.7594
I_SAT = H_PLANCK * (C_LIGHT / LAM_L) / (SIGMA * TAU)  # ~1.33e7 W/m^2
# Formula-derived benchmark values (verified by two independent
# derivations in /tmp/power_check.py):
P_TH_ABS = 0.1195               # W absorbed
P_TH_INC = P_TH_ABS / ETA_ABS   # 0.1538 W incident
ETA_MODE_GAUSS = 0.6948         # derived differential-slope overlap
SLOPE_A = 0.3416                # mode A slope vs incident pump


def rel(a, b):
    return abs(a - b) / max(abs(b), 1e-12)


def bench_params(profile="gaussian", w_p=WP, w_l=WL, L=L_CRYST,
                 alpha=ALPHA, toc=TOC, eta_mode=None):
    """Resolved-params dict for the synthetic uniform benchmark case."""
    eta_abs = 1.0 - math.exp(-alpha * L) if alpha * L > 1e-12 else 1.0
    return {"gain_label": "TL1", "L_m": L, "n0": 2.16,
            "lambda_l_m": LAM_L, "lambda_p_m": LAM_P,
            "sigma_em": SIGMA, "tau_f": TAU, "alpha_p": alpha,
            "w_p0": w_p, "z_p0": L / 2, "Mp2": 1.0, "eta_p": 1.0,
            "profile": profile, "T_oc": toc, "L_i": LI,
            "eta_mode": eta_mode, "eta_abs": eta_abs, "eta_q": ETA_Q,
            "I_sat": I_SAT, "thermal": {}, "warnings": [],
            "F_current_m": 0.23}


def bench_slices(w_l=WL, n_z=24, L=L_CRYST):
    """Uniform synthetic slices (constant mode radius, GL nodes)."""
    x, w = np.polynomial.legendre.leggauss(n_z)
    z = 0.5 * L * (x + 1.0)
    return {"label": "TL1", "L_m": L, "n0": 2.16,
            "gamma_T": 0.0, "gamma_S": 0.0, "z_m": z,
            "w_T_m": np.full(n_z, w_l), "w_S_m": np.full(n_z, w_l),
            "w_z": 0.5 * L * w}


def _propagate(q, M, lam_m):
    """q after an ABCD matrix (scalar q, numpy arrays are fine too)."""
    A, B, C, D = M[0, 0], M[0, 1], M[1, 0], M[1, 1]
    return (A * q + B) / (C * q + D)


# --------------------------------------------------------------------------
# q(z) evolver vs the C++ headless CLI (user's real cavity)
# --------------------------------------------------------------------------

@unittest.skipIf(not os.path.exists(BINARY),
                 "local binary not built: %s" % BINARY)
@unittest.skipIf(not os.path.exists(USER_CAVITY),
                 "user cavity file missing: %s" % USER_CAVITY)
class TestQevolveCLI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = load_rez(USER_CAVITY)
        out = run_headless_file(USER_CAVITY)
        cls.result = out["results"][0]
        assert cls.result["ok"] and cls.result["stable"]
        cls.beam = {e["label"]: e for e in cls.result["beam"]}
        cls.labels = [e["label"] for e in cls.result["beam"]]
        cls.lam_m = 1064e-9

    def test_grin_constants(self):
        # User crystal: F = 230 mm, L = 27 mm, n = 2.16.
        n2 = solve_n2(0.027, 2.16, 0.230)
        self.assertLess(rel(n2, 158.155), 1e-3)
        gamma, _ = grin_gamma(0.027, 2.16, 0.230)
        self.assertLess(rel(gamma, 8.5569), 1e-3)
        # Thin-lens approximation is 0.9% off -- the exact bisection is
        # what the C++ code uses, so it must be used here too.
        approx = 1.0 / math.sqrt(2.16 * 0.230 * 0.027)
        self.assertLess(rel(approx, 8.6343), 1e-3)
        self.assertGreater(abs(approx - gamma) / gamma, 5e-3)
        # Round trip F -> n2 -> F (bisection tolerance ~1e-8 on the
        # equation residual, so the round trip is ~1e-6, not 1e-9).
        self.assertLess(rel(calc_focus(0.027, 2.16, n2), 0.230), 1e-6)

    def test_tl1_exit_matches_cli(self):
        # The evolved TL1 exit (w, R) must match the CLI entry.
        z = np.linspace(0.0, 0.027, 13)
        slices = crystal_slices(self.data, self.result, "TL1", z)
        self.assertLess(slices["exit_rel_err"], 1e-6)
        # The entrance is the previous element's (d3) exit entry.
        self.assertEqual(slices["entrance"][0],
                         self.beam["d3"]["w_T_mm"])
        self.assertEqual(slices["entrance"][1],
                         self.beam["d3"]["w_S_mm"])

    def test_chain_consistency(self):
        # Propagate each CLI entry through the NEXT element's full
        # air-to-air matrix: it must reproduce the next CLI entry.
        # This pins the convention "CLI entry = element exit plane,
        # air side; mirror entries are post-reflection".
        for prev_label, label in zip(self.labels, self.labels[1:]):
            M_T, M_S = element_matrix(self.data, label)
            for plane, w_key, R_key in (
                    ("T", "w_T_mm", "R_T_mm"),
                    ("S", "w_S_mm", "R_S_mm")):
                entry = self.beam[prev_label]
                q_in = q_from_wr(entry[w_key] * 1e-3,
                                 None if entry[R_key] is None
                                 else entry[R_key] * 1e-3, self.lam_m)
                M = M_T if plane == "T" else M_S
                w_out, R_out = wr_from_q(_propagate(q_in, M, self.lam_m),
                                         self.lam_m)
                nxt = self.beam[label]
                self.assertLess(rel(w_out * 1e3, nxt[w_key]), 1e-6,
                                "%s -> %s plane %s w" % (prev_label, label,
                                                         plane))
                if nxt[R_key] is not None:
                    self.assertLess(rel(R_out * 1e3, nxt[R_key]), 1e-6,
                                    "%s -> %s plane %s R"
                                    % (prev_label, label, plane))
                else:
                    # CLI reports a flat wavefront: the evolved R
                    # must be (numerically) infinite.
                    self.assertGreater(abs(R_out), 1e6,
                                       "%s -> %s plane %s: CLI R is null "
                                       "but evolved R = %g mm"
                                       % (prev_label, label, plane,
                                          R_out * 1e3))

    def test_air_side_convention_negative_control(self):
        # If the exit refraction R_out were skipped (medium-side q
        # reported as air-side), the TL1 exit R would be wrong by a
        # factor ~n0 -- the test above must be able to tell. Check
        # that the wrong convention really does fail here.
        L_m, n0, g_T, g_S = element_grin_params(self.data, "TL1")
        wT_in, wS_in, RT_in, RS_in = entrance_entry(self.data,
                                                     self.result, "TL1")
        q_in_T = q_from_wr(wT_in * 1e-3,
                           None if RT_in is None else RT_in * 1e-3,
                           self.lam_m)
        ev = evolve_element(q_in_T, q_in_T, self.lam_m, L_m, n0,
                            g_T, g_S, np.array([L_m]))
        # Medium-side R (no R_out): recompute q at the exit face
        # without dividing by n0.
        from rezeng.qevolve import _m1_matrices
        A, B, C, D = _m1_matrices(np.array([L_m]), n0, g_T)
        q_med = (A[0] * q_in_T + B[0]) / (C[0] * q_in_T + D[0])
        _w, R_med = wr_from_q(q_med, self.lam_m / n0)
        cli_R = self.beam["TL1"]["R_T_mm"]
        self.assertIsNotNone(cli_R)
        self.assertGreater(rel(R_med * 1e3, cli_R), 0.01,
                           "medium-side R must NOT match the CLI "
                           "(else the convention test is blind)")
        # ... while the air-side R does match.
        self.assertLess(rel(ev["exit_R_T_m"] * 1e3, cli_R), 1e-6)

    def test_q_roundtrip_and_waist(self):
        for w_mm, R_mm in ((0.1, None), (0.2, 500.0), (0.5, -450.0)):
            q = q_from_wr(w_mm * 1e-3,
                          None if R_mm is None else R_mm * 1e-3,
                          self.lam_m)
            w2, R2 = wr_from_q(q, self.lam_m)
            self.assertLess(rel(w2, w_mm * 1e-3), 1e-12)
            if R_mm is None:
                self.assertTrue(math.isinf(R2))
            else:
                self.assertLess(rel(R2, R_mm * 1e-3), 1e-12)
        # At the flat end mirror M1 the waist is at the mirror itself.
        entry = self.beam["M1"]
        q = q_from_wr(entry["w_T_mm"] * 1e-3, None, self.lam_m)
        w0, z0 = waist_from_q(q, self.lam_m)
        self.assertLess(rel(w0, entry["w_T_mm"] * 1e-3), 1e-9)
        self.assertLess(abs(z0), 1e-9)

    def test_flat_mirror_is_identity(self):
        M_T, M_S = element_matrix(self.data, "M1")
        np.testing.assert_allclose(M_T, np.eye(2))
        np.testing.assert_allclose(M_S, np.eye(2))


# --------------------------------------------------------------------------
# Mode A (Rigrod)
# --------------------------------------------------------------------------

class TestModeA(unittest.TestCase):
    def test_threshold_benchmark(self):
        p = bench_params()
        p_th = mode_a_threshold(p, WP, WL)
        self.assertLess(rel(p_th, P_TH_INC), 0.01)
        self.assertLess(rel(p_th * ETA_ABS, P_TH_ABS), 0.01)

    def test_threshold_is_not_ten_times(self):
        # The Gemini review quoted 1.2-2.0 W; the spec's own formula
        # gives ~0.12 W absorbed. Guard against "fixing" the formula
        # to match the quoted range.
        p = bench_params()
        self.assertLess(mode_a_threshold(p, WP, WL), 0.2)

    def test_eta_mode_derived(self):
        self.assertLess(rel(overlap_eta_mode(WP, WL, "gaussian"),
                            ETA_MODE_GAUSS), 1e-3)
        # Top-hat pump, same waists: tanh(rho^2) * (w_l/w_p)^2.
        rho2 = (WP / WL) ** 2
        expect = math.tanh(rho2) * (WL / WP) ** 2
        self.assertLess(rel(overlap_eta_mode(WP, WL, "tophat"), expect),
                        1e-12)

    def test_slope_below_quantum_limit(self):
        p = bench_params()
        out = mode_a_output(p, 5.0 * P_TH_INC, WP, WL)
        self.assertLess(rel(out["slope"], SLOPE_A), 0.02)
        # Quantum-defect ceiling: slope can never exceed lam_p/lam_l.
        self.assertLess(out["slope"], LAM_P / LAM_L)
        self.assertGreater(out["P_out"], 0.0)

    def test_below_threshold_zero(self):
        p = bench_params()
        out = mode_a_output(p, 0.5 * P_TH_INC, WP, WL)
        self.assertEqual(out["P_out"], 0.0)
        self.assertTrue(out["below_threshold"])


# --------------------------------------------------------------------------
# Mode B (overlap integral) -- three-limits consistency
# --------------------------------------------------------------------------

class TestModeB(unittest.TestCase):
    def test_overlap_zero_gaussian_matches_analytic(self):
        p = bench_params()
        O0 = overlap_integral(p, bench_slices(), 0.0)
        self.assertLess(rel(O0, analytic_overlap(WP, WL)), 0.005)

    def test_overlap_zero_tophat_matches_analytic(self):
        p = bench_params(profile="tophat")
        O0 = overlap_integral(p, bench_slices(), 0.0)
        rho = WP / WL
        expect = (1.0 - math.exp(-2.0 * rho ** 2)) / (math.pi * WP ** 2)
        self.assertLess(rel(O0, expect), 0.005)

    def test_threshold_consistency_mode_a_vs_b(self):
        # Mode B small-signal gain at the mode A threshold equals delta.
        p = bench_params()
        G0 = small_signal_gain(p, bench_slices(), P_TH_ABS)
        self.assertLess(rel(G0, DELTA), 0.005)

    def test_thin_beam_limit(self):
        # w_c << w_p: mode B threshold is half the uniform-pump
        # (top-hat) analytic threshold.
        p = bench_params()
        sl = bench_slices(w_l=WP / 100.0)
        G0 = small_signal_gain(p, sl, 1.0)     # gain per watt absorbed
        p_th_thin = DELTA / G0
        p_th_tophat = (DELTA * H_PLANCK * (C_LIGHT / LAM_P)
                       * math.pi * WP ** 2 / (2.0 * SIGMA * TAU))
        self.assertLess(rel(p_th_thin, 0.5 * p_th_tophat), 0.005)

    def test_large_pump_tophat_limit(self):
        # w_p = 10 * w_c, top-hat pump: the mode sees a uniform pump
        # density 1/(pi*w_p^2) over its area, so O_0 -> 1/(pi*w_p^2).
        w_p = 10.0 * WL
        p = bench_params(profile="tophat", w_p=w_p)
        sl = bench_slices()
        O0 = overlap_integral(p, sl, 0.0)
        expect = 1.0 / (math.pi * w_p ** 2)
        self.assertLess(rel(O0, expect), 0.01)

    def test_near_threshold_output_matches_mode_a(self):
        # At 1.05x threshold the two modes agree to <1%; the
        # distributed model is slightly superlinear further above
        # threshold (documented, not a bug), so the tight bound is
        # only asserted near threshold.
        p = bench_params()
        sl = bench_slices()
        for s, tol in ((1.05, 0.01), (1.2, 0.05)):
            sol = solve_p_circ(p, sl, s * P_TH_ABS, DELTA)
            ma = mode_a_output(p, s * P_TH_ABS / ETA_ABS, WP, WL)
            self.assertLess(rel(sol["P_out"], ma["P_out"]), tol,
                            "s=%.2f: mode B %.4g vs mode A %.4g"
                            % (s, sol["P_out"], ma["P_out"]))

    def test_differential_slope_near_threshold(self):
        p = bench_params()
        sl = bench_slices()

        def pout_B(s):
            return solve_p_circ(p, sl, s * P_TH_ABS, DELTA)["P_out"]

        s1, s2 = 1.01, 1.10
        P1 = s1 * P_TH_ABS / ETA_ABS
        P2 = s2 * P_TH_ABS / ETA_ABS
        secant = (pout_B(s2) - pout_B(s1)) / (P2 - P1)
        ma = mode_a_output(p, P1, WP, WL)
        self.assertLess(rel(secant, ma["slope"]), 0.03)

    def test_below_threshold_zero(self):
        p = bench_params()
        sol = solve_p_circ(p, bench_slices(), 0.5 * P_TH_ABS, DELTA)
        self.assertEqual(sol["P_out"], 0.0)
        self.assertTrue(sol["below_threshold"])

    def test_small_signal_gain_linear_in_pump(self):
        p = bench_params()
        sl = bench_slices()
        g1 = small_signal_gain(p, sl, 0.05)
        g2 = small_signal_gain(p, sl, 0.10)
        self.assertLess(rel(g2, 2.0 * g1), 1e-9)


# --------------------------------------------------------------------------
# Higher-order modes
# --------------------------------------------------------------------------

class TestHigherOrder(unittest.TestCase):
    def _operating_point(self, s=2.0):
        p = bench_params()
        sl = bench_slices()
        sol = solve_p_circ(p, sl, s * P_TH_ABS, DELTA)
        return p, sl, sol

    def test_hom_gain_below_fundamental(self):
        p, sl, sol = self._operating_point(2.0)
        hom = higher_order_gains(p, sl, 2.0 * P_TH_ABS, sol["P_circ"],
                                 DELTA)
        # TEM_00 sits at threshold (net 0) by construction; the HOMs
        # are below threshold at 2x pump.
        self.assertLess(hom["net10"], 0.0)
        self.assertLess(hom["net01"], 0.0)
        self.assertLess(hom["G10"], small_signal_gain(
            p, sl, 2.0 * P_TH_ABS))

    def test_multimode_threshold_above_fundamental(self):
        # Build scan points directly (no CLI): HOM net gain crosses
        # zero only well above the fundamental threshold.
        p = bench_params()
        sl = bench_slices()
        points = []
        for s in (1.2, 2.0, 3.0, 5.0, 8.0, 12.0, 20.0):
            P_abs = s * P_TH_ABS
            sol = solve_p_circ(p, sl, P_abs, DELTA)
            hom = higher_order_gains(p, sl, P_abs, sol["P_circ"], DELTA)
            points.append({"status": "ok",
                           "P_pump_W": P_abs / ETA_ABS,
                           "net10": hom["net10"], "net01": hom["net01"]})
        P_mm, mode = multimode_threshold(points)
        self.assertIsNotNone(P_mm)
        self.assertGreater(P_mm, P_TH_INC)
        self.assertIn(mode, ("net10", "net01"))

    def test_m2_single_mode_near_threshold(self):
        p, sl, sol = self._operating_point(1.2)
        m2 = two_mode_m2(p, sl, 1.2 * P_TH_ABS, DELTA, sol["P_circ"])
        self.assertLess(abs(m2["M2_x"] - 1.0), 1e-9)
        self.assertLess(abs(m2["M2_y"] - 1.0), 1e-9)
        self.assertEqual(m2["P_10"], 0.0)

    def test_m2_grows_above_multimode_threshold(self):
        # At 30x threshold the HOM net gain is positive and the
        # two-mode balance gives M^2 > 1 (still <= 3: only TEM_10/01
        # are included, so M^2 <= 1 + 2 = 3 by construction).
        p = bench_params()
        sl = bench_slices()
        sol = solve_p_circ(p, sl, 30.0 * P_TH_ABS, DELTA)
        m2 = two_mode_m2(p, sl, 30.0 * P_TH_ABS, DELTA, sol["P_circ"])
        self.assertGreater(m2["M2_x"], 1.0)
        self.assertLessEqual(m2["M2_x"], 3.0)
        self.assertEqual(m2["method"], "two-mode balance")


# --------------------------------------------------------------------------
# Thermal lens
# --------------------------------------------------------------------------

def _thermal_params(**thermal):
    p = bench_params()
    p["thermal"] = thermal
    return p


class TestThermal(unittest.TestCase):
    def test_calibration_anchor(self):
        p = _thermal_params(F0_mm=None, anchor_F_ref_mm=230.0,
                            anchor_P_ref_W=5.0)
        kT, kS, source, warnings, F0_m = thermal_kappa(p)
        self.assertTrue(source.startswith("calibration anchor"))
        self.assertEqual(warnings, [])
        self.assertTrue(math.isinf(F0_m))
        # 1/F(5 W) = 1/inf + kappa * eta_abs * 5 = 1/0.23.
        F_T, F_S, _F_cli, _src, _w = thermal_focal_lengths(p, 5.0)
        self.assertLess(rel(F_T, 0.230), 1e-9)
        self.assertLess(rel(F_S, 0.230), 1e-9)
        # Focal length shortens with pump power.
        F2, _F2s, _c2, _s2, _w2 = thermal_focal_lengths(p, 10.0)
        self.assertLess(F2, F_T)

    def test_reverse_anchor(self):
        p = _thermal_params(P_nom_W=5.0)
        kT, kS, source, warnings, _F0 = thermal_kappa(p)
        self.assertTrue(source.startswith("reverse anchor"))
        self.assertTrue(any("reverse-anchored" in w for w in warnings))
        # Current .rez F (0.23 m) is assumed to be the 5 W value.
        F_T, _F_S, _c, _s, _w = thermal_focal_lengths(p, 5.0)
        self.assertLess(rel(F_T, 0.230), 1e-9)

    def test_physics_estimate(self):
        p = _thermal_params(eta_h=0.24, dn_dT_per_K=3.0e-6,
                            K_c_W_per_mK=5.1)
        kT, kS, source, warnings, _F0 = thermal_kappa(p)
        self.assertEqual(source, "physics estimate")
        expect = 0.24 * 3.0e-6 / (2.0 * math.pi * 5.1 * WP ** 2)
        self.assertLess(rel(kT, expect), 1e-12)

    def test_explicit_kappa_wins(self):
        p = _thermal_params(kappa_th_per_W=0.5, anchor_F_ref_mm=230.0,
                            anchor_P_ref_W=5.0, P_nom_W=5.0)
        kT, _kS, source, _w, _F0 = thermal_kappa(p)
        self.assertEqual(source, "explicit kappa_th")
        self.assertLess(rel(kT, 0.5), 1e-12)

    def test_no_thermal_model(self):
        p = _thermal_params()
        kT, _kS, source, _w, _F0 = thermal_kappa(p)
        self.assertEqual(source, "fixed F")
        self.assertEqual(kT, 0.0)
        F_T, _F_S, _c, _s, _w = thermal_focal_lengths(p, 10.0)
        self.assertLess(rel(F_T, 0.230), 1e-12)


# --------------------------------------------------------------------------
# Side-car schema
# --------------------------------------------------------------------------

class TestSidecar(unittest.TestCase):
    def test_example_sidecar_validates(self):
        eng = load_eng(EXAMPLE_ENG)
        self.assertEqual(validate_eng(eng), [])
        self.assertIn("gain_and_pump", eng)

    def test_new_eng_has_gain_and_pump(self):
        from rezeng import new_eng
        eng = new_eng()
        self.assertIn("gain_and_pump", eng)
        self.assertEqual(validate_eng(eng), [])

    def test_bad_gain_and_pump_values_flagged(self):
        eng = {"format_version": 1, "gain_and_pump": {
            "crystal": {"sigma_em_cm2": -1.0},
            "pump": {"profile": "donut", "Mp2": 0.5},
            "cavity": {"T_oc": 1.5},
            "thermal": {"kappa_th_per_W": -0.1}}}
        problems = validate_eng(eng)
        self.assertTrue(any("sigma_em_cm2" in s for s in problems))
        self.assertTrue(any("profile" in s for s in problems))
        self.assertTrue(any("Mp2" in s for s in problems))
        self.assertTrue(any("T_oc" in s for s in problems))
        self.assertTrue(any("kappa_th_per_W" in s for s in problems))

    def test_missing_fields_raise(self):
        data = load_rez(USER_CAVITY)
        # resolve_params reports the first missing essential field;
        # nothing is invented. (lambda_p_nm is checked first.)
        with self.assertRaises(PowerError) as cm:
            resolve_params(data, {})
        self.assertIn("lambda_p_nm", str(cm.exception))

    def test_resolve_example(self):
        data = load_rez(USER_CAVITY)
        eng = load_eng(EXAMPLE_ENG)
        params = resolve_params(data, eng)
        self.assertEqual(params["gain_label"], "TL1")
        self.assertLess(rel(params["L_m"], 0.027), 1e-12)
        self.assertLess(rel(params["sigma_em"], SIGMA), 1e-12)
        self.assertLess(rel(params["I_sat"], I_SAT), 1e-9)
        self.assertLess(rel(params["eta_abs"], 1.0), 1e-9)
        # The reverse-anchoring warning comes from thermal_kappa
        # (called by the scans), not from resolve_params itself.
        _kT, _kS, source, warnings, _F0 = thermal_kappa(params)
        self.assertTrue(source.startswith("reverse anchor"))
        self.assertTrue(any("reverse-anchored" in w for w in warnings))


# --------------------------------------------------------------------------
# Scans (CLI monkeypatched: one canned stable result)
# --------------------------------------------------------------------------

@unittest.skipIf(not os.path.exists(BINARY),
                 "local binary not built: %s" % BINARY)
@unittest.skipIf(not os.path.exists(USER_CAVITY),
                 "user cavity file missing: %s" % USER_CAVITY)
class TestScans(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = load_rez(USER_CAVITY)
        cls.eng = load_eng(EXAMPLE_ENG)
        out = run_headless_file(USER_CAVITY)
        cls.base_result = out["results"][0]
        assert cls.base_result["ok"] and cls.base_result["stable"]

    def _fake(self, unstable_below_mm=None):
        calls = []

        def run_headless(request, binary=None, timeout=None):
            calls.append(request)
            results = []
            for mut in request.get("mutations") or [{"id": 0}]:
                r = dict(self.base_result)
                r["id"] = mut["id"]
                F_mm = None
                for _label, params in (mut.get("overrides") or {}).items():
                    if "F" in params:
                        F_mm = params["F"]
                if (unstable_below_mm is not None and F_mm is not None
                        and F_mm < unstable_below_mm):
                    r = dict(r, ok=True, stable=False, beam=None,
                             waist=None)
                results.append(r)
            return {"version": 1, "trip_type": "SW", "warnings": [],
                    "results": results}

        return run_headless, calls

    def test_pump_scan_one_cli_call(self):
        import rezeng.power as power_mod
        fake, calls = self._fake()
        old = power_mod.run_headless
        power_mod.run_headless = fake
        try:
            out = pump_scan(self.data, self.eng, [1.0, 2.0, 5.0, 10.0])
        finally:
            power_mod.run_headless = old
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(calls[0]["mutations"]), 4)
        self.assertEqual(len(out["points"]), 4)
        self.assertEqual(out["summary"]["n_ok"], 4)
        # Monotone P_out (all above threshold here) and no instability.
        pouts = [p["P_out_B"] for p in out["points"]]
        self.assertTrue(all(b >= a for a, b in zip(pouts, pouts[1:])))
        self.assertTrue(all(p > 0 for p in pouts))

    def test_instability_flagged_not_aborted(self):
        import rezeng.power as power_mod
        fake, calls = self._fake(unstable_below_mm=150.0)
        old = power_mod.run_headless
        power_mod.run_headless = fake
        try:
            # Reverse anchoring (F = 230 mm at 5 W): F(P) = 1.15/P m,
            # so 8 W -> 144 mm and 10 W -> 115 mm are unstable.
            out = pump_scan(self.data, self.eng,
                            [1.0, 2.0, 4.0, 6.0, 8.0, 10.0])
        finally:
            power_mod.run_headless = old
        self.assertEqual(len(calls), 1)
        by_p = {p["P_pump_W"]: p for p in out["points"]}
        self.assertEqual(by_p[8.0]["status"], "unstable")
        self.assertEqual(by_p[8.0]["flag"], "thermal_instability")
        self.assertEqual(by_p[8.0]["P_out_B"], 0.0)
        self.assertEqual(by_p[10.0]["status"], "unstable")
        self.assertEqual(by_p[6.0]["status"], "ok")
        self.assertEqual(out["summary"]["n_unstable"], 2)
        self.assertEqual(out["summary"]["n_ok"], 4)

    def test_toc_scan_finds_optimum(self):
        import rezeng.power as power_mod
        fake, calls = self._fake()
        old = power_mod.run_headless
        power_mod.run_headless = fake
        try:
            out = toc_scan(self.data, self.eng, 5.0,
                           [0.02, 0.05, 0.10, 0.15, 0.20, 0.30])
        finally:
            power_mod.run_headless = old
        self.assertEqual(len(calls), 1)
        pts = out["points"]
        self.assertEqual(len(pts), 6)
        t_opt = out["summary"]["T_opt"]
        self.assertIsNotNone(t_opt)
        self.assertGreater(t_opt, pts[0]["T_oc"])
        self.assertLess(t_opt, pts[-1]["T_oc"])
        best = max(pts, key=lambda p: p["P_out_B"])
        self.assertEqual(best["T_oc"], t_opt)
        # P_out rises then falls: unimodal around the optimum.
        pouts = [p["P_out_B"] for p in pts]
        i = pouts.index(max(pouts))
        self.assertTrue(all(b >= a for a, b in zip(pouts[:i], pouts[1:i + 1])))
        self.assertTrue(all(b <= a for a, b in zip(pouts[i:], pouts[i + 1:])))

    def test_pump_scan_real_cli_no_evolver_warning(self):
        # Regression: the q(z) evolver must use the *mutated* F of
        # each scan point, not the base .rez F. At 2 W the scan moves
        # F to 575 mm (base 230 mm); with the base F the exit check
        # disagrees by ~85% and a warning is emitted.
        out = pump_scan(self.data, self.eng, [2.0, 5.0])
        self.assertEqual(out["summary"]["n_ok"], 2)
        self.assertFalse(any("evolver exit disagrees" in w
                             for w in out["warnings"]),
                         out["warnings"])
        for pt in out["points"]:
            self.assertLess(pt["exit_rel_err"], 1e-6)


if __name__ == "__main__":
    unittest.main()
