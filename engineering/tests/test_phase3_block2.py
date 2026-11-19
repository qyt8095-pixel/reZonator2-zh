"""Tests for Phase 3 block 2: Monte Carlo tolerance simulation and
reverse fitting (measured spots -> thermal-lens D_th).

Run: ``python3 -m unittest discover -s tests`` (from engineering/).
"""

import math
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rezeng import (MonteCarloError, ReverseError, load_eng, load_rez,
                    run_montecarlo, wilson_interval, fit_plane,
                    synthetic_measurements, working_zone_bounds)
from rezeng.montecarlo import (_prcc, _spearman, _validate_tolerances,
                               sample_perturbations)
from rezeng.reverse import _ModelEvaluator, model_spot

HERE = os.path.dirname(os.path.abspath(__file__))
USER_REZ = "/home/hatch/workspace/user/files/upload.rez"
SYMM_LINKED = os.path.join(os.path.dirname(HERE), "..", "bin", "examples",
                           "spherical_symm.rez")
MC_ENG = os.path.join(HERE, "data", "example-mc.eng.json")
REVERSE_ENG = os.path.join(HERE, "data", "example-reverse.eng.json")

TOL_SMALL = [
    {"label": "d1", "alias": "L", "kind": "length",
     "distribution": "normal", "sigma": 0.0005},
    {"label": "M2", "alias": "R", "kind": "relative",
     "distribution": "uniform", "half_width": 0.01},
    {"label": "TL1", "alias": "F", "kind": "dioptric",
     "distribution": "normal", "sigma": 0.05},
]


class TestWilsonInterval(unittest.TestCase):
    def test_zero_unstable(self):
        # p-hat = 0, N = 1000: Wilson upper bound ~0.38% (the review's
        # number); a normal approximation would report [0, 0].
        lo, hi = wilson_interval(0, 1000)
        self.assertEqual(lo, 0.0)
        self.assertGreater(hi, 0.0037)
        self.assertLess(hi, 0.0039)

    def test_half(self):
        # p-hat = 0.5, N = 1000: [0.469, 0.531] (hand-computed).
        lo, hi = wilson_interval(500, 1000)
        self.assertAlmostEqual(lo, 0.469, places=2)
        self.assertAlmostEqual(hi, 0.531, places=2)

    def test_small_n_hand_computed(self):
        # k = 10, n = 100, z = 1.96: centre = 0.119208, margin =
        # 0.061854, denom = 1.038416 -> [0.0552, 0.1743].
        lo, hi = wilson_interval(10, 100)
        self.assertAlmostEqual(lo, 0.0552, places=3)
        self.assertAlmostEqual(hi, 0.1743, places=3)

    def test_invalid(self):
        with self.assertRaises(MonteCarloError):
            wilson_interval(0, 0)
        with self.assertRaises(MonteCarloError):
            wilson_interval(5, 4)
        with self.assertRaises(MonteCarloError):
            wilson_interval(-1, 10)


class TestSampling(unittest.TestCase):
    def setUp(self):
        self.data = load_rez(USER_REZ)

    def test_rayleigh_cone_moments(self):
        # 2D cone: E[theta^2] = 2 sigma^2; the applied in-plane
        # component theta*cos(phi) is exactly N(0, sigma^2).
        variables = _validate_tolerances(self.data, [
            {"label": "M2", "alias": "Alpha", "kind": "angle",
             "distribution": "rayleigh", "sigma": 0.0005}])
        _samples, draws = sample_perturbations(variables, 20000, seed=3)
        theta_x = draws[:, 0]
        self.assertAlmostEqual(float(np.mean(theta_x)), 0.0, delta=2e-5)
        self.assertAlmostEqual(float(np.std(theta_x)), 0.0005,
                               delta=2e-5)
        cone = np.array([s["extra"]["M2.Alpha_cone_rad"]
                         for s in _samples])
        self.assertAlmostEqual(float(np.mean(cone ** 2)),
                               2 * 0.0005 ** 2, delta=2e-8)

    def test_uniform_relative_bounds(self):
        variables = _validate_tolerances(self.data, [
            {"label": "M2", "alias": "R", "kind": "relative",
             "distribution": "uniform", "half_width": 0.01}])
        _samples, draws = sample_perturbations(variables, 5000, seed=3)
        self.assertTrue(np.all(np.abs(draws) <= 0.01))
        self.assertAlmostEqual(float(np.std(draws)), 0.01 / math.sqrt(3),
                               delta=0.0005)

    def test_truncated_normal_bounded(self):
        variables = _validate_tolerances(self.data, [
            {"label": "d1", "alias": "L", "kind": "length",
             "distribution": "truncated_normal", "sigma": 0.0005,
             "half_width": 0.001}])
        _samples, draws = sample_perturbations(variables, 5000, seed=3)
        self.assertTrue(np.all(np.abs(draws) <= 0.001))
        self.assertLess(float(np.std(draws)), 0.0005)

    def test_dioptric_samples_D_not_F(self):
        # A +/-5% D_th perturbation keeps D symmetric: the mean of
        # 1/F' is D0, while the mean of F' itself is slightly above F0
        # (Jensen) -- the sampler must work in D, not in F.
        variables = _validate_tolerances(self.data, [
            {"label": "TL1", "alias": "F", "kind": "dioptric",
             "distribution": "normal", "sigma": 0.05}])
        samples, _draws = sample_perturbations(variables, 5000, seed=3)
        d0 = 1.0 / 0.230
        d_prime = np.array([1.0 / s["values_si"][("TL1", "F")]
                            for s in samples])
        self.assertAlmostEqual(float(np.mean(d_prime)), d0, delta=0.05)
        self.assertTrue(np.all(d_prime > 0))

    def test_distribution_defaults(self):
        # Curvature defaults to uniform (a symmetric +/- band, not a
        # normal); lengths default to normal. (The scale parameter is
        # still required -- only the distribution name is defaulted.)
        variables = _validate_tolerances(self.data, [
            {"label": "M2", "alias": "R", "kind": "relative",
             "half_width": 0.01},
            {"label": "d1", "alias": "L", "kind": "length",
             "sigma": 0.0005}])
        self.assertEqual(variables[0]["distribution"], "uniform")
        self.assertEqual(variables[1]["distribution"], "normal")

    def test_driven_variable_fails_fast(self):
        # M1.R / M2.R in the shipped example are driven by the R0
        # link; setup must fail instead of evaluating 1000 bad points.
        data = load_rez(SYMM_LINKED)
        with self.assertRaises(MonteCarloError):
            _validate_tolerances(data, [
                {"label": "M1", "alias": "R", "kind": "relative",
                 "distribution": "uniform", "half_width": 0.01}])


class TestSpearmanPRCC(unittest.TestCase):
    def test_ranking_finds_dominant_variable(self):
        # y = 3*x0 + noise; x1 is pure noise; x2 correlates with x0.
        # Both Spearman and PRCC must rank x0 first.
        rng = np.random.default_rng(7)
        n = 200
        x0 = rng.normal(0, 1, n)
        x1 = rng.normal(0, 1, n)
        x2 = 0.5 * x0 + rng.normal(0, 1, n)
        y = 3.0 * x0 + rng.normal(0, 0.5, n)
        X = np.column_stack([x0, x1, x2])
        prcc = _prcc(X, y)
        spear = [_spearman(X[:, j], y) for j in range(3)]
        self.assertGreater(abs(prcc[0]), abs(prcc[1]))
        self.assertGreater(abs(prcc[0]), abs(prcc[2]))
        self.assertGreater(abs(spear[0]), abs(spear[1]))
        self.assertLess(abs(prcc[1]), 0.2)

    def test_constant_column_is_none(self):
        rng = np.random.default_rng(7)
        X = np.column_stack([np.ones(50), rng.normal(0, 1, 50)])
        y = rng.normal(0, 1, 50)
        self.assertIsNone(_spearman(X[:, 0], y))
        prcc = _prcc(X, y)
        self.assertTrue(math.isnan(prcc[0]) or prcc[0] is None)


class TestMonteCarloSmall(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = load_rez(USER_REZ)
        cls.eng = load_eng(MC_ENG)

    def test_small_run_structure(self):
        report = run_montecarlo(self.data, TOL_SMALL, n=40, chunk_size=8,
                                seed=0, watch=("M1", "M4"), eng=self.eng)
        self.assertEqual(report["n"], 40)
        self.assertEqual(report["n_completed"], 40)
        self.assertEqual(report["n_failed"], 0)
        self.assertEqual(report["n_stable"] + report["n_unstable"], 40)
        lo, hi = report["wilson_95"]
        self.assertLessEqual(lo, report["p_unstable"])
        self.assertLessEqual(report["p_unstable"], hi)
        for label in ("M1", "M4"):
            for plane in ("w_T_mm", "w_S_mm"):
                stat = report["watch"][label][plane]
                self.assertEqual(stat["n"], report["n_stable"])
                self.assertLessEqual(stat["ci95"][0], stat["median"])
                self.assertLessEqual(stat["median"], stat["ci95"][1])
        self.assertEqual(report["power"]["status"], "ok")
        self.assertGreater(report["power"]["P_out_W"]["median"], 0.0)
        self.assertEqual(len(report["sensitivity"]), 3)
        for s in report["sensitivity"]:
            for key in ("spearman_w", "prcc_w", "spearman_P_out",
                        "prcc_P_out", "spearman_stable", "prcc_stable"):
                if s[key] is not None:
                    self.assertLessEqual(abs(s[key]), 1.0)

    def test_chunking_does_not_change_results(self):
        # Same seed, different chunk sizes: identical draws, so
        # identical statistics (chunking only regroups the batches).
        base = run_montecarlo(self.data, TOL_SMALL, n=40, chunk_size=8,
                              seed=0, watch=("M1",), eng=None)
        for chunk in (40, 13):
            other = run_montecarlo(self.data, TOL_SMALL, n=40,
                                   chunk_size=chunk, seed=0, watch=("M1",),
                                   eng=None)
            self.assertEqual(other["n_unstable"], base["n_unstable"])
            self.assertEqual(other["watch"]["M1"]["w_T_mm"],
                             base["watch"]["M1"]["w_T_mm"])
            self.assertEqual(other["sensitivity"], base["sensitivity"])

    def test_seed_reproducibility(self):
        a = run_montecarlo(self.data, TOL_SMALL, n=24, chunk_size=8,
                           seed=5, watch=("M1",), eng=None)
        b = run_montecarlo(self.data, TOL_SMALL, n=24, chunk_size=8,
                           seed=5, watch=("M1",), eng=None)
        self.assertEqual(a, b)
        c = run_montecarlo(self.data, TOL_SMALL, n=24, chunk_size=8,
                           seed=6, watch=("M1",), eng=None)
        self.assertNotEqual(a["n_unstable"], c["n_unstable"])

    def test_progress_interrupt(self):
        calls = []

        def progress(done, total):
            calls.append(done)
            return False  # stop after the first chunk

        report = run_montecarlo(self.data, TOL_SMALL, n=40, chunk_size=8,
                                seed=0, watch=("M1",), eng=None,
                                progress=progress)
        self.assertTrue(report["interrupted"])
        self.assertEqual(report["n_completed"], 8)
        self.assertEqual(calls, [8])


class TestReverseFitting(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = load_rez(USER_REZ)
        cls.eng = load_eng(REVERSE_ENG)
        cls.lo, cls.hi, cls.zone_id = working_zone_bounds(
            cls.data, lens=("TL1", "F"))
        cls.bounds = (cls.lo, cls.hi, cls.zone_id)

    def test_output_beam_sign_convention(self):
        # The M4 CLI entry is the REFLECTED beam: same w, opposite
        # sign of R vs the beam incident on M4 (the d4 exit entry).
        # The reverse fitter must use the incident beam, not the
        # reflected one.
        from rezeng import run_headless_file
        from rezeng.qevolve import beam_entry
        result = run_headless_file(USER_REZ)["results"][0]
        wT, wS, RT, RS = beam_entry(result, "d4")
        wT4, wS4, RT4, RS4 = beam_entry(result, "M4")
        self.assertAlmostEqual(wT4, wT, places=6)
        self.assertAlmostEqual(wS4, wS, places=6)
        self.assertAlmostEqual(RT4, -RT, places=3)
        self.assertAlmostEqual(RS4, -RS, places=3)

    def test_recovery_three_points(self):
        # True F = 250 mm (D = 4.0 /m, Zone I), 3 points spanning the
        # waist, 3% noise: D_th must be recovered within 5%.
        for plane in ("T", "S"):
            points = synthetic_measurements(
                self.data, 4.0, [30, 200, 800], plane,
                noise_frac=0.03, seed=1, m2=1.0)
            report = fit_plane(self.data, points, plane,
                               lens=("TL1", "F"), output_label="M4",
                               eng=self.eng, m2=1.0,
                               zone_bounds=self.bounds)
            self.assertTrue(report["converged"])
            self.assertLess(report["rms_rel"], 0.03)
            err = abs(report["D_th_fit_per_m"] - 4.0) / 4.0
            self.assertLess(err, 0.05)
            self.assertEqual(report["zone"], "Zone_I")
            self.assertIsNotNone(report["degeneracy"])
            self.assertFalse(report["degeneracy"]
                             ["all_far_field_one_side"])

    def test_two_point_far_field_degeneracy(self):
        # True D = 9.5 /m (Zone II) gives the same output waist as
        # D = 4.0 /m (Zone I): w0 = 253 um, z0 = -0.4 mm. Two
        # far-field points from the Zone II beam agree with the
        # Zone I model to <1% -- the Zone I-bounded fit then
        # "succeeds" with the WRONG answer. This locks the trap.
        from rezeng.reverse import _ModelEvaluator
        ev = _ModelEvaluator(self.data, lens=("TL1", "F"))
        r_true = ev(9.5)
        r_wrong = ev(4.0)
        for z in (1500, 2500):
            w_true = model_spot(self.data, r_true, "M4", z, "T",
                                1064e-9)
            w_wrong = model_spot(self.data, r_wrong, "M4", z, "T",
                                 1064e-9)
            self.assertLess(abs(w_wrong - w_true) / w_true, 0.01)
        points = synthetic_measurements(
            self.data, 9.5, [1500, 2500], "T",
            noise_frac=0.0, seed=2, m2=1.0)
        report = fit_plane(self.data, points, "T", lens=("TL1", "F"),
                           output_label="M4", eng=self.eng, m2=1.0,
                           zone_bounds=self.bounds)
        self.assertTrue(report["converged"])
        self.assertLess(report["rms_rel"], 0.03)
        # Wrong zone, small residual: the trap.
        self.assertLess(report["D_th_fit_per_m"], 4.64)
        self.assertGreater(report["D_th_fit_per_m"], 3.9)
        self.assertTrue(report["degeneracy"]["all_far_field_one_side"])
        self.assertTrue(any("degeneracy risk" in w
                            for w in report["warnings"]))

    def test_m2_correction(self):
        # Synthetic beam with M^2 = 1.3, true D = 4.0 /m. Fitting
        # without the M^2 correction absorbs the extra divergence
        # into D_th (biased); fitting with M^2 = 1.3 recovers it.
        points = synthetic_measurements(
            self.data, 4.0, [30, 200, 800], "T",
            noise_frac=0.0, seed=3, m2=1.3)
        biased = fit_plane(self.data, points, "T", lens=("TL1", "F"),
                           output_label="M4", eng=self.eng, m2=None,
                           zone_bounds=self.bounds)
        err_biased = abs(biased["D_th_fit_per_m"] - 4.0) / 4.0
        self.assertGreater(err_biased, 0.02)
        self.assertIsNotNone(biased["m2_bias_estimate"])
        self.assertGreater(biased["m2_bias_estimate"]
                           ["delta_D_th_per_m"], 0.0)
        corrected = fit_plane(self.data, points, "T", lens=("TL1", "F"),
                              output_label="M4", eng=self.eng, m2=1.3,
                              zone_bounds=self.bounds)
        err_fixed = abs(corrected["D_th_fit_per_m"] - 4.0) / 4.0
        self.assertLess(err_fixed, 0.05)
        self.assertLess(err_fixed, err_biased)

    def test_substrate_warning_and_estimate(self):
        points = synthetic_measurements(
            self.data, 4.0, [30, 200, 800], "T",
            noise_frac=0.0, seed=4, m2=1.0)
        with_sub = fit_plane(self.data, points, "T", lens=("TL1", "F"),
                             output_label="M4", eng=self.eng, m2=1.0,
                             zone_bounds=self.bounds)
        self.assertIsNotNone(with_sub["substrate_used"])
        self.assertIsNone(with_sub["substrate_error_estimate"])
        no_sub = fit_plane(self.data, points, "T", lens=("TL1", "F"),
                           output_label="M4", eng=None, m2=1.0,
                           zone_bounds=self.bounds)
        self.assertIsNone(no_sub["substrate_used"])
        self.assertTrue(any("substrate" in w for w in no_sub["warnings"]))
        est = no_sub["substrate_error_estimate"]
        self.assertIsNotNone(est)
        self.assertGreater(est["max_rel_diff"], 0.0)
        self.assertLess(est["max_rel_diff"], 0.05)

    def test_input_validation(self):
        with self.assertRaises(ReverseError):
            fit_plane(self.data, [{"z_mm": 100, "w_mm": 0.3}], "T",
                      zone_bounds=self.bounds)
        with self.assertRaises(ReverseError):
            fit_plane(self.data, [(100, 0.3), (200, 0.4)], "T",
                      output_label="NOPE", zone_bounds=self.bounds)
        with self.assertRaises(ReverseError):
            fit_plane(self.data, [(100, 0.3), (200, 0.4)], "T",
                      zone_bounds=(0.1, 0.5))


if __name__ == "__main__":
    unittest.main()
