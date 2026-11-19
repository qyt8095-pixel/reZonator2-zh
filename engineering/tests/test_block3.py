"""Tests for Phase 2 block 3 (rezeng.jones, rezeng.dispersion,
rezeng.mopa, and the power.py extra_loss interface).

Run from the repository root:
    python3 -m unittest discover -s engineering/tests -v

Jones conventions locked here (see rezeng/jones.py for the derivation):

* basis (T, S) = lab frame; forward matrices are defined in the lab
  basis for +z propagation;
* backward pass: reciprocal elements take the transpose, Faraday
  rotators keep the same matrix (non-reciprocal);
* mirrors are diag(m_T, m_S) in the lab basis, default (-1, -1) =
  global phase only. In Fresnel notation m_T = -r_p, m_S = r_s.

Hand-computed anchors used below:

* Two polarisers (0 deg and 45 deg): the one-way product has
  eigenvalues {1/sqrt(2), 0} and the round trip (P0.P45.P0) has
  eigenvalues {1/2, 0}, so the polarisation loss is 1 - 1/4 = 0.75.
* A waveplate + one polariser is lossless for the eigenstate
  (J_rt is a similarity transform of the polariser); the waveplate
  only rotates the eigenstate (HWP 22.5 deg -> eigenstate at 45 deg).
* Faraday 45 deg + polariser 0 deg is an isolator: round-trip loss 1.
* QWP(45 deg) traversed twice (forward + back) is HWP(45 deg).
* Faraday 45 deg traversed twice is R(90 deg); a reciprocal rotator
  45 deg traversed twice is the identity.
* User cavity + example dispersion data: GDD = 2*27*245 - 150 - 300
  = 12780 fs^2, TOD = 2*27*310 + 500 + 1200 = 18440 fs^3.
"""

import json
import math
import os
import tempfile
import unittest

import numpy as np

import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                ".."))

from rezeng import (load_rez, load_eng, validate_eng, run_headless_file,
                    HeadlessError)
from rezeng.jones import (JonesError, rotation_matrix, retarder_matrix,
                          half_wave_plate, quarter_wave_plate,
                          polarizer_matrix, mirror_matrix, matrix_from_spec,
                          build_sequence, round_trip_jones,
                          eigen_polarization, polarization_loss,
                          jones_report)
from rezeng.dispersion import DispersionError, round_trip_dispersion
from rezeng.mopa import (MOPAError, B_WARN_RAD, fn_pass, ring_grid,
                         fluence_profile, resolve_chain, run_chain)
from rezeng.power import (PowerError, mode_a_threshold, mode_a_output,
                          solve_p_circ, pump_scan)

REPO = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", ".."))
ENGINEERING = os.path.join(REPO, "engineering")
TESTS_DATA = os.path.join(ENGINEERING, "tests", "data")
BINARY = os.path.join(REPO, "bin", "rezonator")
USER_CAVITY = os.path.join(os.path.expanduser("~"), "workspace", "user",
                           "files", "upload.rez")
EXAMPLE_JONES_ENG = os.path.join(TESTS_DATA, "example-jones.eng.json")
EXAMPLE_MOPA_ENG = os.path.join(TESTS_DATA, "example-mopa.eng.json")
AMP_SP = os.path.join(TESTS_DATA, "mopa_amp_sp.rez")
REGEN_SW = os.path.join(TESTS_DATA, "mopa_regen_sw.rez")


def rel(a, b):
    return abs(a - b) / max(abs(b), 1e-12)


def assert_close_mat(test, A, B, tol=1e-12):
    test.assertTrue(np.allclose(np.asarray(A), np.asarray(B), atol=tol),
                    "matrices differ:\n%r\nvs\n%r" % (A, B))


def _elem(label, typ, params=None):
    return {"label": label, "type": typ, "title": "", "is_disabled": False,
            "params": params or {}}


def _param(value, unit):
    return {"unit": unit, "value": value}


def _sw_cavity(extra_elements=()):
    """Minimal in-memory SW cavity: M1 - d1 - [extras] - d2 - M2."""
    elems = [_elem("M1", "ElemCurveMirror",
                   {"R": _param(100000, "mm"), "Alpha": _param(0, "deg")}),
             _elem("d1", "ElemEmptyRange",
                   {"L": _param(100, "mm"), "n": _param(1, "none")})]
    elems.extend(extra_elements)
    elems.append(_elem("d2", "ElemEmptyRange",
                       {"L": _param(100, "mm"), "n": _param(1, "none")}))
    elems.append(_elem("M2", "ElemCurveMirror",
                       {"R": _param(100000, "mm"),
                        "Alpha": _param(0, "deg")}))
    return {"builtin_params": {"lambda": _param(1064, "nm")},
            "custom_params": {}, "elements": elems, "formulas": [],
            "param_links": [], "notes": "", "schema_version": "2.0",
            "title": "test cavity", "trip_type": "SW", "pumps": [],
            "windows": []}


# --------------------------------------------------------------------------
# Jones: elementary matrices
# --------------------------------------------------------------------------

class TestJonesMatrices(unittest.TestCase):
    def test_waveplate_known(self):
        # HWP(0) = diag(i, -i); QWP(0) = diag(e^{i pi/4}, e^{-i pi/4}).
        assert_close_mat(self, half_wave_plate(0),
                         np.diag([1j, -1j]))
        assert_close_mat(self, quarter_wave_plate(0),
                         np.diag([np.exp(1j * math.pi / 4),
                                  np.exp(-1j * math.pi / 4)]))
        # HWP(45 deg) swaps T and S (up to a phase).
        out = half_wave_plate(45) @ np.array([1.0, 0.0])
        self.assertAlmostEqual(abs(out[0]), 0.0, places=12)
        self.assertAlmostEqual(abs(out[1]), 1.0, places=12)
        # Retarders are unitary and symmetric.
        for J in (half_wave_plate(30), quarter_wave_plate(10),
                  retarder_matrix(0.7, 1.1)):
            assert_close_mat(self, J.conj().T @ J, np.eye(2))
            assert_close_mat(self, J.T, J)
            self.assertAlmostEqual(abs(np.linalg.det(J)), 1.0, places=12)

    def test_qwp_twice_is_hwp(self):
        # A quarter-wave plate traversed twice is a half-wave plate.
        assert_close_mat(self, quarter_wave_plate(45) @ quarter_wave_plate(45),
                         half_wave_plate(45))
        assert_close_mat(self, quarter_wave_plate(0) @ quarter_wave_plate(0),
                         half_wave_plate(0))

    def test_polarizer_known(self):
        assert_close_mat(self, polarizer_matrix(1.0, 0.0, 0.0),
                         np.diag([1.0, 0.0]))
        assert_close_mat(self, polarizer_matrix(1.0, 0.0, 90.0),
                         np.diag([0.0, 1.0]))
        # Projector: J^2 = J.
        P = polarizer_matrix(1.0, 0.0, 45.0)
        assert_close_mat(self, P @ P, P)
        # Malus: T-polarised input through a 30 deg polariser keeps
        # cos^2(30 deg) = 0.75 of the power.
        out = polarizer_matrix(1.0, 0.0, 30.0) @ np.array([1.0, 0.0])
        self.assertAlmostEqual(float(np.sum(np.abs(out) ** 2)), 0.75,
                               places=12)
        # Partial polariser keeps the amplitude ratio sqrt(Tp/Ts).
        P = polarizer_matrix(0.25, 0.01, 0.0)
        assert_close_mat(self, P, np.diag([0.5, 0.1]))
        with self.assertRaises(JonesError):
            polarizer_matrix(1.5, 0.0, 0.0)

    def test_mirror_default_is_global_phase(self):
        assert_close_mat(self, mirror_matrix(), -np.eye(2))
        assert_close_mat(self, mirror_matrix(0.9, -0.9),
                         np.diag([0.9, -0.9]))
        # Complex coefficients via [re, im].
        assert_close_mat(self, mirror_matrix([0.0, 1.0], -1.0),
                         np.diag([1j, -1.0]))

    def test_matrix_spec(self):
        J, faraday = matrix_from_spec(
            {"type": "matrix",
             "matrix": [[[0.0, 1.0], 0.0], [0.0, [0.0, -1.0]]]})
        assert_close_mat(self, J, np.diag([1j, -1j]))
        self.assertFalse(faraday)
        J, faraday = matrix_from_spec({"type": "faraday",
                                       "rotation_deg": 45.0})
        assert_close_mat(self, J, rotation_matrix(math.radians(45)))
        self.assertTrue(faraday)
        with self.assertRaises(JonesError):
            matrix_from_spec({"type": "prism"})
        with self.assertRaises(JonesError):
            matrix_from_spec({"type": "faraday"})  # no rotation_deg


# --------------------------------------------------------------------------
# Jones: round trip, coordinate flip, eigen-polarisation
# --------------------------------------------------------------------------

class TestJonesRoundTrip(unittest.TestCase):
    def test_empty_cavity_is_identity(self):
        data = _sw_cavity()
        res = round_trip_jones(data, {})
        assert_close_mat(self, res["J"], np.eye(2))
        eig = eigen_polarization(res["J"])
        self.assertAlmostEqual(eig["loss"], 0.0, places=12)
        self.assertAlmostEqual(abs(eig["lambda_max"]), 1.0, places=12)

    def test_faraday_doubles_reciprocal_cancels(self):
        # Faraday rotator 45 deg in the cavity: round trip R(90 deg).
        plate = _elem("FR", "ElemPlate",
                      {"L": _param(5, "mm"), "n": _param(1.5, "none")})
        data = _sw_cavity([plate])
        eng = {"elements_ext": {"FR": {"jones": {"type": "faraday",
                                                 "rotation_deg": 45.0}}}}
        res = round_trip_jones(data, eng)
        assert_close_mat(self, res["J"],
                         rotation_matrix(math.radians(90)))
        eig = eigen_polarization(res["J"])
        self.assertAlmostEqual(eig["loss"], 0.0, places=12)
        # Eigenvectors of a rotation are circular: |ellipticity| = 45.
        self.assertAlmostEqual(abs(eig["ellipticity_deg"]), 45.0, places=9)
        # Reciprocal rotator 45 deg: round trip is the identity.
        eng = {"elements_ext": {"FR": {"jones": {"type": "rotator",
                                                 "rotation_deg": 45.0}}}}
        res = round_trip_jones(data, eng)
        assert_close_mat(self, res["J"], np.eye(2))

    def test_qwp_round_trip_is_hwp(self):
        # QWP(45 deg) in the cavity: forward + backward = HWP(45 deg).
        plate = _elem("WP", "ElemPlate",
                      {"L": _param(5, "mm"), "n": _param(1.5, "none")})
        data = _sw_cavity([plate])
        eng = {"elements_ext": {"WP": {"jones": {"type": "waveplate",
                                                 "retardance_rad":
                                                     math.pi / 2,
                                                 "fast_axis_deg": 45.0}}}}
        res = round_trip_jones(data, eng)
        assert_close_mat(self, res["J"], half_wave_plate(45))
        # Eigenvalues of HWP(45): +-i, no loss.
        eig = eigen_polarization(res["J"])
        self.assertAlmostEqual(eig["loss"], 0.0, places=12)
        for v in eig["eigenvalues"]:
            self.assertAlmostEqual(abs(v), 1.0, places=12)

    def test_waveplate_plus_polarizer_is_lossless(self):
        # A waveplate + polariser in a linear cavity is lossless for
        # the eigenstate: J_rt = H.P.H is (up to a sign) a similarity
        # transform of P, so its eigenvalues are {-1, 0} whatever the
        # waveplate angle. The waveplate only rotates the eigenstate.
        plate = _elem("WP", "ElemPlate",
                      {"L": _param(5, "mm"), "n": _param(1.5, "none")})
        pol = _elem("TFP", "ElemPlate",
                    {"L": _param(1, "mm"), "n": _param(1.5, "none")})
        data = _sw_cavity([plate, pol])
        eng = {"elements_ext": {
            "WP": {"jones": {"type": "waveplate",
                             "retardance_rad": math.pi,
                             "fast_axis_deg": 22.5}},
            "TFP": {"jones": {"type": "polarizer", "Tp": 1.0,
                              "Ts": 0.0, "angle_deg": 0.0}}}}
        eig = eigen_polarization(round_trip_jones(data, eng)["J"])
        self.assertAlmostEqual(eig["loss"], 0.0, places=12)
        # Eigenstate at 45 deg (the HWP maps T onto the polariser axis).
        self.assertAlmostEqual(eig["orientation_deg"], 45.0, places=9)
        self.assertAlmostEqual(abs(eig["lambda_max"]), 1.0, places=12)

    def test_two_polarizers_loss(self):
        # Hand-computed anchor: polarisers at 0 deg and 45 deg give
        # round-trip eigenvalues {1/2, 0} and loss 1 - 1/4 = 0.75.
        pol0 = _elem("P0", "ElemPlate",
                     {"L": _param(1, "mm"), "n": _param(1.5, "none")})
        pol45 = _elem("P45", "ElemPlate",
                      {"L": _param(1, "mm"), "n": _param(1.5, "none")})
        data = _sw_cavity([pol0, pol45])
        eng = {"elements_ext": {
            "P0": {"jones": {"type": "polarizer", "Tp": 1.0, "Ts": 0.0,
                             "angle_deg": 0.0}},
            "P45": {"jones": {"type": "polarizer", "Tp": 1.0, "Ts": 0.0,
                              "angle_deg": 45.0}}}}
        eig = eigen_polarization(round_trip_jones(data, eng)["J"])
        self.assertAlmostEqual(eig["loss"], 0.75, places=12)
        self.assertAlmostEqual(abs(eig["lambda_max"]), 0.5, places=12)
        self.assertAlmostEqual(eig["orientation_deg"], 0.0, places=9)

    def test_faraday_plus_polarizer_is_isolator(self):
        # Faraday 45 deg + polariser 0 deg: the round trip is fully
        # extinguished (loss 1.0) -- the optical-isolator behaviour.
        # This locks the no-transpose rule: transposing the Faraday
        # on the way back would give loss 0 instead.
        plate = _elem("FR", "ElemPlate",
                      {"L": _param(5, "mm"), "n": _param(1.5, "none")})
        pol = _elem("TFP", "ElemPlate",
                    {"L": _param(1, "mm"), "n": _param(1.5, "none")})
        data = _sw_cavity([plate, pol])
        eng = {"elements_ext": {
            "FR": {"jones": {"type": "faraday", "rotation_deg": 45.0}},
            "TFP": {"jones": {"type": "polarizer", "Tp": 1.0, "Ts": 0.0,
                              "angle_deg": 0.0}}}}
        eig = eigen_polarization(round_trip_jones(data, eng)["J"])
        self.assertAlmostEqual(eig["loss"], 1.0, places=12)
        self.assertAlmostEqual(abs(eig["lambda_max"]), 0.0, places=12)

    def test_mirror_differential_phase_gives_loss(self):
        # M1 with (m_T, m_S) = (0.9, -0.9): J_rt = diag(-0.9, 0.9),
        # eigenvalues +-0.9, loss 1 - 0.81 = 0.19.
        data = _sw_cavity()
        eng = {"elements_ext": {"M1": {"jones": {"type": "mirror",
                                                 "m_T": 0.9,
                                                 "m_S": -0.9}}}}
        eig = eigen_polarization(round_trip_jones(data, eng)["J"])
        self.assertAlmostEqual(eig["loss"], 0.19, places=12)

    def test_insertions_and_errors(self):
        data = _sw_cavity()
        ins = [{"after": "d1", "jones": {"type": "waveplate",
                                         "retardance_rad": math.pi / 2,
                                         "fast_axis_deg": 45.0}}]
        res = round_trip_jones(data, {}, ins)
        # Inserted QWP(45) alone: round trip = HWP(45).
        assert_close_mat(self, res["J"], half_wave_plate(45))
        # Insertion by index (after element 1 == after d1).
        res2 = round_trip_jones(
            data, {},
            [{"after": 1, "jones": {"type": "waveplate",
                                    "retardance_rad": math.pi / 2,
                                    "fast_axis_deg": 45.0}}])
        assert_close_mat(self, res2["J"], half_wave_plate(45))
        # Unknown label / bad spec on a mirror / mirror spec on a
        # transmissive element all raise.
        with self.assertRaises(JonesError):
            round_trip_jones(data, {}, [{"after": "nope", "jones":
                                         {"type": "identity"}}])
        with self.assertRaises(JonesError):
            round_trip_jones(data, {"elements_ext": {"M1": {"jones": {
                "type": "waveplate", "retardance_rad": 1.0}}}})
        with self.assertRaises(JonesError):
            round_trip_jones(data, {"elements_ext": {"d1": {"jones": {
                "type": "mirror"}}}})

    def test_sp_and_rr_products(self):
        # SP: single-pass product in list order.
        data = _sw_cavity()
        data["trip_type"] = "SP"
        eng = {"elements_ext": {"d1": {"jones": {"type": "waveplate",
                                                 "retardance_rad":
                                                     math.pi / 2,
                                                 "fast_axis_deg": 0.0}}}}
        res = round_trip_jones(data, eng)
        self.assertEqual(res["kind"], "single_pass")
        assert_close_mat(self, res["J"], quarter_wave_plate(0))
        # RR: one loop product.
        data["trip_type"] = "RR"
        res = round_trip_jones(data, eng)
        self.assertEqual(res["kind"], "round_trip")
        assert_close_mat(self, res["J"], quarter_wave_plate(0))

    @unittest.skipIf(not os.path.exists(USER_CAVITY),
                     "user cavity file missing: %s" % USER_CAVITY)
    def test_user_cavity_birefringent_crystal(self):
        # TL1 as a birefringent crystal, Gamma = 0.15 rad, fast axis
        # T: J_rt = diag(e^{i Gamma}, e^{-i Gamma}), loss 0.
        rep = jones_report(USER_CAVITY, EXAMPLE_JONES_ENG)
        self.assertEqual(rep["trip_type"], "SW")
        J = np.array([[complex(*c) for c in row] for row in rep["J_rt"]])
        gamma = 0.15
        assert_close_mat(self, J, np.diag([np.exp(1j * gamma),
                                           np.exp(-1j * gamma)]),
                         tol=1e-12)
        self.assertAlmostEqual(rep["polarization_loss"], 0.0, places=12)
        self.assertAlmostEqual(abs(complex(*rep["lambda_max"])), 1.0,
                               places=12)


# --------------------------------------------------------------------------
# Dispersion
# --------------------------------------------------------------------------

class TestDispersion(unittest.TestCase):
    def test_sw_counting_user_cavity(self):
        # Hand-computed: GDD = 2*27*245 - 150 - 300 = 12780 fs^2;
        # TOD = 2*27*310 + 500 + 1200 = 18440 fs^3. End mirrors count
        # once, the crystal twice.
        data = load_rez(USER_CAVITY)
        eng = load_eng(EXAMPLE_JONES_ENG)
        res = round_trip_dispersion(data, eng)
        self.assertAlmostEqual(res["GDD_fs2"], 12780.0, places=9)
        self.assertAlmostEqual(res["TOD_fs3"], 18440.0, places=9)
        counts = {p["label"]: p["count"] for p in res["per_element"]}
        self.assertEqual(counts, {"M1": 1, "TL1": 2, "M4": 1})
        sesam = [p for p in res["per_element"] if p["label"] == "M1"][0]
        self.assertAlmostEqual(sesam["modulation_depth"], 0.012)
        self.assertAlmostEqual(sesam["saturation_fluence_uJ_per_cm2"],
                               70.0)
        self.assertEqual(sesam["role"], "SESAM")
        self.assertEqual(res["warnings"], [])

    def test_sp_counting(self):
        # SP: every element counts once. d1 (L=50 mm, gvd=100) gives
        # 5000 fs^2; the gauss aperture has no dispersion data.
        data = load_rez(os.path.join(REPO, "bin", "examples",
                                     "gauss_aperture.rez"))
        eng = {"elements_ext": {"d1": {"gvd_fs2_per_mm": 100.0,
                                       "tod_fs3_per_mm": 50.0}}}
        res = round_trip_dispersion(data, eng)
        self.assertAlmostEqual(res["GDD_fs2"], 5000.0, places=9)
        self.assertAlmostEqual(res["TOD_fs3"], 2500.0, places=9)
        self.assertEqual(res["per_element"][0]["count"], 1)

    def test_missing_L_warning(self):
        # Dispersion coefficients on a mirror (no L parameter) are
        # skipped with a warning, not silently applied.
        data = _sw_cavity()
        eng = {"elements_ext": {"M1": {"gvd_fs2_per_mm": 100.0}}}
        res = round_trip_dispersion(data, eng)
        self.assertEqual(res["GDD_fs2"], 0.0)
        self.assertEqual(len(res["warnings"]), 1)
        self.assertIn("no L parameter", res["warnings"][0])

    def test_no_data_is_zero(self):
        data = load_rez(USER_CAVITY)
        res = round_trip_dispersion(data, {})
        self.assertEqual(res["GDD_fs2"], 0.0)
        self.assertEqual(res["TOD_fs3"], 0.0)
        self.assertEqual(res["per_element"], [])
        with self.assertRaises(DispersionError):
            round_trip_dispersion({**load_rez(USER_CAVITY),
                                   "trip_type": "XX"}, {})


# --------------------------------------------------------------------------
# MOPA: Frantz-Nodvik core
# --------------------------------------------------------------------------

class TestFrantzNodvik(unittest.TestCase):
    def test_ring_grid_energy(self):
        for w in (100e-6, 200e-6, 500e-6):
            u, areas = ring_grid(w, 64)
            E = 2.5e-3
            Jin = fluence_profile(E, w, u)
            self.assertLess(rel(float(np.sum(Jin * areas)), E), 1e-6)

    def test_fn_pass_limits(self):
        J_sat = 1200.0  # J/m^2 (Nd:YVO4)
        x = np.array([0.0, 1e-3, 10.0, 1e6])
        # G0 = 1: identity.
        assert_close = np.allclose(fn_pass(x, 1.0, J_sat), x, rtol=1e-12)
        self.assertTrue(assert_close)
        # Small signal: gain -> G0 (x_0 = 1e-2 / J_sat scale).
        small = fn_pass(np.array([1e-2]), 4.5, J_sat)[0]
        self.assertLess(rel(small / 1e-2, 4.5), 1e-3)
        # Saturation asymptote: J_out -> J_in + J_sat ln G0 (x = 833).
        big = fn_pass(np.array([1e6]), 4.5, J_sat)[0]
        self.assertLess(rel(big - 1e6, J_sat * math.log(4.5)), 1e-9)
        # Overflow-safe at extreme fluence (no warning, finite result).
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            huge = fn_pass(np.array([1e12]), 10.0, J_sat)[0]
        self.assertTrue(math.isfinite(huge))
        self.assertAlmostEqual(huge - 1e12, J_sat * math.log(10.0),
                               delta=1e-6 * J_sat * math.log(10.0))
        with self.assertRaises(MOPAError):
            fn_pass(np.array([1.0]), 0.5, J_sat)
        with self.assertRaises(MOPAError):
            fn_pass(np.array([-1.0]), 2.0, J_sat)


def _chain_eng(stages, seed_J=5e-5, seed_tau_s=40e-12):
    return {"format_version": 1,
            "mopa_chain": {
                "seed_source": {"type": "oscillator_ref",
                                "pulse_energy_J": seed_J,
                                "pulse_duration_s": seed_tau_s,
                                "rep_rate_Hz": 120000},
                "stages": stages}}


def _amp_stage(**over):
    stage = {"stage_id": "amp_1", "rez_file": AMP_SP, "passes": 2,
             "gain_element": "CRY",
             "gain_medium": {"material": "Nd:YVO4",
                             "J_sat_J_per_cm2": 0.12,
                             "small_signal_gain_G0": 4.5,
                             "recovery_time_us": 90}}
    stage.update(over)
    return stage


def _run_chain_tmp(eng_dict, osc_path=USER_CAVITY):
    """Run a chain from an in-memory eng dict (temp side-car file)."""
    with tempfile.NamedTemporaryFile("w", suffix=".eng.json",
                                    delete=False) as f:
        json.dump(eng_dict, f)
        path = f.name
    try:
        return run_chain(osc_path, path)
    finally:
        os.unlink(path)


class TestMOPAChain(unittest.TestCase):
    @unittest.skipIf(not os.path.exists(BINARY),
                     "local binary not built: %s" % BINARY)
    def test_single_pass_small_signal(self):
        # Seed 1 uJ: on-axis fluence ~13 J/m^2 << J_sat = 1200 J/m^2,
        # so the first pass gain is ~G0 = 4.5 (within 2%).
        rep = _run_chain_tmp(_chain_eng([_amp_stage(passes=1)],
                                        seed_J=1e-6))
        stage = rep["stages"][0]
        self.assertEqual(stage["transits"], 1)
        self.assertAlmostEqual(stage["gain"], 4.5, delta=0.09)
        self.assertAlmostEqual(stage["w_T_mm"], 0.221, places=3)
        self.assertLess(abs(stage["E_out_J"] - 4.5e-6), 9e-8)
        # Stored energy drops by the extracted amount.
        self.assertLess(stage["stored_J_final"],
                        stage["stored_J_initial"])
        self.assertGreater(stage["stored_J_final"], 0.0)

    @unittest.skipIf(not os.path.exists(BINARY),
                     "local binary not built: %s" % BINARY)
    def test_depletion_over_passes(self):
        # Two passes at 50 uJ seed: the second pass gain is smaller
        # than the first (gain depletion), and the total output stays
        # below seed + stored energy.
        rep = _run_chain_tmp(_chain_eng([_amp_stage(passes=2)]))
        stage = rep["stages"][0]
        t1, t2 = stage["transits_detail"]
        self.assertGreater(t1["gain"], t2["gain"])
        self.assertLess(rep["E_out_J"],
                        5e-5 + stage["stored_J_initial"])
        self.assertEqual(rep["warnings"], [])

    @unittest.skipIf(not os.path.exists(BINARY),
                     "local binary not built: %s" % BINARY)
    def test_saturation_energy_conservation(self):
        # 10 mJ seed: on-axis fluence ~1.3e5 J/m^2 >> J_sat; the chain
        # must not output more than seed + stored energy.
        rep = _run_chain_tmp(_chain_eng([_amp_stage(passes=2)],
                                        seed_J=10e-3))
        stage = rep["stages"][0]
        self.assertLessEqual(rep["E_out_J"],
                             10e-3 + stage["stored_J_initial"]
                             + 1e-12)
        # Deep saturation: the second pass extracts little more.
        t1, t2 = stage["transits_detail"]
        self.assertLess(t2["gain"], 1.5)
        self.assertGreater(t1["gain"], 1.0)

    @unittest.skipIf(not os.path.exists(BINARY),
                     "local binary not built: %s" % BINARY)
    def test_regen_round_trips(self):
        # Regen: 5 round trips = 10 transits, 4% loss per round trip.
        # Gain per round trip falls as the stored energy depletes.
        stage = {"stage_id": "regen_1", "rez_file": REGEN_SW,
                 "passes": 5, "gain_element": "CRY",
                 "gain_medium": {"material": "Nd:YAG",
                                 "J_sat_J_per_cm2": 0.66,
                                 "initial_stored_energy_J": 5e-3},
                 "round_trip_loss": 0.04}
        rep = _run_chain_tmp(_chain_eng([stage]))
        st = rep["stages"][0]
        self.assertEqual(st["trip_type"], "SW")
        self.assertEqual(st["transits"], 10)
        self.assertAlmostEqual(st["w_T_mm"], 0.369, places=3)
        gains_rt = []
        for k in range(5):
            a = st["transits_detail"][2 * k]
            b = st["transits_detail"][2 * k + 1]
            gains_rt.append(b["E_out_J"] / a["E_in_J"])
        for earlier, later in zip(gains_rt, gains_rt[1:]):
            self.assertGreaterEqual(earlier, later)
        self.assertGreater(st["E_out_J"], 5e-5)
        self.assertLessEqual(rep["E_out_J"],
                             5e-5 + st["stored_J_initial"] + 1e-12)
        # Stored energy decreases monotonically across transits.
        stored = [t["stored_J_after"] for t in st["transits_detail"]]
        for earlier, later in zip(stored, stored[1:]):
            self.assertGreaterEqual(earlier, later)

    @unittest.skipIf(not os.path.exists(BINARY),
                     "local binary not built: %s" % BINARY)
    def test_b_integral_warning(self):
        # Huge n2 + short pulse + high energy: B exceeds 3 rad.
        stage = _amp_stage(passes=1)
        stage["gain_medium"] = dict(stage["gain_medium"])
        stage["gain_medium"]["n2_m2_per_W"] = 1e-17
        rep = _run_chain_tmp(_chain_eng([stage], seed_J=1e-3))
        self.assertGreater(rep["B_total_rad"], B_WARN_RAD)
        self.assertTrue(any("B integral" in w for w in rep["warnings"]))
        # Without n2 there is no B integral and no warning.
        rep2 = _run_chain_tmp(_chain_eng([_amp_stage(passes=1)],
                                         seed_J=1e-3))
        self.assertEqual(rep2["B_total_rad"], 0.0)
        self.assertEqual(rep2["warnings"], [])

    @unittest.skipIf(not os.path.exists(BINARY),
                     "local binary not built: %s" % BINARY)
    def test_lidt_per_transit(self):
        # A stage side-car with a very low LIDT flags the transit.
        with tempfile.TemporaryDirectory() as d:
            import shutil
            stage_path = os.path.join(d, "amp.rez")
            shutil.copy(AMP_SP, stage_path)
            with open(stage_path + ".eng.json", "w") as f:
                json.dump({"format_version": 1, "elements": {
                    "CRY": {"lidt_J_per_cm2": 0.001}}}, f)
            stage = _amp_stage(passes=1)
            stage["rez_file"] = stage_path
            rep = _run_chain_tmp(_chain_eng([stage], seed_J=1e-6))
            t = rep["stages"][0]["transits_detail"][0]
            self.assertEqual(t["lidt_status"], "fail")
            self.assertGreater(t["lidt_ratio"], 1.0)
            # No LIDT data at all: nodata, not an error.
            os.unlink(stage_path + ".eng.json")
            rep2 = _run_chain_tmp(_chain_eng([stage], seed_J=1e-6))
            t2 = rep2["stages"][0]["transits_detail"][0]
            self.assertEqual(t2["lidt_status"], "nodata")
            self.assertIsNone(t2["lidt_ratio"])

    def test_resolve_chain_errors(self):
        with self.assertRaises(MOPAError):
            resolve_chain({})
        with self.assertRaises(MOPAError):
            resolve_chain({"mopa_chain": {"seed_source": {},
                                           "stages": [_amp_stage()]}})
        with self.assertRaises(MOPAError):
            resolve_chain({"mopa_chain": {
                "seed_source": {"pulse_energy_J": 1e-4}, "stages": []}})
        bad = _amp_stage(passes=0)
        with self.assertRaises(MOPAError):
            resolve_chain(_chain_eng([bad]))
        bad = _amp_stage()
        bad["gain_medium"] = {"material": "Nd:YVO4",
                              "J_sat_J_per_cm2": 0.12}
        with self.assertRaises(MOPAError):
            resolve_chain(_chain_eng([bad]))
        bad = _amp_stage()
        bad["gain_medium"] = dict(bad["gain_medium"])
        bad["gain_medium"]["small_signal_gain_G0"] = 0.5
        with self.assertRaises(MOPAError):
            resolve_chain(_chain_eng([bad]))

    def test_example_mopa_fixture_validates(self):
        eng = load_eng(EXAMPLE_MOPA_ENG)
        self.assertEqual(validate_eng(eng), [])
        chain = resolve_chain(eng)
        self.assertEqual(len(chain["stages"]), 2)
        self.assertAlmostEqual(chain["seed"]["pulse_energy_J"], 5e-5)

    @unittest.skipIf(not os.path.exists(BINARY),
                     "local binary not built: %s" % BINARY)
    def test_full_example_chain(self):
        # Seed 50 uJ -> 2-pass YVO4 amp (G0 4.5) -> 10-round-trip
        # YAG regen (5 mJ stored, 4% loss/RT): the chain runs end to
        # end, conserves energy, and the regen dominates the gain.
        eng = load_eng(EXAMPLE_MOPA_ENG)
        for stage in eng["mopa_chain"]["stages"]:
            stage["rez_file"] = os.path.join(TESTS_DATA,
                                             stage["rez_file"])
        rep = _run_chain_tmp(eng)
        self.assertEqual(len(rep["stages"]), 2)
        amp, regen = rep["stages"]
        self.assertGreater(amp["gain"], 1.0)
        self.assertGreater(regen["gain"], amp["gain"])
        self.assertLessEqual(rep["E_out_J"],
                             5e-5 + amp["stored_J_initial"]
                             + regen["stored_J_initial"] + 1e-12)
        self.assertGreater(rep["E_out_J"], 1e-3)


# --------------------------------------------------------------------------
# Power coupling: Jones polarisation loss as extra_loss
# --------------------------------------------------------------------------

def _bench_params():
    """Minimal mode-A params (Nd:YVO4 benchmark values)."""
    return {"T_oc": 0.10, "L_i": 0.02, "eta_q": 808.0 / 1064.0,
            "eta_abs": 0.7769, "eta_mode": 0.6948,
            "sigma_em": 15.6e-19 * 1e-4, "tau_f": 90e-6, "eta_p": 0.95,
            "lambda_p_m": 808e-9, "profile": "gaussian"}


class TestExtraLossInterface(unittest.TestCase):
    def test_mode_a_extra_loss(self):
        p = _bench_params()
        w_p, w_l = 200e-6, 180e-6
        base = mode_a_output(p, 5.0, w_p, w_l)
        lossy = mode_a_output(p, 5.0, w_p, w_l, extra_loss=0.05)
        self.assertGreater(lossy["P_th"], base["P_th"])
        self.assertLess(lossy["P_out"], base["P_out"])
        self.assertLess(lossy["slope"], base["slope"])
        # extra_loss = 0 reproduces the old call exactly.
        self.assertEqual(mode_a_output(p, 5.0, w_p, w_l, 0.0), base)
        self.assertEqual(mode_a_threshold(p, w_p, w_l, 0.0),
                         mode_a_threshold(p, w_p, w_l))
        # A large extra loss can push the laser below threshold.
        off = mode_a_output(p, 5.0, w_p, w_l, extra_loss=5.0)
        self.assertEqual(off["P_out"], 0.0)
        self.assertTrue(off["below_threshold"])

    def test_mode_b_extra_loss(self):
        # Synthetic uniform slices (same construction as test_power).
        n_z = 24
        x, w = np.polynomial.legendre.leggauss(n_z)
        L = 0.010
        z = 0.5 * L * (x + 1.0)
        slices = {"label": "TL1", "L_m": L, "n0": 2.16,
                  "gamma_T": 0.0, "gamma_S": 0.0, "z_m": z,
                  "w_T_m": np.full(n_z, 180e-6),
                  "w_S_m": np.full(n_z, 180e-6), "w_z": 0.5 * L * w}
        p = {"gain_label": "TL1", "L_m": L, "n0": 2.16,
             "lambda_l_m": 1064e-9, "lambda_p_m": 808e-9,
             "sigma_em": 15.6e-19 * 1e-4, "tau_f": 90e-6,
             "alpha_p": 150.0, "w_p0": 200e-6, "z_p0": L / 2,
             "Mp2": 1.0, "eta_p": 1.0, "profile": "gaussian",
             "T_oc": 0.10, "L_i": 0.02, "eta_mode": None,
             "eta_abs": 1.0 - math.exp(-150.0 * L),
             "eta_q": 808.0 / 1064.0,
             "I_sat": 6.62607015e-34 * (299792458.0 / 1064e-9)
                      / (15.6e-19 * 1e-4 * 90e-6),
             "thermal": {}, "warnings": [], "F_current_m": 0.23}
        P_abs = p["eta_abs"] * 5.0
        base = solve_p_circ(p, slices, P_abs, 0.12)
        lossy = solve_p_circ(p, slices, P_abs, 0.12, extra_loss=0.05)
        self.assertGreater(lossy["P_th_abs"], base["P_th_abs"])
        self.assertLess(lossy["P_out"], base["P_out"])
        self.assertEqual(solve_p_circ(p, slices, P_abs, 0.12,
                                      extra_loss=0.0)["P_out"],
                         base["P_out"])

    def test_jones_power_linkage(self):
        # Waveplate angle tunes the polarisation loss, which tunes
        # P_out: two polarisers at 0/45 deg (loss 0.75) vs a single
        # polariser (loss 0) -- the lossy cavity puts out less.
        p = _bench_params()
        w_p, w_l = 200e-6, 180e-6
        pol0 = _elem("P0", "ElemPlate",
                     {"L": _param(1, "mm"), "n": _param(1.5, "none")})
        pol45 = _elem("P45", "ElemPlate",
                      {"L": _param(1, "mm"), "n": _param(1.5, "none")})
        data = _sw_cavity([pol0, pol45])
        eng_two = {"elements_ext": {
            "P0": {"jones": {"type": "polarizer", "Tp": 1.0, "Ts": 0.0,
                             "angle_deg": 0.0}},
            "P45": {"jones": {"type": "polarizer", "Tp": 1.0, "Ts": 0.0,
                              "angle_deg": 45.0}}}}
        eng_one = {"elements_ext": {
            "P0": {"jones": {"type": "polarizer", "Tp": 1.0, "Ts": 0.0,
                             "angle_deg": 0.0}}}}
        loss_two = polarization_loss(
            round_trip_jones(data, eng_two)["J"])
        loss_one = polarization_loss(
            round_trip_jones(data, eng_one)["J"])
        self.assertAlmostEqual(loss_two, 0.75, places=12)
        self.assertAlmostEqual(loss_one, 0.0, places=12)
        out_two = mode_a_output(p, 5.0, w_p, w_l,
                                extra_loss=loss_two)["P_out"]
        out_one = mode_a_output(p, 5.0, w_p, w_l,
                                extra_loss=loss_one)["P_out"]
        self.assertLess(out_two, out_one)
        self.assertGreater(out_two, 0.0)

    @unittest.skipIf(not os.path.exists(BINARY),
                     "local binary not built: %s" % BINARY)
    @unittest.skipIf(not os.path.exists(USER_CAVITY),
                     "user cavity file missing: %s" % USER_CAVITY)
    def test_pump_scan_extra_loss(self):
        # Full pipeline: extra_loss lowers P_out_B at every stable
        # point of a real pump scan (user cavity + example eng).
        from rezeng import load_eng as _load_eng
        eng = _load_eng(os.path.join(TESTS_DATA, "example-power.eng.json"))
        data = load_rez(USER_CAVITY)
        base = pump_scan(data, eng, [2.0, 5.0])
        lossy = pump_scan(data, eng, [2.0, 5.0], extra_loss=0.05)
        for pb, pl in zip(base["points"], lossy["points"]):
            self.assertEqual(pb["status"], pl["status"])
            if pb["status"] == "ok":
                self.assertLess(pl["P_out_B"], pb["P_out_B"])
                self.assertGreater(pl["P_th_B_W"], pb["P_th_B_W"])


if __name__ == "__main__":
    unittest.main()
