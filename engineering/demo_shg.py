"""Demo: SHG module on the user's real cavity with example parameters.

Usage (from the repository root):
    python3 engineering/demo_shg.py

The user's real cavity (~/workspace/user/files/upload.rez) has no
nonlinear crystal, so the demo inserts one: an ElemPlate "LBO_1"
(L = 15 mm, n = 1.60) right after the flat end mirror M1, where the
fundamental waist sits, and shortens d1 by 15 mm (total geometric
length unchanged). The modified cavity is written to /tmp only; the
user's file is never touched.

Every gain/pump number comes from engineering/tests/data/
example-shg.eng.json (Nd:YVO4 example parameters, thermal lens
reverse-anchored at P_nom = 5 W) and every SHG number is a
LITERATURE-TYPICAL EXAMPLE (LBO, d_eff = 0.85 pm/V, n = 1.60/1.61)
-- the results below demonstrate the solver, they are not a
prediction for the real laser. Two phase-matching schemes are run:
NCPM (temperature-stabilised oven, delta_T = 0) and CPM (walk-off
7.2 mrad).
"""

import copy
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))

from rezeng import load_rez, load_eng, validate_eng
from rezeng.shg import shg_pump_scan, insert_crystal_element

REPO = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                     ".."))
USER_CAVITY = os.path.join(os.path.expanduser("~"), "workspace", "user",
                           "files", "upload.rez")
EXAMPLE_ENG = os.path.join(REPO, "engineering", "tests", "data",
                           "example-shg.eng.json")
DEMO_CAVITY = "/tmp/demo_shg_cavity.rez"

PUMP_POWERS = [2.0, 3.0, 5.0, 7.0, 10.0]


def _print_table(title, scan):
    print("--- %s ---" % title)
    print("%6s %8s %8s %8s %8s %8s %8s %8s  %s"
          % ("P_pump", "P_circ", "P_out", "P_2w", "eta_1p", "w_xtal",
             "ellipt", "M2_par", "status"))
    for pt in scan["points"]:
        if pt.get("status") != "ok":
            print("%6.1f %8s %8s %8s %8s %8s %8s %8s  %s"
                  % (pt["P_pump_W"], "-", "-", "-", "-", "-", "-", "-",
                     pt.get("status") + " (%s)"
                     % pt.get("flag", pt.get("error", ""))))
            continue
        print("%6.1f %8.3f %8.3f %8.4f %8.4f %8.1f %8.3f %8.3f  %s / green %s"
              % (pt["P_pump_W"], pt["P_circ"], pt["P_out_B"],
                 pt["P_2w"], pt["eta_1pass"], pt["w_crystal_um"],
                 pt["ellipticity"],
                 pt["M2_parallel"], pt["status"], pt["green_risk"]))
    print("summary: %s" % (scan["summary"],))
    print()


def main():
    data = load_rez(USER_CAVITY)
    eng = load_eng(EXAMPLE_ENG)
    problems = validate_eng(eng)
    if problems:
        print("side-car problems: %s" % (problems,))
        return 1
    demo = insert_crystal_element(data, "LBO_1", 15.0, 1.60, "M1",
                                  shorten_label="d1")
    with open(DEMO_CAVITY, "w", encoding="utf-8") as f:
        json.dump(demo, f, ensure_ascii=False, indent=1)
    print("=== SHG demo: user cavity + inserted LBO plate + EXAMPLE "
          "parameters ===")
    print("cavity: %s with ElemPlate LBO_1 (15 mm, n = 1.60) after M1,"
          " d1 shortened by 15 mm; modified file: %s"
          % (USER_CAVITY, DEMO_CAVITY))
    print("ALL pump/crystal/SHG numbers are examples (see the module "
          "docstring); the thermal lens is reverse-anchored at "
          "P_nom = 5 W.")
    print()

    scan_ncpm = shg_pump_scan(demo, eng, PUMP_POWERS)
    for w in scan_ncpm["warnings"]:
        print("warning: %s" % w)
    _print_table("NCPM (temperature-stabilised oven, delta_T = 0)",
                 scan_ncpm)

    eng_cpm = copy.deepcopy(eng)
    eng_cpm["nonlinear_shg"]["phase_matching"] = "CPM"
    eng_cpm["nonlinear_shg"]["walkoff_mrad"] = 7.2
    eng_cpm["nonlinear_shg"].pop("delta_T_C", None)
    eng_cpm["nonlinear_shg"].pop("temp_acceptance_C_cm", None)
    scan_cpm = shg_pump_scan(demo, eng_cpm, PUMP_POWERS)
    for w in scan_cpm["warnings"]:
        print("warning: %s" % w)
    _print_table("CPM (angle-tuned, walk-off 7.2 mrad)", scan_cpm)
    print("NOTE: P_2w is NOT monotonic in P_pump here (10 W gives less "
          "green than 5 W). That is real physics of this example cavity, "
          "not a solver artefact: the thermal lens moves the mode, and "
          "at F = 115 mm (10 W) the waist in the crystal balloons to "
          "~366 um (vs ~119 um at 5 W, verified directly against the "
          "CLI), so xi and K collapse faster than P_circ grows. At "
          "fixed optics P_2w is monotonic in P_pump (test "
          "test_monotone_in_pump).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
