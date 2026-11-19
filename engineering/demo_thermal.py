"""Phase 4 block 2 demo: thermal conduction + fracture on the user's cavity.

Runs the TL1 (27 mm Nd:YVO4) rod solver at 2/5/10 W incident pump
with the EXAMPLE parameters in tests/data/example-thermal.eng.json
(all invented -- see the side-car note).  The laser mode radius at
the crystal comes from the CLI beam (mean of the entrance/exit
w_T/w_S at TL1).

Prints a compact table: T_max, end-face bulge, sigma_max (primary /
local peak, alpha_a / alpha_c), safety margins, OPD-fit f_th (dn/dT
only and with bulge), the analytic Gaussian closed-loop value, and
the Phase 2 linear-model focal length at the same pump power.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rezeng import load_rez, load_eng
from rezeng.cli import run_headless_file
from rezeng.qevolve import beam_entry, entrance_entry
from rezeng.thermal import thermal_report

USER_CAVITY = "/home/hatch/workspace/user/files/upload.rez"
ENG = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "tests", "data", "example-thermal.eng.json")


def _w_L_um(data):
    """Laser mode radius [um] at TL1 from the CLI beam."""
    result = run_headless_file(USER_CAVITY)["results"][0]
    w_t_in, w_s_in, _, _ = entrance_entry(data, result, "TL1")
    w_t_ex, w_s_ex, _, _ = beam_entry(result, "TL1")
    return 1e3 * (w_t_in + w_s_in + w_t_ex + w_s_ex) / 4.0


def main():
    data = load_rez(USER_CAVITY)
    eng = load_eng(ENG)
    w_L = _w_L_um(data)
    print("w_L at TL1 from CLI: %.1f um" % (w_L,))
    print("%-6s %-8s %-9s %-10s %-10s %-9s %-9s %-9s %-9s %-9s"
          % ("P/W", "Tmax/C", "bulge/um", "sig_a/MPa", "sig_c/MPa",
             "marg_a", "marg_c", "f_par/mm", "f_fit/mm", "f_bul/mm"))
    for power in (2.0, 5.0, 10.0):
        import copy
        eng_i = copy.deepcopy(eng)
        eng_i["thermal"]["pump"]["P_pump_W"] = power
        rep = thermal_report(data, eng_i, w_L_um=w_L)
        fr = rep["fracture"]
        lin = rep["linear_model"]
        print("%-6.0f %-8.1f %-9.3f %-10.2f %-10.2f %-9.3f %-9.3f "
              "%-9.1f %-9.1f %-9.1f  status=%s linear_F=%.0f mm (%s)"
              % (power, rep["T_max_C"], rep["bulge_max_um"] or 0.0,
                 fr["alpha_a"]["sigma_max_MPa"],
                 fr["alpha_c"]["sigma_max_MPa"],
                 fr["alpha_a"]["margin"], fr["alpha_c"]["margin"],
                 (rep["f_paraxial_mm"] or 0.0),
                 rep["opd_fit_dndT"]["f_th_m"] * 1e3,
                 (rep["opd_fit_with_bulge"] or {}).get("f_th_m", 0.0) * 1e3,
                 fr["status"],
                 lin.get("F_T_mm", float("nan")),
                 lin.get("source", lin.get("error", "?"))))
        print("       paraxial closed-loop dev %+.2f%%, mode-vs-paraxial "
              "%+.1f%%, f_analytic %.1f mm, T rise %.1f K"
              % (100.0 * (rep["closed_loop_dev"] or 0.0),
                 100.0 * (rep["mode_vs_paraxial_dev"] or 0.0),
                 rep["f_analytic_gaussian_mm"],
                 rep["T_max_rise_K"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
