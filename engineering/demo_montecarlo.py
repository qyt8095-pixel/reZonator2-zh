"""Demo: Monte Carlo tolerance simulation on the user's real cavity.

Uses ``tests/data/example-mc.eng.json`` -- ALL tolerance bands and
pump/crystal parameters there are EXAMPLES (labelled in the file),
not the user's real tolerances. N=1000, chunk 250, seed 0.

Prints a readable summary to stdout and the full JSON report to
``/tmp/demo_montecarlo.json``.
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))

from rezeng import load_rez, load_eng, validate_eng
from rezeng.montecarlo import run_montecarlo

USER_REZ = "/home/hatch/workspace/user/files/upload.rez"
HERE = os.path.dirname(os.path.abspath(__file__))
ENG = os.path.join(HERE, "tests", "data", "example-mc.eng.json")


def main():
    data = load_rez(USER_REZ)
    eng = load_eng(ENG)
    problems = validate_eng(eng)
    if problems:
        print("side-car problems: %s" % (problems,), file=sys.stderr)
        return 1
    tolerances = eng["tolerances"]
    print("Monte Carlo tolerance simulation (EXAMPLE tolerances, "
          "N=1000, seed=0)")
    print("tolerances:")
    for t in tolerances:
        print("  %(label)s.%(alias)s %(kind)s %(distribution)s "
              "sigma=%(sigma)s half_width=%(half_width)s"
              % {k: t.get(k) for k in ("label", "alias", "kind",
                                       "distribution", "sigma",
                                       "half_width")})
    report = run_montecarlo(data, tolerances, n=1000, chunk_size=250,
                            seed=0, watch=("M1", "M4"), eng=eng,
                            progress=lambda d, t: print(
                                "  ... %d/%d evaluated" % (d, t),
                                file=sys.stderr) or True)
    print("\ncompleted: %d (failed %d, interrupted %s), CLI calls %d"
          % (report["n_completed"], report["n_failed"],
             report["interrupted"], report["n_cli_calls"]))
    print("unstable: %d/%d = %.2f%%, Wilson 95%% CI [%.2f%%, %.2f%%]"
          % (report["n_unstable"],
             report["n_completed"] - report["n_failed"],
             100.0 * report["p_unstable"],
             100.0 * report["wilson_95"][0],
             100.0 * report["wilson_95"][1]))
    for label, entry in report["watch"].items():
        for plane in ("w_T_mm", "w_S_mm"):
            stat = entry[plane]
            print("  %s %s: median %.4f mm, 95%% CI [%.4f, %.4f] mm "
                  "(n=%d)" % (label, plane, stat["median"],
                              stat["ci95"][0], stat["ci95"][1],
                              stat["n"]))
    power = report["power"]
    if power["status"] == "ok":
        print("  P_out (all samples, unstable=0): median %.3f W, 95%% CI "
              "[%.3f, %.3f] W (n=%d)"
              % (power["P_out_W"]["median"], power["P_out_W"]["ci95"][0],
                 power["P_out_W"]["ci95"][1], power["P_out_W"]["n"]))
        print("  P_out (stable only): median %.3f W, 95%% CI [%.3f, "
              "%.3f] W (n=%d)"
              % (power["P_out_stable_W"]["median"],
                 power["P_out_stable_W"]["ci95"][0],
                 power["P_out_stable_W"]["ci95"][1],
                 power["P_out_stable_W"]["n"]))
    else:
        print("  power: nodata (%s)" % power.get("reason"))
    print("\nsensitivity ranking (|PRCC| vs M1 w_T, stable samples):")
    for s in report["sensitivity"]:
        print("  %-10s %-9s spearman_w=%+.3f prcc_w=%+.3f "
              "spearman_P=%+.3f prcc_P=%+.3f spearman_stable=%+.3f"
              % (s["variable"], s["distribution"],
                 s["spearman_w"] if s["spearman_w"] is not None else 0.0,
                 s["prcc_w"] if s["prcc_w"] is not None else 0.0,
                 s["spearman_P_out"]
                 if s["spearman_P_out"] is not None else 0.0,
                 s["prcc_P_out"] if s["prcc_P_out"] is not None else 0.0,
                 s["spearman_stable"]
                 if s["spearman_stable"] is not None else 0.0))
    if report["warnings"]:
        print("\nwarnings:")
        for w in report["warnings"]:
            print("  - %s" % w)
    with open("/tmp/demo_montecarlo.json", "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print("\nfull report: /tmp/demo_montecarlo.json")
    print("NOTE: all tolerance bands and pump/crystal parameters are "
          "EXAMPLES, not the user's real values.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
