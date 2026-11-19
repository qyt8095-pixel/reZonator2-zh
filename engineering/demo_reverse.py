"""Demo: reverse fitting (measured spots -> thermal-lens D_th) on the
user's real cavity.

Two parts, both with SYNTHETIC measurements (the model generates the
"measured" spots, so the true D_th is known -- the standard way to
validate identifiability):

1. Recovery: true F = 250 mm (D = 4.0 /m, Zone I), 3 points spanning
   the waist (z = 30 / 200 / 800 mm), 3% noise. The fit must recover
   D_th within 5%.
2. Degeneracy trap: true D = 9.5 /m (Zone II), only 2 far-field
   points (z = 1500 / 2500 mm). D = 4.0 /m (Zone I) gives the same
   output waist (w0 = 253 um, z0 = -0.4 mm), so the spots agree to
   <0.4% at every z; the Zone I-bounded fit "succeeds" with the wrong
   answer. This is why the fit is always bounded to the working zone.

The output-mirror substrate in ``tests/data/example-reverse.eng.json``
is an EXAMPLE (nominal 6.35 mm fused silica); the real M4 substrate
data is unknown. Prints a readable summary; full JSON to
``/tmp/demo_reverse.json``.
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))

from rezeng import load_rez, load_eng, validate_eng
from rezeng.reverse import (fit_plane, synthetic_measurements,
                            working_zone_bounds)

USER_REZ = "/home/hatch/workspace/user/files/upload.rez"
HERE = os.path.dirname(os.path.abspath(__file__))
ENG = os.path.join(HERE, "tests", "data", "example-reverse.eng.json")


def _show(report, plane):
    print("  plane %s: D_th fit = %.4f /m (F = %.1f mm), "
          "RMS rel = %.2f%%, converged=%s, nfev=%d"
          % (plane, report["D_th_fit_per_m"], report["F_fit_mm"],
             100.0 * report["rms_rel"] if report["rms_rel"] is not None
             else float("nan"),
             report["converged"], report["nfev"]))
    for p in report["points"]:
        print("    z=%6.0f mm  w_meas=%.4f  w_model=%.4f  rel=%+.2f%%"
              % (p["z_mm"], p["w_meas_mm"], p["w_model_mm"],
                 100.0 * p["rel_err"]))
    if report["geometry"]:
        g = report["geometry"]
        print("    fitted output beam: w0=%.1f um, waist z0=%.1f mm, "
              "z_R=%.1f mm" % (g["w0_mm"] * 1e3, g["z0_mm"], g["z_R_mm"]))
    for w in report["warnings"]:
        print("    warning: %s" % w)


def main():
    data = load_rez(USER_REZ)
    eng = load_eng(ENG)
    problems = validate_eng(eng)
    if problems:
        print("side-car problems: %s" % (problems,), file=sys.stderr)
        return 1
    lo, hi, zone_id = working_zone_bounds(data, lens=("TL1", "F"))
    print("working zone: %s, D in [%.4f, %.4f] /m (F in [%.1f, %.1f] mm)"
          % (zone_id, lo, hi, 1.0 / hi * 1e3, 1.0 / lo * 1e3))

    out = {}
    print("\n--- 1. recovery: true F = 250 mm (D = 4.0 /m, Zone I), "
          "3 points, 3% noise ---")
    rec = {}
    for plane in ("T", "S"):
        points = synthetic_measurements(data, 4.0, [30, 200, 800],
                                        plane, noise_frac=0.03, seed=1,
                                        m2=1.0)
        print("  plane %s synthetic points: %s"
              % (plane, [(p["z_mm"], round(p["w_mm"], 4))
                         for p in points]))
        report = fit_plane(data, points, plane, lens=("TL1", "F"),
                           output_label="M4", eng=eng, m2=1.0,
                           zone_bounds=(lo, hi))
        _show(report, plane)
        err = abs(report["D_th_fit_per_m"] - 4.0) / 4.0 * 100.0
        print("    recovery error: %.2f%% (target < 5%%)" % err)
        rec[plane] = report
    out["recovery"] = rec

    print("\n--- 2. degeneracy trap: true D = 9.5 /m (Zone II), "
          "2 far-field points ---")
    deg = {}
    for plane in ("T",):
        points = synthetic_measurements(data, 9.5, [1500, 2500], plane,
                                        noise_frac=0.0, seed=2, m2=1.0)
        print("  plane %s synthetic points (true D = 9.5 /m): %s"
              % (plane, [(p["z_mm"], round(p["w_mm"], 4))
                         for p in points]))
        report = fit_plane(data, points, plane, lens=("TL1", "F"),
                           output_label="M4", eng=eng, m2=1.0,
                           zone_bounds=(lo, hi))
        _show(report, plane)
        print("    fitted D = %.4f /m is in Zone I, but the truth is "
              "D = 9.5 /m in Zone II -- the fit 'succeeded' (RMS "
              "< 3%%) with the WRONG answer. The zone bounds + weak "
              "prior are what select the working zone."
              % report["D_th_fit_per_m"])
        deg[plane] = report
    out["degeneracy"] = deg

    with open("/tmp/demo_reverse.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("\nfull report: /tmp/demo_reverse.json")
    print("NOTE: all measurements are SYNTHETIC (generated from the "
          "model); the substrate data is an EXAMPLE.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
