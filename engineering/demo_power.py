"""Demo: power solver on the user's real cavity with example parameters.

Usage (from the repository root):
    python3 engineering/demo_power.py [--with-m2]

The .rez file is the user's real cavity (~/workspace/user/files/upload.rez).
Every gain/pump number comes from engineering/tests/data/
example-power.eng.json and is a LITERATURE-TYPICAL EXAMPLE, not the
user's measured data -- the results below are therefore a demonstration
of the solver, not a prediction for the real laser. In particular the
thermal lens is reverse-anchored (the .rez F = 230 mm is assumed to be
the value at P_nom = 5 W pump) and the crystal is assumed to be
Nd:YVO4 with sigma_em = 15.6e-19 cm^2, tau_f = 90 us,
alpha_p = 10/cm, T_oc = 10%, L_i = 2%.
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))

from rezeng import load_rez, load_eng, validate_eng
from rezeng.power import pump_scan, toc_scan, multimode_threshold

REPO = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                     ".."))
USER_CAVITY = os.path.join(os.path.expanduser("~"), "workspace", "user",
                           "files", "upload.rez")
EXAMPLE_ENG = os.path.join(REPO, "engineering", "tests", "data",
                           "example-power.eng.json")

PUMP_POWERS = [0.5, 1.0, 2.0, 3.0, 5.0, 7.0, 10.0]
TOC_VALUES = [0.02, 0.05, 0.08, 0.10, 0.15, 0.20, 0.30]


def main():
    with_m2 = "--with-m2" in sys.argv
    data = load_rez(USER_CAVITY)
    eng = load_eng(EXAMPLE_ENG)
    problems = validate_eng(eng)
    if problems:
        print("side-car problems: %s" % (problems,))
        return 1
    print("=== Power solver demo: user cavity + EXAMPLE parameters ===")
    print("cavity: %s (SW, lambda = 1064 nm, gain element TL1 = Nd:YVO4,"
          " L = 27 mm)" % USER_CAVITY)
    print("ALL pump/crystal numbers are examples (see the module "
          "docstring); the thermal lens is reverse-anchored at "
          "P_nom = 5 W.")
    print()

    scan = pump_scan(data, eng, PUMP_POWERS, with_m2=with_m2)
    for w in scan["warnings"]:
        print("warning: %s" % w)
    print("--- P_out vs P_pump (T_oc = 10%%, mode B) ---")
    print("%6s %8s %8s %8s %8s %8s %8s  %s"
          % ("P_pump", "F_cli", "w_l", "P_th_A", "P_th_B", "P_out_A",
             "P_out_B", "status"))
    print("%6s %8s %8s %8s %8s %8s %8s  %s"
          % ("W", "mm", "um", "W", "W", "W", "W", ""))
    for pt in scan["points"]:
        print("%6.1f %8.1f %8.1f %8.3f %8.3f %8.3f %8.3f  %s"
              % (pt["P_pump_W"], pt["F_cli_mm"],
                 pt.get("w_l_um", float("nan")),
                 pt.get("P_th_A_W", float("nan")),
                 pt.get("P_th_B_W", float("nan")),
                 pt.get("P_out_A", float("nan")),
                 pt.get("P_out_B", float("nan")),
                 pt.get("flag") or pt["status"]))
    print("summary: %s" % json.dumps(scan["summary"], ensure_ascii=False))
    p_mm, mode_mm = (scan["summary"].get("multimode_threshold_W"),
                     scan["summary"].get("multimode_mode"))
    if p_mm is not None:
        print("multimode threshold: %.2f W pump (%s net gain crosses "
              "zero)" % (p_mm, mode_mm))
    else:
        print("multimode threshold: not reached in this scan range")
    if "M2_at_max_pump" in scan["summary"]:
        m2 = scan["summary"]["M2_at_max_pump"]
        print("M^2 at %.1f W pump: M2_x=%.3f M2_y=%.3f (%s)"
              % (scan["summary"]["M2_pump_W"], m2["M2_x"], m2["M2_y"],
                 m2["method"]))
    print()

    toc = toc_scan(data, eng, 5.0, TOC_VALUES)
    print("--- T_opt scan at P_pump = 5 W ---")
    print("%6s %8s %8s  %s" % ("T_oc", "P_th_B", "P_out_B", ""))
    for pt in toc["points"]:
        print("%6.2f %8.3f %8.3f" % (pt["T_oc"], pt["P_th_B_W"],
                                     pt["P_out_B"]))
    print("T_opt = %.2f, P_out_max (mode B) = %.3f W"
          % (toc["summary"]["T_opt"], toc["summary"]["P_out_max_B"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
