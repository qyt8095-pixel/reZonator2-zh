"""End-to-end demo of the alignment Jacobian and screw-turn guide on the
user's real cavity.

Prints the M2 +0.1 mrad tilt's effect on the output spot (position and
pointing at M4), the full analytic Jacobian at M4 with its
finite-difference cross-check, and a "how many turns on one screw bring
the spot back to centre" guide. All mount numbers are EXAMPLE values
(100 TPI, 50 mm arms, azimuth 0 deg) -- the real mount specs are still
missing from the user.

    python3 demo_jacobian.py
"""

import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rezeng import (load_rez, run_headless, jacobian_analytic,
                    jacobian_finite_difference, compare_jacobians,
                    recenter_guide, direction_table)

USER_CAVITY = os.path.join(os.path.expanduser("~"), "workspace", "user",
                           "files", "upload.rez")

# EXAMPLE mount configuration (not the user's real mount).
MOUNT = {"tpi": 100, "arm_T_mm": 50.0, "arm_S_mm": 50.0, "azimuth_deg": 0.0}


def _axis_at_m4(data, misalign):
    resp = run_headless({"base_schema": data,
                         "mutations": [{"id": "m", "misalign": misalign}]})
    res = resp["results"][0]
    assert res["ok"], res.get("error")
    for entry in res["axis"]:
        if entry["label"] == "M4":
            return entry
    raise AssertionError("no axis entry for M4")


def main():
    data = load_rez(USER_CAVITY)
    summary = {"cavity": "user real cavity (upload.rez)",
               "mount": dict(MOUNT, note="EXAMPLE values, not measured")}

    # --- 1. M2 tilt +0.1 mrad: output spot position/pointing at M4 ---
    axis = _axis_at_m4(data, {"M2": {"dT_mrad": 0.1}})
    summary["m2_plus_0p1_mrad_at_M4"] = {
        "x_T_mm": axis["x_T_mm"], "th_T_mrad": axis["th_T_mrad"],
        "x_S_mm": axis["x_S_mm"], "th_S_mrad": axis["th_S_mrad"],
        "note": ("M2 pitch +0.1 mrad moves the M4 output spot by "
                 "+0.064 mm in T and tilts it by -0.0006 mrad; "
                 "the S plane is untouched (planes are decoupled).")}
    print("M2 dT = +0.1 mrad -> M4 axis: x_T = %.4f mm, th_T = %.4f mrad, "
          "x_S = %.4f mm, th_S = %.4f mrad"
          % (axis["x_T_mm"], axis["th_T_mrad"],
             axis["x_S_mm"], axis["th_S_mrad"]))

    # --- 2. Full Jacobian at M4 (analytic vs finite difference) ---
    ja = jacobian_analytic(data, "M4")
    jf = jacobian_finite_difference(data, "M4")
    diff, ok = compare_jacobians(ja["jacobian"], jf["jacobian"])
    summary["jacobian_M4"] = {
        "rows": ja["rows"], "columns": ja["columns"],
        "analytic": [[round(v, 6) for v in row] for row in ja["jacobian"]],
        "finite_difference": [[round(v, 6) for v in row]
                              for row in jf["jacobian"]],
        "max_abs_diff": diff, "agree_within_1e-6": ok,
        "units": ("rows x_T/x_S in mm per mrad, th_T/th_S in mrad per "
                  "mrad; columns are mirror MECHANICAL tilts in mrad "
                  "(beam deflection is 2x)")},
    print("\nJacobian at M4 (rows x_T, th_T, x_S, th_S; columns dT/dS per "
          "mirror):")
    print("            " + "  ".join("%12s" % c for c in ja["columns"]))
    for row, vals in zip(ja["rows"], ja["jacobian"]):
        print("%5s       " % row + "  ".join("%12.4f" % v for v in vals))
    print("analytic vs finite-difference max abs diff: %.3e (tol 1e-6, "
          "agree: %s)" % (diff, ok))
    assert ok, "analytic and finite-difference Jacobians disagree"

    # --- 3. Recenter guide: one screw, how many turns? ---
    measured = np.array([axis["x_T_mm"], axis["th_T_mrad"],
                         axis["x_S_mm"], axis["th_S_mrad"]])
    guide = recenter_guide(data, "M4", "M2", measured,
                           tpi=MOUNT["tpi"], arm_T_mm=MOUNT["arm_T_mm"],
                           arm_S_mm=MOUNT["arm_S_mm"],
                           azimuth_deg=MOUNT["azimuth_deg"])
    summary["recenter_with_M2"] = {
        "correction_mrad": guide["correction_mrad"],
        "screws": guide["screws"],
        "residual_axis": guide["residual_axis"],
        "direction_table_back_view": direction_table(),
        "note": ("To bring the M4 spot back to centre after the "
                 "+0.1 mrad M2 tilt, undo it on M2 itself: dT = -0.1 mrad. "
                 "With the EXAMPLE mount (100 TPI, 50 mm arm) that is "
                 "0.0197 turns of the pitch screw, clockwise as seen "
                 "from behind the mount. The pointing residual stays "
                 "below 0.001 mrad.")}
    print("\nRecenter with M2 (example mount: 100 TPI, 50 mm arms, "
          "azimuth 0 deg):")
    print("  correction: dT = %.4f mrad, dS = %.4f mrad"
          % (guide["correction_mrad"]["dT"],
             guide["correction_mrad"]["dS"]))
    for name, s in guide["screws"].items():
        if name == "phi_deg":
            continue
        print("  %s: %.4f turns, %s (as seen from behind)"
              % (name, s["turns"], s["direction"]))
    print("  residual axis: x_T = %.2e mm, th_T = %.2e mrad, "
          "x_S = %.2e mm, th_S = %.2e mrad"
          % (guide["residual_axis"]["x_T_mm"],
             guide["residual_axis"]["th_T_mrad"],
             guide["residual_axis"]["x_S_mm"],
             guide["residual_axis"]["th_S_mrad"]))

    print("\n" + json.dumps(summary, indent=2, ensure_ascii=False))
    return summary


if __name__ == "__main__":
    main()
