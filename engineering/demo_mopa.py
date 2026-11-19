"""Demo: two-stage MOPA chain on the example fixtures.

Usage (from the repository root):
    python3 engineering/demo_mopa.py

The chain is engineering/tests/data/example-mopa.eng.json, with the
stage .rez files in the same directory:

* seed: 50 uJ, 40 ps, 120 kHz (example oscillator output);
* stage 1 "amp_1": single-pass Nd:YVO4 amplifier (SP .rez, crystal
  plate L = 10 mm, n = 1.82), 2 passes, G0 = 4.5, J_sat = 0.12 J/cm^2;
* stage 2 "regen_1": Nd:YAG regenerative amplifier (SW .rez, crystal
  plate L = 10 mm, n = 1.82), 10 round trips, 5 mJ stored energy,
  J_sat = 0.66 J/cm^2, 4% round-trip loss.

Every number is an INVENTED EXAMPLE, not the user's measured data --
the results below demonstrate the chain solver, not a prediction for
a real system. All energies are per pulse; the chain conserves energy
(total output <= seed + stored energy of every stage).
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))

from rezeng import load_eng, validate_eng
from rezeng.mopa import run_chain

REPO = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                     ".."))
TESTS_DATA = os.path.join(REPO, "engineering", "tests", "data")
EXAMPLE_ENG = os.path.join(TESTS_DATA, "example-mopa.eng.json")
OSC_REZ = os.path.join(os.path.expanduser("~"), "workspace", "user",
                       "files", "upload.rez")


def main():
    eng = load_eng(EXAMPLE_ENG)
    problems = validate_eng(eng)
    if problems:
        print("side-car problems: %s" % (problems,))
        return 1
    for stage in eng["mopa_chain"]["stages"]:
        stage["rez_file"] = os.path.join(TESTS_DATA, stage["rez_file"])
    rep = run_chain(OSC_REZ, eng)

    print("=== MOPA chain demo: EXAMPLE parameters only ===")
    print("seed: %.0f uJ, %.0f ps, %.0f kHz"
          % (rep["seed_J"] * 1e6, rep["seed_tau_s"] * 1e12,
             rep["seed_rep_Hz"] / 1e3))
    print()
    for st in rep["stages"]:
        print("--- stage %s (%s, %s, %d transits, w = %.3f x %.3f mm) ---"
              % (st["stage_id"], st["material"],
                 st["trip_type"], st["transits"],
                 st["w_T_mm"], st["w_S_mm"]))
        print("    stored energy: %.3f mJ -> %.3f mJ (extracted %.3f mJ)"
              % (st["stored_J_initial"] * 1e3,
                 st["stored_J_final"] * 1e3,
                 (st["stored_J_initial"] - st["stored_J_final"]) * 1e3))
        print("    %6s %10s %10s %8s %8s %10s %8s"
              % ("transit", "E_in", "E_out", "gain", "fluence",
                 "B", "LIDT"))
        print("    %6s %10s %10s %8s %8s %10s %8s"
              % ("", "uJ", "uJ", "", "J/cm2", "rad", ""))
        for t in st["transits_detail"]:
            print("    %6d %10.1f %10.1f %8.3f %8.3f %10.4f %8s"
                  % (t["transit"], t["E_in_J"] * 1e6,
                     t["E_out_J"] * 1e6, t["gain"],
                     t["fluence_J_per_cm2"], t["B_rad"],
                     t["lidt_status"]))
        print("    stage gain: %.3f x, E_out = %.3f mJ"
              % (st["gain"], st["E_out_J"] * 1e3))
        print()
    print("TOTAL: E_out = %.3f mJ (%.1f uJ seed -> %.1f x)"
          % (rep["E_out_J"] * 1e3, rep["seed_J"] * 1e6,
             rep["E_out_J"] / rep["seed_J"]))
    print("average power at %.0f kHz: %.2f W"
          % (rep["seed_rep_Hz"] / 1e3, rep["E_out_J"] * rep["seed_rep_Hz"]))
    print("    (the rep rate is the seed's; the regen stored energy is")
    print("     per pulse -- a real regen could not be re-pumped with")
    print("     5 mJ per pulse at 120 kHz, i.e. 600 W of pump. The")
    print("     per-pulse chain is the point here, not the average.)")
    print("B integral total: %.4f rad (warn > 3 rad)" % rep["B_total_rad"])
    print("energy check: output %.3f mJ <= seed + stored %.3f mJ: %s"
          % (rep["E_out_J"] * 1e3,
             (rep["seed_J"] + sum(s["stored_J_initial"]
                                  for s in rep["stages"])) * 1e3,
             "OK" if rep["E_out_J"] <= rep["seed_J"]
             + sum(s["stored_J_initial"] for s in rep["stages"]) else
             "VIOLATED"))
    for w in rep["warnings"]:
        print("warning: %s" % w)
    return 0


if __name__ == "__main__":
    sys.exit(main())
