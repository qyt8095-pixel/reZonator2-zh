"""Phase 4 block 1 tests: ghosts / red light / export.

Conventions locked here:
* Alpha is the angle of incidence (AOI), verified against the C++
  source (``src/core/Elements.cpp`` ``ElemCurveMirror``).
* A flat-face ghost is the exact time reversal of the main beam:
  its ``w`` must match the CLI beam at every plane.
* The off-axis ghost ray is traced with the 3x3 augmented ABCD
  formalism; a pure 2x2 co-axial trace cannot see it leave an
  aperture.
"""

import copy
import math
import os
import unittest

import numpy as np

from rezeng.cli import run_headless
from rezeng.ghosts import (ETALON_MIN_RR, GHOST_MIN_R, build_chain,
                           build_surfaces, etalon_fsr_Hz,
                           etalon_modulation, reflect_q, scan_etalons,
                           scan_ghosts, trace_ghost)
from rezeng.redlight import material_index, redlight_report
from rezeng.export import (coating_table, thin_lens_spot_check, to_dxf,
                           to_zmx, validate_dxf, validate_zmx)
from rezeng.rez import load_rez

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
USER_REZ = "/home/hatch/workspace/user/files/upload.rez"

C_LIGHT = 299792458.0


def _param(value, unit):
    return {"error": "", "expr": "", "unit": unit, "value": value}


def _element(label, etype, params, title=""):
    return {"is_disabled": False, "label": label,
            "layout_draw_alt": False, "layout_show_label": True,
            "params": params, "title": title, "type": etype}


def _mirror(label, R_mm, alpha_deg=0.0, title=""):
    params = {"R": _param(R_mm, "mm")}
    if alpha_deg is not None:
        params["Alpha"] = _param(alpha_deg, "deg")
    return _element(label, "ElemCurveMirror", params, title)


def _flat_mirror(label, title=""):
    return _element(label, "ElemFlatMirror", {}, title)


def _range(label, L_mm):
    return _element(label, "ElemEmptyRange",
                    {"L": _param(L_mm, "mm"), "n": _param(1, "none")})


def _plate(label, L_mm, n):
    return _element(label, "ElemPlate",
                    {"L": _param(L_mm, "mm"), "n": _param(n, "none")})


def _schema(elements, lambda_nm=1064.0, title="test cavity"):
    return {"builtin_params": {"lambda": {"unit": "nm",
                                          "value": lambda_nm}},
            "custom_params": {}, "elements": elements, "formulas": [],
            "notes": "", "param_links": [], "pumps": [],
            "schema_version": 2.1, "title": title, "trip_type": "SW",
            "windows": []}


def _symmetric_cavity_with_plate():
    """Symmetric R=200 mm, L=100 mm cavity, waist at the centre,
    with a 20 mm plate (label PLATE) centred on the waist
    (s = 40..60 mm). g = 0.5, stable."""
    return _schema([
        _mirror("M1", 200.0),
        _range("d1", 40.0),
        _plate("PLATE", 20.0, 1.5),
        _range("d2", 40.0),
        _mirror("M2", 200.0),
    ])


def _cli(data):
    result = run_headless({"base_schema": data, "mutations": []})
    return result["results"][0]


class TestAlphaDefinition(unittest.TestCase):
    def test_alpha_is_incidence_angle_in_source(self):
        """Alpha is the AOI, not the fold angle (C++ source)."""
        path = os.path.join(REPO, "src", "core", "Elements.cpp")
        with open(path, "r", encoding="utf-8") as f:
            src = f.read()
        # ElemCurveMirror declares Alpha as "入射角" (angle of
        # incidence), "zero angle is normal incidence".
        self.assertIn("入射角", src)
        self.assertIn("零角度即正入射", src)
        # The matrix is the standard oblique-incidence mirror
        # matrix with alpha = AOI: T: C = -2/(R*cos a),
        # S: C = -2*cos(a)/R.
        self.assertIn("T_(1, 0, -2.0 / radius() / cos(alpha()), 1)", src)
        self.assertIn("S_(1, 0, -2.0 / radius() * cos(alpha()), 1)", src)

    def test_alpha_used_as_aoi_in_python(self):
        """The Python matrix agrees with the C++ AOI definition."""
        from rezeng.qevolve import element_matrix
        data = _schema([_mirror("M", 500.0, alpha_deg=2.5),
                        _range("d", 10.0),
                        _mirror("M2", 500.0)])
        M_T, M_S = element_matrix(data, "M")
        alpha = math.radians(2.5)
        self.assertAlmostEqual(M_T[1, 0], -2.0 / (0.5 * math.cos(alpha)),
                               places=9)
        self.assertAlmostEqual(M_S[1, 0],
                               -2.0 * math.cos(alpha) / 0.5, places=9)


class TestEtalon(unittest.TestCase):
    def test_fsr_and_modulation_hand_computed(self):
        """FSR = c/(2nL) and M = 4s/(1+s)^2, TL1's two faces."""
        # TL1: L = 27 mm, n = 2.16.
        fsr = etalon_fsr_Hz(2.16, 27e-3) / 1e9
        expected = C_LIGHT / (2.0 * 2.16 * 27e-3) / 1e9
        self.assertAlmostEqual(fsr, expected, places=9)
        self.assertAlmostEqual(fsr, 2.5702, places=3)
        mod = etalon_modulation(0.002, 0.002)
        self.assertAlmostEqual(mod, 4 * 0.002 / 1.002 ** 2, places=12)
        self.assertLess(mod, 0.05)
        # High reflectivity -> modulation above the 5% warning level.
        self.assertGreater(etalon_modulation(0.05, 0.05), 0.05)

    def test_pruning_threshold_both_sides(self):
        """R_i*R_j > 1e-6 is kept, below it is pruned."""
        data = load_rez(USER_REZ)
        eng = {"surfaces": {"TL1": {"faces": [
            {"face": "front", "R_1064": 0.002},
            {"face": "back", "R_1064": 0.002}]}}}
        pairs = scan_etalons(data, eng, 1064.0,
                             chain=build_chain(data, _cli(data), eng))
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0]["status"], "ok")
        self.assertAlmostEqual(pairs[0]["R1"] * pairs[0]["R2"], 4e-6)
        # Just below the threshold: 5e-4 * 5e-4 = 2.5e-7 -> pruned.
        eng["surfaces"]["TL1"]["faces"][0]["R_1064"] = 0.0005
        eng["surfaces"]["TL1"]["faces"][1]["R_1064"] = 0.0005
        pairs = scan_etalons(data, eng, 1064.0,
                             chain=build_chain(data, _cli(data), eng))
        self.assertEqual(len(pairs), 0)
        # One side above, product below: 0.002 * 0.0004 = 8e-7.
        eng["surfaces"]["TL1"]["faces"][0]["R_1064"] = 0.002
        eng["surfaces"]["TL1"]["faces"][1]["R_1064"] = 0.0004
        pairs = scan_etalons(data, eng, 1064.0,
                             chain=build_chain(data, _cli(data), eng))
        self.assertEqual(len(pairs), 0)
        # High reflectivity -> warn on modulation.
        eng["surfaces"]["TL1"]["faces"][0]["R_1064"] = 0.05
        eng["surfaces"]["TL1"]["faces"][1]["R_1064"] = 0.05
        pairs = scan_etalons(data, eng, 1064.0,
                             chain=build_chain(data, _cli(data), eng))
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0]["status"], "warn")

    def test_missing_reflectivity_is_nodata(self):
        """A surface without R is nodata, never defaulted."""
        data = load_rez(USER_REZ)
        eng = {"surfaces": {"TL1": {"faces": [
            {"face": "front", "R_1064": 0.002},
            {"face": "back"}]}}}
        pairs = scan_etalons(data, eng, 1064.0,
                             chain=build_chain(data, _cli(data), eng))
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0]["status"], "nodata")
        self.assertIsNone(pairs[0]["R2"])


class TestGhostTrace(unittest.TestCase):
    def test_flat_ghost_retraces_main_beam(self):
        """A flat-face ghost's w matches the CLI beam at every plane."""
        data = load_rez(USER_REZ)
        eng = {"surfaces": {
            "TL1": {"faces": [{"face": "front", "R_1064": 0.002},
                              {"face": "back", "R_1064": 0.002}]},
            "M4": {"faces": [{"face": "back", "R_1064": 0.002}]}}}
        result = _cli(data)
        self.assertTrue(result["stable"])
        chain = build_chain(data, result, eng)
        plane_w = {}
        for seg in chain:
            entry = next(b for b in result["beam"]
                         if b["label"] == seg["label"])
            plane_w[round(seg["s_out_mm"], 6)] = (entry["w_T_mm"],
                                                  entry["w_S_mm"])
        for surface in build_surfaces(data, eng):
            trace = trace_ghost(data, chain, surface, 1064.0)
            worst = 0.0
            for label, s, w_T, w_S, _x_T, _x_S in trace["path"]:
                ref = plane_w[round(s, 6)]
                for a, b in ((w_T, ref[0]), (w_S, ref[1])):
                    worst = max(worst, abs(a - b) / max(b, 1e-12))
            self.assertLess(worst, 1e-9,
                            "ghost %s does not retrace (worst %.3g)"
                            % (trace["surface"], worst))

    def test_reflect_q_curved_face_hand_computed(self):
        """Reflection off a curved face: 1/q' = 1/(-conj q) + C."""
        lam_m = 1064e-9
        from rezeng.qevolve import q_from_wr, wr_from_q
        q_in = q_from_wr(0.2e-3, 500e-3, lam_m)
        C = -2.0 / 0.3  # mirror R = 300 mm
        q_out = reflect_q(q_in, C)
        # w is unchanged by a lossless reflection; R follows the
        # mirror law 1/R' = -1/R + C.
        w_out, R_out = wr_from_q(q_out, lam_m)
        self.assertAlmostEqual(w_out, 0.2e-3, places=12)
        expected_R = 1.0 / (-1.0 / 0.5 + C)
        self.assertAlmostEqual(R_out, expected_R, places=9)
        # Flat face: exact time reversal.
        q_flat = reflect_q(q_in, 0.0)
        self.assertAlmostEqual(q_flat.real, -q_in.real, places=12)
        self.assertAlmostEqual(q_flat.imag, q_in.imag, places=12)

    def test_burn_point_inside_crystal(self):
        """Ghost waist inside the plate (crystal): hand-computed fluence."""
        data = _symmetric_cavity_with_plate()
        result = _cli(data)
        self.assertTrue(result["stable"])
        # Waist of the symmetric cavity is at the centre (s=50 mm),
        # inside the plate (40..60 mm).
        eng = {
            "laser": {"pulse_energy_J": 1e-3},
            "elements": {"PLATE": {"lidt_J_per_cm2": 0.01}},
            "surfaces": {"PLATE": {"faces": [
                {"face": "front", "R_1064": 0.01},
                {"face": "back", "R_1064": 0.01}]}},
        }
        report = scan_ghosts(data, eng, 1064.0)
        back = next(g for g in report["ghosts"]
                    if g["surface"] == "PLATE:back")
        self.assertEqual(back["status"], "fail")
        burn = back["burn"]
        self.assertIsNotNone(burn)
        self.assertEqual(burn["element"], "PLATE")
        self.assertGreater(burn["s_mm"], 40.0)
        self.assertLess(burn["s_mm"], 60.0)
        # The waist is at the cavity centre (s = 50 mm): the
        # physical waist inside the plate is at u = -n*Re(q_air),
        # not -Re(q_air).
        self.assertAlmostEqual(burn["s_mm"], 50.0, places=6)
        # Hand-computed fluence: F = 2*E*R/(pi*w0_T*w0_S).
        w0_T = burn["w0_T_mm"] / 10.0
        w0_S = burn["w0_S_mm"] / 10.0
        expected = 2.0 * 1e-3 * 0.01 / (math.pi * w0_T * w0_S)
        self.assertAlmostEqual(burn["fluence_J_per_cm2"], expected,
                               places=9)
        self.assertAlmostEqual(burn["ratio"], expected / 0.01, places=9)
        # Raise the LIDT: the same ghost becomes a warning, then ok.
        eng["elements"]["PLATE"]["lidt_J_per_cm2"] = expected / 0.85
        report = scan_ghosts(data, eng, 1064.0)
        back = next(g for g in report["ghosts"]
                    if g["surface"] == "PLATE:back")
        self.assertEqual(back["status"], "warn")
        eng["elements"]["PLATE"]["lidt_J_per_cm2"] = 10.0
        report = scan_ghosts(data, eng, 1064.0)
        back = next(g for g in report["ghosts"]
                    if g["surface"] == "PLATE:back")
        self.assertEqual(back["status"], "ok")


class TestOffAxisGhost(unittest.TestCase):
    def test_wedge_ray_displacement_locked(self):
        """A wedged face gives the ghost ray 2*wedge; the drift
        through the plate is 2*wedge*L (hand-computed)."""
        data = _symmetric_cavity_with_plate()
        eng = {"surfaces": {"PLATE": {"faces": [
            {"face": "back", "R_1064": 0.01, "wedge_mrad": 5.0,
             "wedge_plane": "T"}]}}}
        result = _cli(data)
        chain = build_chain(data, result, eng)
        surface = next(s for s in build_surfaces(data, eng)
                       if s["element"] == "PLATE"
                       and s["face"] == "back")
        trace = trace_ghost(data, chain, surface, 1064.0)
        # After crossing the plate backwards the ray centre has
        # drifted by 2*wedge*(L/n): inside the plate the ray angle
        # is wedge/n (Snell), so the transverse drift over the
        # physical length L is 2*wedge*L/n = 2*5e-3*20/1.5 mm.
        plate_entry = [p for p in trace["path"]
                       if p[0] == "PLATE" and abs(p[1] - 40.0) < 1e-9]
        self.assertEqual(len(plate_entry), 1)
        self.assertAlmostEqual(plate_entry[0][4], 2 * 5e-3 * 20.0 / 1.5,
                               places=9)
        self.assertAlmostEqual(plate_entry[0][5], 0.0, places=9)

    def test_aperture_excludes_off_axis_ghost(self):
        """The 3x3 trace excludes a ghost the 2x2 trace would flag.

        The ghost from the plate's front face has its waist at the
        cavity centre (s=50 mm), reached only after passing M1.
        With a 1 mm aperture on M1 and a 10 mrad wedge, the ray
        centre (2*10 mrad * 40 mm = 0.8 mm) is outside the 0.5 mm
        radius, so the ghost leaves before its waist: no burn.
        With a large aperture the same ghost's waist is found and
        the burn is reported -- this is what a pure 2x2 trace
        (no ray, no aperture) would always report.
        """
        data = _symmetric_cavity_with_plate()
        base_eng = {
            "laser": {"pulse_energy_J": 1e-3},
            "elements": {"PLATE": {"lidt_J_per_cm2": 0.001}},
            "surfaces": {"PLATE": {"faces": [
                {"face": "front", "R_1064": 0.01, "wedge_mrad": 10.0,
                 "wedge_plane": "T"}]}},
        }
        # Small aperture on M1: ghost exits at M1, no waist reached.
        eng_small = copy.deepcopy(base_eng)
        eng_small["elements"]["M1"] = {"aperture_diameter_mm": 1.0}
        report = scan_ghosts(data, eng_small, 1064.0)
        front = next(g for g in report["ghosts"]
                     if g["surface"] == "PLATE:front")
        self.assertEqual(front["status"], "ok")
        self.assertIsNone(front["burn"])
        self.assertIsNotNone(front["exited"])
        self.assertEqual(front["exited"]["element"], "M1")
        self.assertEqual(front["waists"], [])
        # Large aperture: the waist is found and the burn is flagged.
        eng_big = copy.deepcopy(base_eng)
        eng_big["elements"]["M1"] = {"aperture_diameter_mm": 25.4}
        report = scan_ghosts(data, eng_big, 1064.0)
        front = next(g for g in report["ghosts"]
                     if g["surface"] == "PLATE:front")
        self.assertEqual(front["status"], "fail")
        self.assertIsNotNone(front["burn"])
        self.assertEqual(front["burn"]["element"], "PLATE")
        self.assertAlmostEqual(front["burn"]["s_mm"], 50.0, places=6)


class TestRedlight(unittest.TestCase):
    def test_sellmeier_values(self):
        """Library indices against published values."""
        self.assertAlmostEqual(material_index("Nd:YVO4:e", 1064.0),
                               2.165, places=3)
        self.assertAlmostEqual(material_index("Nd:YVO4:o", 1064.0),
                               1.957, places=3)
        self.assertAlmostEqual(material_index("Nd:YVO4:e", 632.8),
                               2.215, places=3)
        self.assertAlmostEqual(material_index("fused_silica", 632.8),
                               1.457, places=3)
        self.assertAlmostEqual(material_index("BK7", 632.8),
                               1.515, places=3)
        self.assertAlmostEqual(material_index("LBO:x", 1064.0),
                               1.565, places=3)
        with self.assertRaises(ValueError):
            material_index("unobtainium", 1064.0)

    def test_fallback_on_unstable_cold_cavity(self):
        """The user's cold cavity is unstable: the report must say
        so and switch to the injected HeNe (fallback), labelled."""
        eng = {"materials": {"TL1": {"material": "Nd:YVO4:e"}}}
        report = redlight_report(USER_REZ, eng, w0_mm=0.5)
        self.assertEqual(report["path"], "fallback")
        self.assertFalse(report["cold"]["stable"])
        self.assertAlmostEqual(report["cold"]["g_T"], -1.9545, places=3)
        self.assertIsNotNone(report["injected"])
        self.assertEqual(report["injected"]["element"], "M4")
        self.assertEqual(report["injected"]["w0_mm"], 0.5)
        self.assertFalse(report["injected"]["double_pass"])
        m4 = next(r for r in report["table"] if r["element"] == "M4")
        self.assertAlmostEqual(m4["w_633_T_mm"], 0.5, places=9)
        self.assertAlmostEqual(m4["w_1064_T_mm"], 0.205657, places=5)
        # The cold-cavity changes are recorded.
        changes = {(c["element"], c["param"]): c
                   for c in report["cold"]["changes"]}
        self.assertIn(("TL1", "F"), changes)
        self.assertAlmostEqual(changes[("TL1", "F")]["to"], 1e9)
        self.assertIn(("TL1", "n"), changes)
        self.assertAlmostEqual(changes[("TL1", "n")]["to"], 2.21546,
                               places=4)

    def test_cold_eigenmode_when_stable(self):
        """A cavity without a thermal lens stays stable when cold:
        the red beam is the cold eigenmode, not the fallback."""
        data = _symmetric_cavity_with_plate()
        report = redlight_report(data, {}, w0_mm=0.5)
        self.assertEqual(report["path"], "cold_eigenmode")
        self.assertTrue(report["cold"]["stable"])
        self.assertIsNone(report["injected"])
        for row in report["table"]:
            self.assertIsNotNone(row["w_633_T_mm"])


class TestExport(unittest.TestCase):
    def test_coating_table_user_cavity(self):
        """Coating table: AOI from Alpha, P/S rows, computed fluence."""
        eng = {
            "laser": {"pulse_energy_J": 1e-3, "pulse_duration_s": 10e-9},
            "elements": {
                "M1": {"lidt_J_per_cm2": 2.0},
                "M2": {"lidt_J_per_cm2": 5.0},
                "M4": {"lidt_J_per_cm2": 5.0},
                "TL1": {"lidt_J_per_cm2": 5.0}},
            "surfaces": {
                "M2": {"faces": [{"face": "back", "R_1064": 0.001,
                                  "role": "HR"}]},
                "M4": {"faces": [{"face": "back", "R_1064": 0.001,
                                  "role": "OC"}]},
                "TL1": {"faces": [
                    {"face": "front", "R_1064": 0.002, "role": "AR"},
                    {"face": "back", "R_1064": 0.002, "role": "AR"}]},
                "M1": {"faces": [{"face": "back", "R_1064": 0.001,
                                  "role": "SESAM"}]}},
        }
        table = coating_table(USER_REZ, eng)
        rows = table["rows"]
        # Mirror front faces are HR/OC/SESAM rows too (not just the
        # substrate backs): M2 front is a tilted HR mirror.
        m2f = [r for r in rows if r["element"] == "M2"
               and r["face"] == "front"]
        self.assertEqual(len(m2f), 2)
        self.assertEqual({r["polarization"] for r in m2f}, {"P", "S"})
        self.assertAlmostEqual(m2f[0]["AOI_deg"], 2.5, places=9)
        self.assertIn("HR>99.9%@1064nm", m2f[0]["spec"])
        # M1 front is the SESAM (title "sesam" in the .rez).
        m1f = [r for r in rows if r["element"] == "M1"
               and r["face"] == "front"]
        self.assertEqual(len(m1f), 1)
        self.assertIn("SESAM", m1f[0]["spec"])
        self.assertIsNone(m1f[0]["R_1064"])
        # M2 is tilted (Alpha 2.5 deg): two polarisation rows on
        # the back face as well.
        m2 = [r for r in rows if r["element"] == "M2"
              and r["face"] == "back"]
        self.assertEqual(len(m2), 2)
        self.assertEqual({r["polarization"] for r in m2}, {"P", "S"})
        self.assertAlmostEqual(m2[0]["AOI_deg"], 2.5, places=9)
        self.assertAlmostEqual(m2[0]["R_mm"], 500.0, places=9)
        self.assertIn("HR>99.9%@1064nm", m2[0]["spec"])
        # M4 is untilted: a single unpolarised row per face.
        m4 = [r for r in rows if r["element"] == "M4"
              and r["face"] == "back"]
        self.assertEqual(len(m4), 1)
        self.assertEqual(m4[0]["polarization"], "unpolarized")
        self.assertAlmostEqual(m4[0]["AOI_deg"], 0.0, places=9)
        # Fluence is computed from the CLI beam: M4 w = 0.2057/0.2113.
        expected = 2.0 * 1e-3 / (math.pi * 0.0205657 * 0.0211257)
        self.assertAlmostEqual(m4[0]["fluence_J_per_cm2"], expected,
                               places=3)
        self.assertIsNotNone(m4[0]["peak_kW_per_cm2"])
        # The text form matches the documented example format.
        self.assertIn("M2", table["text"])
        self.assertIn("AOI=2.5 deg", table["text"])

    def test_zmx_structure(self):
        """COORDBRK pairing, thickness signs, PARAXIAL effective f.

        The PARAXIAL carries the matrix-derived effective focal
        length (f = -1/C = 236.278 mm for TL1), NOT the .rez F
        (230 mm): the exact solve_n2 gamma differs from the
        thin-lens gamma, and the .rez F would shift the cavity's g
        from 0.929 to 0.985 (a ~35% beam error). The .rez F is
        reported alongside (f_rez_mm) and in the .zmx NOTE.
        """
        eng = {"materials": {"TL1": {"material": "Nd:YVO4:e"}},
               "elements_ext": {"M1": {
                   "saturation_fluence_uJ_per_cm2": 70.0,
                   "modulation_depth": 0.01}}}
        text, validation = to_zmx(USER_REZ, eng)
        self.assertTrue(validation["ok"])
        checks = {c["check"]: c for c in validation["checks"]}
        self.assertEqual(checks["COORDBRK pairing around MIRROR"]
                         ["mirrors"], 4)
        self.assertEqual(checks["COORDBRK pairing around MIRROR"]
                         ["paired"], 4)
        self.assertTrue(checks["THICKNESS sign flips after each "
                               "MIRROR"]["ok"])
        par = [c for c in validation["checks"]
               if c["check"].startswith("PARAXIAL f")]
        self.assertEqual(len(par), 1)
        self.assertAlmostEqual(par[0]["f_zmx_mm"], 236.27803356389202,
                               places=9)
        self.assertAlmostEqual(par[0]["f_eff_mm"], 236.27803356389202,
                               places=9)
        self.assertAlmostEqual(par[0]["f_rez_mm"], 230.0, places=9)
        self.assertIn("230 mm", text)
        # COORDBRK tilts use the AOI (2.5 and 4 deg), not the fold.
        self.assertIn("TILT X 2.500000", text)
        self.assertIn("TILT X 4.000000", text)
        self.assertNotIn("TILT X 5.000000", text)
        self.assertNotIn("TILT X 8.000000", text)
        # SESAM note is present; no OpticStudio claim.
        self.assertIn("SESAM", text)
        self.assertIn("NOT verified in OpticStudio", text)
        # Thickness after the first mirror is negative.
        lines = text.splitlines()
        thick = [float(l.split()[1]) for l in lines
                 if l.strip().startswith("THIC ")]
        self.assertTrue(any(t < 0 for t in thick))
        self.assertTrue(any(t > 0 for t in thick))

    def test_zmx_thin_lens_spot_check(self):
        """The .zmx thin-lens equivalent reproduces the CLI beam.

        The residual error (7.76% on the user cavity) is the
        stability-edge amplification of the thin-lens model's
        0.06% A/D mismatch: the cavity sits at g_T = 0.929, so
        even the best thin-lens equivalent shifts g to 0.955.
        The .rez F (230 mm) would give a 35% error instead.
        """
        check = thin_lens_spot_check(USER_REZ, {})
        self.assertEqual(check["replaced"], ["TL1"])
        self.assertLess(check["max_rel_err"], 0.10)

    def test_dxf_roundtrip_ezdxf(self):
        """ezdxf writer: layers, point counts, envelope vs CLI."""
        text, validation = to_dxf(USER_REZ, {}, use_ezdxf=True)
        self.assertTrue(validation["ok"])
        self.assertEqual(validation["writer"], "ezdxf")
        checks = {c["check"]: c for c in validation["checks"]}
        for layer in ("OPTICAL_AXIS", "BEAM_1E2", "BEAM_2W",
                      "ELEMENTS", "ANNOTATIONS"):
            self.assertTrue(checks["layer %s present" % layer]["ok"])
        self.assertTrue(checks["envelope max vs CLI max w (mm)"]["ok"])
        self.assertAlmostEqual(
            checks["envelope max vs CLI max w (mm)"]["cli_max_mm"],
            1.264098, places=4)

    def test_dxf_roundtrip_minimal_writer(self):
        """Hand-written minimal writer: same validation passes."""
        text, validation = to_dxf(USER_REZ, {}, use_ezdxf=False)
        self.assertTrue(validation["ok"])
        self.assertIn("minimal", validation["writer"])
        self.assertIn("LWPOLYLINE", text)
        # The minimal parser agrees with ezdxf on the layer set.
        from rezeng.export import _parse_dxf_minimal
        layers, counts = _parse_dxf_minimal(text)
        for layer in ("OPTICAL_AXIS", "BEAM_1E2", "BEAM_2W",
                      "ELEMENTS", "ANNOTATIONS"):
            self.assertIn(layer, layers)
        self.assertGreater(counts["BEAM_1E2"], 100)


if __name__ == "__main__":
    unittest.main()
