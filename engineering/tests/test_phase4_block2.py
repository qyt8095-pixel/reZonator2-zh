"""Phase 4 block 2 tests: thermal conduction + fracture.

Conventions locked here:
* The Gaussian heat source is normalised to the beam-intensity
  prefactor ``2/(pi*w_p^2)`` (the Gemini review's ``1/(2*pi*w_p^2)``
  integrates to ``P_abs/4`` -- a 4x error, corrected and locked by
  the energy-balance test).
* The OPD closed loop compares the FEA ``f_th`` against the analytic
  Gaussian value ``1/f = eta_h*P_abs*(dn/dT)/(pi*K*w_p^2)`` (the
  Phase 2 physics estimate uses ``2*pi`` -- the top-hat result,
  exactly 2x weaker; the demo reports both, the test locks the
  Gaussian one).
* Robin boundary signs are locked by the manufactured-solution
  tests (a uniform-temperature check cannot see a sign error: the
  diagonal and RHS mistakes cancel).
"""

import copy
import math
import os
import time
import unittest

import numpy as np

from rezeng.thermal import (
    ThermalError, analytic_f_th_gaussian, bulge_displacement,
    fill_thermal_typical, fit_opd, heat_source, heat_source_power_W,
    material_thermal, opd_from_field, resolve_thermal, solve_poisson_cyl,
    solve_poisson_slab, solve_rod, thermal_report)
from rezeng.fracture import (
    FractureError, fracture_margin, fracture_report, stress_field,
    stress_from_profile)
from rezeng import load_rez, load_eng

HERE = os.path.dirname(os.path.abspath(__file__))
ENG_DIR = os.path.dirname(HERE)
USER_REZ = "/home/hatch/workspace/user/files/upload.rez"
THERMAL_ENG = os.path.join(HERE, "data", "example-thermal.eng.json")

K_YVO4 = 5.2
DN_DT = 3.0e-6


def _rod_spec(**over):
    spec = {
        "R0_m": 5.0e-3, "L_m": 27.0e-3, "material": "Nd:YVO4",
        "P_pump_W": 5.0, "eta_p": 0.95, "eta_h": 0.24,
        "alpha_per_m": 1000.0, "w_p0_m": 200e-6, "Mp2": 1.2,
        "lambda_p_m": 808e-9, "z_p0_m": 13.5e-3, "profile": "gaussian",
        "h_W_per_m2K": 5000.0, "T_cool_C": 20.0,
        "end_faces": "adiabatic", "Nr": 60, "Nz": 150,
    }
    spec.update(over)
    return spec


class HeatSourceTest(unittest.TestCase):
    def test_gaussian_energy_balance(self):
        """int Q dV = eta_h * P_abs (catches the review's 4x error)."""
        R0, L = 5.0e-3, 27.0e-3
        r = np.linspace(0.0, R0, 401)
        z = np.linspace(0.0, L, 300)
        alpha = np.full_like(z, 1000.0)
        w_p = np.full_like(z, 200e-6)
        Q = heat_source(r, z, 5.0, alpha, w_p, 0.24, profile="gaussian")
        total = heat_source_power_W(Q, r, z)
        p_abs = 5.0 * (1.0 - math.exp(-1000.0 * L))
        # Radial truncation: the pump tail outside R0 is lost.
        trunc = 1.0 - math.exp(-2.0 * R0 ** 2 / (200e-6) ** 2)
        self.assertAlmostEqual(total, 0.24 * p_abs * trunc, delta=0.003)

    def test_tophat_energy_balance(self):
        R0, L = 5.0e-3, 27.0e-3
        # Fine radial grid: the trapezoid rule is poor on the
        # discontinuous top-hat edge (error ~ dr/w_p).
        r = np.linspace(0.0, 1.0e-3, 201)
        z = np.linspace(0.0, L, 300)
        alpha = np.full_like(z, 1000.0)
        w_p = np.full_like(z, 200e-6)
        Q = heat_source(r, z, 5.0, alpha, w_p, 0.24, profile="tophat")
        total = heat_source_power_W(Q, r, z)
        p_abs = 5.0 * (1.0 - math.exp(-1000.0 * L))
        # Trapezoid on a discontinuous edge has ~dr/w_p error.
        self.assertAlmostEqual(total, 0.24 * p_abs, delta=0.05)

    def test_on_axis_value(self):
        """Q(0, z) = 2*eta_h*alpha*P_inc/(pi*w_p^2)."""
        r = np.linspace(0.0, 5.0e-3, 60)
        z = np.linspace(0.0, 27.0e-3, 150)
        alpha = np.full_like(z, 1000.0)
        w_p = np.full_like(z, 200e-6)
        Q = heat_source(r, z, 5.0, alpha, w_p, 0.24)
        p_inc_0 = 5.0
        expected = 2.0 * 0.24 * 1000.0 * p_inc_0 / (math.pi * (200e-6) ** 2)
        self.assertAlmostEqual(Q[0, 0], expected, delta=expected * 1e-9)
        # At z = 10 mm the pump is attenuated by exp(-10).
        p_inc = 5.0 * math.exp(-1000.0 * z[55])
        expected_z = 2.0 * 0.24 * 1000.0 * p_inc / (math.pi * (200e-6) ** 2)
        self.assertAlmostEqual(Q[0, 55], expected_z,
                               delta=expected_z * 1e-9)

    def test_unknown_profile(self):
        r = np.linspace(0.0, 1e-3, 5)
        z = np.linspace(0.0, 1e-3, 5)
        with self.assertRaises(ThermalError):
            heat_source(r, z, 1.0, np.ones(5), np.full(5, 1e-4), 0.2,
                        profile="donut")


class CylindricalSolverTest(unittest.TestCase):
    def test_uniform_Q_analytic(self):
        """Uniform Q, Dirichlet side, adiabatic ends: parabolic profile."""
        R0, L, k, Q0, tc = 2.0e-3, 10.0e-3, 5.2, 1.0e6, 20.0
        r = np.linspace(0.0, R0, 60)
        z = np.linspace(0.0, L, 40)
        Q = np.full((len(r), len(z)), Q0)
        T = solve_poisson_cyl(Q, r, z, k, side=("dirichlet", tc),
                              ends=("adiabatic",))
        exact = tc + Q0 * (R0 ** 2 - r ** 2) / (4.0 * k)
        err = np.max(np.abs(T - exact[:, None])) / (Q0 * R0 ** 2 / (4 * k))
        self.assertLess(err, 0.01)
        # z-independent (adiabatic ends + z-uniform Q).
        self.assertLess(np.max(np.abs(T - T[:, :1])), 1e-9)

    def test_manufactured_solution(self):
        """T = T0 + A(1-r^2/R0^2)(1+0.3 sin^2(pi z/L)), Dirichlet side."""
        R0, L, k, T0, A = 2.0e-3, 10.0e-3, 5.2, 20.0, 10.0
        Nr, Nz = 60, 80
        r = np.linspace(0.0, R0, Nr)
        z = np.linspace(0.0, L, Nz)
        R, Z = np.meshgrid(r, z, indexing="ij")
        f = 1.0 + 0.3 * np.sin(math.pi * Z / L) ** 2
        f2 = 0.3 * 2.0 * (math.pi / L) ** 2 * np.cos(2 * math.pi * Z / L)
        T_ex = T0 + A * (1.0 - R ** 2 / R0 ** 2) * f
        lap = -4.0 * A * f / R0 ** 2 + A * (1.0 - R ** 2 / R0 ** 2) * f2
        Q = -k * lap
        T = solve_poisson_cyl(Q, r, z, k, side=("dirichlet", T0),
                              ends=("adiabatic",))
        err = np.max(np.abs(T - T_ex)) / A
        self.assertLess(err, 0.01)

    def test_robin_cools(self):
        """Robin side with no heat source: uniform T_cool; with heat,
        the edge sits above T_cool and the axis hotter still."""
        R0, L, k = 2.0e-3, 10.0e-3, 5.2
        r = np.linspace(0.0, R0, 40)
        z = np.linspace(0.0, L, 30)
        T = solve_poisson_cyl(np.zeros((len(r), len(z))), r, z, k,
                              side=("robin", 5000.0, 20.0),
                              ends=("adiabatic",))
        self.assertLess(np.max(np.abs(T - 20.0)), 1e-9)
        Q = np.full((len(r), len(z)), 1.0e6)
        T = solve_poisson_cyl(Q, r, z, k, side=("robin", 5000.0, 20.0),
                              ends=("adiabatic",))
        self.assertGreater(T[0, 0], T[-1, 0])
        self.assertGreater(T[-1, 0], 20.0)
        # Energy balance: heat out through the barrel = heat in.
        # Outward flux at r=R0: h (T_edge - T_cool) per unit area.
        flux = 5000.0 * (T[-1, :] - 20.0)          # W/m^2
        power_out = float(np.trapz(flux * 2 * math.pi * R0, z))
        power_in = 1.0e6 * math.pi * R0 ** 2 * L
        self.assertAlmostEqual(power_out, power_in, delta=power_in * 0.02)

    def test_solve_time(self):
        """spsolve on the default 60x150 grid (assembly + solve)."""
        spec = _rod_spec()
        res = solve_rod(spec)
        t0 = time.perf_counter()
        solve_poisson_cyl(res["Q_W_per_m3"], res["r_m"], res["z_m"],
                          res["k_W_per_mK"],
                          side=("robin", 5000.0, 20.0),
                          ends=("adiabatic",))
        dt = time.perf_counter() - t0
        print("\n  [timing] 60x150 rod solve: %.3f s" % (dt,))
        self.assertLess(dt, 5.0)


class SlabSolverTest(unittest.TestCase):
    def test_manufactured_solution(self):
        W, t, k, T0, A = 10.0e-3, 2.0e-3, 5.2, 20.0, 5.0
        Nx, Ny = 50, 30
        x = np.linspace(-W / 2, W / 2, Nx)
        y = np.linspace(-t / 2, t / 2, Ny)
        X, Y = np.meshgrid(x, y, indexing="ij")
        s = np.sin(math.pi * (X + W / 2) / W) * np.sin(
            math.pi * (Y + t / 2) / t)
        T_ex = T0 + A * s
        Q = k * A * math.pi ** 2 * (1.0 / W ** 2 + 1.0 / t ** 2) * s
        T = solve_poisson_slab(Q, x, y, k,
                               top_bottom=("dirichlet", T0),
                               sides=("dirichlet", T0))
        self.assertLess(np.max(np.abs(T - T_ex)) / A, 0.01)

    def test_slab_symmetry_and_cooling(self):
        """Gaussian heat, cooled large faces: symmetric, hotter inside."""
        W, t, k = 10.0e-3, 2.0e-3, 5.2
        x = np.linspace(-W / 2, W / 2, 50)
        y = np.linspace(-t / 2, t / 2, 30)
        X, Y = np.meshgrid(x, y, indexing="ij")
        Q = 1.0e7 * np.exp(-2 * (X ** 2 + Y ** 2) / (1.0e-3) ** 2)
        T = solve_poisson_slab(Q, x, y, k,
                               top_bottom=("robin", 5000.0, 20.0),
                               sides=("adiabatic",))
        self.assertLess(np.max(np.abs(T - T[:, ::-1])), 1e-9)
        self.assertLess(np.max(np.abs(T - T[::-1, :])), 1e-9)
        self.assertGreater(T[len(x) // 2, len(y) // 2], T[0, len(y) // 2])


class OpdClosedLoopTest(unittest.TestCase):
    def test_on_axis_curvature_exact(self):
        """Direct T''(0) curvature vs the analytic value (< 2%).

        The PDE identity ``2*int T''(0,z) dz = -int Q(0,z)/k dz``
        (adiabatic ends) makes this exact for the solver; it tests
        the discretisation, not the polynomial fit.  (The fitted
        ``f_th`` over ``r <= 1.5*w_L`` is an *effective* lens over
        the mode and runs ~11% above the paraxial value -- see
        ``test_opd_fit_range_effect`` -- so it is not compared
        against the analytic value here.)
        """
        spec = _rod_spec()
        res = solve_rod(spec)
        T, r, z = res["T_C"], res["r_m"], res["z_m"]
        mat = res["material"]
        dn_dT, k = mat["dn_dT_per_K"], mat["k_W_per_mK"]
        q_axis = float(np.trapz(res["Q_W_per_m3"][0, :], z))
        c2_exact = -dn_dT * q_axis / (4.0 * k)
        dr = r[1] - r[0]
        tpp0 = 2.0 * (T[1, :] - T[0, :]) / dr ** 2
        c2_direct = dn_dT * float(np.trapz(tpp0, z)) / 2.0
        print("\n  [closed loop] on-axis c2 direct=%.4f, exact=%.4f"
              % (c2_direct, c2_exact))
        self.assertLess(abs(c2_direct - c2_exact) / abs(c2_exact), 0.02)

    def test_opd_fit_range_effect(self):
        """A narrow fit recovers the paraxial value; the 1.5*w_L fit
        is the effective lens over the mode (~11% longer)."""
        spec = _rod_spec(Nr=120, Nz=300)
        res = solve_rod(spec)
        T, r, z = res["T_C"], res["r_m"], res["z_m"]
        mat = res["material"]
        dn_dT = mat["dn_dT_per_K"]
        q_axis = float(np.trapz(res["Q_W_per_m3"][0, :], z))
        f_exact = -1.0 / (2.0 * (-dn_dT * q_axis / (4.0 * mat["k_W_per_mK"])))
        opd = opd_from_field(T, r, z, dn_dT, mat["n_1064"],
                             T_ref_C=res["T_cool_C"])
        w_L = 250e-6
        f_narrow = fit_opd(r, opd, w_L, r_max_factor=1.0)["f_th_m"]
        f_wide = fit_opd(r, opd, w_L, r_max_factor=1.5)["f_th_m"]
        print("\n  [fit range] analytic=%.1f mm, fit(1.0 w_L)=%.1f mm, "
              "fit(1.5 w_L)=%.1f mm"
              % (f_exact * 1e3, f_narrow * 1e3, f_wide * 1e3))
        self.assertLess(abs(f_narrow - f_exact) / f_exact, 0.05)
        self.assertGreater(f_wide, f_narrow)

    def test_analytic_matches_formula(self):
        """analytic_f_th_gaussian == the closed-form 1/f expression."""
        f = analytic_f_th_gaussian(1.14, 3.0e-6, 5.2, 200e-6)
        expect = math.pi * 5.2 * (200e-6) ** 2 / (1.14 * 3.0e-6)
        self.assertAlmostEqual(f, expect, delta=expect * 1e-12)

    def test_grid_convergence(self):
        """Second-order convergence; 60x150 is coarse for a 200 um
        pump (documented, not hidden): T_max deviates ~8% and f_th
        ~15% from the 120x300 grid, and the deviations shrink ~4x
        per doubling."""
        base = _rod_spec()
        results = {}
        for Nr, Nz in ((60, 150), (120, 300), (240, 600)):
            res = solve_rod(dict(base, Nr=Nr, Nz=Nz))
            mat = res["material"]
            w_L = 250e-6
            f = fit_opd(res["r_m"], opd_from_field(
                res["T_C"], res["r_m"], res["z_m"], mat["dn_dT_per_K"],
                mat["n_1064"], T_ref_C=20.0), w_L)["f_th_m"]
            results[(Nr, Nz)] = (float(np.max(res["T_C"])) - 20.0, f)
        t60, f60 = results[(60, 150)]
        t120, f120 = results[(120, 300)]
        t240, f240 = results[(240, 600)]
        dT1 = abs(t120 - t60) / t60
        dT2 = abs(t240 - t120) / t120
        df1 = abs(f120 - f60) / f60
        df2 = abs(f240 - f120) / f120
        print("\n  [convergence] dT 60->120=%.2f%%, 120->240=%.2f%%; "
              "df 60->120=%.2f%%, 120->240=%.2f%%"
              % (100 * dT1, 100 * dT2, 100 * df1, 100 * df2))
        # Second order: each doubling cuts the error ~4x.
        self.assertLess(dT2, dT1 / 2.0)
        self.assertLess(df2, df1 / 2.0)
        # The 120x300 grid is within a few percent of the 240x600 one.
        self.assertLess(dT2, 0.03)
        self.assertLess(df2, 0.06)

    def test_end_caps(self):
        """End caps: no heat in the undoped zones, field continuous."""
        spec = _rod_spec(segments=[
            {"z0_mm": 0.0, "z1_mm": 2.0, "alpha_per_cm": 0.0},
            {"z0_mm": 2.0, "z1_mm": 25.0, "alpha_per_cm": 10.0},
            {"z0_mm": 25.0, "z1_mm": 27.0, "alpha_per_cm": 0.0}])
        res = solve_rod(spec)
        z = res["z_m"]
        cap = (z < 1.9e-3) | (z > 25.1e-3)
        self.assertLess(float(np.max(np.abs(res["Q_W_per_m3"][:, cap]))),
                        1e-9)
        # Absorbed power still matches the doped length only.
        p_abs = 5.0 * 0.95 * (1.0 - math.exp(-1000.0 * 23.0e-3))
        self.assertAlmostEqual(res["P_abs_W"], p_abs, delta=p_abs * 1e-9)
        self.assertTrue(np.all(np.isfinite(res["T_C"])))


class FractureTest(unittest.TestCase):
    def test_constant_temperature_zero_stress(self):
        r = np.linspace(0.0, 2.0e-3, 50)
        T = np.full_like(r, 50.0)
        s_r, s_t, s_z = stress_from_profile(r, T, 4.4e-6, 133e9, 0.33)
        self.assertLess(np.max(np.abs(s_r)), 1e-6)
        self.assertLess(np.max(np.abs(s_t)), 1e-6)
        self.assertLess(np.max(np.abs(s_z)), 1e-6)

    def test_parabolic_profile_analytic(self):
        """T = T0 + dT(1-r^2/R0^2): sigma_max = alpha*E*dT/(2(1-nu))."""
        R0, dT = 2.0e-3, 10.0
        alpha, E, nu = 4.4e-6, 133e9, 0.33
        r = np.linspace(0.0, R0, 200)
        T = 20.0 + dT * (1.0 - r ** 2 / R0 ** 2)
        s_r, s_t, s_z = stress_from_profile(r, T, alpha, E, nu)
        C = alpha * E / (1.0 - nu)
        expect_max = C * dT / 2.0
        self.assertAlmostEqual(float(np.max(s_t)), expect_max,
                               delta=expect_max * 0.01)
        self.assertAlmostEqual(float(np.max(s_z)), expect_max,
                               delta=expect_max * 0.01)
        # Radial stress vanishes at the free surface, is -C*dT/4 on axis.
        self.assertAlmostEqual(float(s_r[-1]), 0.0, delta=expect_max * 0.01)
        self.assertAlmostEqual(float(s_r[0]), -C * dT / 4.0,
                               delta=expect_max * 0.01)

    def test_margin_thresholds(self):
        self.assertEqual(fracture_margin(10e6, 50.0)[1], "ok")
        self.assertEqual(fracture_margin(20e6, 50.0)[1], "warn")
        self.assertEqual(fracture_margin(30e6, 50.0)[1], "fail")
        self.assertAlmostEqual(fracture_margin(10e6, 50.0)[0], 0.8)

    def test_bulge_uniform(self):
        """Uniform dT over z_eff: u_z = (1+nu)*alpha*dT*z_eff."""
        r = np.linspace(0.0, 2.0e-3, 10)
        z = np.linspace(0.0, 10.0e-3, 21)
        T = np.full((len(r), len(z)), 30.0)
        u = bulge_displacement(T, r, z, 4.4e-6, 0.33, z_eff_m=2.0e-3,
                               T_ref_C=20.0)
        expect = 1.33 * 4.4e-6 * 10.0 * 2.0e-3
        self.assertTrue(np.allclose(u, expect, rtol=1e-9))
        # z_eff between nodes: the partial interval is interpolated.
        u2 = bulge_displacement(T, r, z, 4.4e-6, 0.33, z_eff_m=2.3e-3,
                                T_ref_C=20.0)
        expect2 = 1.33 * 4.4e-6 * 10.0 * 2.3e-3
        self.assertTrue(np.allclose(u2, expect2, rtol=1e-9))

    def test_stress_field_primary_vs_peak(self):
        spec = _rod_spec()
        res = solve_rod(spec)
        mat = res["material"]
        field = stress_field(res["T_C"], res["r_m"], res["z_m"],
                             mat["alpha_a_per_K"], mat["E_GPa"] * 1e9,
                             mat["nu"])
        # The hot pumped face peaks above the z-averaged value.
        self.assertGreater(field["local_peak"]["sigma_max_Pa"],
                           field["primary"]["sigma_max_Pa"])
        self.assertGreater(field["primary"]["sigma_max_Pa"], 0.0)


class ResolveTest(unittest.TestCase):
    def test_missing_fields_raise(self):
        data = load_rez(USER_REZ)
        eng = load_eng(THERMAL_ENG)
        for path in (("thermal", "pump", "P_pump_W"),
                     ("thermal", "pump", "eta_h"),
                     ("thermal", "cooling", "h_W_per_m2K")):
            bad = copy.deepcopy(eng)
            node = bad
            for key in path[:-1]:
                node = node[key]
            del node[path[-1]]
            with self.assertRaises(ThermalError):
                resolve_thermal(data, bad)
        bad = copy.deepcopy(eng)
        bad["thermal"]["material"] = "Unobtainium"
        with self.assertRaises(ThermalError):
            resolve_thermal(data, bad)

    def test_fill_typical_keeps_overrides(self):
        filled = fill_thermal_typical({
            "material": "Nd:YVO4",
            "material_overrides": {"dn_dT_per_K": 3.0e-6}})
        self.assertEqual(filled["material_overrides"]["dn_dT_per_K"], 3.0e-6)
        self.assertEqual(filled["material_overrides"]["k_W_per_mK"], 5.2)
        self.assertEqual(material_thermal("YVO4")["k_W_per_mK"], 5.2)
        with self.assertRaises(ThermalError):
            material_thermal("Unobtainium")


class ReportTest(unittest.TestCase):
    def test_demo_report(self):
        data = load_rez(USER_REZ)
        eng = load_eng(THERMAL_ENG)
        rep = thermal_report(data, eng, w_L_um=250.0)
        self.assertGreater(rep["T_max_C"], 20.0)
        self.assertLess(rep["T_max_C"], 200.0)
        self.assertIsNotNone(rep["closed_loop_dev"])
        self.assertLess(abs(rep["closed_loop_dev"]), 0.10)
        self.assertIn("fracture", rep)
        self.assertIn(rep["fracture"]["status"], ("ok", "warn", "fail"))
        # Phase 2 anchor model at 5 W must give back ~230 mm.
        lin = rep["linear_model"]
        self.assertIn("F_T_mm", lin)
        self.assertAlmostEqual(lin["F_T_mm"], 230.0, delta=5.0)
        self.assertIn("phase_plate", rep)
        self.assertGreater(rep["phase_plate"]["f_th_mm"], 0.0)


if __name__ == "__main__":
    unittest.main()
