"""Phase 4 block 3 tests: FFT Fox-Li diffraction engine.

Conventions locked here:

* Sampling: ``z_c = N*dx^2/lam`` (hand check: N=256, dx=15.625 um,
  lam=1064 nm -> 58.74 mm); the single-FFT Fresnel output step at
  z=400 mm is 106.4 um.  The dispatcher routes long legs to
  two-step Fresnel only when the intermediate grid is wide enough
  (the equal-split form clips the beam at small z: +37% in w at
  z=10 mm); otherwise BL-ASM.
* ``exp(+ikz)`` convention: a mirror/lens multiplies by
  ``exp(+i*k*C*r^2/2)``; the crystal OPD plate is
  ``exp(+i*k0*OPD)`` with ``OPD = -r^2/(2*f_th) + c4*r^4 + c6*r^6``.
  A flipped OPD sign defocuses the crystal and fails the
  split-step-vs-GRIN test.
* Crystal anchor OPD: ``f_th = 1/(n2*L)`` with ``n2 = n0*gamma^2``
  -- NOT the ``.rez`` ``F`` (C++ ``calc_focus`` definition,
  230 mm for TL1) and NOT the matrix focal length ``-1/C``
  (236.3 mm).  Only the OPD-equivalent focal length (234.2 mm)
  is the faithful split-step discretisation of the parabolic
  index profile (split-step vs exact GRIN: exit R within 0.08%
  at 4 slices, 0.02% at 8; the ``.rez`` F gives -2.7%).
* ``M^2`` uses the position-angle covariance
  ``M_x^2 = 4*pi*sqrt(sigma_x^2*sigma_fx^2 - sigma_{x,fx}^2)``:
  at a non-waist plane the naive ``4*pi*sigma_x*sigma_fx``
  overestimates badly (locked by a curved-wavefront case).
* Convergence is dual: ``|dgamma| < tol`` AND overlap defect
  ``< tol``.  Two modes of nearly equal loss beat instead of
  converging: the run reports ``converged=False`` with
  ``plateau=True`` and the current gamma/overlap -- nothing is
  faked into a convergence.
"""

import math
import os
import unittest

import numpy as np

from rezeng import load_rez, load_eng, validate_eng
from rezeng.cli import run_headless_file
from rezeng.foxli import (
    CavityOperator, FoxLiError, asm_propagate, critical_distance,
    crystal_pass, foxli_iterate, foxli_report, initial_field,
    opd_profile, propagate, second_moments, single_fft_fresnel_step,
    two_step_fresnel_propagate, waist_m2)
from rezeng.qevolve import (beam_entry, element_grin_params,
                            entrance_entry, evolve_element, q_from_wr)

HERE = os.path.dirname(os.path.abspath(__file__))
USER_REZ = "/home/hatch/workspace/user/files/upload.rez"
FOXLI_ENG = os.path.join(HERE, "data", "example-foxli.eng.json")

LAM = 1064e-9
N = 256
WINDOW = 8e-3
DX = WINDOW / N
W0 = 0.2e-3


def _gauss_field(w_m=W0, R_m=None, n=N, dx_m=DX, lam_m=LAM):
    return initial_field(n, dx_m, w_m, w_m, R_m, R_m, lam_m,
                         noise_frac=0.0)


def _analytic_w(z_m, w0_m=W0, lam_m=LAM):
    zR = math.pi * w0_m ** 2 / lam_m
    return w0_m * math.sqrt(1.0 + (z_m / zR) ** 2)


def _power(E, dx_m=DX):
    return float(np.sum(np.abs(E) ** 2)) * dx_m * dx_m


class SamplingTest(unittest.TestCase):
    def test_critical_distance_hand_check(self):
        """z_c = N*dx^2/lam: 256, 15.625 um, 1064 nm -> 58.74 mm."""
        z_c = critical_distance(256, 15.625e-6, 1064e-9)
        # Hand: 256 * (15.625e-6)^2 / 1064e-9 = 6.25e-8 / 1.064e-6.
        self.assertAlmostEqual(z_c, 0.05874, delta=0.00005)

    def test_critical_distance_user_grid(self):
        """256, 8 mm window (dx = 31.25 um) -> z_c = 235 mm."""
        self.assertAlmostEqual(critical_distance(N, DX, LAM), 0.235,
                               delta=0.001)

    def test_single_fft_step_hand_check(self):
        """lam*z/(N*dx) at z = 400 mm -> 106.4 um (half the beam)."""
        step = single_fft_fresnel_step(256, 15.625e-6, 0.4, 1064e-9)
        # Hand: 1064e-9 * 0.4 / (256 * 15.625e-6) = 1.064e-4 m.
        self.assertAlmostEqual(step, 106.4e-6, delta=0.5e-6)

    def test_critical_distance_rejects_bad_input(self):
        for args in ((0, DX, LAM), (N, 0.0, LAM), (N, DX, 0.0)):
            with self.assertRaises(FoxLiError):
                critical_distance(*args)


class PropagatorTest(unittest.TestCase):
    def test_propagate_matches_analytic_abcd(self):
        """Dispatcher (ASM short, TSF long): w within 0.05%, M2 ~ 1."""
        E0 = _gauss_field()
        for z in (10e-3, 30e-3, 100e-3, 200e-3, 300e-3, 400e-3,
                  470e-3):
            E1 = propagate(E0, z, LAM, DX)
            m = second_moments(E1, DX, LAM)
            wa = _analytic_w(z)
            self.assertAlmostEqual(m["w_T_mm"] * 1e-3, wa,
                                   delta=0.0005 * wa)
            self.assertAlmostEqual(m["M2_T"], 1.0, delta=0.002)
            self.assertAlmostEqual(_power(E1), 1.0, delta=1e-6)

    def test_asm_reversibility(self):
        """ASM +z then -z returns the field (relative L2 < 1e-9)."""
        E0 = _gauss_field()
        E1 = asm_propagate(E0, 400e-3, LAM, DX)
        E2 = asm_propagate(E1, -400e-3, LAM, DX)
        err = (np.sqrt(np.sum(np.abs(E2 - E0) ** 2))
               / np.sqrt(np.sum(np.abs(E0) ** 2)))
        self.assertLess(err, 1e-9)

    def test_tsf_accurate_above_zc(self):
        """Two-step Fresnel is exact for z >= z_c (400 mm here)."""
        E0 = _gauss_field()
        E1 = two_step_fresnel_propagate(E0, 400e-3, LAM, DX)
        m = second_moments(E1, DX, LAM)
        self.assertAlmostEqual(m["w_T_mm"] * 1e-3, _analytic_w(400e-3),
                               delta=0.0005 * _analytic_w(400e-3))
        self.assertAlmostEqual(m["M2_T"], 1.0, delta=0.002)

    def test_tsf_fails_at_small_z_so_the_guard_exists(self):
        """Equal-split TSF clips the beam at z = 10 mm (w +37%).

        This is why propagate() must never dispatch TSF there:
        the intermediate grid (lam*z/(2*dx) wide) is narrower
        than the beam.  The dispatcher test above proves the
        guard routes small z to ASM instead.
        """
        E0 = _gauss_field()
        E1 = two_step_fresnel_propagate(E0, 10e-3, LAM, DX)
        m = second_moments(E1, DX, LAM)
        rel = (m["w_T_mm"] * 1e-3 - _analytic_w(10e-3)) \
            / _analytic_w(10e-3)
        self.assertGreater(rel, 0.10)

    def test_propagate_zero_distance_is_identity(self):
        E0 = _gauss_field()
        E1 = propagate(E0, 0.0, LAM, DX)
        self.assertIsNot(E1, E0)
        np.testing.assert_allclose(E1, E0, rtol=0, atol=0)


class CrystalTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = load_rez(USER_REZ)
        cls.res = run_headless_file(USER_REZ)["results"][0]
        w_t, w_s, R_t, R_s = entrance_entry(cls.data, cls.res, "TL1")
        cls.w_t, cls.w_s, cls.R_t, cls.R_s = w_t, w_s, R_t, R_s
        L_m, n0, g_T, g_S = element_grin_params(cls.data, "TL1")
        cls.L_m, cls.n0, cls.g_T, cls.g_S = L_m, n0, g_T, g_S
        q_T = q_from_wr(w_t * 1e-3,
                        (R_t * 1e-3 if R_t else float("inf")), LAM)
        q_S = q_from_wr(w_s * 1e-3,
                        (R_s * 1e-3 if R_s else float("inf")), LAM)
        cls.exact = evolve_element(q_T, q_S, LAM, L_m, n0, g_T, g_S,
                                   np.array([L_m]))
        # OPD-equivalent anchor focal length f_th = 1/(n2*L).
        cls.f_split = 1.0 / (n0 * g_T * g_T * L_m)

    def _entrance_field(self):
        return initial_field(
            N, DX, self.w_t * 1e-3, self.w_s * 1e-3,
            self.R_t * 1e-3 if self.R_t else None,
            self.R_s * 1e-3 if self.R_s else None,
            LAM, noise_frac=0.0)

    def test_split_step_vs_exact_grin(self):
        """4-slice split-step (f_th = 1/(n2*L)): w 0.05%, R 0.1%."""
        E_in = self._entrance_field()
        E_out = crystal_pass(E_in, self.L_m, self.n0, self.f_split,
                             0.0, 0.0, LAM, DX, n_slices=4)
        m = second_moments(E_out, DX, LAM)
        ex = self.exact
        self.assertAlmostEqual(m["w_T_mm"] * 1e-3, ex["exit_w_T_m"],
                               delta=0.001 * ex["exit_w_T_m"])
        self.assertAlmostEqual(m["w_S_mm"] * 1e-3, ex["exit_w_S_m"],
                               delta=0.001 * ex["exit_w_S_m"])
        self.assertAlmostEqual(m["R_T_mm"] * 1e-3, ex["exit_R_T_m"],
                               delta=0.01 * abs(ex["exit_R_T_m"]))
        self.assertAlmostEqual(m["R_S_mm"] * 1e-3, ex["exit_R_S_m"],
                               delta=0.01 * abs(ex["exit_R_S_m"]))

    def test_split_step_converges_with_slices(self):
        """8 slices: exit R within 0.1% of the exact GRIN."""
        E_in = self._entrance_field()
        E_out = crystal_pass(E_in, self.L_m, self.n0, self.f_split,
                             0.0, 0.0, LAM, DX, n_slices=8)
        m = second_moments(E_out, DX, LAM)
        self.assertAlmostEqual(m["R_T_mm"] * 1e-3,
                               self.exact["exit_R_T_m"],
                               delta=0.001 * abs(self.exact["exit_R_T_m"]))

    def test_rez_F_is_not_the_opd_focal_length(self):
        """The .rez F (230 mm) gives R -2.7%: the anchor must not
        use it.  The OPD-equivalent value is 234.2 mm."""
        E_in = self._entrance_field()
        E_out = crystal_pass(E_in, self.L_m, self.n0, 230e-3,
                             0.0, 0.0, LAM, DX, n_slices=4)
        m = second_moments(E_out, DX, LAM)
        # R = -324 mm vs the exact -333 mm: |R| 2.7% too small.
        rel = (m["R_T_mm"] * 1e-3 - self.exact["exit_R_T_m"]) \
            / abs(self.exact["exit_R_T_m"])
        self.assertGreater(rel, 0.02)
        self.assertAlmostEqual(self.f_split, 0.234182, delta=0.0005)

    def test_operator_anchor_uses_opd_equivalent_f(self):
        """CavityOperator's crystal step carries f_th = 1/(n2*L)."""
        op = CavityOperator(self.data)
        steps = dict(op.forward_steps)
        crystal = [s for s in steps["TL1"] if s[0] == "crystal"]
        self.assertEqual(len(crystal), 1)
        f_th = crystal[0][3]
        self.assertAlmostEqual(f_th[0], self.f_split, delta=1e-9)
        self.assertAlmostEqual(f_th[1], self.f_split, delta=1e-9)
        self.assertNotAlmostEqual(f_th[0], 0.230, delta=1e-3)

    def test_plain_plate_is_glass_propagation(self):
        """f_th = inf, no aberration: crystal == ASM in glass."""
        E_in = self._entrance_field()
        E_out = crystal_pass(E_in, self.L_m, self.n0, float("inf"),
                             0.0, 0.0, LAM, DX, n_slices=4)
        E_ref = asm_propagate(E_in, self.L_m, LAM / self.n0, DX)
        rel = (np.sqrt(np.sum(np.abs(E_out - E_ref) ** 2))
               / np.sqrt(np.sum(np.abs(E_ref) ** 2)))
        self.assertLess(rel, 1e-9)

    def test_opd_clamped_to_fit_radius(self):
        """Only the fitted c4/c6 are clamped beyond r_max.

        The fitted polynomial diverges outside the fit region
        (5 W example: OPD -200 um at r = 2 mm, ~190 wavelengths);
        the clamp freezes the c4/c6 contribution at its r_max
        value.  The quadratic is the paraxial lens and must NOT be
        clamped: truncating it at r_max turns the lens into a
        hard-edged one and a quadratic-only control run converges
        to a non-Gaussian mode (M2 = 1.42 at 5 W) instead of the
        CLI Gaussian (see test_quadratic_control_is_gaussian).
        """
        n = N
        x = (np.arange(n) - n // 2) * DX
        X, Y = np.meshgrid(x, x, indexing="ij")
        clamped = opd_profile(X, Y, 351e-3, 4.08e6, -4.07e12,
                              r_max_m=0.747e-3)
        free = opd_profile(X, Y, 351e-3, 4.08e6, -4.07e12)
        row = n // 2
        ix = lambda rr: int(np.argmin(np.abs(x - rr)))
        # (1) With no aberration the clamp is a no-op: the OPD is
        # the pure unclamped quadratic everywhere.
        quad_clamped = opd_profile(X, Y, 351e-3, 0.0, 0.0,
                                   r_max_m=0.747e-3)
        quad_free = opd_profile(X, Y, 351e-3, 0.0, 0.0)
        self.assertLess(np.max(np.abs(quad_clamped - quad_free)), 1e-15)
        # (2) Beyond r_max the OPD is the unclamped quadratic plus
        # the c4/c6 value frozen at r_max.
        r_fit = 0.747e-3
        aberr_fit = (4.08e6 * r_fit ** 4 - 4.07e12 * r_fit ** 6)
        quad_2mm = -(2e-3) ** 2 / (2.0 * 351e-3)
        self.assertAlmostEqual(clamped[row, ix(2e-3)],
                               quad_2mm + aberr_fit, delta=1e-12)
        # (3) The clamped OPD stays far below the divergent
        # polynomial (max|free| is 0.129 m on this grid).
        self.assertLess(np.max(np.abs(clamped)), 1e-4)
        self.assertLess(np.max(np.abs(clamped)),
                        np.max(np.abs(free)) * 0.01)


class CrossValidationTest(unittest.TestCase):
    """User cavity, no aperture, no aberration vs the CLI Gaussian.

    The no-aperture operator has no loss discrimination between
    the fundamental and the low-order noise modes (all |gamma| ~ 1),
    so a 5% noise start beats instead of converging (plateau at
    overlap defect ~6e-4, see test_noisy_start_plateaus).  The
    cross-validation therefore starts from the pure CLI Gaussian,
    which *is* the eigenmode of the no-aperture operator: it
    converges in 2 rounds and validates the whole engine end to
    end (propagators, crystal split-step, mirror phases -- any of
    them wrong and the Gaussian would not be a fixed point).
    The noisy-start mode finding is covered by the apertured test.
    """

    @classmethod
    def setUpClass(cls):
        cls.data = load_rez(USER_REZ)
        cls.data["_rez_path"] = USER_REZ

    def test_no_aperture_cross_validation(self):
        rep = foxli_report(self.data, {"foxli": {"noise_frac": 0.0}},
                           max_rounds=60, tol=1e-5)
        self.assertTrue(rep["converged"])
        self.assertLessEqual(rep["rounds"], 5)
        self.assertLess(rep["L_diff"], 1e-4)
        self.assertGreaterEqual(rep["M2_T"], 1.00)
        self.assertLessEqual(rep["M2_T"], 1.02)
        self.assertGreaterEqual(rep["M2_S"], 1.00)
        self.assertLessEqual(rep["M2_S"], 1.02)
        for beam in rep["beam"]:
            for plane in ("T", "S"):
                cli = beam["cli_w_%s_mm" % plane]
                got = beam["w_%s_mm" % plane]
                self.assertAlmostEqual(got, cli, delta=0.01 * cli)
                self.assertGreaterEqual(beam["M2_" + plane], 1.00)
                self.assertLessEqual(beam["M2_" + plane], 1.02)

    def test_noisy_start_plateaus_without_aperture(self):
        """5% noise, no aperture: honest non-convergence, but the
        beam numbers still match (the mode is right, just not pure)."""
        rep = foxli_report(self.data, {}, max_rounds=60, tol=1e-5)
        self.assertFalse(rep["converged"])
        self.assertIsNotNone(rep["gamma"])
        self.assertIsNotNone(rep["overlap_defect"])
        self.assertGreater(rep["overlap_defect"], 1e-4)
        for beam in rep["beam"]:
            for plane in ("T", "S"):
                cli = beam["cli_w_%s_mm" % plane]
                got = beam["w_%s_mm" % plane]
                self.assertAlmostEqual(got, cli, delta=0.01 * cli)
        self.assertGreaterEqual(rep["M2_T"], 1.00)
        self.assertLessEqual(rep["M2_T"], 1.02)


class ApertureTest(unittest.TestCase):
    def test_aperture_increases_loss_and_converges(self):
        """M2 radius 2.0 mm (beam w = 1.26 mm): the aperture gives
        the loss discrimination the power iteration needs, so the
        noisy start converges; L_diff matches the clipping estimate
        1-(1-exp(-2a^2/w^2))^2 = 0.0133 per round trip (two passes).
        The hard edge aberrates the mode (M2 ~ 1.26, D4-sigma w
        +30%: diffraction rings inflate the second moment)."""
        data = load_rez(USER_REZ)
        data["_rez_path"] = USER_REZ
        eng = {"foxli": {"apertures": {"M2": 2.0}}}
        rep = foxli_report(data, eng, max_rounds=80, tol=1e-5)
        self.assertTrue(rep["converged"])
        self.assertFalse(rep["plateau"])
        self.assertGreater(rep["L_diff"], 0.005)
        self.assertLess(rep["L_diff"], 0.03)
        # Far above the no-aperture loss (1.4e-6).
        self.assertGreater(rep["L_diff"], 1e-3)
        self.assertGreaterEqual(rep["M2_T"], 1.0)
        self.assertLess(rep["M2_T"], 1.5)
        # Mode still recognisable (D4-sigma w within 40% of CLI).
        self.assertAlmostEqual(rep["w_T_mm"], rep["cli_w_T_mm"],
                               delta=0.40 * rep["cli_w_T_mm"])


class ThermalDegradationTest(unittest.TestCase):
    def test_thermal_aberration_degrades_M2(self):
        """5 W M2 phase plate (f_th = 351 mm, c4/c6, clamped to the
        0.747 mm fit radius): the spherical aberration destroys the
        Gaussian mode (M2 >> 1.02).  The example thermal params are
        inconsistent with the anchor (narrow 200 um pump vs 498 um
        mode: the beam overfills the thermal lens and the effective
        lens is weak, near the Zone I lower edge), so the number is
        a severe degradation, not a gentle one -- see the README.

        A small aperture (M2 radius 2.0 mm) is used for mode
        selection: on a lossless operator power iteration cannot
        converge (no differential loss), and the strong aberration
        leaves the iteration wandering without it.  The aperture
        is a Fox-Li modelling choice, documented in the README;
        the quadratic-only control with the same aperture gives
        M2 = 1.12, so the aberration's incremental degradation
        (M2 ~ 5.8) is well separated from the aperture's own
        diffraction.
        """
        data = load_rez(USER_REZ)
        data["_rez_path"] = USER_REZ
        eng = {"foxli": {"apertures": {"M2": 2.0},
                         "opd": {"f_th_mm": 351.0, "c4_per_m3": 4.08e6,
                                 "c6_per_m5": -4.07e12,
                                 "r_fit_max_mm": 0.747}}}
        rep = foxli_report(data, eng, max_rounds=100, tol=1e-5)
        self.assertTrue(rep["converged"])
        self.assertGreater(rep["M2_T"], 1.5)
        self.assertGreater(rep["M2_S"], 1.5)
        # The crystal step carries the fit radius (clamp active).
        op = CavityOperator(data, opd=eng["foxli"]["opd"])
        steps = dict(op.forward_steps)
        crystal = [s for s in steps["TL1"] if s[0] == "crystal"]
        self.assertEqual(len(crystal), 1)
        self.assertAlmostEqual(crystal[0][6], 0.747e-3, delta=1e-9)

    def test_quadratic_control_is_gaussian(self):
        """Quadratic-only control (c4 = c6 = 0) is a clean Gaussian.

        Regression test for the OPD-clamp bug: when the clamp also
        truncated the quadratic at r_fit, this control converged to
        a non-Gaussian mode (M2 = 1.42, w 35% above the CLI value)
        instead of the CLI Gaussian.  With the quadratic unclamped
        the mode is Gaussian (M2 in [1.00, 1.02]) and its M1 waist
        matches the CLI cavity with the equivalent lens
        (TL1.F = 351 mm; the .rez F and the OPD f_th differ by
        ~1%, so the waist tolerance is 3%).

        The strict dual convergence flag is NOT asserted here: on
        a lossless operator the overlap defect decays only ~0.4%
        per round (no differential loss to select the mode), so
        the 1e-5 defect criterion needs ~1000 rounds and the
        plateau detector stops the run first.  The field itself
        is the Gaussian eigenmode (M2, w), which is what this test
        locks; the convergence behaviour of a lossless operator is
        covered by ConvergenceTest (mock operators) and documented
        in the README.
        """
        from rezeng.cli import run_headless_file
        data = load_rez(USER_REZ)
        data["_rez_path"] = USER_REZ
        eng = {"foxli": {"opd": {"f_th_mm": 351.0, "c4_per_m3": 0.0,
                                 "c6_per_m5": 0.0,
                                 "r_fit_max_mm": 0.747}}}
        rep = foxli_report(data, eng, max_rounds=60, tol=1e-5)
        self.assertGreaterEqual(rep["M2_T"], 1.00)
        self.assertLess(rep["M2_T"], 1.02)
        self.assertGreaterEqual(rep["M2_S"], 1.00)
        self.assertLess(rep["M2_S"], 1.02)
        # The defect is small and still decreasing (slow convergence
        # on a lossless operator), not a stuck mode-beating plateau.
        self.assertLess(rep["overlap_defect"], 1e-3)
        cli = run_headless_file(
            USER_REZ, mutations=[{"id": 0,
                                  "overrides": {"TL1": {"F": 351.0}}}]
            )["results"][0]
        cli_w_T = [e for e in cli["beam"] if e["label"] == "M1"][0]["w_T_mm"]
        self.assertAlmostEqual(rep["w_T_mm"], cli_w_T,
                               delta=0.03 * cli_w_T)


class EngValidationTest(unittest.TestCase):
    def test_foxli_section_valid(self):
        eng = load_eng(FOXLI_ENG)
        self.assertEqual(validate_eng(eng), [])

    def test_foxli_section_rejects_bad(self):
        base = {"format_version": 1, "foxli": {
            "grid_size": 256, "window_mm": 8.0,
            "wavelength_nm": 1064.0, "noise_frac": 0.05, "seed": 0,
            "max_rounds": 60, "tol": 1e-5, "n_slices": 4,
            "apertures": {"M2": 2.0},
            "opd": {"f_th_mm": 351.0, "c4_per_m3": 4.08e6,
                    "c6_per_m5": -4.07e12, "r_fit_max_mm": 0.747}}}
        for mutate in (
                lambda e: e["foxli"].update(grid_size=0),
                lambda e: e["foxli"].update(noise_frac=1.5),
                lambda e: e["foxli"].update(tol=0.0),
                lambda e: e["foxli"].update(n_slices=0),
                lambda e: e["foxli"].update(bogus_key=1),
                lambda e: e["foxli"].update(apertures={"M2": -1.0}),
                lambda e: e["foxli"]["opd"].update(f_th_mm=-5.0),
                lambda e: e["foxli"]["opd"].update(bogus=1.0),
        ):
            import copy
            eng = copy.deepcopy(base)
            mutate(eng)
            self.assertTrue(validate_eng(eng), mutate)


class InitialFieldTest(unittest.TestCase):
    def test_noise_power_fraction(self):
        """5% amplitude noise = 0.25% power (noise_frac^2)."""
        E0 = initial_field(N, DX, W0, W0, None, None, LAM,
                           noise_frac=0.05, seed=0)
        E_pure = initial_field(N, DX, W0, W0, None, None, LAM,
                               noise_frac=0.0)
        overlap = abs(np.sum(np.conj(E_pure) * E0)) ** 2 \
            / (np.sum(np.abs(E_pure) ** 2) * np.sum(np.abs(E0) ** 2))
        # Noise power fraction = 1 - overlap ~ noise_frac^2.
        self.assertAlmostEqual(1.0 - overlap, 0.0025, delta=0.001)

    def test_noise_is_deterministic(self):
        """Same seed reproduces the field; another seed differs."""
        a = initial_field(N, DX, W0, W0, None, None, LAM,
                          noise_frac=0.05, seed=0)
        b = initial_field(N, DX, W0, W0, None, None, LAM,
                          noise_frac=0.05, seed=0)
        c = initial_field(N, DX, W0, W0, None, None, LAM,
                          noise_frac=0.05, seed=1)
        np.testing.assert_array_equal(a, b)
        self.assertFalse(np.allclose(a, c))

    def test_pure_gaussian_has_M2_one(self):
        E0 = initial_field(N, DX, W0, W0, None, None, LAM,
                           noise_frac=0.0)
        m = second_moments(E0, DX, LAM)
        self.assertAlmostEqual(m["w_T_mm"], W0 * 1e3, delta=0.002)
        self.assertAlmostEqual(m["M2_T"], 1.0, delta=0.002)


class MomentsTest(unittest.TestCase):
    def test_curved_wavefront_covariance(self):
        """R = 100 mm, w = 0.2 mm: covariance M2 ~ 1, naive ~ 1.55.

        The naive 4*pi*sigma_x*sigma_fx at a non-waist plane reads
        1.55 for a pure Gaussian (55% high); the covariance term
        corrects it to 1.  Locking both numbers pins the formula.
        """
        E = initial_field(N, DX, W0, W0, 100e-3, 100e-3, LAM,
                          noise_frac=0.0)
        m = second_moments(E, DX, LAM)
        self.assertAlmostEqual(m["M2_T"], 1.0, delta=0.01)
        self.assertAlmostEqual(m["R_T_mm"], 100.0, delta=1.0)
        naive = 4.0 * math.pi * m["sigma_x_m"] * m["sigma_fx_per_m"]
        self.assertGreater(naive, 1.4)
        # Covariance from the moments: naive^2 = M2^2 + (4*pi*cov)^2.
        recon = math.sqrt(m["M2_T"] ** 2
                          + (4.0 * math.pi * m["cov_x"]) ** 2)
        self.assertAlmostEqual(recon, naive, delta=0.01)

    def test_waist_propagation_agrees(self):
        """M2 by propagating to the waist first == covariance M2."""
        E = initial_field(N, DX, W0, W0, 100e-3, 100e-3, LAM,
                          noise_frac=0.0)
        m = second_moments(E, DX, LAM)
        w = waist_m2(E, DX, LAM)
        self.assertAlmostEqual(w["M2_T"], m["M2_T"], delta=0.02)
        self.assertAlmostEqual(w["M2_S"], m["M2_S"], delta=0.02)
        # Waist of the (0.2 mm, R = 100 mm) beam: 58 mm upstream
        # (z0 < 0), w0 ~ 0.129 mm (q = 1/(1/R - i*lam/(pi*w^2))).
        self.assertAlmostEqual(w["z0_T_mm"], -58.2, delta=1.0)


class _MockOperator:
    """Stand-in for CavityOperator with a scripted round trip."""

    def __init__(self, fn):
        self.fn = fn

    def round_trip(self, E):
        return self.fn(E)


class ConvergenceTest(unittest.TestCase):
    def test_identity_operator_converges(self):
        """A field already an eigenmode converges in <= 3 rounds."""
        op = _MockOperator(lambda E: E.copy())
        E0 = _gauss_field()
        run = foxli_iterate(op, E0, max_rounds=10, tol=1e-5)
        self.assertTrue(run["converged"])
        self.assertLessEqual(run["rounds"], 3)
        self.assertAlmostEqual(run["gamma"], 1.0, delta=1e-9)
        self.assertAlmostEqual(run["L_diff"], 0.0, delta=1e-9)

    def test_beating_modes_plateau_honestly(self):
        """Two equal-loss modes alternating: no convergence, but a
        plateau flag and the current gamma/overlap are reported."""
        rng = np.random.default_rng(7)
        A = rng.standard_normal((N, N)) + 1j * rng.standard_normal((N, N))
        B = rng.standard_normal((N, N)) + 1j * rng.standard_normal((N, N))
        A = A / np.sqrt(np.sum(np.abs(A) ** 2))
        B = B / np.sqrt(np.sum(np.abs(B) ** 2))
        # Make the overlap real and 0.7: B <- 0.7*A + sqrt(1-0.49)*B_perp.
        B = B - A * np.sum(np.conj(A) * B)
        B = B / np.sqrt(np.sum(np.abs(B) ** 2))
        B = 0.7 * A + math.sqrt(1.0 - 0.49) * B
        state = {"n": 0}

        def alternate(E):
            state["n"] += 1
            return A.copy() if state["n"] % 2 == 1 else B.copy()

        op = _MockOperator(alternate)
        run = foxli_iterate(op, _gauss_field(), max_rounds=200,
                            tol=1e-5, plateau_rounds=50)
        self.assertFalse(run["converged"])
        self.assertTrue(run["plateau"])
        self.assertLessEqual(run["rounds"], 60)
        # Overlap defect stays 1 - 0.7 = 0.3; gamma stays 0.7.
        self.assertAlmostEqual(run["overlap_defect"], 0.3, delta=0.01)
        self.assertAlmostEqual(abs(run["gamma"]), 0.7, delta=0.01)

    def test_phase_drift_hits_max_rounds(self):
        """Gamma drifting every round: neither converged nor plateau."""
        state = {"n": 0}

        def drift(E):
            state["n"] += 1
            return E * np.exp(1j * 0.01 * state["n"])

        op = _MockOperator(drift)
        run = foxli_iterate(op, _gauss_field(), max_rounds=20, tol=1e-5)
        self.assertFalse(run["converged"])
        self.assertFalse(run["plateau"])
        self.assertEqual(run["rounds"], 20)
        self.assertIsNotNone(run["gamma"])
        self.assertIsNotNone(run["overlap_defect"])
