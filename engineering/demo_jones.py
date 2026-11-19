"""Demo: Jones polarisation + GDD/TOD on the user's real cavity.

Usage (from the repository root):
    python3 engineering/demo_jones.py

The .rez file is the user's real cavity (~/workspace/user/files/upload.rez).
All polarisation/dispersion numbers come from engineering/tests/data/
example-jones.eng.json and are INVENTED EXAMPLES, not the user's
measured data: TL1 is given a birefringent retardance Gamma = 0.15 rad
with GVD 245 fs^2/mm / TOD 310 fs^3/mm (fused silica at 1064 nm),
M1 is a SESAM with GDD -150 fs^2 / TOD 500 fs^3, M4 a chirped mirror
with GDD -300 fs^2 / TOD 1200 fs^3. The results below are therefore a
demonstration of the solver, not a prediction for the real laser.

The demo also shows the Jones -> power linkage: a waveplate inserted
at TL1 with different fast-axis angles changes the round-trip
polarisation loss, which changes the mode-A output power (via the
``extra_loss`` parameter of the power solver).
"""

import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))

from rezeng import load_rez, load_eng, validate_eng
from rezeng.jones import (round_trip_jones, eigen_polarization,
                          polarization_loss, jones_report)
from rezeng.dispersion import round_trip_dispersion
from rezeng.power import mode_a_output

REPO = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                     ".."))
USER_CAVITY = os.path.join(os.path.expanduser("~"), "workspace", "user",
                           "files", "upload.rez")
EXAMPLE_ENG = os.path.join(REPO, "engineering", "tests", "data",
                           "example-jones.eng.json")

# Minimal mode-A params (Nd:YVO4 benchmark values, example).
POWER_PARAMS = {"T_oc": 0.10, "L_i": 0.02, "eta_q": 808.0 / 1064.0,
                "eta_abs": 0.7769, "eta_mode": 0.6948,
                "sigma_em": 15.6e-19 * 1e-4, "tau_f": 90e-6, "eta_p": 0.95,
                "lambda_p_m": 808e-9, "profile": "gaussian"}


def main():
    data = load_rez(USER_CAVITY)
    eng = load_eng(EXAMPLE_ENG)
    problems = validate_eng(eng)
    if problems:
        print("side-car problems: %s" % (problems,))
        return 1
    print("=== Jones + dispersion demo: user cavity + EXAMPLE parameters ===")
    print("cavity: %s (SW, lambda = 1064 nm)" % USER_CAVITY)
    print("ALL polarisation/dispersion numbers are examples (see the "
          "module docstring).")
    print()

    rep = jones_report(data, eng)
    print("--- round-trip Jones matrix J_rt (lab basis T, S) ---")
    for row in rep["J_rt"]:
        print("    [%+.4f%+.4fj  %+.4f%+.4fj]"
              % (row[0][0], row[0][1], row[1][0], row[1][1]))
    print("eigenvalues: %s"
          % ["%+.4f%+.4fj" % (v[0], v[1]) for v in rep["eigenvalues"]])
    print("eigen-polarisation: orientation %.2f deg, ellipticity %.3f deg"
          % (rep["orientation_deg"], rep["ellipticity_deg"]))
    print("polarisation loss: %.4f (1 - |lambda_max|^2)"
          % rep["polarization_loss"])
    print("per-element matrices: %s"
          % ", ".join("%s (%s)" % (p["label"], p["kind"])
                      for p in rep["sequence"]))
    print()

    disp = round_trip_dispersion(data, eng)
    print("--- round-trip dispersion ---")
    for p in disp["per_element"]:
        print("    %-4s count=%d  GDD=%+9.1f fs^2  TOD=%+9.1f fs^3  %s"
              % (p["label"], p["count"], p["gdd_fs2"], p["tod_fs3"],
                 p["role"]))
    print("TOTAL: GDD = %.1f fs^2, TOD = %.1f fs^3"
          % (disp["GDD_fs2"], disp["TOD_fs3"]))
    print("    (hand check: GDD = 2*27*245 - 150 - 300 = 12780 fs^2;"
          " TOD = 2*27*310 + 500 + 1200 = 18440 fs^3)")
    sesam = [p for p in disp["per_element"] if p["label"] == "M1"][0]
    print("    SESAM M1: modulation depth %.3f, saturation fluence "
          "%.0f uJ/cm^2 (interface only, no dynamics in this block)"
          % (sesam["modulation_depth"],
             sesam["saturation_fluence_uJ_per_cm2"]))
    for w in disp["warnings"]:
        print("warning: %s" % w)
    print()

    # Jones -> power linkage: a waveplate at TL1, angle sweep.
    print("--- waveplate-angle tuning: polarisation loss -> P_out ---")
    print("    (a QWP inserted at TL1; the polariser is a Brewster")
    print("     plate at d1 with Tp=1, Ts=0 in this example; a HWP")
    print("     would cancel itself on the round trip, so a QWP is")
    print("     used -- its retardance doubles to a HWP on the return")
    print("     pass, and the loss is sin^2(2*theta))")
    print("%8s %10s %10s" % ("theta", "pol_loss", "P_out_A"))
    print("%8s %10s %10s" % ("deg", "", "W @ 5 W pump"))
    for theta in (0.0, 15.0, 22.5, 30.0, 45.0):
        eng2 = {"elements_ext": {
            "TL1": {"jones": {"type": "waveplate",
                              "retardance_rad": math.pi / 2,
                              "fast_axis_deg": theta}},
            "d1": {"jones": {"type": "polarizer", "Tp": 1.0, "Ts": 0.0,
                             "angle_deg": 0.0}}}}
        loss = polarization_loss(round_trip_jones(data, eng2)["J"])
        out = mode_a_output(POWER_PARAMS, 5.0, 200e-6, 180e-6,
                            extra_loss=loss)
        print("%8.1f %10.4f %10.3f" % (theta, loss, out["P_out"]))
    print()
    print("The round-trip loss is sin^2(2*theta): 0 at theta = 0, 0.5")
    print("at 22.5 deg, 1 at 45 deg, where the eigen-polarisation is")
    print("fully extinguished. Caveat: at loss -> 1 no self-consistent")
    print("polarisation exists at all, so the scalar extra_loss model")
    print("is at its limit there (it still returns a small P_out); a")
    print("full vector model would give zero output at 45 deg.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
